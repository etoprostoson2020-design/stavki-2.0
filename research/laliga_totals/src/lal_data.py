"""
Data layer for the La Liga totals study.

Two independent mirrors of football-data.co.uk are reconciled here:

  RESULTS  (10 seasons, 2016/17..2025/26) -- datasets/football-datasets
  ODDS     ( 9 seasons, 2016/17..2024/25) -- xgabora/Club-Football-Match-Data

The results mirror is authoritative for match outcomes; the odds mirror
contributes prices only.  Season 2025/26 therefore has no prices at all,
which is the single most important limitation of the whole study.

The 6+2+2 protocol is enforced mechanically: ``load()`` refuses to hand back
validation or holdout rows unless the caller passes an explicit unlock token.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)

DEV_SEASONS = ["2016-17", "2017-18", "2018-19", "2019-20", "2020-21", "2021-22"]
VAL_SEASONS = ["2022-23", "2023-24"]
TEST_SEASONS = ["2024-25", "2025-26"]
ALL_SEASONS = DEV_SEASONS + VAL_SEASONS + TEST_SEASONS

SEASON_TAG = {s: s.replace("-", "")[2:] + s.split("-")[1] for s in ALL_SEASONS}

# Explicit, named price benchmark. Chosen before any result was inspected.
# football-data.co.uk ships B365>2.5 / B365<2.5 as a PRE-MATCH quote, not a
# closing quote; the closing columns (B365C) are absent from this mirror.
PRIMARY_PRICE = ("O25_B365", "U25_B365")
ROBUSTNESS_PRICE = ("O25_MAX", "U25_MAX")


class ProtocolError(PermissionError):
    """Raised when a closed block is requested without an explicit unlock."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_registry() -> list[dict]:
    """SHA-256 registry of every raw input actually present on disk."""
    rows = []
    for p in sorted(RAW.glob("*.csv")):
        rows.append(
            {
                "file": p.name,
                "bytes": p.stat().st_size,
                "sha256": sha256(p),
                "role": "odds" if "xgabora" in p.name else "results",
            }
        )
    return rows


def _season_of(date: pd.Timestamp) -> str:
    """La Liga season label from a kickoff date (season starts in July)."""
    y = date.year if date.month >= 7 else date.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def _load_results() -> pd.DataFrame:
    frames = []
    for s in ALL_SEASONS:
        tag = s[2:4] + s[5:7]
        f = RAW / f"fd_la-liga_season-{tag}.csv"
        d = pd.read_csv(f)
        d["season"] = s
        d["src_file"] = f.name
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["Date"], format="%Y-%m-%d")
    df = df.rename(
        columns={
            "HomeTeam": "home",
            "AwayTeam": "away",
            "FTHG": "hg",
            "FTAG": "ag",
            "HTHG": "hg_ht",
            "HTAG": "ag_ht",
            "HS": "sh_h", "AS": "sh_a", "HST": "sot_h", "AST": "sot_a",
            "HC": "cor_h", "AC": "cor_a", "HR": "red_h", "AR": "red_a",
        }
    )
    keep = ["season", "date", "home", "away", "hg", "ag", "hg_ht", "ag_ht",
            "sh_h", "sh_a", "sot_h", "sot_a", "cor_h", "cor_a", "red_h", "red_a",
            "src_file"]
    return df[keep]


def _load_odds() -> pd.DataFrame:
    d = pd.read_csv(RAW / "xgabora_SP1.csv")
    d["date"] = pd.to_datetime(d["MatchDate"], format="%Y-%m-%d")
    d = d.rename(
        columns={
            "HomeTeam": "home", "AwayTeam": "away", "MatchTime": "kickoff",
            "OddHome": "H_B365", "OddDraw": "D_B365", "OddAway": "A_B365",
            "MaxHome": "H_MAX", "MaxDraw": "D_MAX", "MaxAway": "A_MAX",
            "Over25": "O25_B365", "Under25": "U25_B365",
            "MaxOver25": "O25_MAX", "MaxUnder25": "U25_MAX",
            "HandiSize": "ah_line", "HandiHome": "ah_home", "HandiAway": "ah_away",
            "HomeElo": "elo_h_src", "AwayElo": "elo_a_src",
        }
    )
    keep = ["date", "home", "away", "kickoff",
            "H_B365", "D_B365", "A_B365", "H_MAX", "D_MAX", "A_MAX",
            "O25_B365", "U25_B365", "O25_MAX", "U25_MAX",
            "ah_line", "ah_home", "ah_away", "elo_h_src", "elo_a_src",
            "FTHome", "FTAway"]
    return d[keep]


def build_master() -> pd.DataFrame:
    """Reconcile the two mirrors into one match table."""
    res = _load_results()
    od = _load_odds()

    merged = res.merge(
        od, on=["date", "home", "away"], how="left", validate="one_to_one",
        indicator=True,
    )

    # Cross-source integrity: where both mirrors carry the score they must agree.
    both = merged["_merge"] == "both"
    disagree = both & (
        (merged["hg"] != merged["FTHome"]) | (merged["ag"] != merged["FTAway"])
    )
    merged["score_conflict"] = disagree
    merged = merged.drop(columns=["FTHome", "FTAway"])
    merged["has_odds"] = merged["_merge"] == "both"
    merged = merged.drop(columns=["_merge"])

    m = merged
    m["G"] = m["hg"] + m["ag"]
    m["G_ht"] = m["hg_ht"] + m["ag_ht"]
    m["G_2h"] = m["G"] - m["G_ht"]

    # The three mutually exclusive settlement states.
    m["state"] = np.where(m["G"] <= 1, "A", np.where(m["G"] == 2, "B", "C"))
    m["is_A"] = (m["state"] == "A").astype(int)
    m["is_B"] = (m["state"] == "B").astype(int)
    m["is_C"] = (m["state"] == "C").astype(int)

    m["block"] = np.select(
        [m["season"].isin(DEV_SEASONS), m["season"].isin(VAL_SEASONS)],
        ["dev", "val"], default="test",
    )
    m["has_kickoff"] = m["kickoff"].notna() & (m["kickoff"].astype(str) != "")

    # Chronological order. Matches sharing a date (and, where known, a kickoff
    # time) form one simultaneous batch; no order is invented inside a batch.
    m["kickoff_dt"] = pd.to_datetime(
        m["date"].dt.strftime("%Y-%m-%d") + " " + m["kickoff"].fillna("00:00:00"),
        errors="coerce",
    )
    m = m.sort_values(["kickoff_dt", "date", "home"], kind="mergesort").reset_index(drop=True)
    # batch = set of matches that must be decided before any of them resolves
    m["batch_key"] = np.where(
        m["has_kickoff"],
        m["kickoff_dt"].dt.strftime("%Y-%m-%d %H:%M"),
        m["date"].dt.strftime("%Y-%m-%d") + " ALLDAY",
    )
    m["batch_id"] = pd.factorize(m["batch_key"])[0]
    m["match_id"] = (
        m["season"] + "|" + m["date"].dt.strftime("%Y%m%d") + "|" + m["home"] + "|" + m["away"]
    )
    return m


_CACHE: dict[str, pd.DataFrame] = {}


def load(block: str = "dev", unlock: str | None = None, schema_only: bool = False) -> pd.DataFrame:
    """Return matches for one block.

    ``block`` is one of ``dev``, ``val``, ``test``, ``all``.  Anything beyond
    ``dev`` requires ``unlock`` to match the stage token, so that opening a
    closed block is always a deliberate act recorded in the code.
    """
    if "master" not in _CACHE:
        _CACHE["master"] = build_master()
    m = _CACHE["master"]

    tokens = {"val": "VALIDATION_RUN_ONCE", "test": "HOLDOUT_RUN_ONCE", "all": "FINAL_REPORT"}
    if block in tokens and unlock != tokens[block] and not schema_only:
        raise ProtocolError(
            f"block '{block}' is closed; pass unlock='{tokens[block]}' only when the "
            "development stage is frozen"
        )
    if block == "all":
        out = m
    else:
        out = m[m["block"] == block]
    if schema_only and block != "dev":
        # Schema inspection only: outcomes and prices are blanked out.
        out = out.copy()
        for c in ["hg", "ag", "hg_ht", "ag_ht", "G", "G_ht", "G_2h", "state",
                  "is_A", "is_B", "is_C", "O25_B365", "U25_B365", "O25_MAX", "U25_MAX"]:
            out[c] = np.nan
    return out.copy().reset_index(drop=True)


def write_json(name: str, obj) -> Path:
    p = OUT / name
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=_default))
    return p


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not serialisable: {type(o)}")
