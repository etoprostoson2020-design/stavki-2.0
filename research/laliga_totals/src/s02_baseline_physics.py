"""Stage 2 -- undivided-league baseline (7.1) and the physics of goals (5).

Development block only.  Everything here answers the question "what does the
raw event stream look like, and what does the market charge for it".
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D
import lal_settlement as S

OUT = {}


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def main():
    m = D.load("dev")
    n = len(m)
    pA, pB, pC = m["is_A"].mean(), m["is_B"].mean(), m["is_C"].mean()

    print(f"=== 7.1  UNDIVIDED LEAGUE BASELINE  (development, n={n}) ===\n")
    print(f"  pA  P(G<=1) = {pA:.4f}   CI {wilson(m['is_A'].sum(), n)[0]:.4f}-{wilson(m['is_A'].sum(), n)[1]:.4f}")
    print(f"  pB  P(G==2) = {pB:.4f}   CI {wilson(m['is_B'].sum(), n)[0]:.4f}-{wilson(m['is_B'].sum(), n)[1]:.4f}")
    print(f"  pC  P(G>=3) = {pC:.4f}   CI {wilson(m['is_C'].sum(), n)[0]:.4f}-{wilson(m['is_C'].sum(), n)[1]:.4f}")
    print(f"  mean goals  = {m['G'].mean():.4f}   var = {m['G'].var(ddof=1):.4f}  "
          f"(var/mean = {m['G'].var(ddof=1)/m['G'].mean():.4f})")
    print(f"  skew = {m['G'].skew():.4f}   kurtosis(excess) = {m['G'].kurt():.4f}")

    f = S.fair_odds(pA, pB, pC)
    print("\n  --- fair prices implied by the unconditional base rates ---")
    for k in S.MARKETS:
        w, p, l = S.wpl(k, pA, pB, pC)
        print(f"   {k:10s} fair={float(f[k]):6.3f}   win={float(w):.4f} push={float(p):.4f} loss={float(l):.4f}")

    OUT["league_baseline"] = {
        "n": int(n), "pA": float(pA), "pB": float(pB), "pC": float(pC),
        "mean_goals": float(m["G"].mean()), "var_goals": float(m["G"].var(ddof=1)),
        "skew": float(m["G"].skew()), "excess_kurtosis": float(m["G"].kurt()),
        "fair": {k: float(f[k]) for k in S.MARKETS},
    }

    # ---- goal count distribution vs Poisson --------------------------------
    print("\n=== 5.  PHYSICS: total-goal distribution ===\n")
    lam = m["G"].mean()
    from scipy.stats import poisson, nbinom
    vc = m["G"].value_counts().sort_index()
    rows = []
    for g in range(0, 9):
        obs = int(vc.get(g, 0))
        exp_p = poisson.pmf(g, lam) * n
        rows.append({"goals": g, "obs": obs, "obs_pct": 100 * obs / n,
                     "poisson_exp": exp_p, "poisson_pct": 100 * poisson.pmf(g, lam)})
    tail = int((m["G"] >= 9).sum())
    dist = pd.DataFrame(rows)
    print(dist.round(2).to_string(index=False), f"\n  9+: {tail}")
    OUT["goal_distribution"] = dist.to_dict("records") + [{"goals": "9+", "obs": tail}]

    # dispersion test: is the count over-dispersed relative to Poisson?
    var, mean = m["G"].var(ddof=1), m["G"].mean()
    print(f"\n  dispersion index var/mean = {var/mean:.4f}  "
          f"({'over' if var > mean else 'under'}-dispersed vs Poisson)")
    # zero inflation check
    print(f"  P(G=0) observed = {(m['G']==0).mean():.4f}  Poisson = {poisson.pmf(0, lam):.4f}")

    # ---- per-season stability ---------------------------------------------
    print("\n--- season stability of the three states ---")
    ss = m.groupby("season").agg(n=("G", "size"), mean_G=("G", "mean"),
                                 pA=("is_A", "mean"), pB=("is_B", "mean"),
                                 pC=("is_C", "mean")).round(4)
    ss["fair_O25"] = (1 / ss["pC"]).round(3)
    ss["fair_U25"] = (1 / (ss["pA"] + ss["pB"])).round(3)
    ss["fair_O20"] = ((1 - ss["pB"]) / ss["pC"]).round(3)
    ss["fair_U20"] = ((1 - ss["pB"]) / ss["pA"]).round(3)
    print(ss.to_string())
    OUT["season_stability"] = ss.reset_index().to_dict("records")

    # chi-square homogeneity of A/B/C across dev seasons
    from scipy.stats import chi2_contingency
    tab = pd.crosstab(m["season"], m["state"])
    chi2, pv, dof, _ = chi2_contingency(tab)
    print(f"\n  chi2 homogeneity of A/B/C across dev seasons: chi2={chi2:.2f} "
          f"dof={dof} p={pv:.4f}")
    OUT["season_homogeneity"] = {"chi2": float(chi2), "dof": int(dof), "p": float(pv)}

    # ---- home / away, halves ----------------------------------------------
    print("\n--- where the goals come from ---")
    print(f"  home goals/match {m['hg'].mean():.4f}   away goals/match {m['ag'].mean():.4f}"
          f"   home share {m['hg'].sum()/m['G'].sum():.4f}")
    print(f"  1st half {m['G_ht'].mean():.4f}/match   2nd half {m['G_2h'].mean():.4f}/match"
          f"   2H share {m['G_2h'].sum()/m['G'].sum():.4f}")
    print(f"  P(0-0 at HT) = {(m['G_ht']==0).mean():.4f}   P(0-0 FT) = {(m['G']==0).mean():.4f}")
    OUT["home_away_halves"] = {
        "home_gpm": float(m["hg"].mean()), "away_gpm": float(m["ag"].mean()),
        "h1_gpm": float(m["G_ht"].mean()), "h2_gpm": float(m["G_2h"].mean()),
        "h2_share": float(m["G_2h"].sum() / m["G"].sum()),
    }

    # ---- conditional on half-time state (the "regime switch") --------------
    print("\n--- P(final state | half-time score) : does a closed match open up? ---")
    ht_rows = []
    m2 = m.copy()
    m2["ht_key"] = np.where(
        m2["G_ht"] == 0, "0-0",
        np.where(m2["G_ht"] == 1, "1 goal HT",
                 np.where(m2["G_ht"] == 2, "2 goals HT", "3+ goals HT")))
    for k, d in m2.groupby("ht_key"):
        ht_rows.append({"ht": k, "n": len(d), "share": len(d) / n,
                        "pA": d["is_A"].mean(), "pB": d["is_B"].mean(),
                        "pC": d["is_C"].mean(), "mean_2h_goals": d["G_2h"].mean()})
    ht = pd.DataFrame(ht_rows).sort_values("ht")
    print(ht.round(4).to_string(index=False))
    OUT["by_halftime_state"] = ht.to_dict("records")

    # ---- the pB hinge ------------------------------------------------------
    print("\n=== THE pB HINGE: what the 2.0 push is worth ===\n")
    print(f"  P(exactly 2 goals) = {pB:.4f}")
    print("  Insurance value only matters relative to price. At the fair price the")
    print("  push is worth exactly zero -- it is fully paid for by the shorter odds:")
    print(f"    fair O2.5 = {float(f['OVER_2.5']):.4f}   fair O2.0 = {float(f['OVER_2.0']):.4f}"
          f"   ratio = {float(f['OVER_2.0']/f['OVER_2.5']):.4f}  (= 1 - pB = {1-pB:.4f})")
    print(f"    fair U2.5 = {float(f['UNDER_2.5']):.4f}   fair U2.0 = {float(f['UNDER_2.0']):.4f}"
          f"   ratio = {float(f['UNDER_2.0']/f['UNDER_2.5']):.4f}")
    print(f"  So a fair book must cut the OVER price by {100*pB:.2f}% to grant the push,")
    print(f"  and must LENGTHEN the UNDER price by {100*(float(f['UNDER_2.0']/f['UNDER_2.5'])-1):.2f}%")
    print("  because Under 2.0 gives up the two-goal wins that Under 2.5 collects.")
    OUT["pB_hinge"] = {
        "pB": float(pB),
        "over_price_ratio_2p0_over_2p5": float(f["OVER_2.0"] / f["OVER_2.5"]),
        "under_price_ratio_2p0_over_2p5": float(f["UNDER_2.0"] / f["UNDER_2.5"]),
    }

    # ---- what the real market charged --------------------------------------
    print("\n=== THE REAL PRICE OF THE 2.5 LINE (Bet365 pre-match, dev) ===\n")
    pr = m[m["O25_B365"].notna()].copy()
    q_o, q_u = S.devig_two_way(pr["O25_B365"].values, pr["U25_B365"].values, "proportional")
    pr["mkt_pC"] = q_o
    pr["ovr"] = 1 / pr["O25_B365"] + 1 / pr["U25_B365"]
    print(f"  priced matches {len(pr)} / {n}  ({100*len(pr)/n:.1f}%)")
    print(f"  mean overround {pr['ovr'].mean():.4f}  -> mean vig per side "
          f"{100*(pr['ovr'].mean()-1)/2:.2f}%")
    print(f"  mean market pC (de-vigged) = {pr['mkt_pC'].mean():.4f}  vs realised pC = {pC:.4f}")

    # naive flat-bet every match on each 2.5 side
    for mk, col in [("OVER_2.5", "O25_B365"), ("UNDER_2.5", "U25_B365")]:
        pl = S.settle(mk, pr[col].values, pr["state"].values)
        print(f"  blind {mk:10s} n={len(pl)}  PnL={pl.sum():+8.2f}u  ROI={100*pl.mean():+6.2f}%")
    for mk, col in [("OVER_2.5", "O25_MAX"), ("UNDER_2.5", "U25_MAX")]:
        sub = pr[pr[col].notna()]
        pl = S.settle(mk, sub[col].values, sub["state"].values)
        print(f"  blind {mk:10s} n={len(pl)}  PnL={pl.sum():+8.2f}u  ROI={100*pl.mean():+6.2f}%  [MARKET MAX]")

    OUT["market_price_dev"] = {
        "priced": int(len(pr)), "mean_overround": float(pr["ovr"].mean()),
        "mean_market_pC": float(pr["mkt_pC"].mean()), "realised_pC": float(pC),
        "blind_roi": {
            "OVER_2.5_B365": float(S.settle("OVER_2.5", pr["O25_B365"].values, pr["state"].values).mean()),
            "UNDER_2.5_B365": float(S.settle("UNDER_2.5", pr["U25_B365"].values, pr["state"].values).mean()),
            "OVER_2.5_MAX": float(S.settle("OVER_2.5", pr["O25_MAX"].values, pr["state"].values).mean()),
            "UNDER_2.5_MAX": float(S.settle("UNDER_2.5", pr["U25_MAX"].values, pr["state"].values).mean()),
        },
    }

    D.write_json("s02_baseline_physics.json", OUT)
    print("\n[written] out/s02_baseline_physics.json")


if __name__ == "__main__":
    main()
