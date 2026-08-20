"""The frozen strategy candidates.

Every selector reads only pre-match fields.  Thresholds come from
out/totals_frozen_classes.json and the constants below, all fixed on
development before validation was opened.
"""
from __future__ import annotations
import numpy as np

import lal_classes as C

TH = None


def _th():
    global TH
    if TH is None:
        TH = C.load_thresholds()
    return TH


def _ok(r, need_history=True):
    if need_history:
        if not np.isfinite(getattr(r, "tm_idx_h", np.nan)) or r.tm_idx_h < _th()["min_history"]:
            return False
        if not np.isfinite(getattr(r, "tm_idx_a", np.nan)) or r.tm_idx_a < _th()["min_history"]:
            return False
    return True


# ---------------------------------------------------------------- C1
def c1_league_blind_under(r):
    """Control: back UNDER 2.5 in every match, no filter, no minimum price."""
    return "UNDER_2.5", None, "ALL_MATCHES"


# ---------------------------------------------------------------- C2
def c2_strong_home_under(r):
    """UNDER 2.5 when the home side is in the top Elo quintile."""
    if not _ok(r):
        return None, None, "INSUFFICIENT_HISTORY"
    if not np.isfinite(r.elo_h) or r.elo_h < _th()["strength"]["q80"]:
        return None, None, "HOME_NOT_STRONG"
    return "UNDER_2.5", 1.75, "STRONG_HOME"


# ---------------------------------------------------------------- C3
def c3_attack_meets_solid_defence(r):
    """UNDER 2.5 when a top-30% attack faces a top-30% defence."""
    if not _ok(r):
        return None, None, "INSUFFICIENT_HISTORY"
    p = _th()["profile"]
    hi, lo = p["attack_hi"], p["defence_tight"]
    if not all(np.isfinite(x) for x in (r.gf_r10_h, r.gf_r10_a, r.ga_r10_h, r.ga_r10_a)):
        return None, None, "MISSING_FORM"
    cond = (r.gf_r10_h >= hi and r.ga_r10_a <= lo) or (r.gf_r10_a >= hi and r.ga_r10_h <= lo)
    if not cond:
        return None, None, "PROFILE_NOT_MATCHED"
    return "UNDER_2.5", 1.75, "ATK_VS_SOLID"


# ---------------------------------------------------------------- C4
MKT_FORM_GAP = 0.06          # frozen on development


def c4_market_above_form(r):
    """UNDER 2.5 when the market's pC exceeds the teams' own recent pC rate.

    Form estimate is the average of the two sides' rolling 10-match share of
    3+ goal games -- a model-free, purely empirical expectation.
    """
    if not _ok(r):
        return None, None, "INSUFFICIENT_HISTORY"
    if not np.isfinite(r.mkt_pC) or not np.isfinite(r.pC_r10_h) or not np.isfinite(r.pC_r10_a):
        return None, None, "MISSING_INPUT"
    form_pC = 0.5 * (r.pC_r10_h + r.pC_r10_a)
    if r.mkt_pC - form_pC < MKT_FORM_GAP:
        return None, None, "GAP_TOO_SMALL"
    return "UNDER_2.5", 1.70, "MARKET_ABOVE_FORM"


# ---------------------------------------------------------------- C5
OVER_GAP = 0.06


def c5_form_above_market(r):
    """The mirror image: OVER 2.5 when recent form runs hotter than the market."""
    if not _ok(r):
        return None, None, "INSUFFICIENT_HISTORY"
    if not np.isfinite(r.mkt_pC) or not np.isfinite(r.pC_r10_h) or not np.isfinite(r.pC_r10_a):
        return None, None, "MISSING_INPUT"
    form_pC = 0.5 * (r.pC_r10_h + r.pC_r10_a)
    if form_pC - r.mkt_pC < OVER_GAP:
        return None, None, "GAP_TOO_SMALL"
    return "OVER_2.5", 1.90, "FORM_ABOVE_MARKET"


# ---------------------------------------------------------------- C6
def c6_low_total_under(r):
    """UNDER 2.5 in matches the market itself prices as low-scoring."""
    if not _ok(r):
        return None, None, "INSUFFICIENT_HISTORY"
    if not np.isfinite(r.mkt_pC) or r.mkt_pC > _th()["market"]["low_total"]:
        return None, None, "NOT_LOW_TOTAL"
    return "UNDER_2.5", 1.55, "LOW_MARKET_TOTAL"


# ---------------------------------------------------------------- C7
SEQ_HOT = 0.62


def c7_sequential_fade_hot_league(r):
    """Sequential family: after a hot run of league batches, back UNDER 2.5.

    Included only so that the sequential family is tested on the same footing
    as the others; it is expected to fail its permutation gate.
    """
    if not _ok(r):
        return None, None, "INSUFFICIENT_HISTORY"
    if not np.isfinite(getattr(r, "seqC_5", np.nan)):
        return None, None, "NO_SEQUENCE_YET"
    if r.seqC_5 < SEQ_HOT:
        return None, None, "LEAGUE_NOT_HOT"
    return "UNDER_2.5", 1.70, "SEQ_HOT_FADE"


CANDIDATES = {
    "C1_LEAGUE_BLIND_UNDER_2.5": {
        "fn": c1_league_blind_under, "family": "league_wide",
        "mechanism": "control: is the whole league mispriced on the under side?",
        "expected_frequency": "every match"},
    "C2_STRONG_HOME_UNDER_2.5": {
        "fn": c2_strong_home_under, "family": "strength_class",
        "mechanism": "public over-backs strong home sides, inflating the total",
        "expected_frequency": "~20% of matches"},
    "C3_ATK_VS_SOLID_UNDER_2.5": {
        "fn": c3_attack_meets_solid_defence, "family": "profile_chemistry",
        "mechanism": "a hot attack meeting a tight defence is priced on the "
                     "attack's reputation, not on the pairing",
        "expected_frequency": "~17% of matches"},
    "C4_MARKET_ABOVE_FORM_UNDER_2.5": {
        "fn": c4_market_above_form, "family": "profile_chemistry",
        "mechanism": "fade the market where it prices more goals than either "
                     "side has actually been producing",
        "expected_frequency": "~15% of matches"},
    "C5_FORM_ABOVE_MARKET_OVER_2.5": {
        "fn": c5_form_above_market, "family": "profile_chemistry",
        "mechanism": "symmetric over-side test of the same gap",
        "expected_frequency": "~15% of matches"},
    "C6_LOW_TOTAL_UNDER_2.5": {
        "fn": c6_low_total_under, "family": "strength_class",
        "mechanism": "the low-total corner of the book carries the least margin",
        "expected_frequency": "~25% of matches"},
    "C7_SEQ_HOT_FADE_UNDER_2.5": {
        "fn": c7_sequential_fade_hot_league, "family": "sequential",
        "mechanism": "mean reversion after a hot run of league batches",
        "expected_frequency": "~10% of matches"},
}
