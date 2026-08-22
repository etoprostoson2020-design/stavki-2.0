"""Stage 5 -- does the chronological stream of La Liga matches carry a signal?

Every candidate effect must survive, in this order:
  1. a raw association test on development
  2. a within-season permutation test (order destroyed, composition kept)
  3. placebo orders (alphabetical, reversed, random-seeded)
  4. block bootstrap over matchday blocks
  5. per-season sign consistency
  6. a simultaneity check (does it hold for same-kickoff batches?)
  7. Benjamini-Hochberg control over the whole family of tests
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

import lal_data as D
import s03_features as FEAT

RNG = np.random.default_rng(20240817)
N_PERM = 1500
N_BOOT = 2000
RES = {}


def bh(pvals: dict, alpha=0.10) -> dict:
    """Benjamini-Hochberg. Returns {name: (p, q, reject)}."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    n = len(items)
    out, prev = {}, 1.0
    for i in range(n - 1, -1, -1):
        name, p = items[i]
        q = min(prev, p * n / (i + 1))
        out[name] = {"p": float(p), "q": float(q), "reject_at_0.10": bool(q <= alpha)}
        prev = q
    return out


# ------------------------------------------------------------------ helpers

def cramers_v(tab: np.ndarray) -> float:
    chi2 = chi2_contingency(tab)[0]
    n = tab.sum()
    return float(np.sqrt(chi2 / (n * (min(tab.shape) - 1))))


def perm_test(d: pd.DataFrame, stat_fn, n=N_PERM, key="season") -> tuple[float, float, float]:
    """Shuffle the OUTCOME sequence inside each season, keeping composition."""
    obs = stat_fn(d)
    null = np.empty(n)
    groups = [g.index.values for _, g in d.groupby(key)]
    states = d["state"].values.copy()
    tmp = d.copy()
    pos = {ix: i for i, ix in enumerate(d.index.values)}
    gidx = [np.array([pos[i] for i in g]) for g in groups]
    for t in range(n):
        s = states.copy()
        for gi in gidx:
            s[gi] = RNG.permutation(s[gi])
        tmp["state"] = s
        tmp["is_A"] = (s == "A").astype(int)
        tmp["is_B"] = (s == "B").astype(int)
        tmp["is_C"] = (s == "C").astype(int)
        null[t] = stat_fn(tmp)
    p = float((np.sum(null >= obs) + 1) / (n + 1))
    return obs, p, float(np.mean(null))


def block_bootstrap_gap(prev_flag: np.ndarray, outcome: np.ndarray,
                        batch: np.ndarray, n=N_BOOT):
    """Block bootstrap of  E[outcome | prev_flag] - E[outcome | not prev_flag].

    Whole simultaneous batches are resampled together so that the dependence
    inside a batch is preserved.  Implemented on raw integer arrays: rebuilding
    a DataFrame thousands of times is prohibitively slow.
    """
    order = np.argsort(batch, kind="mergesort")
    b_sorted = batch[order]
    starts = np.flatnonzero(np.r_[True, b_sorted[1:] != b_sorted[:-1]])
    ends = np.r_[starts[1:], len(b_sorted)]
    groups = [order[s:e] for s, e in zip(starts, ends)]
    k = len(groups)
    vals = np.empty(n)
    for t in range(n):
        pick = RNG.integers(0, k, size=k)
        idx = np.concatenate([groups[i] for i in pick])
        f = prev_flag[idx].astype(bool)
        if f.sum() == 0 or (~f).sum() == 0:
            vals[t] = np.nan
            continue
        vals[t] = outcome[idx][f].mean() - outcome[idx][~f].mean()
    vals = vals[np.isfinite(vals)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))



# ------------------------------------------------------------------ tests

def t_transition_matrix(dev: pd.DataFrame) -> dict:
    """League-level: previous completed batch's last state -> this match's state."""
    d = dev.dropna(subset=["prev_state"])
    tab = pd.crosstab(d["prev_state"], d["state"])
    chi2, p, dof, exp = chi2_contingency(tab)
    trans = (tab.T / tab.sum(axis=1)).T
    base = d["state"].value_counts(normalize=True)
    print("\n--- league transition matrix  P(state | previous league state) ---")
    print(trans.round(4).to_string())
    print(f"  unconditional: {base.round(4).to_dict()}")
    print(f"  chi2={chi2:.3f} dof={dof} p={p:.4f}  Cramer V={cramers_v(tab.values):.4f}")

    def stat(x):
        x = x.dropna(subset=["prev_state"])
        t = pd.crosstab(x["prev_state"], x["state"])
        if t.shape != (3, 3):
            return 0.0
        return float(chi2_contingency(t)[0])

    obs, pperm, nullmean = perm_test(d, stat)
    print(f"  permutation test (order shuffled within season): "
          f"observed chi2={obs:.3f}, null mean={nullmean:.3f}, p={pperm:.4f}")
    return {"chi2": float(chi2), "p_asymptotic": float(p), "cramers_v": cramers_v(tab.values),
            "p_permutation": float(pperm), "transition": trans.round(5).to_dict(),
            "unconditional": base.round(5).to_dict()}


def t_team_transition(dev: pd.DataFrame) -> dict:
    """Does a team's own previous match state predict its next match total?"""
    out = {}
    for side, col in [("home", "prev_state_h"), ("away", "prev_state_a")]:
        d = dev.dropna(subset=[col])
        tab = pd.crosstab(d[col], d["state"])
        chi2, p, dof, _ = chi2_contingency(tab)
        trans = (tab.T / tab.sum(axis=1)).T
        print(f"\n--- {side} team's previous match state -> this match state ---")
        print(trans.round(4).to_string())
        print(f"  chi2={chi2:.3f} p={p:.4f} V={cramers_v(tab.values):.4f}")
        out[side] = {"chi2": float(chi2), "p": float(p), "v": cramers_v(tab.values),
                     "transition": trans.round(5).to_dict()}
    return out


def t_run_length(dev: pd.DataFrame) -> dict:
    """Inertia vs mean reversion: P(C) after k consecutive league C batches."""
    d = dev.dropna(subset=["seqC_1", "seqC_3", "seqC_5"])
    rows = []
    for k, col in [(1, "seqC_1"), (3, "seqC_3"), (5, "seqC_5"), (10, "seqC_10")]:
        dd = dev.dropna(subset=[col])
        lo = dd[dd[col] <= dd[col].quantile(0.25)]
        hi = dd[dd[col] >= dd[col].quantile(0.75)]
        rows.append({"k": k, "n_lo": len(lo), "pC_after_cold": lo["is_C"].mean(),
                     "n_hi": len(hi), "pC_after_hot": hi["is_C"].mean(),
                     "diff": hi["is_C"].mean() - lo["is_C"].mean()})
    r = pd.DataFrame(rows)
    print("\n--- inertia vs mean reversion: P(C) after cold vs hot league runs ---")
    print(r.round(4).to_string(index=False))

    def stat(x):
        xx = x.dropna(subset=["seqC_5"])
        hi = xx[xx["seqC_5"] >= xx["seqC_5"].quantile(0.75)]
        lo = xx[xx["seqC_5"] <= xx["seqC_5"].quantile(0.25)]
        return abs(hi["is_C"].mean() - lo["is_C"].mean())

    # NOTE: seqC_5 is itself built from the sequence, so the permutation must
    # rebuild it.  Instead we permute the OUTCOME column and recompute the
    # rolling mean directly from the permuted series.
    d5 = dev.dropna(subset=["seqC_5"]).copy()
    obs = stat(d5)
    null = np.empty(1000)
    for t in range(1000):
        parts = []
        for _, g in dev.groupby("season"):
            g = g.copy()
            g["is_C"] = RNG.permutation(g["is_C"].values)
            bag = g.groupby("batch_id")["is_C"].mean()
            g["seqC_5"] = g["batch_id"].map(bag.shift(1).rolling(5, min_periods=5).mean())
            parts.append(g)
        null[t] = stat(pd.concat(parts).dropna(subset=["seqC_5"]))
    pperm = float((np.sum(null >= obs) + 1) / 1001)
    print(f"  hot-minus-cold gap: observed={obs:.4f}  permutation null mean={null.mean():.4f}"
          f"  p={pperm:.4f}")
    return {"table": r.to_dict("records"), "gap_obs": float(obs),
            "gap_null_mean": float(null.mean()), "p_permutation": pperm}


def t_two_goal_clusters(dev: pd.DataFrame) -> dict:
    """Do exactly-two-goal matches cluster in time?"""
    d = dev.dropna(subset=["prev_state"])
    pB_after_B = d[d["prev_state"] == "B"]["is_B"].mean()
    pB_other = d[d["prev_state"] != "B"]["is_B"].mean()
    obs = pB_after_B - pB_other

    def stat(x):
        xx = x.dropna(subset=["prev_state"])
        return xx[xx["prev_state"] == "B"]["is_B"].mean() - xx[xx["prev_state"] != "B"]["is_B"].mean()

    _, pperm, nullmean = perm_test(d, lambda x: abs(stat(x)), n=1000)
    lo, hi = block_bootstrap_gap(
        (d["prev_state"] == "B").values.astype(int),
        d["is_B"].values.astype(int),
        d["batch_id"].values, n=2000)
    print("\n--- clustering of exactly-two-goal matches ---")
    print(f"  P(B | prev league state B) = {pB_after_B:.4f}   otherwise {pB_other:.4f}"
          f"   gap = {obs:+.4f}")
    print(f"  permutation p (|gap|) = {pperm:.4f}   block-bootstrap 95% CI = [{lo:+.4f}, {hi:+.4f}]")
    return {"pB_after_B": float(pB_after_B), "pB_other": float(pB_other), "gap": float(obs),
            "p_permutation": float(pperm), "boot_ci": [lo, hi]}


def t_market_error_sequence(dev: pd.DataFrame) -> dict:
    """Does the league's recent market error predict the next match's error?"""
    d = dev.dropna(subset=["seqR_5", "mkt_pC"])
    d = d.copy()
    d["err"] = d["is_C"] - d["mkt_pC"]
    r = float(np.corrcoef(d["seqR_5"], d["err"])[0, 1])
    q = d.groupby(pd.qcut(d["seqR_5"], 5, labels=False)).agg(
        n=("err", "size"), seqR=("seqR_5", "mean"), err=("err", "mean"),
        pC=("is_C", "mean"), mkt=("mkt_pC", "mean")).round(4)
    print("\n--- does the league's recent market error persist? ---")
    print(q.to_string())
    print(f"  corr(seqR_5, next error) = {r:+.4f}")

    null = np.empty(1000)
    for t in range(1000):
        parts = []
        for _, g in d.groupby("season"):
            g = g.copy()
            g["err"] = RNG.permutation(g["err"].values)
            bag = g.groupby("batch_id")["err"].mean()
            g["seqR_5"] = g["batch_id"].map(bag.shift(1).rolling(5, min_periods=5).mean())
            parts.append(g)
        p2 = pd.concat(parts).dropna(subset=["seqR_5"])
        null[t] = abs(np.corrcoef(p2["seqR_5"], p2["err"])[0, 1])
    pperm = float((np.sum(null >= abs(r)) + 1) / 1001)
    print(f"  permutation p = {pperm:.4f} (null mean |corr| = {null.mean():.4f})")
    return {"corr": r, "p_permutation": pperm, "quintiles": q.reset_index().to_dict("records")}


def t_partial_round(dev: pd.DataFrame) -> dict:
    """Does the goal yield of the already-played part of a matchday predict the rest?"""
    d = dev.copy()
    d["md"] = d["season"] + "|" + d["date"].dt.strftime("%Y-%m")
    rows = []
    for (s, dt), g in d.groupby(["season", d["date"]]):
        g = g.sort_values(["kickoff_dt", "home"])
        if len(g) < 3:
            continue
        # only meaningful where kickoff times actually differ
        if g["batch_id"].nunique() < 2:
            continue
        bids = list(dict.fromkeys(g["batch_id"]))
        for i in range(1, len(bids)):
            past = g[g["batch_id"].isin(bids[:i])]
            now = g[g["batch_id"] == bids[i]]
            rows.append({"prior_mean_G": past["G"].mean(), "prior_n": len(past),
                         "now_G": now["G"].mean(), "now_pC": now["is_C"].mean(),
                         "now_n": len(now), "season": s})
    r = pd.DataFrame(rows)
    if len(r) < 50:
        print("\n--- partial-matchday carry-over: too few multi-batch days ---")
        return {"n": len(r), "note": "insufficient"}
    c = float(np.corrcoef(r["prior_mean_G"], r["now_G"])[0, 1])
    print(f"\n--- partial-matchday carry-over  (n={len(r)} within-day transitions) ---")
    print(f"  corr(mean goals in earlier batches, mean goals in next batch) = {c:+.4f}")
    null = np.array([float(np.corrcoef(r["prior_mean_G"], RNG.permutation(r["now_G"]))[0, 1])
                     for _ in range(2000)])
    pperm = float((np.sum(np.abs(null) >= abs(c)) + 1) / 2001)
    print(f"  permutation p = {pperm:.4f}")
    return {"n": int(len(r)), "corr": c, "p_permutation": pperm}


def t_placebo_orders(dev: pd.DataFrame) -> dict:
    """Same statistic under orders that carry no information."""
    out = {}
    base = dev.dropna(subset=["prev_state"])
    tab = pd.crosstab(base["prev_state"], base["state"])
    real = float(chi2_contingency(tab)[0])
    for name, keyfn in [
        ("alphabetical_by_home", lambda x: x.sort_values(["season", "home", "date"])),
        ("reversed_chronology", lambda x: x.sort_values(["season", "kickoff_dt", "home"],
                                                        ascending=[True, False, False])),
        ("random_seeded", lambda x: x.sample(frac=1.0, random_state=99)),
    ]:
        d = keyfn(dev.copy())
        parts = []
        for _, g in d.groupby("season", sort=False):
            g = g.copy()
            g["ps"] = g["state"].shift(1)
            parts.append(g)
        dd = pd.concat(parts).dropna(subset=["ps"])
        t = pd.crosstab(dd["ps"], dd["state"])
        out[name] = float(chi2_contingency(t)[0]) if t.shape == (3, 3) else None
    print("\n--- placebo orders (chi2 of the transition table) ---")
    print(f"  true chronology            {real:.3f}")
    for k, v in out.items():
        print(f"  {k:26s} {v:.3f}")
    out["true_chronology"] = real
    return out


def t_by_season(dev: pd.DataFrame) -> dict:
    """Sign consistency of the leading sequential contrast, season by season."""
    rows = []
    for s, g in dev.groupby("season"):
        gg = g.dropna(subset=["prev_state"])
        after_c = gg[gg["prev_state"] == "C"]["is_C"].mean()
        after_a = gg[gg["prev_state"] == "A"]["is_C"].mean()
        rows.append({"season": s, "n": len(gg), "pC_after_C": after_c,
                     "pC_after_A": after_a, "diff": after_c - after_a})
    r = pd.DataFrame(rows)
    print("\n--- season-by-season: P(C | prev C) - P(C | prev A) ---")
    print(r.round(4).to_string(index=False))
    same = int(np.sign(r["diff"]).value_counts().max())
    print(f"  consistent sign in {same}/{len(r)} seasons")
    return {"rows": r.to_dict("records"), "max_same_sign": same, "n_seasons": int(len(r))}


def t_simultaneity(dev: pd.DataFrame) -> dict:
    """Within a simultaneous batch there is no order -- any 'effect' must vanish."""
    d = dev[dev["has_kickoff"]].copy()
    big = d.groupby("batch_id").filter(lambda g: len(g) >= 2)
    rows = []
    for _, g in big.groupby("batch_id"):
        g = g.sort_values("home")
        if len(g) < 2:
            continue
        rows.append({"first": g["state"].iloc[0], "second": g["state"].iloc[1]})
    r = pd.DataFrame(rows)
    if len(r) < 60:
        return {"n": len(r), "note": "insufficient"}
    tab = pd.crosstab(r["first"], r["second"])
    chi2, p, dof, _ = chi2_contingency(tab)
    print(f"\n--- simultaneity placebo: fake 'order' inside same-kickoff batches (n={len(r)}) ---")
    print(f"  chi2={chi2:.3f} dof={dof} p={p:.4f}  (must be non-significant)")
    return {"n": int(len(r)), "chi2": float(chi2), "p": float(p)}


def main():
    m = FEAT.build()
    dev = m[m["block"] == "dev"].copy()
    print(f"=== SECTION 8: SEQUENTIAL ANALYSIS (development, n={len(dev)}) ===")
    print(f"  matches with known kickoff time: {dev['has_kickoff'].sum()} / {len(dev)}")
    print(f"  distinct simultaneous batches:   {dev['batch_id'].nunique()}")
    print("  NOTE 2016/17-2018/19 have no kickoff time: a whole calendar day is")
    print("  treated as one simultaneous batch there, so no intra-day order is invented.")

    RES["transition_league"] = t_transition_matrix(dev)
    RES["transition_team"] = t_team_transition(dev)
    RES["run_length"] = t_run_length(dev)
    RES["two_goal_clusters"] = t_two_goal_clusters(dev)
    RES["market_error_sequence"] = t_market_error_sequence(dev)
    RES["partial_round"] = t_partial_round(dev)
    RES["placebo_orders"] = t_placebo_orders(dev)
    RES["by_season"] = t_by_season(dev)
    RES["simultaneity_placebo"] = t_simultaneity(dev)

    # ---- multiple-testing control over the whole family --------------------
    fam = {
        "league_transition": RES["transition_league"]["p_permutation"],
        "team_transition_home": RES["transition_team"]["home"]["p"],
        "team_transition_away": RES["transition_team"]["away"]["p"],
        "run_length_gap": RES["run_length"]["p_permutation"],
        "two_goal_clusters": RES["two_goal_clusters"]["p_permutation"],
        "market_error_persistence": RES["market_error_sequence"]["p_permutation"],
    }
    if "p_permutation" in RES["partial_round"]:
        fam["partial_round_carryover"] = RES["partial_round"]["p_permutation"]
    RES["family"] = fam
    RES["benjamini_hochberg"] = bh(fam, alpha=0.10)

    print("\n=== MULTIPLE TESTING CONTROL (Benjamini-Hochberg, alpha=0.10) ===")
    for k, v in sorted(RES["benjamini_hochberg"].items(), key=lambda kv: kv[1]["p"]):
        print(f"  {k:28s} p={v['p']:.4f}  q={v['q']:.4f}  "
              f"{'SURVIVES' if v['reject_at_0.10'] else 'rejected'}")

    surviving = [k for k, v in RES["benjamini_hochberg"].items() if v["reject_at_0.10"]]
    RES["surviving_effects"] = surviving
    print(f"\n  SEQUENTIAL EFFECTS SURVIVING FDR CONTROL: "
          f"{surviving if surviving else 'NONE'}")

    D.write_json("totals_sequential_tests.json", RES)
    print("\n[written] out/totals_sequential_tests.json")


if __name__ == "__main__":
    main()
