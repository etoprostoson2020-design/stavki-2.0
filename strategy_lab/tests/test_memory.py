"""Фаза 7, приёмка по документу 10.

Система обязана отвечать «мы уже это проверяли и чем кончилось?» без ручного
поиска по файлам, и не считать одно и то же дважды.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from fsl.experiments.engine import Condition
from fsl.memory import dedupe, families, lifecycle, regions
from fsl.memory import registry as reg
from fsl.memory.context import build_context, what_do_we_know
from fsl.memory.fingerprints import jaccard, semantic_fingerprint
from fsl.models import ExhaustedRegion, Fixture, HypothesisRecord, KillRecord, Team

POL = {"qualification": "qh", "statistical": "sh"}
FV = {"FORM_PPG_DIFF.v1": "fh"}
C1 = [Condition("FORM_PPG_DIFF.v1", ">=", 1.0)]
C2 = [Condition("FORM_PPG_DIFF.v2", ">=", 1.2)]      # та же логика, другие числа
C3 = [Condition("REST_DAYS_DIFF.v1", ">=", 1.0)]     # другая логика


def _rec(sess, conds, target="RES_HOME", dsv="dsv1", **kw):
    return reg.record_hypothesis(sess, league="ESP_1", seasons=["16-17"],
                                 conditions=conds, target=target, feature_versions=FV,
                                 dataset_version=dsv, policy_hashes=POL, **kw)


# ------------------------------------------------------------- дедупликация
def test_duplicate_flood_creates_one_record(sess):
    """Red Team #8: сто одинаковых гипотез — одна строка, счётчик встреч сто."""
    for _ in range(100):
        _rec(sess, C1, result={"n_signals": 10, "z": 2.0})
    rows = sess.scalars(select(HypothesisRecord)).all()
    assert len(rows) == 1
    assert rows[0].times_seen == 100


def test_exact_duplicate_is_not_re_evaluated(sess):
    _rec(sess, C1, result={"n_signals": 10, "z": 4.0})
    d = dedupe.check(sess, C1, "RES_HOME", dataset_version="dsv1",
                     feature_versions=FV, policy_hashes=POL)
    assert d.verdict == "EXACT_DUPLICATE" and not d.should_evaluate


def test_same_logic_other_numbers_is_known_region(sess):
    """Окно и порог другие — но это та же область, и память об этом говорит."""
    _rec(sess, C1, result={"n_signals": 10, "z": 4.0})
    d = dedupe.check(sess, C2, "RES_HOME", dataset_version="dsv1",
                     feature_versions=FV, policy_hashes=POL)
    assert d.verdict == "SEMANTIC_KNOWN"
    assert d.should_evaluate          # считать стоит, но с оглядкой на прошлое
    assert semantic_fingerprint(C1, "RES_HOME") == semantic_fingerprint(C2, "RES_HOME")


def test_different_logic_is_new(sess):
    _rec(sess, C1, result={"n_signals": 10, "z": 4.0})
    d = dedupe.check(sess, C3, "RES_HOME", dataset_version="dsv1",
                     feature_versions=FV, policy_hashes=POL)
    assert d.verdict == "NEW" and d.should_evaluate


def test_same_question_on_new_data_is_rerun_not_duplicate(sess):
    """Та же формула на новых данных — продолжение, а не дубликат."""
    _rec(sess, C1, dsv="dsv1", result={"n_signals": 10, "z": 4.0})
    d = dedupe.check(sess, C1, "RES_HOME", dataset_version="dsv2",
                     feature_versions=FV, policy_hashes=POL)
    assert d.verdict == "RERUN_ON_NEW_DATA" and d.should_evaluate


def test_signal_duplicate_is_detected(sess):
    """Разные формулы, одно множество матчей — одно открытие, а не два."""
    _rec(sess, C1, result={"n_signals": 3, "z": 4.0}, signal_fixture_ids=[1, 2, 3])
    d = dedupe.check(sess, C3, "RES_HOME", dataset_version="dsv1",
                     feature_versions=FV, policy_hashes=POL,
                     signal_fixture_ids=[3, 2, 1])
    assert d.verdict == "SIGNAL_DUPLICATE" and not d.should_evaluate


def test_near_duplicate_by_jaccard(sess):
    families.store_signals(sess, "STR-A", 1, "dsv1", list(range(100)))
    d = dedupe.check(sess, C3, "RES_HOME", dataset_version="dsv1",
                     feature_versions=FV, policy_hashes=POL,
                     signal_fixture_ids=list(range(96)))
    assert d.verdict == "NEAR_DUPLICATE"
    assert d.jaccard >= 0.90 and not d.should_evaluate


# ---------------------------------------------------------------- регионы
def test_region_is_exhausted_and_reopens_on_new_data(sess):
    for thr in range(8):
        _rec(sess, [Condition("REST_DAYS_DIFF.v1", ">=", float(thr))],
             target="OVER_25", result={"n_signals": 50, "z": 1.2},
             passed_threshold=False)
    marked = regions.mark_exhausted_regions(sess, "ESP_1", "dsv1",
                                            batch_threshold=3.0, min_tested=6)
    assert len(marked) == 1
    assert regions.is_exhausted(sess, "REST_DAYS_DIFF|>=|OVER_25", "dsv1") is not None
    # на новом датасете вопрос открыт заново
    assert regions.is_exhausted(sess, "REST_DAYS_DIFF|>=|OVER_25", "dsv2") is None


def test_region_with_a_hit_is_not_exhausted(sess):
    for thr in range(8):
        _rec(sess, [Condition("FORM_PPG_DIFF.v1", ">=", float(thr))],
             result={"n_signals": 50, "z": 1.0 if thr else 5.0},
             passed_threshold=bool(thr == 0))
    marked = regions.mark_exhausted_regions(sess, "ESP_1", "dsv1",
                                            batch_threshold=3.0, min_tested=6)
    assert marked == []


# ------------------------------------------------------------ PARK / KILL
def _add_fixtures(sess, n, offset=0):
    """Пара команд в сезоне встречается один раз — ограничение fixtures это держит."""
    home = Team(canonical_name=f"HOME{offset}")
    sess.add(home)
    sess.flush()
    for i in range(n):
        away = Team(canonical_name=f"AWAY{offset}_{i}")
        sess.add(away)
        sess.flush()
        sess.add(Fixture(league="ESP_1", season="16-17",
                         match_date=dt.date(2016, 8, 20),
                         kickoff_utc=dt.datetime(2016, 8, 20, tzinfo=dt.timezone.utc),
                         kickoff_precision="EXACT", sync_batch=i + offset,
                         home_team_id=home.id, away_team_id=away.id,
                         fthg=1, ftag=0, ftr="H", hthg=0, htag=0, htr="D",
                         stats={}, source_lineage={}, dataset_version="dsv1"))
    sess.flush()


def test_park_stores_revival_condition_and_fires_on_new_data(sess):
    _add_fixtures(sess, 10)
    lifecycle.park(sess, "STR-A", 1, reason="нет независимого OOS",
                   revival_condition="открыт блок test", min_new_fixtures=20,
                   review_days=3650)
    assert lifecycle.revival_candidates(sess) == []      # данных ещё не прибавилось
    _add_fixtures(sess, 25, offset=1000)
    rev = lifecycle.revival_candidates(sess)
    assert len(rev) == 1
    assert rev[0]["triggered_by"] == "новые данные"
    assert rev[0]["revival_condition"] == "открыт блок test"


def test_kill_stores_reason_and_rejects_unknown_code(sess):
    lifecycle.kill(sess, "STR-B", 1, code="ONE_TEAM_EFFECT",
                   reason="весь эффект на одной команде",
                   evidence={"top1_share": 0.9}, policy_version="QP_v0.1")
    hist = lifecycle.failure_history(sess, "STR-B")
    assert hist["kills"][0]["code"] == "ONE_TEAM_EFFECT"
    with pytest.raises(ValueError, match="неизвестный код KILL"):
        lifecycle.kill(sess, "STR-C", 1, code="ПОТОМУ_ЧТО", reason="", evidence={},
                       policy_version="x")


def test_nothing_is_deleted_from_memory(sess):
    """Провалы не удаляются: KILL остаётся в памяти навсегда."""
    lifecycle.kill(sess, "STR-D", 1, code="NO_OOS_SUPPORT", reason="не подтвердилась",
                   evidence={}, policy_version="QP_v0.1")
    lifecycle.kill(sess, "STR-D", 2, code="SIGN_FLIPPED", reason="знак перевернулся",
                   evidence={}, policy_version="QP_v0.1")
    assert sess.scalar(select(KillRecord).where(KillRecord.version == 1)) is not None
    assert len(lifecycle.failure_history(sess, "STR-D")["kills"]) == 2


# ------------------------------------------------------------- семейства
def test_correlated_strategies_form_one_family(sess):
    families.store_signals(sess, "STR-A", 1, "dsv1", list(range(100)))
    families.store_signals(sess, "STR-B", 1, "dsv1", list(range(5, 105)))   # J ~ 0.90
    families.store_signals(sess, "STR-C", 1, "dsv1", list(range(500, 600)))  # чужая
    fams = families.rebuild_families(sess, threshold=0.5)
    sizes = sorted(len(f["members"]) for f in fams)
    assert sizes == [1, 2], "коррелированные не склеились или склеились лишние"
    assert jaccard(set(range(100)), set(range(5, 105))) > 0.5


# ------------------------------------------------- контекст и прямой вопрос
def test_memory_context_skips_known_candidates(sess):
    class Cand:
        def __init__(self, cid, conds, target):
            self.candidate_id, self.conditions, self.target = cid, tuple(conds), target

    cands = [Cand("a", C1, "RES_HOME"), Cand("b", C3, "RES_HOME")]
    first = build_context(sess, cands, dataset_version="dsv1",
                          feature_versions=FV, policy_hashes=POL)
    assert first["to_evaluate"] == 2

    for c in cands:
        _rec(sess, list(c.conditions), result={"n_signals": 5, "z": 1.0})
    second = build_context(sess, cands, dataset_version="dsv1",
                           feature_versions=FV, policy_hashes=POL)
    assert second["to_evaluate"] == 0
    assert second["verdicts"]["EXACT_DUPLICATE"] == 2


def test_ask_memory_answers_without_reading_files(sess):
    for thr, z in ((0.5, 4.1), (1.0, 5.2), (1.5, 2.0)):
        _rec(sess, [Condition("FORM_PPG_DIFF.v1", ">=", thr)],
             result={"n_signals": 100, "z": z}, passed_threshold=z > 3)
    ans = what_do_we_know(sess, [Condition("FORM_PPG_DIFF.v1", ">=", 0.9)], "RES_HOME")
    assert ans["region"]["hypotheses_tested"] == 3
    assert ans["region"]["best_abs_z"] == 5.2
    assert ans["region"]["passed_threshold"] == 2
    assert ans["checked_before"] == 3


def test_meta_memory_accumulates_feature_performance(sess):
    for z, passed in ((5.0, True), (1.0, False), (4.0, True)):
        reg.update_meta(sess, C1, "RES_HOME", z=z, passed=passed)
    m = [x for x in reg.meta_summary(sess) if x["feature_id"] == "FORM_PPG_DIFF"][0]
    assert m["hypotheses"] == 3 and m["passed_threshold"] == 2
    assert m["best_abs_z"] == 5.0 and m["pass_rate"] == round(2 / 3, 3)
