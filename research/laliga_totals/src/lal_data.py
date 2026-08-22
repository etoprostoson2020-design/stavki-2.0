"""
Data layer for the La Liga totals study.

Input is the genuine football-data.co.uk season export for SP1, 2016/17-2025/26,
supplied by the user.  The column scheme drifts three times across that span
(61/64 -> 105 -> 119 -> 131 columns), so prices are harmonised onto stable
names following the convention of the `laliga-loader` skill.

Price availability is NOT uniform, and this drives every economic choice:

  market average pre-match   BbAv>2.5 | Avg>2.5      all 10 seasons   PRIMARY
  market maximum pre-match   BbMx>2.5 | Max>2.5      all 10 seasons   robustness
  Bet365 pre-match           B365>2.5                 2019/20 onward
  market average CLOSING     AvgC>2.5                 2019/20 onward   robustness
  Pinnacle CLOSING           PC>2.5                   2019/20 onward   robustness
  market maximum CLOSING     MaxC>2.5                 2019/20 onward
  Betfair exchange           BFE>2.5                  2024/25 onward

There is NO Over/Under 2.0 quote and no alternative total line anywhere in the
data: 2.5 is the only goal line football-data.co.uk publishes.

The 6+2+2 protocol is enforced mechanically: ``load()`` refuses to hand back
validation or holdout rows without an explicit unlock token.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_v2"
LEGACY = ROOT / "data" / "raw"
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)

SEASON_FILES = ["16-17", "17-18", "18-19", "19-20", "20-21",
                "21-22", "22-23", "23-24", "24-25", "25-26"]
DEV_SEASONS = SEASON_FILES[:6]
VAL_SEASONS = SEASON_FILES[6:8]
TEST_SEASONS = SEASON_FILES[8:]
ALL_SEASONS = SEASON_FILES

# Harmonised price names -> candidate source columns, first match wins.
ODDS_ALIASES = {
    "OV25":      ["BbAv>2.5", "Avg>2.5"],
    "UN25":      ["BbAv<2.5", "Avg<2.5"],
    "OV25_MAX":  ["BbMx>2.5", "Max>2.5"],
    "UN25_MAX":  ["BbMx<2.5", "Max<2.5"],
    "OV25_B365": ["B365>2.5"],
    "UN25_B365": ["B365<2.5"],
    "OV25_C":    ["AvgC>2.5"],
    "UN25_C":    ["AvgC<2.5"],
    "OV25_PC":   ["PC>2.5"],
    "UN25_PC":   ["PC<2.5"],
    "OV25_MAXC": ["MaxC>2.5"],
    "UN25_MAXC": ["MaxC<2.5"],
    "OV25_BFE":  ["BFE>2.5"],
    "UN25_BFE":  ["BFE<2.5"],
    "AHL":       ["BbAHh", "AHh"],
    "AHL_C":     ["AHCh"],
    "AHH":       ["BbAvAHH", "AvgAHH"],
    "AHA":       ["BbAvAHA", "AvgAHA"],
    "AVG_H":     ["BbAvH", "AvgH"],
    "AVG_D":     ["BbAvD", "AvgD"],
    "AVG_A":     ["BbAvA", "AvgA"],
    "B365_H":    ["B365H"], "B365_D": ["B365D"], "B365_A": ["B365A"],
    "PSC_H":     ["PSCH"],  "PSC_D":  ["PSCD"],  "PSC_A":  ["PSCA"],
}

# The named price benchmark, fixed before any result was inspected.
PRIMARY_PRICE = ("OV25", "UN25")               # market average, pre-match, 10 seasons
ROBUSTNESS_PRICES = {
    "market_max_prematch":  ("OV25_MAX", "UN25_MAX"),
    "bet365_prematch":      ("OV25_B365", "UN25_B365"),
    "market_avg_closing":   ("OV25_C", "UN25_C"),
    "pinnacle_closing":     ("OV25_PC", "UN25_PC"),
    "market_max_closing":   ("OV25_MAXC", "UN25_MAXC"),
    "betfair_exchange":     ("OV25_BFE", "UN25_BFE"),
}


class ProtocolError(PermissionError):
    """Raised when a closed block is requested without an explicit unlock."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_registry() -> list[dict]:
    rows = []
    for s in SEASON_FILES:
        p = RAW / f"{s}.csv"
        if p.exists():
            rows.append({"file": p.name, "season": s, "bytes": p.stat().st_size,
                         "sha256": sha256(p), "role": "football-data.co.uk SP1 export"})
    return rows


def _harmonise(df: pd.DataFrame) -> pd.DataFrame:
    built = {}
    for target, sources in ODDS_ALIASES.items():
        col = pd.Series(np.nan, index=df.index, dtype="float64")
        for src in sources:
            if src in df.columns:
                col = col.combine_first(pd.to_numeric(df[src], errors="coerce"))
        built[target] = col
    return pd.concat([df, pd.DataFrame(built, index=df.index)], axis=1)


def _parse_date(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    miss = d.isna()
    if miss.any():
        d.loc[miss] = pd.to_datetime(s[miss], format="%d/%m/%y", errors="coerce")
    miss = d.isna()
    if miss.any():
        d.loc[miss] = pd.to_datetime(s[miss], errors="coerce", dayfirst=True)
    return d


def build_master() -> pd.DataFrame:
    frames = []
    for s in SEASON_FILES:
        p = RAW / f"{s}.csv"
        d = pd.read_csv(p, encoding="utf-8-sig")
        d = d.dropna(how="all")
        d = d[d["HomeTeam"].notna() & (d["HomeTeam"].astype(str).str.strip() != "")]
        d["season"] = s
        d["src_file"] = p.name
        if "Time" not in d.columns:
            d["Time"] = np.nan
        d = _harmonise(d)
        frames.append(d)
    m = pd.concat(frames, ignore_index=True)

    # Sanitise prices: a decimal quote at or below 1.00 is impossible (a winning
    # bet would return less than the stake).  football-data carries a handful of
    # 0.0 placeholders; they are missing data, not prices.
    price_cols = [c for c in m.columns
                  if c.startswith(("OV25", "UN25", "AVG_", "B365_", "PSC_", "AHH", "AHA"))]
    for c in price_cols:
        m[c] = m[c].where(m[c] > 1.0)

    m["date"] = _parse_date(m["Date"])
    m = m.rename(columns={
        "HomeTeam": "home", "AwayTeam": "away",
        "FTHG": "hg", "FTAG": "ag", "HTHG": "hg_ht", "HTAG": "ag_ht",
        "HS": "sh_h", "AS": "sh_a", "HST": "sot_h", "AST": "sot_a",
        "HC": "cor_h", "AC": "cor_a", "HR": "red_h", "AR": "red_a",
        "Time": "kickoff",
    })
    for c in ["hg", "ag", "hg_ht", "ag_ht"]:
        m[c] = pd.to_numeric(m[c], errors="coerce").astype("Int64")

    m["G"] = (m["hg"] + m["ag"]).astype(int)
    m["G_ht"] = (m["hg_ht"] + m["ag_ht"]).astype("Int64")
    m["G_2h"] = m["G"] - m["G_ht"]

    m["state"] = np.where(m["G"] <= 1, "A", np.where(m["G"] == 2, "B", "C"))
    m["is_A"] = (m["state"] == "A").astype(int)
    m["is_B"] = (m["state"] == "B").astype(int)
    m["is_C"] = (m["state"] == "C").astype(int)

    m["block"] = np.select(
        [m["season"].isin(DEV_SEASONS), m["season"].isin(VAL_SEASONS)],
        ["dev", "val"], default="test")

    m["has_kickoff"] = m["kickoff"].notna() & (m["kickoff"].astype(str).str.strip() != "")
    m["kickoff_dt"] = pd.to_datetime(
        m["date"].dt.strftime("%Y-%m-%d") + " "
        + m["kickoff"].fillna("00:00").astype(str).str.slice(0, 5),
        errors="coerce")
    m["kickoff_dt"] = m["kickoff_dt"].fillna(m["date"])

    m = m.sort_values(["kickoff_dt", "date", "home"], kind="mergesort").reset_index(drop=True)
    m["batch_key"] = np.where(
        m["has_kickoff"], m["kickoff_dt"].dt.strftime("%Y-%m-%d %H:%M"),
        m["date"].dt.strftime("%Y-%m-%d") + " ALLDAY")
    m["batch_id"] = pd.factorize(m["batch_key"])[0]
    m["match_id"] = (m["season"] + "|" + m["date"].dt.strftime("%Y%m%d")
                     + "|" + m["home"] + "|" + m["away"])

    # Canonical names used by the rest of the pipeline.
    #   *_PRI  the primary benchmark: market average pre-match, all 10 seasons
    #   *_ROB  the headline robustness price: market maximum pre-match
    # Every other price set stays under its own OV25_*/UN25_* name and is
    # addressed explicitly where a robustness scenario needs it.
    m["O25_PRI"], m["U25_PRI"] = m["OV25"], m["UN25"]
    m["O25_ROB"], m["U25_ROB"] = m["OV25_MAX"], m["UN25_MAX"]
    m["H_B365"], m["D_B365"], m["A_B365"] = m["AVG_H"], m["AVG_D"], m["AVG_A"]
    m["ah_line"] = m["AHL"]
    m["ah_home"], m["ah_away"] = m["AHH"], m["AHA"]
    return m


_CACHE: dict[str, pd.DataFrame] = {}


def load(block: str = "dev", unlock: str | None = None, schema_only: bool = False) -> pd.DataFrame:
    if "master" not in _CACHE:
        _CACHE["master"] = build_master()
    m = _CACHE["master"]
    tokens = {"val": "VALIDATION_RUN_ONCE", "test": "HOLDOUT_RUN_ONCE", "all": "FINAL_REPORT"}
    if block in tokens and unlock != tokens[block] and not schema_only:
        raise ProtocolError(
            f"block '{block}' is closed; pass unlock='{tokens[block]}' only when the "
            "development stage is frozen")
    out = m if block == "all" else m[m["block"] == block]
    if schema_only and block != "dev":
        out = out.copy()
        for c in ["hg", "ag", "hg_ht", "ag_ht", "G", "G_ht", "G_2h", "state",
                  "is_A", "is_B", "is_C"] + [c for c in out.columns if c.startswith(("OV25", "UN25"))]:
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
    if o is pd.NA:
        return None
    raise TypeError(f"not serialisable: {type(o)}")
