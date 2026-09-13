"""Расчёт значений признаков и запись слоя L4."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from fsl.features.registry import FeatureSpec, PreMatchContext
from fsl.logging import get_logger
from fsl.temporal.time_machine import TimeMachine

log = get_logger(__name__)


def compute_features(fixtures: list[dict], specs: list[FeatureSpec]
                     ) -> dict[int, dict[str, float | None]]:
    """Для каждого матча — значения всех признаков, посчитанные только по прошлому."""
    reset = all(s.season_transition == "SEASON_RESET" for s in specs)
    out: dict[int, dict[str, float | None]] = {}
    for f, home_view, away_view in TimeMachine(fixtures, season_reset=reset).walk():
        ctx = PreMatchContext(
            fixture_id=f["fixture_id"], league=f["league"], season=f["season"],
            kickoff_utc=f["kickoff_utc"], kickoff_precision=f["kickoff_precision"],
            sync_batch=f["sync_batch"], home_team=f["home_team"], away_team=f["away_team"])
        out[f["fixture_id"]] = {s.key: s.compute(ctx, home_view, away_view) for s in specs}
    return out


def coverage(values: dict[int, dict[str, float | None]]) -> dict[str, dict]:
    keys = next(iter(values.values())).keys() if values else []
    rep = {}
    for k in keys:
        col = [v[k] for v in values.values()]
        n_av = sum(1 for x in col if x is not None)
        rep[k] = {"available": n_av, "unavailable": len(col) - n_av,
                  "coverage": round(n_av / len(col), 4) if col else 0.0}
    return rep


def write_parquet(values: dict[int, dict[str, float | None]], fixtures: list[dict],
                  path: Path, dataset_version: str, spec_versions: dict[str, str]) -> Path:
    meta = {f["fixture_id"]: f for f in fixtures}
    rows = []
    for fid, feats in values.items():
        f = meta[fid]
        for key, val in feats.items():
            rows.append({"fixture_id": fid, "league": f["league"], "season": f["season"],
                         "kickoff_utc": f["kickoff_utc"], "feature_key": key,
                         "value": val,                     # None остаётся None
                         "definition_hash": spec_versions[key],
                         "dataset_version": dataset_version,
                         "source_lineage": "FOOTBALL_DATA"})
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    log.info("features.parquet", path=str(path), rows=len(df))
    return path
