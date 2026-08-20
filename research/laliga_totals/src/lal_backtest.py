"""Flat-stake backtest engine with a complete decision journal.

Rules, fixed for every candidate:
  * pre-match decisions only; the selector sees nothing from its own match
  * 1 unit flat on the chosen market; never more than one main bet per match
  * simultaneous kickoffs are decided as one batch before any of them resolves
  * no chasing: a past loss never changes the next stake
  * a push returns exactly the stake and is not a win
  * every skip is journalled with its reason
  * no manual exclusion of losing matches, ever
"""
from __future__ import annotations
import numpy as np
import pandas as pd

import lal_settlement as S

PRICE_COL = {"OVER_2.5": "O25_B365", "UNDER_2.5": "U25_B365"}
PRICE_COL_MAX = {"OVER_2.5": "O25_MAX", "UNDER_2.5": "U25_MAX"}


def run(d: pd.DataFrame, decide, price_map=PRICE_COL, haircut=0.0,
        candidate_id="") -> pd.DataFrame:
    """``decide(row) -> (market, min_price, reason)`` with market None = skip."""
    recs = []
    for r in d.sort_values(["kickoff_dt", "date", "home"]).itertuples(index=False):
        market, min_price, reason = decide(r)
        rec = {"candidate": candidate_id, "match_id": r.match_id, "season": r.season,
               "date": r.date, "batch_id": r.batch_id, "home": r.home, "away": r.away,
               "G": r.G, "state": r.state, "decision": market or "NO_BET",
               "reason": reason, "price": np.nan, "min_price": min_price,
               "stake": 0.0, "pnl": 0.0, "result": "SKIP"}
        if market is None:
            recs.append(rec)
            continue
        col = price_map[market]
        price = getattr(r, col, np.nan)
        if price is None or (isinstance(price, float) and np.isnan(price)):
            rec["reason"] = "NO_PRICE"
            recs.append(rec)
            continue
        price = float(price) * (1.0 - haircut)
        if min_price is not None and price < min_price:
            rec["decision"] = "NO_BET"
            rec["reason"] = f"PRICE_BELOW_MIN({price:.3f}<{min_price:.3f})"
            rec["price"] = price
            recs.append(rec)
            continue
        pnl = float(S.settle(market, np.array([price]), np.array([r.state]))[0])
        rec.update(price=price, stake=1.0, pnl=pnl,
                   result="PUSH" if pnl == 0.0 else ("WIN" if pnl > 0 else "LOSS"))
        recs.append(rec)
    return pd.DataFrame(recs)


def summarise(led: pd.DataFrame) -> dict:
    bets = led[led["stake"] > 0]
    eligible = led[led["decision"] != "NO_BET"]
    n = len(bets)
    if n == 0:
        return {"bets": 0, "eligible": int(len(eligible)), "roi": np.nan, "pnl": 0.0}
    pnl = bets["pnl"].values
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))
    dd = float((peak[1:] - cum).max())
    losses = (bets["result"] == "LOSS").astype(int).values
    streak = mx = 0
    for x in losses:
        streak = streak + 1 if x else 0
        mx = max(mx, streak)
    by_season = bets.groupby("season")["pnl"].agg(["size", "sum"])
    gross_pos = by_season[by_season["sum"] > 0]["sum"].sum()
    team_pnl = pd.concat([
        bets.groupby("home")["pnl"].sum(), bets.groupby("away")["pnl"].sum()
    ], axis=1).sum(axis=1)
    team_gross_pos = team_pnl[team_pnl > 0].sum()
    return {
        "bets": int(n),
        "eligible": int(len(led)),
        "priced_availability": float(n / max(len(eligible), 1)),
        "wins": int((bets["result"] == "WIN").sum()),
        "pushes": int((bets["result"] == "PUSH").sum()),
        "losses": int((bets["result"] == "LOSS").sum()),
        "turnover": float(n),
        "pnl": float(pnl.sum()),
        "roi": float(pnl.mean()),
        "mean_price": float(bets["price"].mean()),
        "max_drawdown": dd,
        "max_drawdown_pct_turnover": float(dd / n),
        "max_losing_streak": int(mx),
        "seasons_with_bets": int(by_season.shape[0]),
        "positive_seasons": int((by_season["sum"] > 0).sum()),
        "max_season_share_of_gross_positive": float(
            by_season[by_season["sum"] > 0]["sum"].max() / gross_pos) if gross_pos > 0 else np.nan,
        "max_team_share_of_gross_positive": float(
            team_pnl.max() / team_gross_pos) if team_gross_pos > 0 else np.nan,
        "by_season": by_season.reset_index().to_dict("records"),
    }


def bootstrap_roi(led: pd.DataFrame, n=4000, seed=1) -> tuple[float, float]:
    bets = led[led["stake"] > 0]
    if len(bets) < 20:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    # resample whole batches so simultaneous decisions stay together
    groups = [g["pnl"].values for _, g in bets.groupby("batch_id")]
    k = len(groups)
    out = np.empty(n)
    for t in range(n):
        pick = rng.integers(0, k, size=k)
        out[t] = np.concatenate([groups[i] for i in pick]).mean()
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))
