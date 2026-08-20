"""Stage 3 -- build the causal feature table once and cache it.

Features are computed over the whole chronology (rolling windows must cross
season boundaries) but every analysis script filters to its own block.  The
leakage tests below are the guarantee that this is safe.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D
import lal_features as F

CACHE = D.ROOT / "data" / "features.parquet"


def build(force=False) -> pd.DataFrame:
    if CACHE.exists() and not force:
        return pd.read_parquet(CACHE)
    m = D.build_master()
    m = F.build_all(m)
    m.to_parquet(CACHE, index=False)
    return m


FEATURE_PREFIXES = ("gf_", "ga_", "tg_", "pA_", "pB_", "pC_", "seq", "prev_",
                    "elo_", "mkt_pC", "mkt_pH", "mkt_pD", "mkt_pA_win", "mkt_lambda",
                    "mkt_fav", "mkt_dom", "mkt_draw", "ah_", "C_streak", "A_streak",
                    "tm_idx", "rest_days")

# mkt_resid is the residual of a FINISHED match. It is a valid input only after
# being lagged (seqR_*); it is never a feature of the match it describes.
FORBIDDEN_AS_FEATURE = ("mkt_resid",)


def feature_columns(m: pd.DataFrame) -> list[str]:
    return [c for c in m.columns
            if c.startswith(FEATURE_PREFIXES) and c not in FORBIDDEN_AS_FEATURE]


def _scramble(base: pd.DataFrame, rows, rng) -> pd.DataFrame:
    """Replace the goal outcome of the given rows with random goals."""
    d = base.copy()
    idx = d.index[rows]
    d.loc[idx, "hg"] = rng.integers(0, 5, size=len(idx))
    d.loc[idx, "ag"] = rng.integers(0, 5, size=len(idx))
    d.loc[idx, "hg_ht"] = 0
    d.loc[idx, "ag_ht"] = 0
    return d


def _rebuild(base: pd.DataFrame) -> pd.DataFrame:
    d = base.copy()
    d["G"] = d["hg"] + d["ag"]
    d["G_ht"] = d["hg_ht"] + d["ag_ht"]
    d["G_2h"] = d["G"] - d["G_ht"]
    d["state"] = np.where(d["G"] <= 1, "A", np.where(d["G"] == 2, "B", "C"))
    d["is_A"] = (d["state"] == "A").astype(int)
    d["is_B"] = (d["state"] == "B").astype(int)
    d["is_C"] = (d["state"] == "C").astype(int)
    return F.build_all(d)


def _same_rows(a: pd.DataFrame, b: pd.DataFrame, cols, rows) -> list[str]:
    """Column names that differ on the given row positions."""
    bad = []
    for c in cols:
        x, y = a[c].iloc[rows], b[c].iloc[rows]
        if x.dtype.kind in "fiu" and y.dtype.kind in "fiu":
            if not np.allclose(x.fillna(-9e9).values.astype(float),
                               y.fillna(-9e9).values.astype(float), equal_nan=True):
                bad.append(c)
        else:
            if not x.fillna("_").reset_index(drop=True).equals(
                    y.fillna("_").reset_index(drop=True)):
                bad.append(c)
    return bad


def leakage_report(m: pd.DataFrame) -> dict:
    """Causality tests. Every one must pass or the study is void."""
    rng = np.random.default_rng(0)
    rep = {}
    base = D.build_master()
    cols = feature_columns(m)
    rep["n_features_tested"] = len(cols)

    # --- Test 1: truncation invariance (no FUTURE information) --------------
    # Destroy every outcome after a cutoff; features at or before the cutoff
    # must be bit-identical.
    t1 = {}
    for frac in (0.35, 0.60, 0.85):
        k = int(len(base) * frac)
        scr = _scramble(base, np.arange(k + 1, len(base)), rng)
        rb = _rebuild(scr)
        bad = _same_rows(m, rb, cols, np.arange(0, k + 1))
        t1[f"cutoff_{frac}"] = {"cutoff_row": k, "differing_features": bad}
    rep["truncation_invariance"] = t1

    # --- Test 2: own-row invariance (no SELF information) -------------------
    # Change one match's own outcome; that match's own features must not move.
    t2 = {}
    probes = rng.choice(np.arange(500, len(base)), size=12, replace=False)
    for r in sorted(probes.tolist()):
        scr = _scramble(base, np.array([r]), rng)
        rb = _rebuild(scr)
        bad = _same_rows(m, rb, cols, np.array([r]))
        t2[str(r)] = bad
    rep["own_row_invariance"] = t2

    # --- Test 3: window warm-up --------------------------------------------
    rep["warmup"] = {
        "gf_r6_h_set_before_6_matches": int(m.loc[m["tm_idx_h"] < 6, "gf_r6_h"].notna().sum()),
        "gf_r20_a_set_before_20_matches": int(m.loc[m["tm_idx_a"] < 20, "gf_r20_a"].notna().sum()),
    }

    # --- Test 4: batch integrity -------------------------------------------
    rep["batch_keys_unique_per_batch"] = int(
        m.groupby("batch_id")["batch_key"].nunique().max()) == 1

    # --- Test 5: descriptive correlations on dev ---------------------------
    sub = m[m["block"] == "dev"]
    cors = {}
    for c in ["seqC_1", "seqC_5", "seqR_5", "gf_r6_h", "tg_r10_h", "elo_diff", "mkt_pC"]:
        d = sub[[c, "is_C"]].dropna()
        cors[c] = float(np.corrcoef(d[c], d["is_C"])[0, 1]) if len(d) > 30 else None
    rep["dev_correlation_with_is_C"] = cors
    return rep


def main():
    m = build(force=True)
    print(f"features built: {m.shape[0]} rows x {m.shape[1]} cols -> {CACHE.name}")
    rep = leakage_report(m)
    print("\n=== LEAKAGE / CAUSALITY REPORT ===")
    print(f"  features under test: {rep['n_features_tested']}")

    ok = True
    print("\n  Test 1 - truncation invariance (no future information):")
    for k, v in rep["truncation_invariance"].items():
        bad = v["differing_features"]
        ok &= not bad
        print(f"    {k:14s} rows 0..{v['cutoff_row']:<5d} differing: "
              f"{'NONE' if not bad else bad}")

    print("\n  Test 2 - own-row invariance (no self information):")
    bad2 = {r: b for r, b in rep["own_row_invariance"].items() if b}
    ok &= not bad2
    print(f"    12 probe matches, differing features: "
          f"{'NONE' if not bad2 else bad2}")

    print("\n  Test 3 - rolling-window warm-up:")
    for k, v in rep["warmup"].items():
        ok &= (v == 0)
        print(f"    {k:38s} {v}  {'OK' if v == 0 else 'LEAK'}")

    print(f"\n  Test 4 - batch integrity: {rep['batch_keys_unique_per_batch']}")
    ok &= rep["batch_keys_unique_per_batch"]

    print("\n  Test 5 - dev corr(feature, is_C):")
    for k, v in rep["dev_correlation_with_is_C"].items():
        print(f"     {k:12s} {v:+.4f}" if v is not None else f"     {k:12s} n/a")

    rep["GATE"] = "PASS" if ok else "FAIL"
    D.write_json("s03_leakage_report.json", rep)
    print(f"\n  LEAKAGE GATE: {rep['GATE']}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
