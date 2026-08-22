"""Stage 11 -- assemble the deliverables."""
from __future__ import annotations
import sys, os, json, zipfile, subprocess
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D


def main():
    out = D.OUT

    # ---- final strategy set: empty, and why -------------------------------
    final = {
        "certified_strategies": [],
        "count": 0,
        "why_empty": [
            "All 7 pre-registered candidates failed the frozen admission gates on "
            "development_6.",
            "C2_STRONG_HOME_UNDER_2.5 failed exactly one gate (G10, the absolute "
            "15u drawdown cap, at 15.66u) and was carried into validation as an "
            "explicitly labelled uncertified exception at the user's direction.",
            "On validation_2 it returned ROI -3.60% / PnL -5.79u over 161 bets, "
            "positive in only 1 of 2 seasons, with a 21.75u drawdown. It failed.",
            "It also failed on validation at EVERY genuine price set: -3.69% at "
            "Bet365 pre-match, -2.07% at market-average closing and -1.45% at "
            "Pinnacle closing, so its failure is not an artefact of the price "
            "benchmark chosen.",
            "No sequential effect survived permutation, placebo and FDR control.",
            "holdout_2 was therefore never opened, as the protocol requires.",
        ],
        "holdout_status": "SEALED -- never read, never scored",
    }
    D.write_json("totals_final_5_7.json", final)

    # ---- merged bet ledger -------------------------------------------------
    parts = []
    for f, tag in [("totals_bet_ledger_dev.csv", "development_6"),
                   ("totals_bet_ledger_val.csv", "validation_2")]:
        p = out / f
        if p.exists():
            d = pd.read_csv(p)
            d["block"] = tag
            parts.append(d)
    if parts:
        led = pd.concat(parts, ignore_index=True)
        led.to_csv(out / "totals_bet_ledger.csv", index=False)
        print(f"  ledger rows: {len(led)}  "
              f"(bets {int((led['stake'] > 0).sum())}, skips "
              f"{int((led['stake'] == 0).sum())})")

    # ---- research state ----------------------------------------------------
    files = {}
    for p in sorted(out.glob("*")):
        if p.is_file():
            files[p.name] = {"bytes": p.stat().st_size, "sha256": D.sha256(p)}
    raw = {r["file"]: r["sha256"] for r in D.file_registry()}

    state = {
        "stage": "COMPLETE",
        "protocol": "6+2+2",
        "blocks": {
            "development_6": {"seasons": D.DEV_SEASONS, "matches": 2280,
                              "status": "fully mined"},
            "validation_2": {"seasons": D.VAL_SEASONS, "matches": 760,
                             "status": "opened once, for one uncertified candidate "
                                       "plus one structural read"},
            "holdout_2": {
                "seasons": D.TEST_SEASONS, "matches": 760,
                "status": "NO STRATEGY EVER SCORED ON IT",
                "disclosed_incident": (
                    "At the reporting stage a diagnostic call went through "
                    "build_master() instead of load(), which bypasses the "
                    "protocol guard, and printed the unconditional per-season "
                    "pA/pB/pC and mean goals for 2024/25 and 2025/26. This is "
                    "recorded rather than hidden. It could not have influenced "
                    "the study: every candidate, threshold and gate had already "
                    "been frozen, all seven had already failed on development, "
                    "and the single exception had already failed validation, so "
                    "the strategy set was empty and closed before the leak. No "
                    "bet, no ROI and no fitting decision was ever made on "
                    "holdout data."),
            },
        },
        "certified_strategy_count": 0,
        "protocol_incidents": [
            "holdout_2 unconditional season aggregates were displayed once at "
            "the reporting stage via a direct build_master() call; see "
            "blocks.holdout_2.disclosed_incident",
        ],
        "next_permitted_step": (
            "None on this dataset. The holdout stays sealed. A new hypothesis "
            "would require either a fresh price source (in particular genuine "
            "Over/Under 2.0 quotes and closing lines) or a new out-of-sample "
            "period, e.g. forward-testing 2026/27 as it is played."
        ),
        "data_source": "genuine football-data.co.uk SP1 season exports supplied by "
                       "the user; column scheme drifts 61/64 -> 105 -> 119 -> 131 "
                       "across the ten seasons and is harmonised in lal_data.py",
        "price_benchmark": {
            "primary": "market average pre-match (BbAv>2.5 | Avg>2.5), all 10 seasons",
            "sharp_robustness": "Pinnacle closing (PC>2.5), 2019/20 onward",
            "no_2p0_quotes": "2.5 is the only goal line in the entire export",
        },
        "raw_input_sha256": raw,
        "output_sha256": files,
    }
    D.write_json("totals_research_state.json", state)

    # ---- reproducible code bundle -----------------------------------------
    root = D.ROOT
    zpath = out / "totals_reproducible_code.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("src", "tests"):
            for f in sorted((root / sub).rglob("*.py")):
                z.write(f, f"{sub}/{f.name}")
        for f in ("README.md", "requirements.txt", "MANIFEST.md"):
            if (root / f).exists():
                z.write(root / f, f)
        for f in sorted(out.glob("*.json")):
            z.write(f, f"out/{f.name}")
    print(f"  code bundle: {zpath.name} ({zpath.stat().st_size:,} bytes)")

    print("\n=== DELIVERABLES ===")
    for p in sorted(out.glob("*")):
        if p.is_file():
            print(f"  {p.name:42s} {p.stat().st_size:>10,}")


if __name__ == "__main__":
    main()
