"""Stage 1 -- file registry and data audit.

Runs over ALL seasons deliberately, but reports only structural facts
(row counts, field coverage, price coverage, margins, schema drift).
No outcome frequency, no profitability: those stay locked to development.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D
import lal_settlement as S

pd.set_option("display.width", 200)


def main():
    reg = D.file_registry()
    m = D.build_master()

    audit = {"file_registry": reg, "rows_total": int(len(m))}

    # ---- structural checks -------------------------------------------------
    per_season = []
    for s in D.ALL_SEASONS:
        d = m[m["season"] == s]
        teams = pd.unique(pd.concat([d["home"], d["away"]]))
        per_season.append({
            "season": s,
            "block": d["block"].iloc[0],
            "matches": int(len(d)),
            "teams": int(len(teams)),
            "matches_per_team_min": int(pd.concat([d["home"], d["away"]]).value_counts().min()),
            "matches_per_team_max": int(pd.concat([d["home"], d["away"]]).value_counts().max()),
            "date_min": d["date"].min(), "date_max": d["date"].max(),
            "dup_fixtures": int(d.duplicated(["home", "away"]).sum()),
            "has_kickoff_pct": round(100 * d["has_kickoff"].mean(), 1),
            "odds_pct": round(100 * d["has_odds"].mean(), 1),
            "o25_present_pct": round(100 * d["O25_B365"].notna().mean(), 1),
            "u25_present_pct": round(100 * d["U25_B365"].notna().mean(), 1),
            "o25max_present_pct": round(100 * d["O25_MAX"].notna().mean(), 1),
            "ah_present_pct": round(100 * d["ah_line"].notna().mean(), 1),
            "x1x2_present_pct": round(100 * d["H_B365"].notna().mean(), 1),
            "ht_goals_missing": int(d["hg_ht"].isna().sum()),
            "score_conflicts": int(d["score_conflict"].sum()),
        })
    ps = pd.DataFrame(per_season)
    audit["per_season"] = ps.to_dict("records")

    # ---- integrity assertions ---------------------------------------------
    checks = {}
    checks["every_season_has_380"] = bool((ps["matches"] == 380).all())
    checks["every_season_has_20_teams"] = bool((ps["teams"] == 20).all())
    checks["every_team_plays_38"] = bool(
        (ps["matches_per_team_min"] == 38).all() and (ps["matches_per_team_max"] == 38).all())
    checks["no_duplicate_fixtures"] = bool((ps["dup_fixtures"] == 0).all())
    checks["no_duplicate_match_ids"] = bool(m["match_id"].duplicated().sum() == 0)
    checks["no_cross_source_score_conflict"] = bool(m["score_conflict"].sum() == 0)
    checks["ht_goals_le_ft_goals"] = bool(
        ((m["hg_ht"] <= m["hg"]) & (m["ag_ht"] <= m["ag"])).all())
    checks["goals_nonneg_int"] = bool(
        (m["hg"] >= 0).all() and (m["ag"] >= 0).all()
        and (m["hg"] % 1 == 0).all() and (m["ag"] % 1 == 0).all())
    checks["states_partition"] = bool(
        (m["is_A"] + m["is_B"] + m["is_C"] == 1).all())
    checks["dates_monotone_within_season"] = bool(all(
        m[m["season"] == s].sort_values("date")["date"].is_monotonic_increasing
        for s in D.ALL_SEASONS))
    checks["split_sizes"] = {b: int((m["block"] == b).sum()) for b in ["dev", "val", "test"]}
    audit["integrity"] = checks

    # ---- price audit -------------------------------------------------------
    price = m[m["O25_B365"].notna() & m["U25_B365"].notna()].copy()
    price["ovr_25"] = 1 / price["O25_B365"] + 1 / price["U25_B365"]
    price["ovr_25_max"] = np.where(
        price["O25_MAX"].notna() & price["U25_MAX"].notna(),
        1 / price["O25_MAX"] + 1 / price["U25_MAX"], np.nan)
    price["ovr_1x2"] = 1 / price["H_B365"] + 1 / price["D_B365"] + 1 / price["A_B365"]

    pm = price.groupby("season").agg(
        n=("O25_B365", "size"),
        o25_mean=("O25_B365", "mean"), o25_min=("O25_B365", "min"), o25_max=("O25_B365", "max"),
        u25_mean=("U25_B365", "mean"), u25_min=("U25_B365", "min"), u25_max=("U25_B365", "max"),
        ovr25_mean=("ovr_25", "mean"), ovr25_p99=("ovr_25", lambda x: x.quantile(0.99)),
        ovr25max_mean=("ovr_25_max", "mean"),
        ovr1x2_mean=("ovr_1x2", "mean"),
    ).round(4).reset_index()
    audit["price_audit_by_season"] = pm.to_dict("records")

    # outliers: implausible margins or prices
    audit["price_outliers"] = {
        "overround_25_below_1": int((price["ovr_25"] < 1.0).sum()),
        "overround_25_above_1.15": int((price["ovr_25"] > 1.15).sum()),
        "o25_below_1.01": int((price["O25_B365"] < 1.01).sum()),
        "o25_above_5": int((price["O25_B365"] > 5).sum()),
        "max_worse_than_b365_over": int((price["O25_MAX"] < price["O25_B365"]).sum()),
        "max_worse_than_b365_under": int((price["U25_MAX"] < price["U25_B365"]).sum()),
    }

    # ---- what is NOT in the data ------------------------------------------
    audit["absent_markets"] = {
        "over_under_2.0_prices": "ABSENT in every available source",
        "closing_prices": "ABSENT (mirror carries pre-match B365 only, no B365C)",
        "opening_prices": "ABSENT",
        "alternative_total_lines (1.5, 3.5, asian 2.25 ...)": "ABSENT",
        "shot_xg_lineups_goal_times_referee_weather": "ABSENT",
        "season_2025_26_prices": "ABSENT (odds mirror ends 2025-05-25)",
    }
    audit["price_benchmark"] = {
        "primary": "Bet365 pre-match Over/Under 2.5 (O25_B365 / U25_B365)",
        "robustness": "market maximum Over/Under 2.5 (O25_MAX / U25_MAX)",
        "note": "pre-match, NOT closing. Closing prices are systematically "
                "sharper, so every economic number here is optimistic relative "
                "to a closing-line benchmark.",
    }

    D.write_json("totals_data_audit.json", audit)

    print("=== FILE REGISTRY ===")
    for r in reg:
        print(f"  {r['file']:34s} {r['bytes']:>10,}  {r['role']:8s} {r['sha256'][:16]}...")
    print("\n=== PER SEASON ===")
    print(ps.to_string(index=False))
    print("\n=== INTEGRITY ===")
    for k, v in checks.items():
        print(f"  {k:36s} {v}")
    print("\n=== PRICE AUDIT ===")
    print(pm.to_string(index=False))
    print("\n=== PRICE OUTLIERS ===")
    for k, v in audit["price_outliers"].items():
        print(f"  {k:34s} {v}")


if __name__ == "__main__":
    main()
