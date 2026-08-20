"""Stage 1 -- file registry, data audit and price-coverage audit.

Runs over all seasons but reports only structural facts: row counts, field
coverage, price coverage, margins, schema drift.  No outcome frequency and no
profitability -- those stay locked to development.
"""
from __future__ import annotations
import sys, os, warnings
sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import lal_data as D
import lal_settlement as S

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)

PRICE_SETS = {
    "market_avg_prematch":  ("OV25", "UN25"),
    "market_max_prematch":  ("OV25_MAX", "UN25_MAX"),
    "bet365_prematch":      ("OV25_B365", "UN25_B365"),
    "market_avg_closing":   ("OV25_C", "UN25_C"),
    "pinnacle_closing":     ("OV25_PC", "UN25_PC"),
    "market_max_closing":   ("OV25_MAXC", "UN25_MAXC"),
    "betfair_exchange":     ("OV25_BFE", "UN25_BFE"),
}


def main():
    reg = D.file_registry()
    m = D.build_master()
    audit = {"file_registry": reg, "rows_total": int(len(m))}

    per = []
    for s in D.ALL_SEASONS:
        d = m[m["season"] == s]
        cnt = pd.concat([d["home"], d["away"]]).value_counts()
        per.append({
            "season": s, "block": d["block"].iloc[0], "matches": len(d),
            "teams": int(pd.concat([d["home"], d["away"]]).nunique()),
            "per_team_min": int(cnt.min()), "per_team_max": int(cnt.max()),
            "date_min": d["date"].min(), "date_max": d["date"].max(),
            "dup_fixtures": int(d.duplicated(["home", "away"]).sum()),
            "kickoff_pct": round(100 * d["has_kickoff"].mean(), 1),
            "batches": int(d["batch_id"].nunique()),
            "ht_missing": int(d["hg_ht"].isna().sum()),
            "raw_cols": int(pd.read_csv(D.RAW / f"{s}.csv", nrows=1,
                                        encoding="utf-8-sig").shape[1]),
        })
    ps = pd.DataFrame(per)
    audit["per_season"] = ps.to_dict("records")

    checks = {
        "every_season_380": bool((ps["matches"] == 380).all()),
        "every_season_20_teams": bool((ps["teams"] == 20).all()),
        "every_team_38": bool((ps["per_team_min"] == 38).all() and (ps["per_team_max"] == 38).all()),
        "no_dup_fixtures": bool((ps["dup_fixtures"] == 0).all()),
        "no_dup_match_ids": bool(m["match_id"].duplicated().sum() == 0),
        "ht_le_ft": bool(((m["hg_ht"] <= m["hg"]) & (m["ag_ht"] <= m["ag"])).all()),
        "states_partition": bool((m["is_A"] + m["is_B"] + m["is_C"] == 1).all()),
        "dates_parsed": bool(m["date"].notna().all()),
        "split_sizes": {b: int((m["block"] == b).sum()) for b in ["dev", "val", "test"]},
    }
    audit["integrity"] = checks

    # ---- cross-check against the earlier proxy dataset ---------------------
    legacy = {}
    lp = D.LEGACY
    if (lp / "fd_la-liga_season-1617.csv").exists():
        frames = []
        for s in D.ALL_SEASONS:
            tag = s[:2] + s[3:]
            f = lp / f"fd_la-liga_season-{tag}.csv"
            if f.exists():
                d = pd.read_csv(f)
                d["season"] = s
                frames.append(d)
        old = pd.concat(frames, ignore_index=True)
        old["date"] = pd.to_datetime(old["Date"])
        key = ["season", "HomeTeam", "AwayTeam"]
        old_k = old.set_index([old["season"], old["HomeTeam"], old["AwayTeam"]])
        new_k = m.set_index([m["season"], m["home"], m["away"]])
        common = old_k.index.intersection(new_k.index)
        a = old_k.loc[common]
        b = new_k.loc[common]
        legacy = {
            "matched_fixtures": int(len(common)),
            "score_disagreements": int(((a["FTHG"].values != b["hg"].values)
                                        | (a["FTAG"].values != b["ag"].values)).sum()),
            "ht_disagreements": int(((a["HTHG"].values != b["hg_ht"].values)
                                     | (a["HTAG"].values != b["ag_ht"].values)).sum()),
        }
    audit["cross_check_vs_previous_dataset"] = legacy

    # ---- price coverage ----------------------------------------------------
    cov = []
    for s in D.ALL_SEASONS:
        d = m[m["season"] == s]
        row = {"season": s, "block": d["block"].iloc[0]}
        for name, (o, u) in PRICE_SETS.items():
            ok = d[o].notna() & d[u].notna()
            row[name] = round(100 * ok.mean(), 1)
        cov.append(row)
    cv = pd.DataFrame(cov)
    audit["price_coverage_pct"] = cv.to_dict("records")

    # ---- margin by price set ----------------------------------------------
    marg = []
    for name, (o, u) in PRICE_SETS.items():
        d = m[m[o].notna() & m[u].notna()]
        if not len(d):
            continue
        ovr = 1 / d[o] + 1 / d[u]
        marg.append({"price_set": name, "n": len(d),
                     "seasons": d["season"].nunique(),
                     "mean_over_price": round(d[o].mean(), 4),
                     "mean_under_price": round(d[u].mean(), 4),
                     "mean_overround": round(ovr.mean(), 4),
                     "vig_per_side_pct": round(100 * (ovr.mean() - 1) / 2, 3),
                     "ovr_below_1": int((ovr < 1).sum()),
                     "ovr_above_1.15": int((ovr > 1.15).sum())})
    mg = pd.DataFrame(marg)
    audit["margin_by_price_set"] = mg.to_dict("records")

    audit["absent_markets"] = {
        "over_under_2.0_and_every_alternative_total_line":
            "ABSENT -- 2.5 is the only goal line in the entire football-data export",
        "opening_prices": "ABSENT (pre-match and closing only)",
        "closing_totals_before_2019_20": "ABSENT (Bb* scheme carries no closing total)",
        "bet365_totals_before_2019_20": "ABSENT",
        "xg_lineups_goal_times_referee_weather": "ABSENT",
    }
    audit["price_benchmark"] = {
        "primary": "market average pre-match (BbAv>2.5 | Avg>2.5) -- the only "
                   "Over/Under 2.5 series that exists in all ten seasons",
        "robustness": list(PRICE_SETS),
        "note": "Pinnacle closing (PC>2.5) is the sharp benchmark and exists from "
                "2019/20; any edge that survives only on pre-match prices and dies "
                "on the closing line is a stale-price artefact, not an edge.",
    }

    D.write_json("totals_data_audit.json", audit)

    print("=== FILE REGISTRY ===")
    for r in reg:
        print(f"  {r['file']:12s} {r['bytes']:>9,}  {r['sha256'][:20]}...")
    print("\n=== PER SEASON ===")
    print(ps.to_string(index=False))
    print("\n=== INTEGRITY ===")
    for k, v in checks.items():
        print(f"  {k:26s} {v}")
    print("\n=== CROSS-CHECK vs PREVIOUS (proxy) DATASET ===")
    for k, v in legacy.items():
        print(f"  {k:26s} {v}")
    print("\n=== PRICE COVERAGE (% of matches with both sides quoted) ===")
    print(cv.to_string(index=False))
    print("\n=== MARGIN BY PRICE SET ===")
    print(mg.to_string(index=False))


if __name__ == "__main__":
    main()
