"""Stage 9 -- the one-shot validation run.

Two tracks, kept strictly apart:

  TRACK A (certified)   the frozen gates applied literally.  Zero candidates
                        cleared development, so this track opens nothing and
                        the certified strategy set is EMPTY.

  TRACK B (uncertified) at the user's explicit direction, C2 -- which failed
                        only the scale-dependent absolute drawdown cap of gate
                        G10 while passing its relative twin by a wide margin --
                        is carried into validation.  Every number produced here
                        is labelled NOT CERTIFIED: it was obtained outside the
                        frozen protocol and must not be read as protocol-grade
                        evidence.

No formula, threshold or selector is changed in this file.
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D
import lal_backtest as BT
import lal_candidates as CA
import lal_settlement as S
import s03_features as FEAT
import s08_gates_dev as G

pd.set_option("display.width", 250)

TRACK_A_CLEARED = []                       # empty: nothing passed the frozen gates
TRACK_B_CLEARED = ["C2_STRONG_HOME_UNDER_2.5"]


def main():
    m = FEAT.build()
    # protocol guard: this is the single sanctioned read of the validation block
    val = D.load("val", unlock="VALIDATION_RUN_ONCE")
    val = m[m["match_id"].isin(val["match_id"])].copy()
    print(f"=== STAGE 9: VALIDATION (one shot, n={len(val)}, "
          f"seasons {sorted(val['season'].unique())}) ===\n")

    print("TRACK A -- frozen gates applied literally")
    print(f"  candidates cleared by development: {TRACK_A_CLEARED or 'NONE'}")
    print("  -> validation opens nothing on this track; certified set is EMPTY.\n")

    print("TRACK B -- user-directed exception, NOT CERTIFIED")
    print(f"  candidates: {TRACK_B_CLEARED}")
    print("  reason: C2 failed only G10's absolute 15u drawdown cap (15.66u) while")
    print("          passing the relative cap (4.35% of turnover vs 20% allowed).\n")

    rows, ledgers, detail = [], [], {}
    for name in TRACK_B_CLEARED:
        meta = CA.CANDIDATES[name]
        s, led = G.full_summary(val, meta["fn"], name)
        led["track"] = "B_uncertified"
        ledgers.append(led)
        detail[name] = s
        rows.append({
            "candidate": name, "bets": s["bets"], "avail": s.get("priced_availability"),
            "roi": s.get("roi"), "pnl": s.get("pnl"),
            "roi_hc2": s.get("roi_hc2"), "roi_hc5": s.get("roi_hc5"),
            "roi_max": s.get("roi_market_max"),
            "boot_lo": s.get("roi_boot_lo"), "boot_hi": s.get("roi_boot_hi"),
            "seasons+": s.get("positive_seasons"), "seasons": s.get("seasons_with_bets"),
            "maxDD": s.get("max_drawdown"), "streak": s.get("max_losing_streak"),
            "wins": s.get("wins"), "losses": s.get("losses"),
        })
    r = pd.DataFrame(rows)
    print("--- validation results (UNCERTIFIED TRACK) ---")
    print(r.round(4).to_string(index=False))

    # the structural question, independent of any strategy: is the market's
    # over-prediction of pC still present in the validation seasons?
    print("\n--- structural check: market bias on pC, validation seasons ---")
    v = val.dropna(subset=["mkt_pC"])
    bys = v.groupby("season").apply(lambda g: pd.Series({
        "n": len(g), "pC": g["is_C"].mean(), "mkt_pC": g["mkt_pC"].mean(),
        "bias": g["mkt_pC"].mean() - g["is_C"].mean(),
        "pB": g["is_B"].mean(), "pA": g["is_A"].mean(),
        "roi_blind_U25": S.settle("UNDER_2.5", g["U25_B365"].values, g["state"].values).mean(),
        "roi_blind_O25": S.settle("OVER_2.5", g["O25_B365"].values, g["state"].values).mean(),
    }), include_groups=False)
    print(bys.round(4).to_string())

    verdict = {
        "track_A_certified": {
            "cleared_by_development": TRACK_A_CLEARED,
            "validation_opened": False,
            "certified_strategy_set": [],
            "note": "zero candidates passed the frozen gates on development, so "
                    "under the protocol validation opens nothing and holdout "
                    "stays closed on this track",
        },
        "track_B_uncertified": {
            "candidates": TRACK_B_CLEARED,
            "results": {k: {kk: vv for kk, vv in v.items() if kk != "neighbours"}
                        for k, v in detail.items()},
            "status": "NOT CERTIFIED -- obtained outside the frozen protocol at "
                      "the user's explicit direction",
        },
        "structural_market_bias_validation": bys.reset_index().to_dict("records"),
    }
    D.write_json("s09_validation.json", verdict)
    if ledgers:
        pd.concat(ledgers, ignore_index=True).to_csv(
            D.OUT / "totals_bet_ledger_val.csv", index=False)

    # does C2 hold up well enough to justify spending the holdout on track B?
    passed = []
    for name in TRACK_B_CLEARED:
        s = detail[name]
        ok = (s["bets"] >= 30 and s["pnl"] > 0 and s["roi"] > 0
              and s.get("roi_hc2", -1) > -0.02)
        print(f"\n  {name}: validation {'HOLDS' if ok else 'DOES NOT HOLD'} "
              f"(roi={100*s['roi']:+.2f}%, pnl={s['pnl']:+.2f}u, "
              f"hc2={100*s.get('roi_hc2', float('nan')):+.2f}%)")
        if ok:
            passed.append(name)
    verdict["track_B_cleared_for_holdout"] = passed
    D.write_json("s09_validation.json", verdict)
    print(f"\n  TRACK B cleared for holdout: {passed or 'NONE'}")
    print("\n[written] out/s09_validation.json, out/totals_bet_ledger_val.csv")


if __name__ == "__main__":
    main()
