"""Stage 6 -- probability models for (pA, pB, pC), compared out of sample.

Models
  emp      unconditional development base rates
  pois     independent Poisson on home/away goals, team attack/defence
  dc       Dixon-Coles (Poisson with the low-score correlation correction)
  nb       negative binomial on the TOTAL, mean from team form
  multi    multinomial logistic straight onto A/B/C
  mkt      the market itself: de-vigged pC, pB/pA split from a Poisson map
  mkt+     market pC blended with a multinomial correction

Scoring: log loss, Brier, calibration slope/intercept, per-state error, and
economic usefulness.  A complex model is kept only if it beats the simple one
out of sample on BOTH calibration and economics.

Walk-forward: fit on all development matches strictly before season s, predict
season s.  Nothing from the predicted season enters the fit.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson, nbinom
from sklearn.linear_model import LogisticRegression

import lal_data as D
import lal_settlement as S
import s03_features as FEAT

STATES = ["A", "B", "C"]
EPS = 1e-9


# ------------------------------------------------------------------- models

def m_empirical(train, test):
    p = np.array([train["is_A"].mean(), train["is_B"].mean(), train["is_C"].mean()])
    return np.tile(p, (len(test), 1))


def _abc_from_lambda(lh, la, rho=None):
    """P(A/B/C) from two Poisson means, optional Dixon-Coles correction."""
    K = 12
    ph = poisson.pmf(np.arange(K)[None, :], np.asarray(lh)[:, None])
    pa = poisson.pmf(np.arange(K)[None, :], np.asarray(la)[:, None])
    joint = ph[:, :, None] * pa[:, None, :]
    if rho is not None:
        tau = np.ones((K, K))
        tau[0, 0] = 1 - np.outer(lh, la).mean() * rho if False else 1.0
        # element-wise DC tau needs per-match lambdas; do it explicitly
        lhm = np.asarray(lh)[:, None, None]
        lam = np.asarray(la)[:, None, None]
        t = np.ones(joint.shape)
        t[:, 0, 0] = (1 - lhm[:, 0, 0] * lam[:, 0, 0] * rho)
        t[:, 0, 1] = (1 + lhm[:, 0, 0] * rho)
        t[:, 1, 0] = (1 + lam[:, 0, 0] * rho)
        t[:, 1, 1] = (1 - rho)
        joint = joint * np.clip(t, 1e-6, None)
        joint = joint / joint.sum(axis=(1, 2), keepdims=True)
    tot = np.add.outer(np.arange(K), np.arange(K))
    pA = joint[:, tot <= 1].sum(axis=1)
    pB = joint[:, tot == 2].sum(axis=1)
    pC = 1.0 - pA - pB
    return np.column_stack([pA, pB, np.clip(pC, EPS, None)])


def _fit_attack_defence(train):
    """Poisson attack/defence ratings by maximum likelihood."""
    teams = sorted(set(train["home"]) | set(train["away"]))
    ti = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = train["home"].map(ti).values
    ai = train["away"].map(ti).values
    hg, ag = train["hg"].values, train["ag"].values

    def nll(par):
        atk, dfn = par[:n], par[n:2 * n]
        hfa, base = par[2 * n], par[2 * n + 1]
        lh = np.exp(base + hfa + atk[hi] - dfn[ai])
        la = np.exp(base + atk[ai] - dfn[hi])
        return -(poisson.logpmf(hg, lh).sum() + poisson.logpmf(ag, la).sum()) \
            + 0.02 * (np.sum(atk ** 2) + np.sum(dfn ** 2))

    x0 = np.zeros(2 * n + 2)
    x0[2 * n] = 0.25
    x0[2 * n + 1] = np.log(train[["hg", "ag"]].values.mean())
    r = minimize(nll, x0, method="L-BFGS-B")
    return {"teams": ti, "par": r.x, "n": n}


def _lambdas(fit, test, default):
    ti, par, n = fit["teams"], fit["par"], fit["n"]
    atk, dfn, hfa, base = par[:n], par[n:2 * n], par[2 * n], par[2 * n + 1]
    hi = test["home"].map(ti)
    ai = test["away"].map(ti)
    lh = np.where(hi.isna() | ai.isna(), default,
                  np.exp(base + hfa + atk[hi.fillna(0).astype(int)] - dfn[ai.fillna(0).astype(int)]))
    la = np.where(hi.isna() | ai.isna(), default,
                  np.exp(base + atk[ai.fillna(0).astype(int)] - dfn[hi.fillna(0).astype(int)]))
    return lh, la


def m_poisson(train, test):
    fit = _fit_attack_defence(train)
    d = train[["hg", "ag"]].values.mean()
    lh, la = _lambdas(fit, test, d)
    return _abc_from_lambda(lh, la)


def m_dixon_coles(train, test):
    fit = _fit_attack_defence(train)
    d = train[["hg", "ag"]].values.mean()
    lh_tr, la_tr = _lambdas(fit, train, d)

    def nll_rho(r):
        r = float(np.clip(r, -0.2, 0.2))
        p = _abc_from_lambda(lh_tr, la_tr, rho=r)
        y = train["state"].map({"A": 0, "B": 1, "C": 2}).values
        return -np.log(np.clip(p[np.arange(len(y)), y], EPS, None)).sum()

    best, brho = np.inf, 0.0
    for r in np.linspace(-0.15, 0.15, 31):
        v = nll_rho(r)
        if v < best:
            best, brho = v, r
    lh, la = _lambdas(fit, test, d)
    return _abc_from_lambda(lh, la, rho=brho)


def m_negbin(train, test):
    """Negative binomial on the total, mean driven by team form."""
    mu_tr = (train["gf_r10_h"].fillna(train["gf_r10_h"].mean())
             + train["ga_r10_a"].fillna(train["ga_r10_a"].mean())
             + train["gf_r10_a"].fillna(train["gf_r10_a"].mean())
             + train["ga_r10_h"].fillna(train["ga_r10_h"].mean())) / 2.0
    scale = train["G"].mean() / mu_tr.mean()
    mu_tr = mu_tr * scale
    var = train["G"].var(ddof=1)
    mean = train["G"].mean()
    r = max(mean ** 2 / max(var - mean, 1e-3), 1.0)

    mu_te = (test["gf_r10_h"].fillna(train["gf_r10_h"].mean())
             + test["ga_r10_a"].fillna(train["ga_r10_a"].mean())
             + test["gf_r10_a"].fillna(train["gf_r10_a"].mean())
             + test["ga_r10_h"].fillna(train["ga_r10_h"].mean())) / 2.0 * scale
    p = r / (r + mu_te.values)
    pmf = lambda k: nbinom.pmf(k, r, p)
    pA = pmf(0) + pmf(1)
    pB = pmf(2)
    return np.column_stack([pA, pB, np.clip(1 - pA - pB, EPS, None)])


MULTI_FEATURES = ["elo_diff", "elo_sum", "gf_r10_h", "ga_r10_h", "gf_r10_a", "ga_r10_a",
                  "tg_r10_h", "tg_r10_a", "tg_v8_h", "tg_v8_a", "mkt_dominance"]


def m_multinomial(train, test):
    cols = MULTI_FEATURES
    tr = train.dropna(subset=cols)
    if len(tr) < 200:
        return m_empirical(train, test)
    mu, sd = tr[cols].mean(), tr[cols].std().replace(0, 1)
    X = ((tr[cols] - mu) / sd).values
    y = tr["state"].map({"A": 0, "B": 1, "C": 2}).values
    clf = LogisticRegression(max_iter=2000, C=0.5).fit(X, y)
    Xt = ((test[cols].fillna(mu) - mu) / sd).values
    return clf.predict_proba(Xt)


def m_market(train, test):
    """Market pC, with pA/pB split by the Poisson map at the implied lambda."""
    pc = test["mkt_pC"].values
    lam = test["mkt_lambda"].values
    fallback = np.array([train["is_A"].mean(), train["is_B"].mean(), train["is_C"].mean()])
    p0 = poisson.pmf(0, lam) + poisson.pmf(1, lam)
    p2 = poisson.pmf(2, lam)
    rest = np.clip(1 - pc, EPS, None)
    tot = np.clip(p0 + p2, EPS, None)
    pA = rest * p0 / tot
    pB = rest * p2 / tot
    out = np.column_stack([pA, pB, pc])
    bad = ~np.isfinite(out).all(axis=1)
    out[bad] = fallback
    return out


def m_market_plus(train, test):
    """Market baseline corrected by a small logistic model of its own error."""
    base_tr = m_market(train, train)
    base_te = m_market(train, test)
    cols = ["mkt_pC", "elo_sum", "tg_r10_h", "tg_r10_a", "mkt_dominance"]
    tr = train.dropna(subset=cols)
    if len(tr) < 200:
        return base_te
    mu, sd = tr[cols].mean(), tr[cols].std().replace(0, 1)
    X = ((tr[cols] - mu) / sd).values
    y = tr["state"].map({"A": 0, "B": 1, "C": 2}).values
    clf = LogisticRegression(max_iter=2000, C=0.25).fit(X, y)
    Xt = ((test[cols].fillna(mu) - mu) / sd).values
    corr = clf.predict_proba(Xt)
    out = 0.5 * base_te + 0.5 * corr
    return out / out.sum(axis=1, keepdims=True)


MODELS = {"emp": m_empirical, "pois": m_poisson, "dc": m_dixon_coles,
          "nb": m_negbin, "multi": m_multinomial, "mkt": m_market, "mkt+": m_market_plus}


# ------------------------------------------------------------------ scoring

def score(p, y_state):
    y = pd.Series(y_state).map({"A": 0, "B": 1, "C": 2}).values
    p = np.clip(p, EPS, 1 - EPS)
    p = p / p.sum(axis=1, keepdims=True)
    onehot = np.eye(3)[y]
    ll = -np.log(p[np.arange(len(y)), y]).mean()
    brier = ((p - onehot) ** 2).sum(axis=1).mean()
    out = {"log_loss": float(ll), "brier": float(brier), "n": int(len(y))}
    for i, s in enumerate(STATES):
        out[f"mae_p{s}"] = float(abs(p[:, i] - onehot[:, i]).mean())
        out[f"bias_p{s}"] = float(p[:, i].mean() - onehot[:, i].mean())
    # calibration of pC by logistic regression of outcome on logit(pC)
    z = np.log(p[:, 2] / (1 - p[:, 2]))
    if np.std(z) > 1e-6:
        lr = LogisticRegression(max_iter=1000).fit(z.reshape(-1, 1), onehot[:, 2])
        out["cal_slope_pC"] = float(lr.coef_[0][0])
        out["cal_intercept_pC"] = float(lr.intercept_[0])
    return out


def walk_forward(dev):
    seasons = sorted(dev["season"].unique())
    preds = {k: [] for k in MODELS}
    idx = []
    for i, s in enumerate(seasons):
        if i < 2:                      # need at least two seasons of history
            continue
        train = dev[dev["season"].isin(seasons[:i])]
        test = dev[dev["season"] == s]
        idx.append(test.index.values)
        for k, fn in MODELS.items():
            preds[k].append(fn(train, test))
        print(f"  walk-forward: trained on {seasons[:i]} -> predicted {s} (n={len(test)})")
    index = np.concatenate(idx)
    return index, {k: np.vstack(v) for k, v in preds.items()}


def main():
    m = FEAT.build()
    dev = m[m["block"] == "dev"].copy()
    print(f"=== SECTION 9: PROBABILITY MODELS (walk-forward on development) ===\n")
    index, preds = walk_forward(dev)
    truth = dev.loc[index]

    rows = []
    for k, p in preds.items():
        sc = score(p, truth["state"].values)
        sc["model"] = k
        rows.append(sc)
    sc = pd.DataFrame(rows).set_index("model")
    cols = ["n", "log_loss", "brier", "mae_pA", "mae_pB", "mae_pC",
            "bias_pA", "bias_pB", "bias_pC", "cal_slope_pC", "cal_intercept_pC"]
    print("\n--- out-of-sample scores (all predicted development seasons) ---")
    print(sc[cols].round(4).to_string())

    # reliability of pC, per model
    print("\n--- reliability of pC (decile bins, observed frequency) ---")
    rel = {}
    for k, p in preds.items():
        d = pd.DataFrame({"p": p[:, 2], "y": truth["is_C"].values})
        d["b"] = pd.qcut(d["p"], 10, labels=False, duplicates="drop")
        r = d.groupby("b").agg(pred=("p", "mean"), obs=("y", "mean"), n=("y", "size"))
        rel[k] = r.reset_index().to_dict("records")
        gap = float((r["pred"] - r["obs"]).abs().mean())
        print(f"  {k:6s} mean |pred-obs| over deciles = {gap:.4f}")

    # calibration of pB specifically -- the 2.0 vs 2.5 hinge
    print("\n--- calibration of pB (the hinge that decides 2.0 vs 2.5) ---")
    for k, p in preds.items():
        d = pd.DataFrame({"p": p[:, 1], "y": truth["is_B"].values})
        d["b"] = pd.qcut(d["p"], 5, labels=False, duplicates="drop")
        r = d.groupby("b").agg(pred=("p", "mean"), obs=("y", "mean"), n=("y", "size"))
        gap = float((r["pred"] - r["obs"]).abs().mean())
        spread = float(r["obs"].max() - r["obs"].min())
        print(f"  {k:6s} mean |pred-obs| = {gap:.4f}   observed pB spread across "
              f"predicted quintiles = {spread:.4f}")

    # economic usefulness: bet the 2.5 side the model likes, at real prices
    print("\n--- economic usefulness at the primary market-average price (EV>0 filter, dev walk-forward) ---")
    econ = []
    for k, p in preds.items():
        pr = truth.copy()
        pr["pA"], pr["pB"], pr["pC"] = p[:, 0], p[:, 1], p[:, 2]
        ok = pr["O25_PRI"].notna()
        pr = pr[ok]
        pp = p[ok.values]
        ev_o = S.ev("OVER_2.5", pr["O25_PRI"].values, pp[:, 0], pp[:, 1], pp[:, 2])
        ev_u = S.ev("UNDER_2.5", pr["U25_PRI"].values, pp[:, 0], pp[:, 1], pp[:, 2])
        pick = np.where(ev_o > ev_u, "OVER_2.5", "UNDER_2.5")
        best_ev = np.maximum(ev_o, ev_u)
        take = best_ev > 0.0
        price = np.where(pick == "OVER_2.5", pr["O25_PRI"].values, pr["U25_PRI"].values)
        pl = np.array([S.settle(pick[i], price[i], np.array([pr["state"].values[i]]))[0]
                       for i in range(len(pr))])
        econ.append({"model": k, "bets": int(take.sum()),
                     "roi_all": float(pl.mean()),
                     "roi_evfilter": float(pl[take].mean()) if take.sum() else np.nan,
                     "pnl_evfilter": float(pl[take].sum()) if take.sum() else 0.0,
                     "over_share": float((pick[take] == "OVER_2.5").mean()) if take.sum() else np.nan})
    ec = pd.DataFrame(econ).set_index("model")
    print(ec.round(4).to_string())

    D.write_json("totals_model_diagnostics.json", {
        "scores": sc.reset_index().to_dict("records"),
        "reliability_pC": rel,
        "economics": ec.reset_index().to_dict("records"),
        "walk_forward": "train on all earlier development seasons, predict the next",
    })
    print("\n[written] out/totals_model_diagnostics.json")


if __name__ == "__main__":
    main()
