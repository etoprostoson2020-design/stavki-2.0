"""Stage 7 -- the break-even map between the 2.0 and 2.5 lines.

This is the answer to "it depends on the odds".  For any (pA,pB,pC) and any
pair of prices, exactly one of the five actions is optimal, and the boundaries
are closed-form.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D
import lal_settlement as S
import s03_features as FEAT

pd.set_option("display.width", 250)


def indifference_table(pA, pB, pC, o25_grid):
    """For each Over-2.5 price, the Over-2.0 price that matches its EV."""
    rows = []
    for o in o25_grid:
        ov, _ = S.breakeven_2p0_vs_2p5(pA, pB, pC, o)
        rows.append({"o25_over": o, "ev_over25": float(S.ev("OVER_2.5", o, pA, pB, pC)),
                     "o20_over_indifferent": float(ov),
                     "ratio": float(ov) / o})
    return pd.DataFrame(rows)


def under_indifference_table(pA, pB, pC, u25_grid):
    rows = []
    for u in u25_grid:
        _, un = S.breakeven_2p0_vs_2p5(pA, pB, pC, u)
        rows.append({"u25_under": u, "ev_under25": float(S.ev("UNDER_2.5", u, pA, pB, pC)),
                     "u20_under_indifferent": float(un),
                     "ratio": float(un) / u})
    return pd.DataFrame(rows)


def main():
    m = FEAT.build()
    dev = m[m["block"] == "dev"]
    pA, pB, pC = dev["is_A"].mean(), dev["is_B"].mean(), dev["is_C"].mean()

    print("=== SECTION 10: BREAK-EVEN MAP ===\n")
    print(f"  league base rates (development): pA={pA:.4f} pB={pB:.4f} pC={pC:.4f}\n")

    f = S.fair_odds(pA, pB, pC)
    print("  --- minimum acceptable price (EV=0) and the price for a 2% edge ---")
    tab = []
    for mk in S.MARKETS:
        w, p, l = S.wpl(mk, pA, pB, pC)
        tab.append({"market": mk, "fair": float(f[mk]),
                    "min_for_EV0": float(f[mk]),
                    "min_for_2pct": float(S.min_price(mk, pA, pB, pC, 0.02)),
                    "min_for_5pct": float(S.min_price(mk, pA, pB, pC, 0.05)),
                    "win": float(w), "push": float(p), "loss": float(l)})
    t = pd.DataFrame(tab)
    print(t.round(4).to_string(index=False))

    print("\n  --- OVER: what 2.0 price matches a given 2.5 price? ---")
    it = indifference_table(pA, pB, pC, np.arange(1.70, 2.71, 0.10))
    print(it.round(4).to_string(index=False))
    print(f"\n  The ratio is constant at 1 - pB/(pC*o25) ... in absolute terms the")
    print(f"  2.0 over price must be exactly pB/pC = {pB/pC:.4f} lower than the 2.5 price.")

    print("\n  --- UNDER: what 2.0 price matches a given 2.5 price? ---")
    ut = under_indifference_table(pA, pB, pC, np.arange(1.60, 2.41, 0.10))
    print(ut.round(4).to_string(index=False))
    print(f"\n  The 2.0 under price must be ((pA+pB)*u25 - pB)/pA -- a MULTIPLICATIVE")
    print(f"  stretch of about {(pA+pB)/pA:.3f}x minus a constant, because Under 2.0")
    print("  surrenders every two-goal win that Under 2.5 collects.")

    # ---- the decision surface across market-total segments -----------------
    print("\n=== DECISION SURFACE BY MARKET TOTAL (development deciles) ===\n")
    dm = dev.dropna(subset=["mkt_pC"]).copy()
    dm["q"] = pd.qcut(dm["mkt_pC"], 5, labels=False)
    rows = []
    for q, g in dm.groupby("q"):
        a, b, c = g["is_A"].mean(), g["is_B"].mean(), g["is_C"].mean()
        ff = S.fair_odds(a, b, c)
        o25 = g["O25_PRI"].mean()
        u25 = g["U25_PRI"].mean()
        ov_ind, _ = S.breakeven_2p0_vs_2p5(a, b, c, o25)
        _, un_ind = S.breakeven_2p0_vs_2p5(a, b, c, u25)
        rows.append({
            "decile": int(q), "n": len(g), "mkt_pC": g["mkt_pC"].mean(),
            "pA": a, "pB": b, "pC": c,
            "fair_O20": float(ff["OVER_2.0"]), "fair_O25": float(ff["OVER_2.5"]),
            "fair_U20": float(ff["UNDER_2.0"]), "fair_U25": float(ff["UNDER_2.5"]),
            "offered_O25": o25, "offered_U25": u25,
            "EV_O25": float(S.ev("OVER_2.5", o25, a, b, c)),
            "EV_U25": float(S.ev("UNDER_2.5", u25, a, b, c)),
            "O20_needed_to_match_O25": float(ov_ind),
            "U20_needed_to_match_U25": float(un_ind),
        })
    ds = pd.DataFrame(rows)
    print(ds.round(4).to_string(index=False))

    # ---- price-haircut sensitivity ----------------------------------------
    print("\n=== HOW MUCH PRICE DECAY EACH MARKET CAN ABSORB ===\n")
    print("  (percentage the offered price may fall before EV turns negative,")
    print("   starting from a price that gives a 3% edge)")
    for mk in S.MARKETS:
        o3 = float(S.min_price(mk, pA, pB, pC, 0.03))
        o0 = float(f[mk])
        print(f"   {mk:10s} 3%-edge price {o3:.3f} -> fair {o0:.3f}   "
              f"cushion {100*(o3-o0)/o3:.2f}% of price")

    D.write_json("s07_breakeven.json", {
        "base_rates": {"pA": float(pA), "pB": float(pB), "pC": float(pC)},
        "min_prices": t.to_dict("records"),
        "over_indifference": it.to_dict("records"),
        "under_indifference": ut.to_dict("records"),
        "decision_surface_by_market_total": ds.to_dict("records"),
        "over_absolute_gap_pB_over_pC": float(pB / pC),
        "under_multiplicative_stretch": float((pA + pB) / pA),
    })
    print("\n[written] out/s07_breakeven.json")


if __name__ == "__main__":
    main()
