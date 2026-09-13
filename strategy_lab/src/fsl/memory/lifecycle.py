"""PARK и KILL. Ничего не удаляется, у всего есть причина."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from fsl.logging import get_logger
from fsl.models import Fixture, KillRecord, ParkRecord, Strategy

log = get_logger(__name__)

def _as_utc(value: dt.datetime | None) -> dt.datetime | None:
    """Приводит время к UTC-aware.

    PostgreSQL отдаёт timestamptz с зоной, SQLite — naive. Сравнивать их
    напрямую нельзя, а тесты обязаны идти на обоих.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)


KILL_CODES = {
    "NO_OOS_SUPPORT": "на независимых данных эффект не подтвердился",
    "SIGN_FLIPPED": "знак эффекта перевернулся",
    "BELOW_BATCH_THRESHOLD": "ниже порога батча: неотличимо от нулевого мира",
    "ONE_TEAM_EFFECT": "эффект держится на одной команде",
    "ONE_SEASON_EFFECT": "эффект держится на одном сезоне",
    "DUPLICATE_OF_EXISTING": "дубликат уже принятой стратегии",
    "HARD_FAIL": "жёсткий отказ: утечка, порча данных или подмена критерия",
}


def park(sess, strategy_id: str, version: int, *, reason: str,
         revival_condition: str, min_new_fixtures: int = 380,
         review_days: int = 180, priority: int = 5) -> ParkRecord:
    """Паркует идею с явным условием возврата, а не «когда-нибудь посмотрим»."""
    now = dt.datetime.now(dt.timezone.utc)
    rec = ParkRecord(
        strategy_id=strategy_id, version=version, reason=reason,
        revival_condition=revival_condition, min_new_fixtures=min_new_fixtures,
        fixtures_at_park=sess.scalar(select(func.count()).select_from(Fixture)) or 0,
        review_after=now + dt.timedelta(days=review_days), priority=priority)
    sess.add(rec)
    st = sess.scalar(select(Strategy).where(Strategy.strategy_id == strategy_id,
                                            Strategy.version == version))
    if st is not None:
        st.stage = "PARK"
        st.action = "PARK"
        st.park_kill_reason = reason
    sess.flush()
    log.info("memory.park", strategy_id=strategy_id, version=version, priority=priority)
    return rec


def kill(sess, strategy_id: str, version: int, *, code: str, reason: str,
         evidence: dict, policy_version: str) -> KillRecord:
    if code not in KILL_CODES:
        raise ValueError(f"неизвестный код KILL: {code}; доступны {sorted(KILL_CODES)}")
    rec = KillRecord(strategy_id=strategy_id, version=version, code=code,
                     reason=reason, evidence=evidence, policy_version=policy_version)
    sess.add(rec)
    st = sess.scalar(select(Strategy).where(Strategy.strategy_id == strategy_id,
                                            Strategy.version == version))
    if st is not None:
        st.stage = "KILL"
        st.action = "KILL"
        st.strategy_class = "REJECTED"
        st.park_kill_reason = f"{code}: {reason}"
    sess.flush()
    log.info("memory.kill", strategy_id=strategy_id, version=version, code=code)
    return rec


def revival_candidates(sess) -> list[dict]:
    """Кого пора пересмотреть: данных прибавилось или срок подошёл."""
    now = dt.datetime.now(dt.timezone.utc)
    total = sess.scalar(select(func.count()).select_from(Fixture)) or 0
    out = []
    for r in sess.scalars(select(ParkRecord).where(ParkRecord.revived_at.is_(None))).all():
        new_fixtures = total - r.fixtures_at_park
        by_data = new_fixtures >= r.min_new_fixtures
        review_after = _as_utc(r.review_after)
        by_time = review_after is not None and now >= review_after
        if by_data or by_time:
            out.append({"strategy_id": r.strategy_id, "version": r.version,
                        "reason": r.reason, "revival_condition": r.revival_condition,
                        "new_fixtures": new_fixtures,
                        "min_new_fixtures": r.min_new_fixtures,
                        "triggered_by": "новые данные" if by_data else "срок пересмотра",
                        "priority": r.priority})
    return sorted(out, key=lambda d: d["priority"])


def mark_revived(sess, strategy_id: str, version: int) -> None:
    r = sess.scalar(select(ParkRecord).where(
        ParkRecord.strategy_id == strategy_id, ParkRecord.version == version,
        ParkRecord.revived_at.is_(None)))
    if r is not None:
        r.revived_at = dt.datetime.now(dt.timezone.utc)
        sess.flush()


def failure_history(sess, strategy_id: str) -> dict:
    parks = sess.scalars(select(ParkRecord).where(
        ParkRecord.strategy_id == strategy_id)).all()
    kills = sess.scalars(select(KillRecord).where(
        KillRecord.strategy_id == strategy_id)).all()
    return {"strategy_id": strategy_id,
            "parks": [{"version": p.version, "reason": p.reason,
                       "revival_condition": p.revival_condition,
                       "revived": p.revived_at is not None} for p in parks],
            "kills": [{"version": k.version, "code": k.code, "reason": k.reason,
                       "policy_version": k.policy_version} for k in kills]}
