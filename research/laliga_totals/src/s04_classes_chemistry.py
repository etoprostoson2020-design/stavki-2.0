"""Stage 4 -- freeze the class thresholds, then map the segment landscape."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D
import lal_classes as C
import lal_eval as E
import lal_settlement as S
import s03_features as FEAT

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)


def main():
    m = FEAT.build()
    dev = m[m["block"] == "dev"].copy()

    th = C.fit_thresholds(dev)
    D.write_json("totals_frozen_classes.json", th)
    print("=== FROZEN CLASS THRESHOLDS (fitted on development only) ===")
    for k, v in th.items():
        print(f"  {k}: {v}")

    dev = C.apply_classes(dev, th)
    print(f"\n  classifiable matches (both teams >= {th['min_history']} played): "
          f"{dev['classifiable'].sum()} / {len(dev)}")

    # ---------------- named segments ---------------------------------------
    masks = C.segment_masks(dev)
    rows = []
    for name, mask in masks.items():
        d = dev[mask]
        st = E.segment_stats(d)
        if st["n"] < 30:
            rows.append({"segment": name, "n": st["n"], "note": "too small"})
            continue
        r = {"segment": name, "n": st["n"], "pA": st["pA"], "pB": st["pB"], "pC": st["pC"],
             "mean_G": st["mean_goals"],
             "fair_O20": st["fair"]["OVER_2.0"], "fair_O25": st["fair"]["OVER_2.5"],
             "fair_U20": st["fair"]["UNDER_2.0"], "fair_U25": st["fair"]["UNDER_2.5"],
             "mkt_pC": st.get("mkt_pC_mean"), "mkt_bias": st.get("mkt_pC_bias"),
             "roi_O25": st["realised_2p5"]["OVER_2.5"]["roi"],
             "roi_U25": st["realised_2p5"]["UNDER_2.5"]["roi"],
             "avail": st["priced_availability"]}
        rows.append(r)
    seg = pd.DataFrame(rows)
    print("\n=== SEGMENT LANDSCAPE (development) ===")
    print(seg.round(4).to_string(index=False))
    D.write_json("s04_segments_dev.json", seg.to_dict("records"))

    # ---------------- chemistry grid: attack x defence ---------------------
    print("\n=== CHEMISTRY: attacking profile of the pair ===")
    d = dev[dev["classifiable"]].copy()
    d["pair_atk"] = d["atk_h"] + " x " + d["atk_a"]
    d["pair_def"] = d["def_h"] + " x " + d["def_a"]
    g = d.groupby("pair_atk").agg(n=("G", "size"), pA=("is_A", "mean"), pB=("is_B", "mean"),
                                  pC=("is_C", "mean"), G=("G", "mean")).round(4)
    g = g[g["n"] >= 40].sort_values("pC", ascending=False)
    print(g.to_string())

    print("\n=== CHEMISTRY: defensive profile of the pair ===")
    g2 = d.groupby("pair_def").agg(n=("G", "size"), pA=("is_A", "mean"), pB=("is_B", "mean"),
                                   pC=("is_C", "mean"), G=("G", "mean")).round(4)
    g2 = g2[g2["n"] >= 40].sort_values("pC", ascending=False)
    print(g2.to_string())

    # cross grid: is total goals driven by attack, defence, or their interaction?
    print("\n=== ATTACK x DEFENCE interaction (mean total goals, n in brackets) ===")
    d["atk_sum"] = d["gf_r10_h"] + d["gf_r10_a"]
    d["def_sum"] = d["ga_r10_h"] + d["ga_r10_a"]
    d["atk_q"] = pd.qcut(d["atk_sum"], 3, labels=["low_atk", "mid_atk", "high_atk"])
    d["def_q"] = pd.qcut(d["def_sum"], 3, labels=["tight", "mid", "leaky"])
    piv = d.pivot_table(index="atk_q", columns="def_q", values="G", aggfunc="mean", observed=True)
    cnt = d.pivot_table(index="atk_q", columns="def_q", values="G", aggfunc="size", observed=True)
    print(piv.round(3).to_string())
    print("\n  counts:"); print(cnt.to_string())
    pivC = d.pivot_table(index="atk_q", columns="def_q", values="is_C", aggfunc="mean", observed=True)
    pivB = d.pivot_table(index="atk_q", columns="def_q", values="is_B", aggfunc="mean", observed=True)
    print("\n  pC:"); print(pivC.round(4).to_string())
    print("\n  pB:"); print(pivB.round(4).to_string())

    # ---------------- does pB move at all? ---------------------------------
    print("\n=== IS pB A CONSTANT?  (the hinge that decides 2.0 vs 2.5) ===")
    dm = dev.dropna(subset=["mkt_pC"]).copy()
    dm["mkt_q"] = pd.qcut(dm["mkt_pC"], 10, labels=False)
    q = dm.groupby("mkt_q").agg(n=("G", "size"), mkt_pC=("mkt_pC", "mean"),
                                pA=("is_A", "mean"), pB=("is_B", "mean"),
                                pC=("is_C", "mean"), G=("G", "mean")).round(4)
    print(q.to_string())
    print(f"\n  pB range across market deciles: {q['pB'].min():.4f} .. {q['pB'].max():.4f}"
          f"   (spread {q['pB'].max()-q['pB'].min():.4f})")
    print(f"  pC range across market deciles: {q['pC'].min():.4f} .. {q['pC'].max():.4f}"
          f"   (spread {q['pC'].max()-q['pC'].min():.4f})")
    from scipy.stats import chi2_contingency
    tab = pd.crosstab(dm["mkt_q"], dm["state"])
    chi2, pv, dof, _ = chi2_contingency(tab)
    print(f"  chi2 (state x market decile): chi2={chi2:.2f} dof={dof} p={pv:.2e}")
    chi2b, pvb = chi2_contingency(pd.crosstab(dm["mkt_q"], dm["is_B"]))[:2]
    print(f"  chi2 (is_B x market decile): chi2={chi2b:.2f} p={pvb:.4f}  "
          f"-> pB {'DOES' if pvb < 0.05 else 'does NOT'} vary with the market's total")

    D.write_json("s04_chemistry_dev.json", {
        "pair_attack": g.reset_index().to_dict("records"),
        "pair_defence": g2.reset_index().to_dict("records"),
        "market_decile": q.reset_index().to_dict("records"),
        "pB_spread_across_deciles": float(q["pB"].max() - q["pB"].min()),
        "pC_spread_across_deciles": float(q["pC"].max() - q["pC"].min()),
        "chi2_state_by_decile": {"chi2": float(chi2), "p": float(pv)},
        "chi2_isB_by_decile": {"chi2": float(chi2b), "p": float(pvb)},
    })
    print("\n[written] out/s04_*.json, out/totals_frozen_classes.json")


if __name__ == "__main__":
    main()
