"""Pre-match feature construction.  Every feature is strictly causal.

Rule enforced throughout: a feature attached to match t may only use matches
that had already *finished* before match t's batch started.  Rolling team
statistics are shifted by one within each team's own chronological sequence;
league-level sequence features are shifted by one batch, never one match, so
that simultaneous kickoffs cannot see each other.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

import lal_settlement as S

ELO_START = 1500.0
ELO_PROMOTED = 1400.0
ELO_K = 20.0
ELO_HFA = 60.0
ELO_CARRY = 0.75          # regression to league mean between seasons


def build_elo(m: pd.DataFrame) -> pd.DataFrame:
    """Rolling Elo from results alone.  Returns elo_h / elo_a as of kickoff."""
    m = m.sort_values(["kickoff_dt", "date", "home"], kind="mergesort").reset_index(drop=True)
    rating: dict[str, float] = {}
    seen_season: dict[str, str] = {}
    eh = np.zeros(len(m))
    ea = np.zeros(len(m))
    prev_season = None
    for i, r in enumerate(m.itertuples(index=False)):
        s = r.season
        if s != prev_season and prev_season is not None:
            mean = np.mean(list(rating.values())) if rating else ELO_START
            for k in rating:
                rating[k] = mean + ELO_CARRY * (rating[k] - mean)
            prev_season = s
        elif prev_season is None:
            prev_season = s
        for t in (r.home, r.away):
            if t not in rating:
                # a club appearing for the first time is a promoted side
                rating[t] = ELO_START if seen_season == {} else ELO_PROMOTED
                seen_season[t] = s
        rh, ra = rating[r.home], rating[r.away]
        eh[i], ea[i] = rh, ra
        exp_h = 1.0 / (1.0 + 10 ** (-(rh + ELO_HFA - ra) / 400.0))
        gd = abs(r.hg - r.ag)
        mult = 1.0 if gd <= 1 else (1.5 if gd == 2 else (1.75 + (gd - 3) / 8.0))
        score_h = 1.0 if r.hg > r.ag else (0.5 if r.hg == r.ag else 0.0)
        delta = ELO_K * mult * (score_h - exp_h)
        rating[r.home] = rh + delta
        rating[r.away] = ra - delta
    m["elo_h"] = eh
    m["elo_a"] = ea
    m["elo_diff"] = m["elo_h"] + ELO_HFA - m["elo_a"]
    m["elo_sum"] = m["elo_h"] + m["elo_a"]
    return m


def team_long(m: pd.DataFrame) -> pd.DataFrame:
    """Two rows per match, one per team, in chronological order."""
    a = m[["match_id", "season", "date", "kickoff_dt", "batch_id", "home", "away",
           "hg", "ag", "G", "G_ht", "state"]].copy()
    a["team"], a["opp"], a["venue"] = a["home"], a["away"], "H"
    a["gf"], a["ga"] = a["hg"], a["ag"]
    b = a.copy()
    b["team"], b["opp"], b["venue"] = a["away"], a["home"], "A"
    b["gf"], b["ga"] = a["ag"], a["hg"]
    tl = pd.concat([a, b], ignore_index=True)
    tl = tl.sort_values(["team", "kickoff_dt", "date"], kind="mergesort").reset_index(drop=True)
    return tl


def rolling_team_features(m: pd.DataFrame, windows=(6, 10, 20)) -> pd.DataFrame:
    """Team-level rolling form, shifted so match t never sees itself."""
    tl = team_long(m)
    g = tl.groupby("team", sort=False)
    tl["tm_idx"] = g.cumcount()                     # matches already played
    for w in windows:
        for col, name in [("gf", "gf"), ("ga", "ga"), ("G", "tg")]:
            tl[f"{name}_r{w}"] = (
                g[col].apply(lambda s: s.shift(1).rolling(w, min_periods=w).mean())
                .reset_index(level=0, drop=True))
    for w in windows:
        for st in ("A", "B", "C"):
            tl[f"p{st}_r{w}"] = (
                g["state"].apply(lambda s: (s == st).shift(1).rolling(w, min_periods=w).mean())
                .reset_index(level=0, drop=True))
    tl["gf_var_r10"] = (g["gf"].apply(lambda s: s.shift(1).rolling(10, min_periods=10).std())
                        .reset_index(level=0, drop=True))
    tl["tg_var_r10"] = (g["G"].apply(lambda s: s.shift(1).rolling(10, min_periods=10).std())
                        .reset_index(level=0, drop=True))
    tl["rest_days"] = (g["date"].diff().dt.days)

    # venue-specific form
    tl["_vkey"] = tl["team"] + "|" + tl["venue"]
    gv = tl.groupby("_vkey", sort=False)
    for col, name in [("gf", "gf"), ("ga", "ga"), ("G", "tg")]:
        tl[f"{name}_v8"] = (gv[col].apply(lambda s: s.shift(1).rolling(8, min_periods=8).mean())
                            .reset_index(level=0, drop=True))

    feat_cols = [c for c in tl.columns if any(
        c.startswith(p) for p in ("gf_", "ga_", "tg_", "pA_", "pB_", "pC_"))] + \
        ["tm_idx", "rest_days"]

    h = tl[tl["venue"] == "H"][["match_id"] + feat_cols].add_suffix("_h").rename(
        columns={"match_id_h": "match_id"})
    a = tl[tl["venue"] == "A"][["match_id"] + feat_cols].add_suffix("_a").rename(
        columns={"match_id_a": "match_id"})
    out = m.merge(h, on="match_id", how="left").merge(a, on="match_id", how="left")
    return out


def market_features(m: pd.DataFrame, devig="proportional") -> pd.DataFrame:
    """No-vig market probabilities and the derived market expectations."""
    m = m.copy()
    ok = m["O25_PRI"].notna() & m["U25_PRI"].notna()
    pc = np.full(len(m), np.nan)
    q_o, q_u = S.devig_two_way(m.loc[ok, "O25_PRI"].values,
                               m.loc[ok, "U25_PRI"].values, devig)
    pc[ok.values] = np.ravel(q_o)
    m["mkt_pC"] = pc                       # market P(G>=3), margin removed

    ok3 = m["H_B365"].notna() & m["D_B365"].notna() & m["A_B365"].notna()
    q = np.column_stack([1 / m["H_B365"], 1 / m["D_B365"], 1 / m["A_B365"]])
    s = q.sum(axis=1, keepdims=True)
    p3 = np.where(ok3.values[:, None], q / s, np.nan)
    m["mkt_pH"], m["mkt_pD"], m["mkt_pA_win"] = p3[:, 0], p3[:, 1], p3[:, 2]
    m["mkt_fav_edge"] = np.abs(m["mkt_pH"] - m["mkt_pA_win"])
    m["mkt_dominance"] = np.maximum(m["mkt_pH"], m["mkt_pA_win"])
    m["mkt_draw"] = m["mkt_pD"]
    m["ah_supremacy"] = -m["ah_line"]      # positive = home expected to win by

    # market's implied goal expectation, inverted from pC under a Poisson map
    m["mkt_lambda"] = _lambda_from_pC(m["mkt_pC"].values)

    # market residual on the finished match (used only as a LAGGED feature)
    m["mkt_resid"] = m["is_C"] - m["mkt_pC"]
    return m


def _lambda_from_pC(pc, lo=0.2, hi=8.0, iters=60):
    """Invert P(Poisson(lam) >= 3) = pC by bisection."""
    from scipy.stats import poisson
    pc = np.asarray(pc, float)
    lo = np.full(pc.shape, lo)
    hi = np.full(pc.shape, hi)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        val = 1.0 - poisson.cdf(2, mid)
        too_low = val < pc
        lo = np.where(too_low, mid, lo)
        hi = np.where(too_low, hi, mid)
    out = 0.5 * (lo + hi)
    return np.where(np.isnan(pc), np.nan, out)


def sequence_features(m: pd.DataFrame, ks=(1, 2, 3, 5, 10)) -> pd.DataFrame:
    """League-level chronological state features, lagged by whole batches.

    A match may only see batches that closed strictly before its own batch,
    so simultaneous kickoffs never inform one another.
    """
    m = m.sort_values(["kickoff_dt", "date", "home"], kind="mergesort").reset_index(drop=True)
    out = m.copy()

    # per-season league sequence
    parts = []
    for season, d in m.groupby("season", sort=False):
        d = d.copy()
        # batch-level aggregates, then shifted onto the *next* batch
        bag = d.groupby("batch_id", sort=True).agg(
            bA=("is_A", "mean"), bB=("is_B", "mean"), bC=("is_C", "mean"),
            bG=("G", "mean"), bn=("G", "size"),
            bresid=("mkt_resid", "mean")).reset_index()
        for k in ks:
            bag[f"seqC_{k}"] = bag["bC"].shift(1).rolling(k, min_periods=k).mean()
            bag[f"seqB_{k}"] = bag["bB"].shift(1).rolling(k, min_periods=k).mean()
            bag[f"seqA_{k}"] = bag["bA"].shift(1).rolling(k, min_periods=k).mean()
            bag[f"seqG_{k}"] = bag["bG"].shift(1).rolling(k, min_periods=k).mean()
            bag[f"seqR_{k}"] = bag["bresid"].shift(1).rolling(k, min_periods=k).mean()
        # last completed match of the league (previous batch, last listed match)
        last = d.groupby("batch_id", sort=True)["state"].last().shift(1)
        bag["prev_state"] = bag["batch_id"].map(last)
        parts.append(bag.assign(season=season))
    seq = pd.concat(parts, ignore_index=True)
    out = out.merge(seq.drop(columns=["bA", "bB", "bC", "bG", "bn", "bresid"]),
                    on=["season", "batch_id"], how="left")

    # per-team sequence: state of that team's previous match
    tl = team_long(m).sort_values(["team", "kickoff_dt", "date"], kind="mergesort")
    tl["prev_team_state"] = tl.groupby("team")["state"].shift(1)
    tl["prev_team_G"] = tl.groupby("team")["G"].shift(1)
    # length of the team's current run of consecutive C matches, as of kickoff
    isC = (tl["state"] == "C").astype(int)
    prevC = isC.groupby(tl["team"]).shift(1)
    grp = (prevC != prevC.groupby(tl["team"]).shift(1)).groupby(tl["team"]).cumsum()
    tl["team_C_streak"] = (prevC.groupby([tl["team"], grp]).cumsum() * prevC).fillna(0)
    isA = (tl["state"] == "A").astype(int)
    prevA = isA.groupby(tl["team"]).shift(1)
    grpA = (prevA != prevA.groupby(tl["team"]).shift(1)).groupby(tl["team"]).cumsum()
    tl["team_A_streak"] = (prevA.groupby([tl["team"], grpA]).cumsum() * prevA).fillna(0)

    # Half-by-half goals of each team's PREVIOUS league match, within the same
    # season.  Needed by the user-supplied half-pattern strategies.
    tl["_G1"] = pd.to_numeric(tl["G_ht"], errors="coerce").astype(float)
    tl["_G2"] = (pd.to_numeric(tl["G"], errors="coerce")
                 - pd.to_numeric(tl["G_ht"], errors="coerce")).astype(float)
    g2 = tl.groupby(["team", "season"], sort=False)
    tl["prev_G1"] = g2["_G1"].shift(1)
    tl["prev_G2"] = g2["_G2"].shift(1)

    cols = ["match_id", "prev_team_state", "prev_team_G", "team_C_streak",
            "team_A_streak", "prev_G1", "prev_G2"]
    h = tl[tl["venue"] == "H"][cols].rename(columns={
        "prev_team_state": "prev_state_h", "prev_team_G": "prev_G_h",
        "team_C_streak": "C_streak_h", "team_A_streak": "A_streak_h",
        "prev_G1": "prev_G1_h", "prev_G2": "prev_G2_h"})
    a = tl[tl["venue"] == "A"][cols].rename(columns={
        "prev_team_state": "prev_state_a", "prev_team_G": "prev_G_a",
        "team_C_streak": "C_streak_a", "team_A_streak": "A_streak_a",
        "prev_G1": "prev_G1_a", "prev_G2": "prev_G2_a"})
    out = out.merge(h, on="match_id", how="left").merge(a, on="match_id", how="left")
    return out


MATCH_MINUTES = 105          # 90 + stoppage; a match is "completed" after this


def last_completed_features(m: pd.DataFrame) -> pd.DataFrame:
    """Second-half goals of the league's last COMPLETED match before kickoff.

    A match counts as finished MATCH_MINUTES after its own kickoff.  When
    several matches tie for "last completed" (identical kickoff), no order
    exists between them, so the flag is set only if ALL of them satisfy the
    condition -- deterministic, and never invents an order.

    Seasons without a kickoff time collapse to one timestamp per day, which
    makes "the last completed match" undefined; ``prev_done_known`` is False
    there and the strategies that need it must skip those seasons.
    """
    m = m.sort_values(["kickoff_dt", "date", "home"], kind="mergesort").reset_index(drop=True)
    out_g2 = np.full(len(m), np.nan)
    out_n = np.zeros(len(m), dtype=int)
    known = np.zeros(len(m), dtype=bool)

    for season, d in m.groupby("season", sort=False):
        idx = d.index.values
        ko = d["kickoff_dt"].values.astype("datetime64[m]").astype(np.int64)
        g2 = (d["G"] - d["G_ht"]).values.astype(float)
        has_t = d["has_kickoff"].values
        order = np.argsort(ko, kind="mergesort")
        ko_s, g2_s, idx_s = ko[order], g2[order], idx[order]
        for pos in range(len(ko_s)):
            thresh = ko_s[pos] - MATCH_MINUTES
            k = np.searchsorted(ko_s, thresh, side="right")
            if k == 0:
                continue
            last_ko = ko_s[k - 1]
            tied = g2_s[:k][ko_s[:k] == last_ko]
            i = idx_s[pos]
            out_n[i] = len(tied)
            # condition holds only if every tied match had an empty second half
            out_g2[i] = 0.0 if np.all(tied == 0) else float(np.max(tied))
            known[i] = bool(has_t[order][pos])
    m["prev_done_G2"] = out_g2
    m["prev_done_n"] = out_n
    m["prev_done_known"] = known
    return m


def build_all(m: pd.DataFrame) -> pd.DataFrame:
    m = build_elo(m)
    m = rolling_team_features(m)
    m = market_features(m)
    m = sequence_features(m)
    m = last_completed_features(m)
    return m
