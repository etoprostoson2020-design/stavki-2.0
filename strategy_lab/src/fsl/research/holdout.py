"""Holdout Ledger.

Разбор архитектуры, пункт 2: пакет требует последовательного открытия сезонов,
но нигде не считает остаток. Ла Лига — 10 сезонов, из них 8 уже просмотрены.
Здесь остаток считается явно, и discovery запрещён, если батч обнуляет его.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from fsl.logging import get_logger
from fsl.models import HoldoutLedger

log = get_logger(__name__)

MIN_UNSEEN_AFTER_BATCH = 2      # сколько сезонов обязано остаться нетронутыми


class HoldoutExhausted(RuntimeError):
    """Батч оставил бы лигу без неоткрытых сезонов."""


def seed(sess, league: str, blocks: dict[str, list[str]]) -> None:
    for block, seasons in blocks.items():
        for season in seasons:
            row = sess.scalar(select(HoldoutLedger).where(
                HoldoutLedger.league == league, HoldoutLedger.season == season))
            if row is None:
                sess.add(HoldoutLedger(league=league, season=season, block=block,
                                       state="UNSEEN"))
    sess.flush()


def mark_seen(sess, league: str, seasons: list[str], by: str, note: str = "") -> None:
    """SEEN необратим: обратного закрытия сезона не существует."""
    for season in seasons:
        row = sess.scalar(select(HoldoutLedger).where(
            HoldoutLedger.league == league, HoldoutLedger.season == season))
        if row is None:
            raise RuntimeError(f"сезон {season} не заведён в ledger")
        if row.state == "SEEN":
            continue
        row.state = "SEEN"
        row.opened_at = dt.datetime.now(dt.timezone.utc)
        row.opened_by = by
        row.note = note
    sess.flush()


def remaining(sess, league: str) -> dict:
    rows = sess.scalars(select(HoldoutLedger).where(HoldoutLedger.league == league)).all()
    unseen = [r.season for r in rows if r.state == "UNSEEN"]
    return {
        "league": league,
        "total_seasons": len(rows),
        "seen": sorted(r.season for r in rows if r.state == "SEEN"),
        "unseen": sorted(unseen),
        "unseen_count": len(unseen),
        "by_block": {b: sorted(r.season for r in rows if r.block == b and r.state == "UNSEEN")
                     for b in ("DISCOVERY", "VALIDATION", "TEST")},
    }


def guard_discovery(sess, league: str, seasons: list[str]) -> dict:
    """Пропускает discovery-батч, только если после него остаётся запас холдаута."""
    state = remaining(sess, league)
    would_open = [s for s in seasons if s in state["unseen"]]
    left = state["unseen_count"] - len(would_open)
    if left < MIN_UNSEEN_AFTER_BATCH:
        raise HoldoutExhausted(
            f"{league}: батч открыл бы {would_open}, осталось бы {left} "
            f"неоткрытых сезонов при минимуме {MIN_UNSEEN_AFTER_BATCH}")
    return {"would_open": would_open, "unseen_after": left}
