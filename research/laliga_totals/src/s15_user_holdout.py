"""Stage 15 -- neighbour stability, then the ONE-SHOT holdout for the user rules.

Order matters and is enforced by reading top to bottom:
  1. neighbour stability on development (gate G13) -- thresholds nudged, sign checked
  2. the frozen combined rule is run once on holdout_2, untouched
Nothing is re-tuned after step 2.
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


def make_combined(u_min, o_min, band_lo, band_hi):
    """The combined rule with its four numeric thresholds parameterised."""
    def fn(r):
        # S2
        if (np.isfinite(getattr(r, "prev_G2_h", np.nan))
                and np.isfinite(getattr(r, "prev_G2_a", np.nan))
                and r.prev_G2_h >= 2 and r.prev_G2_a == 0):
            o, u = getattr(r, "O25_PRI", np.nan), getattr(r, "U25_PRI", np.nan)
            if np.isfinite(o) and np.isfinite(u) and o < u and u >= u_min:
                return "UNDER_2.5", None, "S2"
        # S3
        if (np.isfinite(getattr(r, "prev_G1_h", np.nan))
                and np.isfinite(getattr(r, "prev_G1_a", np.nan))
                and r.prev_G1_h == 0 and r.prev_G1_a >= 2):
            o, u = getattr(r, "O25_PRI", np.nan), getattr(r, "U25_PRI", np.nan)
            if np.isfinite(o) and np.isfinite(u) and o < u and o >= o_min:
                return "OVER_2.5", None, "S3"
        # S1
        if getattr(r, "prev_done_known", False) and getattr(r, "prev_done_G2", np.nan) == 0:
            u = getattr(r, "U25_PRI", np.nan)
            if np.isfinite(u) and band_lo <= u <= band_hi:
                return "UNDER_2.5", None, "S1"
        return None, None, "NO_RULE"
    return fn


def neighbours(dev):
    print("=== G13: УСТОЙЧИВОСТЬ К СОСЕДНИМ ПОРОГАМ (development) ===\n")
    base = (2.00, 1.55, 1.80, 1.89)
    rows = []
    variants = [("базовые пороги", base)]
    for u in (1.90, 1.95, 2.05, 2.10):
        variants.append((f"ТМ2.5 >= {u:.2f}", (u, 1.55, 1.80, 1.89)))
    for o in (1.45, 1.50, 1.60, 1.65):
        variants.append((f"ТБ2.5 >= {o:.2f}", (2.00, o, 1.80, 1.89)))
    for lo, hi in ((1.75, 1.94), (1.78, 1.91), (1.82, 1.87), (1.85, 1.95)):
        variants.append((f"полоса {lo:.2f}-{hi:.2f}", (2.00, 1.55, lo, hi)))
    for label, (u, o, lo, hi) in variants:
        s = BT.summarise(BT.run(dev, make_combined(u, o, lo, hi), candidate_id="nb"))
        rows.append({"вариант": label, "ставок": s["bets"], "ROI": s["roi"], "PnL": s["pnl"]})
    t = pd.DataFrame(rows)
    print(t.round(4).to_string(index=False))
    signs = np.sign(t["ROI"].values)
    ok = bool((signs == signs[0]).all())
    print(f"\n  знак ROI одинаков во всех {len(t)} вариантах: {ok}")
    print(f"  диапазон ROI: {100*t['ROI'].min():+.2f}% .. {100*t['ROI'].max():+.2f}%")
    return ok, t


def main():
    m = FEAT.build()
    dev = m[m["block"] == "dev"].copy()
    nb_ok, nb_tab = neighbours(dev)

    if not nb_ok:
        print("\n  G13 ПРОВАЛЕН — holdout не открывается.")
        D.write_json("s15_user_holdout.json", {"neighbour_ok": False,
                                               "neighbours": nb_tab.to_dict("records"),
                                               "holdout_opened": False})
        return

    print("\n" + "=" * 70)
    print("=== ОДНОРАЗОВЫЙ HOLDOUT (2024/25-2025/26) ===")
    print("=" * 70)
    print("\n  Правила заморожены в lal_candidates.py и здесь не менялись.")
    print("  Допуск: development все ворота + валидация подтвердила"
          " (ROI +12.52%, p=0.0225).\n")

    test = D.load("test", unlock="HOLDOUT_RUN_ONCE")
    test = m[m["match_id"].isin(test["match_id"])].copy()
    print(f"  матчей в holdout: {len(test)}  сезоны {sorted(test['season'].unique())}\n")

    rows, detail = [], {}
    for name, meta in CA.USER_CANDIDATES.items():
        s, led = G.full_summary(test, meta["fn"], name)
        detail[name] = s
        if s["bets"] == 0:
            rows.append({"strategy": name, "bets": 0}); continue
        rows.append({"strategy": name, "bets": s["bets"], "wins": s["wins"],
                     "losses": s["losses"], "roi": s["roi"], "pnl": s["pnl"],
                     "roi_hc2": s.get("roi_hc2"), "roi_hc5": s.get("roi_hc5"),
                     "boot_lo": s.get("roi_boot_lo"), "boot_hi": s.get("roi_boot_hi"),
                     "seasons+": s["positive_seasons"], "maxDD": s["max_drawdown"],
                     "streak": s["max_losing_streak"]})
    res = pd.DataFrame(rows)
    print("--- HOLDOUT, эталонная цена ---")
    print(res.round(4).to_string(index=False))

    print("\n--- по сезонам ---")
    for name in CA.USER_CANDIDATES:
        s = detail[name]
        if not s["bets"]:
            continue
        bys = pd.DataFrame(s["by_season"]).rename(columns={"size": "ставок", "sum": "PnL"})
        print(f"\n  {name}")
        print("   " + bys.round(2).to_string(index=False).replace("\n", "\n   "))

    print("\n--- все наборы цен на holdout ---")
    rr = []
    for name in CA.USER_CANDIDATES:
        row = {"strategy": name}
        for pn, v in (detail[name].get("price_robustness") or {}).items():
            row[pn] = v["roi"]
        rr.append(row)
    print(pd.DataFrame(rr).round(4).to_string(index=False))

    print("\n--- перестановочный тест на holdout ---")
    sd = P.prepare(test)
    perms = {}
    for rule in (None, "S1", "S2", "S3"):
        r = P.perm_p(sd, rule, n=2000)
        key = rule or "COMBINED"
        perms[key] = r
        if r is None:
            print(f"  {key}: нет ставок"); continue
        print(f"  {key:8s}: {r['bets']:3d} ставок  ROI {100*r['roi']:+7.2f}%  "
              f"нуль {100*r['null_mean']:+6.2f}%  p={r['p']:.4f}")

    print("\n=== ИТОГ ПО ТРЁМ БЛОКАМ (комбинация) ===")
    D.write_json("s15_user_holdout.json", {
        "neighbour_ok": nb_ok, "neighbours": nb_tab.to_dict("records"),
        "holdout_opened": True,
        "results": {k: {kk: vv for kk, vv in v.items() if kk != "neighbours"}
                    for k, v in detail.items()},
        "permutation_on_holdout": perms,
    })
    print("\n[written] out/s15_user_holdout.json")


if __name__ == "__main__":
    main()
