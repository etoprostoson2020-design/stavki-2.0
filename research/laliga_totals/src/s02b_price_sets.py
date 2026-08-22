"""Stage 2b -- what every available price set says, and what closing prices do to it.

The single most important question the real data can answer that the earlier
proxy could not: does the market's over-statement of pC survive the CLOSING
line?  An edge that lives only on pre-match prices is a stale-quote artefact.
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

SETS = {
    "market_avg_prematch  [PRIMARY]": ("OV25", "UN25"),
    "market_max_prematch":            ("OV25_MAX", "UN25_MAX"),
    "bet365_prematch":                ("OV25_B365", "UN25_B365"),
    "market_avg_closing":             ("OV25_C", "UN25_C"),
    "pinnacle_closing    [SHARP]":    ("OV25_PC", "UN25_PC"),
    "market_max_closing":             ("OV25_MAXC", "UN25_MAXC"),
    "betfair_exchange":               ("OV25_BFE", "UN25_BFE"),
}


def rows_for(d: pd.DataFrame, label: str, o: str, u: str) -> dict | None:
    sub = d[d[o].notna() & d[u].notna()]
    if len(sub) < 50:
        return None
    q_o, _ = S.devig_two_way(sub[o].values, sub[u].values, "proportional")
    mkt_pC = float(np.mean(np.ravel(q_o)))
    real_pC = float(sub["is_C"].mean())
    ovr = float((1 / sub[o] + 1 / sub[u]).mean())
    roi_o = float(S.settle("OVER_2.5", sub[o].values, sub["state"].values).mean())
    roi_u = float(S.settle("UNDER_2.5", sub[u].values, sub["state"].values).mean())
    return {"price_set": label, "n": len(sub), "seasons": sub["season"].nunique(),
            "overround": round(ovr, 4), "vig_side_%": round(100 * (ovr - 1) / 2, 2),
            "mkt_pC": round(mkt_pC, 4), "real_pC": round(real_pC, 4),
            "bias": round(mkt_pC - real_pC, 4),
            "roi_OVER_%": round(100 * roi_o, 2), "roi_UNDER_%": round(100 * roi_u, 2)}


def main():
    m = D.build_master()
    dev = m[m["block"] == "dev"]

    print("=== PRICE SETS ON DEVELOPMENT (2016/17-2021/22) ===\n")
    rows = [r for lbl, (o, u) in SETS.items() if (r := rows_for(dev, lbl, o, u))]
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))

    print("\n=== SAME COMPARISON, RESTRICTED TO SEASONS WHERE CLOSING EXISTS ===")
    print("    (2019/20-2021/22 -- the only like-for-like window on development)\n")
    dev2 = dev[dev["OV25_PC"].notna()]
    rows2 = [r for lbl, (o, u) in SETS.items() if (r := rows_for(dev2, lbl, o, u))]
    t2 = pd.DataFrame(rows2)
    print(t2.to_string(index=False))

    # ---- the decisive contrast -------------------------------------------
    print("\n=== PRE-MATCH vs CLOSING, MATCHED PAIRS ===\n")
    pair = dev[dev["OV25"].notna() & dev["OV25_C"].notna()].copy()
    pair["drift_over"] = pair["OV25_C"] / pair["OV25"] - 1
    pair["drift_under"] = pair["UN25_C"] / pair["UN25"] - 1
    qa, _ = S.devig_two_way(pair["OV25"].values, pair["UN25"].values, "proportional")
    qc, _ = S.devig_two_way(pair["OV25_C"].values, pair["UN25_C"].values, "proportional")
    pair["pC_pre"] = np.ravel(qa)
    pair["pC_close"] = np.ravel(qc)
    print(f"  matched matches: {len(pair)}  (seasons {sorted(pair['season'].unique())})")
    print(f"  mean de-vigged pC pre-match : {pair['pC_pre'].mean():.4f}")
    print(f"  mean de-vigged pC closing   : {pair['pC_close'].mean():.4f}")
    print(f"  realised pC                 : {pair['is_C'].mean():.4f}")
    print(f"  bias pre-match : {pair['pC_pre'].mean() - pair['is_C'].mean():+.4f}")
    print(f"  bias closing   : {pair['pC_close'].mean() - pair['is_C'].mean():+.4f}")
    print(f"  mean line move on the over : {100*pair['drift_over'].mean():+.2f}% of price")
    print(f"  mean line move on the under: {100*pair['drift_under'].mean():+.2f}% of price")

    # does the closing line know something the pre-match line does not?
    from sklearn.linear_model import LogisticRegression
    X = np.column_stack([pair["pC_pre"].values, pair["pC_close"].values])
    y = pair["is_C"].values
    lr = LogisticRegression(max_iter=1000).fit(X, y)
    print(f"\n  logit(is_C) ~ pC_pre + pC_close  ->  coef pre = {lr.coef_[0][0]:+.3f}, "
          f"coef close = {lr.coef_[0][1]:+.3f}")
    print("  (the larger coefficient is the price that actually carries the information)")

    # ---- season-by-season bias under each price set ------------------------
    print("\n=== SEASON-BY-SEASON pC BIAS (market avg pre-match vs Pinnacle closing) ===\n")
    srows = []
    for s in D.DEV_SEASONS:
        d = dev[dev["season"] == s]
        r = {"season": s, "n": len(d), "real_pC": round(float(d["is_C"].mean()), 4)}
        for lbl, (o, u) in [("pre", ("OV25", "UN25")), ("close", ("OV25_PC", "UN25_PC"))]:
            sub = d[d[o].notna() & d[u].notna()]
            if len(sub) < 50:
                r[f"bias_{lbl}"] = None
                r[f"roiU_{lbl}"] = None
                continue
            q, _ = S.devig_two_way(sub[o].values, sub[u].values, "proportional")
            r[f"bias_{lbl}"] = round(float(np.mean(np.ravel(q))) - float(sub["is_C"].mean()), 4)
            r[f"roiU_{lbl}"] = round(100 * float(
                S.settle("UNDER_2.5", sub[u].values, sub["state"].values).mean()), 2)
        srows.append(r)
    st = pd.DataFrame(srows)
    print(st.to_string(index=False))

    D.write_json("s02b_price_sets.json", {
        "development_all_seasons": t.to_dict("records"),
        "development_closing_window": t2.to_dict("records"),
        "prematch_vs_closing": {
            "n": int(len(pair)),
            "pC_pre": float(pair["pC_pre"].mean()),
            "pC_close": float(pair["pC_close"].mean()),
            "realised": float(pair["is_C"].mean()),
            "bias_pre": float(pair["pC_pre"].mean() - pair["is_C"].mean()),
            "bias_close": float(pair["pC_close"].mean() - pair["is_C"].mean()),
            "coef_pre": float(lr.coef_[0][0]), "coef_close": float(lr.coef_[0][1]),
        },
        "by_season": st.to_dict("records"),
    })
    print("\n[written] out/s02b_price_sets.json")


if __name__ == "__main__":
    main()
