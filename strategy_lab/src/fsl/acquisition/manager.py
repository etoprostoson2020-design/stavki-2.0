"""Регистрация снапшотов в БД."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import select

from fsl.acquisition.base import FetchResult
from fsl.acquisition.footballdata import FootballDataAdapter
from fsl.logging import get_logger
from fsl.models import RawSnapshot, Source

log = get_logger(__name__)

SOURCES = [
    ("FOOTBALL_DATA", "Football-Data.co.uk", "HISTORICAL"),
    ("API_FOOTBALL", "API-Football", "LIVE"),
    ("USER_FILE", "Пользовательские файлы", "USER"),
]


def ensure_sources(sess) -> dict[str, Source]:
    out = {}
    for code, name, kind in SOURCES:
        src = sess.scalar(select(Source).where(Source.code == code))
        if src is None:
            src = Source(code=code, name=name, kind=kind)
            sess.add(src)
            sess.flush()
        out[code] = src
    return out


def register_snapshot(sess, source: Source, fr: FetchResult) -> RawSnapshot:
    existing = sess.scalar(
        select(RawSnapshot).where(RawSnapshot.source_id == source.id,
                                  RawSnapshot.league == fr.league,
                                  RawSnapshot.season == fr.season,
                                  RawSnapshot.sha256 == fr.sha256))
    if existing is not None:
        return existing

    df = pd.read_csv(fr.path, encoding="utf-8", encoding_errors="replace",
                     low_memory=False, skip_blank_lines=True)
    df = df.dropna(how="all")
    snap = RawSnapshot(source_id=source.id, league=fr.league, season=fr.season,
                       path=str(fr.path), sha256=fr.sha256, size_bytes=fr.size_bytes,
                       n_rows=int(len(df)), n_cols=int(df.shape[1]), origin=fr.origin)
    sess.add(snap)
    sess.flush()
    log.info("raw.registered", league=fr.league, season=fr.season,
             rows=snap.n_rows, cols=snap.n_cols)
    return snap


def import_seasons(sess, league: str, seasons: list[str],
                   local_files: dict[str, Path] | None = None) -> list[RawSnapshot]:
    adapter = FootballDataAdapter()
    src = ensure_sources(sess)[adapter.code]
    out = []
    for season in seasons:
        lf = (local_files or {}).get(season)
        fr = adapter.fetch_season(league, season, local_file=lf)
        out.append(register_snapshot(sess, src, fr))
    return out
