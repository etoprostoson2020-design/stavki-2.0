"""Match and team classification.

Every class is a function of pre-match information only.  Thresholds are fitted
once on development and then written to out/totals_frozen_classes.json; from
that point the classifier reads the frozen file and never re-fits.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

FROZEN = Path(__file__).resolve().parents[1] / "out" / "totals_frozen_classes.json"

MIN_HISTORY = 10          # matches a team must have played before it is classified


def fit_thresholds(dev: pd.DataFrame) -> dict:
    """Derive cut points from the development block only."""
    d = dev.dropna(subset=["elo_h", "elo_a"])
    elo = pd.concat([d["elo_h"], d["elo_a"]])
    strength = {
        "q20": float(elo.quantile(0.20)), "q40": float(elo.quantile(0.40)),
        "q60": float(elo.quantile(0.60)), "q80": float(elo.quantile(0.80)),
    }
    dd = dev.dropna(subset=["mkt_dominance"])
    fav = {
        "heavy": float(dd["mkt_dominance"].quantile(0.85)),
        "moderate": float(dd["mkt_dominance"].quantile(0.60)),
        "even_max": float(dd["mkt_dominance"].quantile(0.35)),
    }
    a = dev.dropna(subset=["gf_r10_h", "gf_r10_a", "ga_r10_h", "ga_r10_a"])
    atk = pd.concat([a["gf_r10_h"], a["gf_r10_a"]])
    dfn = pd.concat([a["ga_r10_h"], a["ga_r10_a"]])
    profile = {
        "attack_hi": float(atk.quantile(0.70)), "attack_lo": float(atk.quantile(0.30)),
        "defence_leaky": float(dfn.quantile(0.70)), "defence_tight": float(dfn.quantile(0.30)),
    }
    t = dev.dropna(subset=["tg_r10_h", "tg_r10_a"])
    tempo = (t["tg_r10_h"] + t["tg_r10_a"]) / 2
    pace = {"open": float(tempo.quantile(0.75)), "closed": float(tempo.quantile(0.25))}
    mk = dev.dropna(subset=["mkt_pC"])
    market = {"high_total": float(mk["mkt_pC"].quantile(0.75)),
              "low_total": float(mk["mkt_pC"].quantile(0.25))}
    return {"strength": strength, "favourite": fav, "profile": profile,
            "pace": pace, "market": market, "min_history": MIN_HISTORY,
            "fitted_on": "development_6 (2016/17-2021/22)"}


def load_thresholds() -> dict:
    return json.loads(FROZEN.read_text())


def _strength_label(elo, th):
    s = th["strength"]
    return np.select(
        [elo >= s["q80"], elo >= s["q60"], elo >= s["q40"], elo >= s["q20"]],
        ["strong", "above_avg", "average", "below_avg"], default="weak")


def apply_classes(m: pd.DataFrame, th: dict) -> pd.DataFrame:
    d = m.copy()
    enough = (d["tm_idx_h"] >= th["min_history"]) & (d["tm_idx_a"] >= th["min_history"])
    d["classifiable"] = enough

    d["strength_h"] = _strength_label(d["elo_h"], th)
    d["strength_a"] = _strength_label(d["elo_a"], th)

    f = th["favourite"]
    d["fav_class"] = np.select(
        [d["mkt_dominance"] >= f["heavy"],
         d["mkt_dominance"] >= f["moderate"],
         d["mkt_dominance"] <= f["even_max"]],
        ["heavy_fav", "moderate_fav", "even"], default="slight_fav")
    d["fav_side"] = np.where(d["mkt_pH"] >= d["mkt_pA_win"], "home", "away")

    p = th["profile"]
    for side in ("h", "a"):
        d[f"atk_{side}"] = np.select(
            [d[f"gf_r10_{side}"] >= p["attack_hi"], d[f"gf_r10_{side}"] <= p["attack_lo"]],
            ["attacking", "blunt"], default="mid_atk")
        d[f"def_{side}"] = np.select(
            [d[f"ga_r10_{side}"] >= p["defence_leaky"], d[f"ga_r10_{side}"] <= p["defence_tight"]],
            ["leaky", "solid"], default="mid_def")

    pc = th["pace"]
    tempo = (d["tg_r10_h"] + d["tg_r10_a"]) / 2
    d["pace_class"] = np.select(
        [tempo >= pc["open"], tempo <= pc["closed"]], ["open", "closed"], default="mid_pace")

    mk = th["market"]
    d["mkt_total_class"] = np.select(
        [d["mkt_pC"] >= mk["high_total"], d["mkt_pC"] <= mk["low_total"]],
        ["high_total", "low_total"], default="mid_total")
    return d


# ---------------------------------------------------------------- segments

def segment_masks(d: pd.DataFrame) -> dict:
    """The named segments that the final decision matrix must report."""
    ok = d["classifiable"]
    strong_h = d["strength_h"] == "strong"
    strong_a = d["strength_a"] == "strong"
    weak_h = d["strength_h"] == "weak"
    weak_a = d["strength_a"] == "weak"
    atk_h = d["atk_h"] == "attacking"
    atk_a = d["atk_a"] == "attacking"
    blunt_h = d["atk_h"] == "blunt"
    blunt_a = d["atk_a"] == "blunt"
    solid_h = d["def_h"] == "solid"
    solid_a = d["def_a"] == "solid"

    return {
        "ALL_LA_LIGA": pd.Series(True, index=d.index),
        "STRONG_TEAM_HOME": ok & strong_h,
        "STRONG_TEAM_AWAY": ok & strong_a,
        "HEAVY_FAV_VS_WEAK": ok & (d["fav_class"] == "heavy_fav") & (weak_h | weak_a),
        "MODERATE_FAV": ok & (d["fav_class"] == "moderate_fav"),
        "EVEN_MATCH": ok & (d["fav_class"] == "even"),
        "TWO_ATTACKING": ok & atk_h & atk_a,
        "TWO_DEFENSIVE": ok & solid_h & solid_a,
        "STRONG_ATK_VS_STRONG_DEF": ok & ((atk_h & solid_a) | (atk_a & solid_h)),
        "WEAK_ATK_VS_WEAK_ATK": ok & blunt_h & blunt_a,
        "HIGH_MARKET_TOTAL": ok & (d["mkt_total_class"] == "high_total"),
        "LOW_MARKET_TOTAL": ok & (d["mkt_total_class"] == "low_total"),
        "OPEN_PACE": ok & (d["pace_class"] == "open"),
        "CLOSED_PACE": ok & (d["pace_class"] == "closed"),
    }
