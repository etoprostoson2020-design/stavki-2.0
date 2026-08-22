"""Stage 12 -- evaluate the three user-supplied strategies on development.

Same machinery as every other candidate: flat 1u, pre-match only, one bet per
match, the frozen gates, price-set robustness and a permutation test for the
sequential one.
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
import lal_settlement as S
import s03_features as FEAT
import s08_gates_dev as G

pd.set_option("display.width", 260)
pd.set_option("display.max_columns", 40)
RNG = np.random.default_rng(4242)


def trigger_audit(dev: pd.DataFrame):
    """How often does each individual condition hold at all?"""
    print("=== СКОЛЬКО РАЗ ВООБЩЕ СРАБАТЫВАЕТ КАЖДОЕ УСЛОВИЕ (development) ===\n")
    n = len(dev)
    rows = []

    kt = dev["prev_done_known"]
    rows.append(("S1: сезон с временем начала", int(kt.sum()), n))
    c1 = kt & (dev["prev_done_G2"] == 0)
    rows.append(("S1: + пустой 2-й тайм у предыдущего", int(c1.sum()), n))
    c1b = c1 & dev["U25_PRI"].between(1.80, 1.89)
    rows.append(("S1: + ТМ2.5 в 1.80-1.89  -> СТАВКА", int(c1b.sum()), n))

    a = dev["prev_G2_h"] >= 2
    rows.append(("S2: у хозяев 2+ гола во 2-м тайме", int(a.sum()), n))
    b = a & (dev["prev_G2_a"] == 0)
    rows.append(("S2: + у гостей 0 во 2-м тайме", int(b.sum()), n))
    c = b & (dev["O25_PRI"] < dev["U25_PRI"])
    rows.append(("S2: + ТБ дешевле ТМ", int(c.sum()), n))
    d = c & (dev["U25_PRI"] >= 2.00)
    rows.append(("S2: + ТМ2.5 >= 2.00  -> СТАВКА", int(d.sum()), n))

    e = dev["prev_G1_h"] == 0
    rows.append(("S3: у хозяев 0 в 1-м тайме", int(e.sum()), n))
    f = e & (dev["prev_G1_a"] >= 2)
    rows.append(("S3: + у гостей 2+ в 1-м тайме", int(f.sum()), n))
    g = f & (dev["O25_PRI"] < dev["U25_PRI"])
    rows.append(("S3: + ТБ дешевле ТМ", int(g.sum()), n))
    h = g & (dev["O25_PRI"] >= 1.55)
    rows.append(("S3: + ТБ2.5 >= 1.55  -> СТАВКА", int(h.sum()), n))

    for label, k, tot in rows:
        print(f"  {label:42s} {k:5d}  ({100*k/tot:5.1f}% матчей)")

    print(f"\n  S2 и S3 срабатывают одновременно: {int((d & h).sum())} матчей")
    return {"overlap_s2_s3": int((d & h).sum())}


def permutation_test(dev: pd.DataFrame, fn, name, n_perm=1500):
    """Break the chronological link, keep the composition. Does the edge survive?

    The season's outcomes (goals by half) are shuffled across matches, features
    that depend on them are rebuilt, and the strategy is re-run. If the real ROI
    sits inside the shuffled distribution, the ordering carried no information.
    """
    import lal_features as F
    base = D.build_master()
    real = BT.summarise(BT.run(dev, fn, candidate_id=name))
    if real["bets"] < 20:
        return {"note": "too few bets to test"}
    obs = real["roi"]

    null = np.empty(n_perm)
    cols = ["hg", "ag", "hg_ht", "ag_ht"]
    for t in range(n_perm):
        d = base.copy()
        parts = []
        for _, g in d.groupby("season", sort=False):
            g = g.copy()
            perm = RNG.permutation(len(g))
            for c in cols:
                g[c] = g[c].values[perm]
            parts.append(g)
        d = pd.concat(parts, ignore_index=True)
        d["G"] = d["hg"] + d["ag"]
        d["G_ht"] = d["hg_ht"] + d["ag_ht"]
        d["G_2h"] = d["G"] - d["G_ht"]
        d["state"] = np.where(d["G"] <= 1, "A", np.where(d["G"] == 2, "B", "C"))
        for k, v in [("is_A", "A"), ("is_B", "B"), ("is_C", "C")]:
            d[k] = (d["state"] == v).astype(int)
        d = F.build_all(d)
        dd = d[d["block"] == "dev"]
        r = BT.summarise(BT.run(dd, fn, candidate_id=name))
        null[t] = r["roi"] if r["bets"] >= 5 else np.nan
    null = null[np.isfinite(null)]
    p = float((np.sum(null >= obs) + 1) / (len(null) + 1))
    return {"roi_obs": float(obs), "null_mean": float(null.mean()),
            "null_p95": float(np.percentile(null, 95)), "p_permutation": p,
            "n_null": int(len(null))}


def main():
    m = FEAT.build()
    dev = m[m["block"] == "dev"].copy()
    print(f"=== ТРИ СТРАТЕГИИ ПОЛЬЗОВАТЕЛЯ, development (2016/17-2021/22, n={len(dev)}) ===\n")
    audit = trigger_audit(dev)

    baseline = BT.summarise(BT.run(dev, CA.c1_league_blind_under, candidate_id="base"))["roi"]
    print(f"\n  базовая линия — слепое ТМ2.5 по всей лиге: {100*baseline:+.2f}%\n")

    rows, ledgers, detail = [], [], {}
    for name, meta in CA.USER_CANDIDATES.items():
        s, led = G.full_summary(dev, meta["fn"], name)
        ledgers.append(led)
        detail[name] = s
        if s["bets"] == 0:
            rows.append({"strategy": name, "bets": 0})
            continue
        lo, hi = s.get("roi_boot_lo"), s.get("roi_boot_hi")
        rows.append({
            "strategy": name, "bets": s["bets"], "wins": s["wins"], "losses": s["losses"],
            "roi": s["roi"], "pnl": s["pnl"],
            "roi_hc2": s.get("roi_hc2"), "roi_hc5": s.get("roi_hc5"),
            "boot_lo": lo, "boot_hi": hi,
            "seasons+": s["positive_seasons"], "seasons": s["seasons_with_bets"],
            "maxDD": s["max_drawdown"], "streak": s["max_losing_streak"],
            "seas_conc": s.get("max_season_share_of_gross_positive"),
            "team_conc": s.get("max_team_share_of_gross_positive"),
        })
    res = pd.DataFrame(rows)
    print("=== РЕЗУЛЬТАТ НА DEVELOPMENT ===")
    print(res.round(4).to_string(index=False))

    print("\n=== ПО СЕЗОНАМ ===")
    for name in CA.USER_CANDIDATES:
        s = detail[name]
        if s["bets"] == 0:
            continue
        bys = pd.DataFrame(s["by_season"])
        print(f"\n  {name}  (всего {s['bets']} ставок, ROI {100*s['roi']:+.2f}%)")
        print("   " + bys.rename(columns={"size": "ставок", "sum": "PnL"}).round(2)
              .to_string(index=False).replace("\n", "\n   "))

    print("\n=== УСТОЙЧИВОСТЬ К НАБОРУ ЦЕН ===")
    rr = []
    for name in CA.USER_CANDIDATES:
        row = {"strategy": name}
        for pn, v in (detail[name].get("price_robustness") or {}).items():
            row[pn] = v["roi"]
        rr.append(row)
    print(pd.DataFrame(rr).round(4).to_string(index=False))

    print("\n=== ВОРОТА ДОПУСКА ===")
    gates_out = {}
    for name, meta in CA.USER_CANDIDATES.items():
        s = detail[name]
        if s["bets"] == 0:
            gates_out[name] = {"ALL_PASS": False, "reason": "no bets"}
            print(f"  {name:32s} FAIL  (ни одной ставки)")
            continue
        gt = G.evaluate_gates(s, s.get("roi_boot_lo", np.nan), True, baseline,
                              False, meta["family"] == "sequential")
        gates_out[name] = gt
        failed = [k for k, v in gt.items() if k != "ALL_PASS" and v is False]
        print(f"  {name:32s} {'PASS' if gt['ALL_PASS'] else 'FAIL'}"
              f"{'' if gt['ALL_PASS'] else '  провалено: ' + ', '.join(failed)}")

    # The permutation test lives in s13 (vectorised, 2000 draws) -- running a
    # slow duplicate here would only rebuild the same evidence.
    perms = {"see": "s13_user_permutation.json"}

    D.write_json("s12_user_strategies.json", {
        "trigger_audit": audit,
        "baseline_roi_dev": float(baseline),
        "results": {k: {kk: vv for kk, vv in v.items() if kk != "neighbours"}
                    for k, v in detail.items()},
        "gates": gates_out,
        "permutation": perms,
    })
    pd.concat(ledgers, ignore_index=True).to_csv(
        D.OUT / "totals_bet_ledger_user_dev.csv", index=False)
    print("\n[written] out/s12_user_strategies.json, out/totals_bet_ledger_user_dev.csv")


if __name__ == "__main__":
    main()
