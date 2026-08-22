"""Stage 14 -- one-shot validation of the three user strategies.

The rules were frozen in lal_candidates.py before this file was run; nothing is
re-tuned here.  Every available price set is reported, because a rule that only
works on a soft pre-match quote and dies on the closing line is not a rule.
"""
from __future__ import annotations
import sys, os, warnings
sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import lal_data as D
import lal_backtest as BT
import lal_candidates as CA
import s03_features as FEAT
import s08_gates_dev as G
import s13_user_permutation as P

pd.set_option("display.width", 260)


def main():
    m = FEAT.build()
    val = D.load("val", unlock="VALIDATION_RUN_ONCE")
    val = m[m["match_id"].isin(val["match_id"])].copy()

    print(f"=== ВАЛИДАЦИЯ ТРЁХ СТРАТЕГИЙ (2022/23-2023/24, n={len(val)}) ===\n")
    print("  ОГОВОРКА: блок валидации в этом исследовании уже открывался ранее —")
    print("  для кандидата C2. Эти три стратегии новые и заморожены до запуска,")
    print("  так что подгонки под увиденное нет, но это не первое чтение блока.\n")

    rows, detail = [], {}
    for name, meta in CA.USER_CANDIDATES.items():
        s, led = G.full_summary(val, meta["fn"], name)
        detail[name] = s
        if s["bets"] == 0:
            rows.append({"strategy": name, "bets": 0})
            continue
        rows.append({
            "strategy": name, "bets": s["bets"], "wins": s["wins"],
            "losses": s["losses"], "roi": s["roi"], "pnl": s["pnl"],
            "roi_hc2": s.get("roi_hc2"), "roi_hc5": s.get("roi_hc5"),
            "boot_lo": s.get("roi_boot_lo"), "boot_hi": s.get("roi_boot_hi"),
            "seasons+": s["positive_seasons"], "maxDD": s["max_drawdown"],
            "streak": s["max_losing_streak"],
        })
    res = pd.DataFrame(rows)
    print("--- результат на валидации, эталонная цена (среднерыночная предматчевая) ---")
    print(res.round(4).to_string(index=False))

    print("\n--- по сезонам ---")
    for name in CA.USER_CANDIDATES:
        s = detail[name]
        if s["bets"] == 0:
            continue
        bys = pd.DataFrame(s["by_season"]).rename(columns={"size": "ставок", "sum": "PnL"})
        print(f"\n  {name}")
        print("   " + bys.round(2).to_string(index=False).replace("\n", "\n   "))

    print("\n--- все наборы цен ---")
    rr = []
    for name in CA.USER_CANDIDATES:
        row = {"strategy": name}
        for pn, v in (detail[name].get("price_robustness") or {}).items():
            row[pn] = v["roi"]
        rr.append(row)
    print(pd.DataFrame(rr).round(4).to_string(index=False))

    # permutation on validation as well
    print("\n--- перестановочный тест на валидации ---")
    sd = P.prepare(val)
    perms = {}
    for rule in (None, "S1", "S2", "S3"):
        r = P.perm_p(sd, rule, n=2000)
        key = rule or "COMBINED"
        perms[key] = r
        if r is None:
            print(f"  {key}: нет ставок")
            continue
        print(f"  {key:8s}: {r['bets']:3d} ставок  ROI {100*r['roi']:+7.2f}%  "
              f"нуль {100*r['null_mean']:+6.2f}%  p={r['p']:.4f}")

    # verdict
    print("\n=== ВЕРДИКТ ===")
    passed = []
    for name in CA.USER_CANDIDATES:
        s = detail[name]
        ok = (s["bets"] >= 20 and s["pnl"] > 0 and s["roi"] > 0
              and s.get("roi_hc2", -1) > 0)
        print(f"  {name:32s} {'ПОДТВЕРДИЛАСЬ' if ok else 'НЕ ПОДТВЕРДИЛАСЬ'}"
              f"  (ставок {s['bets']}, ROI {100*s['roi']:+.2f}%, "
              f"PnL {s['pnl']:+.2f}u)" if s["bets"] else f"  {name:32s} нет ставок")
        if ok:
            passed.append(name)

    D.write_json("s14_user_validation.json", {
        "results": {k: {kk: vv for kk, vv in v.items() if kk != "neighbours"}
                    for k, v in detail.items()},
        "permutation_on_validation": perms,
        "passed": passed,
        "disclosure": "validation block was previously opened for candidate C2; "
                      "these three rules are new and were frozen before this run",
    })
    print(f"\n  ПРОШЛИ ВАЛИДАЦИЮ: {passed or 'НИ ОДНА'}")
    print("\n[written] out/s14_user_validation.json")


if __name__ == "__main__":
    main()
