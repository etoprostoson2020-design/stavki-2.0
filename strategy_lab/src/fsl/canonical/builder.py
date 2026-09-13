"""L1 NORMALIZED → L2 CANONICAL.

Из provider-записи остаются только поля разрешённого списка. Котировки в
канонический слой не попадают: они сохраняются в RAW и будут доступны будущему
Market Evaluation, но discovery их не видит физически, а не по флагу.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy import select

from fsl.canonical.resolver import TeamResolver
from fsl.hashing import stable_hash
from fsl.logging import get_logger
from fsl.models import Fixture, RawSnapshot

log = get_logger(__name__)

#: Единственные поля источника, попадающие в канонический слой.
CORE_FIELDS = ["Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
               "HTHG", "HTAG", "HTR", "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC",
               "HY", "AY", "HR", "AR"]
STAT_FIELDS = ["HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR"]

#: Длительность матча с перерывом. Матчи, стартующие внутри этого окна,
#: считаются идущими одновременно и не видят результатов друг друга.
MATCH_MINUTES = 115
#: Условный час для сезонов, где источник не даёт Time.
DATE_ONLY_HOUR = 12


def _read_core(snap: RawSnapshot) -> pd.DataFrame:
    df = pd.read_csv(snap.path, encoding="utf-8", encoding_errors="replace",
                     low_memory=False).dropna(how="all")
    if "Time" not in df.columns:
        df["Time"] = pd.NA          # 16-17…18-19: внутридневной порядок неизвестен
    missing = [c for c in CORE_FIELDS if c not in df.columns]
    if missing:
        raise ValueError(f"{snap.season}: в источнике нет обязательных полей {missing}")
    out = df[CORE_FIELDS].copy()
    out["__season"] = snap.season
    out["__league"] = snap.league
    return out


def _kickoff(row) -> tuple[dt.datetime, str]:
    d = pd.to_datetime(row["Date"], dayfirst=True, format="mixed")
    t = row["Time"]
    if pd.isna(t) or not str(t).strip():
        return (dt.datetime(d.year, d.month, d.day, DATE_ONLY_HOUR,
                            tzinfo=dt.timezone.utc), "DATE_ONLY")
    hh, mm = str(t).split(":")[:2]
    return (dt.datetime(d.year, d.month, d.day, int(hh), int(mm),
                        tzinfo=dt.timezone.utc), "EXACT")


def assign_sync_batches(rows: list[dict]) -> None:
    """Проставляет sync_batch. Матчи одного блока не видят результатов друг друга.

    Без времени начала — вся календарная дата один блок. Со временем — блок
    разрывается, когда следующий стартовый свисток не раньше конца предыдущего.
    """
    rows.sort(key=lambda r: (r["kickoff_utc"], r["home_team_raw"]))
    batch = -1
    prev_date = None
    prev_end = None
    for r in rows:
        day = r["kickoff_utc"].date()
        exact = r["kickoff_precision"] == "EXACT"
        if prev_date is None or day != prev_date:
            batch += 1
            prev_end = r["kickoff_utc"] + dt.timedelta(minutes=MATCH_MINUTES)
        elif not exact:
            pass                                     # тот же день, времени нет — тот же блок
        elif r["kickoff_utc"] >= prev_end:
            batch += 1
            prev_end = r["kickoff_utc"] + dt.timedelta(minutes=MATCH_MINUTES)
        else:
            prev_end = max(prev_end, r["kickoff_utc"] + dt.timedelta(minutes=MATCH_MINUTES))
        r["sync_batch"] = batch
        prev_date = day


def _clean_int(v):
    """NULL остаётся NULL. Ноль — только настоящий ноль из источника."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return None
    return int(v)


def build_canonical(sess, league: str, seasons: list[str], dataset_version: str) -> int:
    resolver = TeamResolver(sess, source_code="FOOTBALL_DATA")
    snaps = sess.scalars(select(RawSnapshot).where(
        RawSnapshot.league == league, RawSnapshot.season.in_(seasons))).all()
    if not snaps:
        raise RuntimeError(f"нет снапшотов для {league} {seasons}")

    rows: list[dict] = []
    for snap in sorted(snaps, key=lambda s: s.season):
        df = _read_core(snap)
        for _, r in df.iterrows():
            ko, precision = _kickoff(r)
            rows.append(dict(
                league=league, season=snap.season,
                match_date=ko.date(), kickoff_utc=ko, kickoff_precision=precision,
                home_team_raw=str(r["HomeTeam"]), away_team_raw=str(r["AwayTeam"]),
                fthg=_clean_int(r["FTHG"]), ftag=_clean_int(r["FTAG"]),
                ftr=(None if pd.isna(r["FTR"]) else str(r["FTR"])),
                hthg=_clean_int(r["HTHG"]), htag=_clean_int(r["HTAG"]),
                htr=(None if pd.isna(r["HTR"]) else str(r["HTR"])),
                stats={f: _clean_int(r[f]) for f in STAT_FIELDS},
            ))

    assign_sync_batches(rows)

    written = 0
    for r in rows:
        home = resolver.resolve(r["home_team_raw"])
        away = resolver.resolve(r["away_team_raw"])
        if home.id == away.id:
            raise ValueError(f"матч сам с собой: {r['home_team_raw']} vs {r['away_team_raw']}")
        lineage = {f: {"source": "FOOTBALL_DATA", "snapshot": r["season"]}
                   for f in ("fthg", "ftag", "hthg", "htag", *[s.lower() for s in STAT_FIELDS])}
        sess.add(Fixture(
            league=r["league"], season=r["season"], match_date=r["match_date"],
            kickoff_utc=r["kickoff_utc"], kickoff_precision=r["kickoff_precision"],
            sync_batch=r["sync_batch"],
            home_team_id=home.id, away_team_id=away.id,
            fthg=r["fthg"], ftag=r["ftag"], ftr=r["ftr"],
            hthg=r["hthg"], htag=r["htag"], htr=r["htr"],
            stats=r["stats"], source_lineage=lineage,
            quality_grade="A", conflict=False, dataset_version=dataset_version))
        written += 1
    sess.flush()
    log.info("canonical.built", league=league, seasons=len(seasons), fixtures=written,
             batches=len({r["sync_batch"] for r in rows}))
    return written


def dataset_version_for(sess, league: str, seasons: list[str]) -> str:
    """Версия датасета = источники + их контрольные суммы + лок окружения."""
    from fsl.hashing import environment_lock
    snaps = sess.scalars(select(RawSnapshot).where(
        RawSnapshot.league == league, RawSnapshot.season.in_(seasons))).all()
    payload = {"league": league,
               "snapshots": sorted((s.season, s.sha256) for s in snaps),
               "core_fields": CORE_FIELDS,
               "environment": environment_lock()}
    return stable_hash(payload, 16)
