"""Segment evaluation: probabilities, fair prices, real-price economics."""
from __future__ import annotations
import numpy as np
import pandas as pd

import lal_settlement as S


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def segment_stats(d: pd.DataFrame, price_over="O25_B365", price_under="U25_B365") -> dict:
    """Everything the decision matrix needs for one segment."""
    n = len(d)
    if n == 0:
        return {"n": 0}
    pA, pB, pC = d["is_A"].mean(), d["is_B"].mean(), d["is_C"].mean()
    f = S.fair_odds(pA, pB, pC)
    out = {
        "n": int(n),
        "pA": float(pA), "pB": float(pB), "pC": float(pC),
        "pC_ci": [round(x, 4) for x in wilson(d["is_C"].sum(), n)],
        "pB_ci": [round(x, 4) for x in wilson(d["is_B"].sum(), n)],
        "mean_goals": float(d["G"].mean()),
        "fair": {k: float(f[k]) for k in S.MARKETS},
    }

    pr = d[d[price_over].notna() & d[price_under].notna()]
    out["priced_n"] = int(len(pr))
    out["priced_availability"] = float(len(pr) / n)
    if len(pr) == 0:
        return out

    # realised economics on the two markets that actually have prices
    econ = {}
    for mk, col in [("OVER_2.5", price_over), ("UNDER_2.5", price_under)]:
        pl = S.settle(mk, pr[col].values, pr["state"].values)
        econ[mk] = {
            "n": int(len(pl)), "mean_price": float(pr[col].mean()),
            "pnl": float(pl.sum()), "roi": float(pl.mean()),
            "roi_hc2": float(S.settle(mk, pr[col].values * 0.98, pr["state"].values).mean()),
            "roi_hc5": float(S.settle(mk, pr[col].values * 0.95, pr["state"].values).mean()),
            "hit": float((pl > 0).mean()),
        }
    out["realised_2p5"] = econ

    # what the market thought, vs what happened
    out["mkt_pC_mean"] = float(pr["mkt_pC"].mean())
    out["mkt_pC_bias"] = float(pr["mkt_pC"].mean() - pC)
    out["mean_overround"] = float((1 / pr[price_over] + 1 / pr[price_under]).mean())

    # implied 2.0 prices a fair book would have had to offer, and the price the
    # 2.5 book actually implies for the same side
    out["implied_2p0_from_book"] = _implied_2p0(pr, price_over, price_under, pB)
    return out


def _implied_2p0(pr: pd.DataFrame, po: str, pu: str, pB: float) -> dict:
    """Translate the observed 2.5 book into the 2.0 price it is consistent with.

    A book that offers o25 on the over, and believes P(B)=pB, is indifferent at
        o20_over  = o25 - pB / pC        (same EV, push instead of loss)
        o20_under = ((pA+pB) o25 - pB) / pA
    Using the book's own de-vigged pC and the segment's realised pB split.
    """
    pc = pr["mkt_pC"].values
    o_over = pr[po].values
    o_under = pr[pu].values
    pA_mkt = (1 - pc) * (1 - pB / (1 - pc + 1e-12))   # not identified; see note
    ov, un = S.breakeven_2p0_vs_2p5(
        np.full_like(pc, np.nan), np.full_like(pc, pB), pc, o_over)
    # over side needs only pB and pC
    over_equiv = o_over - pB / pc
    # under side needs pA = 1 - pB - pC
    pA_hat = np.clip(1 - pB - pc, 1e-6, None)
    under_equiv = ((pA_hat + pB) * o_under - pB) / pA_hat
    return {
        "mean_o25_over": float(np.mean(o_over)),
        "mean_equivalent_o20_over": float(np.mean(over_equiv)),
        "mean_u25_under": float(np.mean(o_under)),
        "mean_equivalent_u20_under": float(np.mean(under_equiv)),
        "note": "the 2.0 price at which the punter is indifferent to the "
                "observed 2.5 price; NOT a quote that was ever offered",
    }


def by_season(d: pd.DataFrame, price_over="O25_B365", price_under="U25_B365") -> pd.DataFrame:
    rows = []
    for s, g in d.groupby("season"):
        pr = g[g[price_over].notna()]
        r = {"season": s, "n": len(g), "pA": g["is_A"].mean(), "pB": g["is_B"].mean(),
             "pC": g["is_C"].mean(), "priced": len(pr)}
        if len(pr):
            r["roi_O25"] = S.settle("OVER_2.5", pr[price_over].values, pr["state"].values).mean()
            r["roi_U25"] = S.settle("UNDER_2.5", pr[price_under].values, pr["state"].values).mean()
        rows.append(r)
    return pd.DataFrame(rows)
