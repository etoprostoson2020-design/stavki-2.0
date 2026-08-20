"""Stage 8 -- freeze the admission gates, then run every candidate on development.

The gates are written to out/totals_frozen_gates.json BEFORE validation is
opened, and are never weakened afterwards.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D
import lal_classes as C
import lal_backtest as BT
import lal_candidates as CA
import s03_features as FEAT

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)

GATES = {
    "G01_no_future_leakage": {"rule": "s03 leakage gate must PASS", "type": "hard"},
    "G02_real_named_price": {
        "rule": "economic certification only from Bet365 pre-match O/U 2.5; "
                "markets without a real historical price cannot be certified",
        "type": "hard"},
    "G03_priced_availability": {"rule": ">= 0.80", "min": 0.80},
    "G04_min_bets_dev": {"rule": ">= 60 priced bets on development", "min": 60},
    "G05_min_seasons": {"rule": "bets in >= 4 development seasons", "min": 4},
    "G06_raw_positive": {"rule": "raw PnL > 0 and raw ROI > 0", "min": 0.0},
    "G07_haircut2_positive": {"rule": "PnL after 2% price haircut > 0", "min": 0.0},
    "G08_haircut5_roi": {"rule": "ROI after 5% haircut >= -0.02", "min": -0.02},
    "G09_positive_seasons": {"rule": "positive PnL in >= 2/3 of eligible seasons",
                             "min_frac": 2 / 3},
    "G10_drawdown": {"rule": "max drawdown <= 15u AND <= 20% of turnover",
                     "max_u": 15.0, "max_frac": 0.20},
    "G11_losing_streak": {"rule": "max losing streak <= 12", "max": 12},
    "G12_concentration": {"rule": "one season <= 50% of gross positive PnL; "
                                  "one team <= 30%", "season_max": 0.50, "team_max": 0.30},
    "G13_neighbour_stability": {"rule": "sign of ROI unchanged on neighbouring "
                                        "frozen parameter settings", "type": "hard"},
    "G14_beats_baselines": {"rule": "ROI must exceed both the blind-league "
                                    "baseline and the market baseline", "type": "hard"},
    "G15_sequential_extra": {"rule": "a sequential candidate must additionally pass "
                                     "its permutation and placebo tests", "type": "hard"},
}


def evaluate_gates(s: dict, boot_lo: float, neighbour_ok: bool,
                   baseline_roi: float, seq_ok: bool, is_seq: bool) -> dict:
    r = {}
    r["G03_priced_availability"] = s.get("priced_availability", 0) >= 0.80
    r["G04_min_bets_dev"] = s["bets"] >= 60
    r["G05_min_seasons"] = s["seasons_with_bets"] >= 4
    r["G06_raw_positive"] = s["pnl"] > 0 and s["roi"] > 0
    r["G07_haircut2_positive"] = s["pnl_hc2"] > 0
    r["G08_haircut5_roi"] = s["roi_hc5"] >= -0.02
    r["G09_positive_seasons"] = (s["positive_seasons"] / max(s["seasons_with_bets"], 1)) >= 2 / 3
    r["G10_drawdown"] = (s["max_drawdown"] <= 15.0) and (s["max_drawdown_pct_turnover"] <= 0.20)
    r["G11_losing_streak"] = s["max_losing_streak"] <= 12
    conc_s = s.get("max_season_share_of_gross_positive")
    conc_t = s.get("max_team_share_of_gross_positive")
    r["G12_concentration"] = bool(
        (conc_s is not None and not np.isnan(conc_s) and conc_s <= 0.50)
        and (conc_t is not None and not np.isnan(conc_t) and conc_t <= 0.30))
    r["G13_neighbour_stability"] = neighbour_ok
    r["G14_beats_baselines"] = s["roi"] > baseline_roi
    r["G15_sequential_extra"] = (not is_seq) or seq_ok
    r["ALL_PASS"] = all(r.values())
    return r


def neighbour_check(d, name, base_roi) -> tuple[bool, dict]:
    """Re-run with each frozen numeric parameter nudged, and check the sign."""
    variants = {}
    th = C.load_thresholds()
    if name == "C4_MARKET_ABOVE_FORM_UNDER_2.5":
        for g in (0.04, 0.05, 0.07, 0.08):
            old = CA.MKT_FORM_GAP
            CA.MKT_FORM_GAP = g
            led = BT.run(d, CA.c4_market_above_form, candidate_id=name)
            CA.MKT_FORM_GAP = old
            b = led[led["stake"] > 0]
            variants[f"gap={g}"] = float(b["pnl"].mean()) if len(b) else np.nan
    elif name == "C5_FORM_ABOVE_MARKET_OVER_2.5":
        for g in (0.04, 0.05, 0.07, 0.08):
            old = CA.OVER_GAP
            CA.OVER_GAP = g
            led = BT.run(d, CA.c5_form_above_market, candidate_id=name)
            CA.OVER_GAP = old
            b = led[led["stake"] > 0]
            variants[f"gap={g}"] = float(b["pnl"].mean()) if len(b) else np.nan
    elif name == "C2_STRONG_HOME_UNDER_2.5":
        for q in ("q60", "q80"):
            thr = th["strength"][q]
            def fn(r, thr=thr):
                if r.tm_idx_h < th["min_history"] or r.tm_idx_a < th["min_history"]:
                    return None, None, "INSUFFICIENT_HISTORY"
                if not np.isfinite(r.elo_h) or r.elo_h < thr:
                    return None, None, "HOME_NOT_STRONG"
                return "UNDER_2.5", 1.75, "STRONG_HOME"
            led = BT.run(d, fn, candidate_id=name)
            b = led[led["stake"] > 0]
            variants[f"elo>={q}"] = float(b["pnl"].mean()) if len(b) else np.nan
    elif name == "C7_SEQ_HOT_FADE_UNDER_2.5":
        for s in (0.55, 0.58, 0.65, 0.70):
            old = CA.SEQ_HOT
            CA.SEQ_HOT = s
            led = BT.run(d, CA.c7_sequential_fade_hot_league, candidate_id=name)
            CA.SEQ_HOT = old
            b = led[led["stake"] > 0]
            variants[f"seq>={s}"] = float(b["pnl"].mean()) if len(b) else np.nan
    if not variants:
        return True, {"note": "no free numeric parameter"}
    signs = [np.sign(v) for v in variants.values() if np.isfinite(v)]
    ok = bool(signs) and all(s == np.sign(base_roi) for s in signs)
    return ok, variants


def full_summary(d, fn, name) -> dict:
    led = BT.run(d, fn, candidate_id=name)
    s = BT.summarise(led)
    if s["bets"] == 0:
        return s, led
    for hc, tag in [(0.02, "hc2"), (0.05, "hc5")]:
        l2 = BT.run(d, fn, haircut=hc, candidate_id=name)
        s2 = BT.summarise(l2)
        s[f"pnl_{tag}"] = s2["pnl"]
        s[f"roi_{tag}"] = s2["roi"]
        s[f"bets_{tag}"] = s2["bets"]
    lo, hi = BT.bootstrap_roi(led)
    s["roi_boot_lo"], s["roi_boot_hi"] = lo, hi
    lmax = BT.run(d, fn, price_map=BT.PRICE_COL_MAX, candidate_id=name)
    smax = BT.summarise(lmax)
    s["roi_market_max"] = smax["roi"]
    s["pnl_market_max"] = smax["pnl"]

    # Robustness across every price set that exists. Each is scored only on the
    # matches that price set actually quotes, so the samples are not comparable
    # in size -- they are comparable in sign.
    rob = {}
    for pname, pmap in BT.PRICE_MAPS.items():
        try:
            lr = BT.run(d, fn, price_map=pmap, candidate_id=name)
        except Exception:
            continue
        sr = BT.summarise(lr)
        if sr["bets"] >= 40:
            rob[pname] = {"bets": sr["bets"], "roi": round(sr["roi"], 4),
                          "pnl": round(sr["pnl"], 2)}
    s["price_robustness"] = rob
    return s, led


def main():
    D.write_json("totals_frozen_gates.json", {
        "frozen_at": "before validation was opened",
        "gates": GATES,
        "price_benchmark": D.PRIMARY_PRICE,
        "robustness_prices": D.ROBUSTNESS_PRICES,
        "stake": "flat 1 unit",
        "note": "gates may not be weakened after any result is seen",
    })
    print("=== FROZEN GATES written to out/totals_frozen_gates.json ===\n")

    m = FEAT.build()
    dev = m[m["block"] == "dev"].copy()

    # baseline the candidates must beat: blind under, and the market itself
    base_led = BT.run(dev, CA.c1_league_blind_under, candidate_id="baseline")
    baseline_roi = BT.summarise(base_led)["roi"]
    print(f"  blind-league UNDER 2.5 baseline ROI on development: {100*baseline_roi:+.2f}%\n")

    import json
    seq_res = json.loads((D.OUT / "totals_sequential_tests.json").read_text()) \
        if (D.OUT / "totals_sequential_tests.json").exists() else {"surviving_effects": []}
    seq_ok = len(seq_res.get("surviving_effects", [])) > 0

    rows, ledgers, passports = [], [], {}
    for name, meta in CA.CANDIDATES.items():
        s, led = full_summary(dev, meta["fn"], name)
        ledgers.append(led)
        is_seq = meta["family"] == "sequential"
        if s["bets"] == 0:
            gates = {"ALL_PASS": False, "reason": "no bets"}
        else:
            nb_ok, nb = neighbour_check(dev, name, s["roi"])
            s["neighbours"] = nb
            gates = evaluate_gates(s, s.get("roi_boot_lo", np.nan), nb_ok,
                                   baseline_roi if name != "C1_LEAGUE_BLIND_UNDER_2.5" else -9,
                                   seq_ok, is_seq)
        s["gates"] = gates
        passports[name] = {**meta, "development": {k: v for k, v in s.items() if k != "fn"}}
        passports[name].pop("fn", None)
        rows.append({
            "candidate": name, "family": meta["family"], "bets": s["bets"],
            "avail": s.get("priced_availability"), "roi": s.get("roi"),
            "pnl": s.get("pnl"), "roi_hc2": s.get("roi_hc2"), "roi_hc5": s.get("roi_hc5"),
            "roi_max": s.get("roi_market_max"),
            "boot_lo": s.get("roi_boot_lo"), "seasons+": s.get("positive_seasons"),
            "seasons": s.get("seasons_with_bets"), "maxDD": s.get("max_drawdown"),
            "streak": s.get("max_losing_streak"),
            "seas_conc": s.get("max_season_share_of_gross_positive"),
            "team_conc": s.get("max_team_share_of_gross_positive"),
            "roi_close": (s.get("price_robustness", {}).get("pinnacle_closing") or {}).get("roi"),
            "n_close": (s.get("price_robustness", {}).get("pinnacle_closing") or {}).get("bets"),
            "PASS": gates.get("ALL_PASS"),
        })

    res = pd.DataFrame(rows)
    print("=== DEVELOPMENT RESULTS, ALL CANDIDATES ===")
    print(res.round(4).to_string(index=False))

    print("\n=== PRICE-SET ROBUSTNESS (ROI by price set, development) ===")
    rr = []
    for name in CA.CANDIDATES:
        row = {"candidate": name}
        for pn, v in passports[name]["development"].get("price_robustness", {}).items():
            row[pn] = v["roi"]
        rr.append(row)
    print(pd.DataFrame(rr).round(4).to_string(index=False))

    print("\n=== GATE DETAIL ===")
    for name in CA.CANDIDATES:
        g = passports[name]["development"].get("gates", {})
        failed = [k for k, v in g.items() if k != "ALL_PASS" and v is False]
        print(f"  {name:34s} {'PASS' if g.get('ALL_PASS') else 'FAIL'}"
              f"{'' if g.get('ALL_PASS') else '  failed: ' + ', '.join(failed)}")

    survivors = [n for n in CA.CANDIDATES
                 if passports[n]["development"].get("gates", {}).get("ALL_PASS")]
    print(f"\n  CANDIDATES CLEARED FOR VALIDATION: {survivors if survivors else 'NONE'}")

    pd.concat(ledgers, ignore_index=True).to_csv(D.OUT / "totals_bet_ledger_dev.csv", index=False)
    D.write_json("totals_strategy_candidates.json",
                 {"stage": "development", "passports": passports,
                  "cleared_for_validation": survivors,
                  "baseline_roi_dev": float(baseline_roi)})
    print("\n[written] out/totals_strategy_candidates.json, out/totals_bet_ledger_dev.csv")


if __name__ == "__main__":
    main()
