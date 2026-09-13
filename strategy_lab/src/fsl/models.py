"""Каноническая схема. Слои L0 RAW → L1/L2 CANONICAL → L4 FEATURES → L5 RESEARCH."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------- L0 RAW
class Source(Base):
    """Реестр источников. Ни один research-модуль не обращается к ним напрямую."""
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)      # FOOTBALL_DATA, API_FOOTBALL, USER_FILE
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))                   # HISTORICAL / LIVE / USER
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RawSnapshot(Base):
    """L0: неизменяемый оригинал того, что отдал источник."""
    __tablename__ = "raw_snapshots"
    __table_args__ = (UniqueConstraint("source_id", "league", "season", "sha256",
                                       name="uq_raw_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    league: Mapped[str] = mapped_column(String(16))
    season: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    n_rows: Mapped[int] = mapped_column(Integer)
    n_cols: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(Text)                       # URL или локальный путь
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    source: Mapped[Source] = relationship()


# ------------------------------------------------------- Entity resolution
class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(128), unique=True)
    country: Mapped[str] = mapped_column(String(64), default="ESP")


class TeamAlias(Base):
    """Team Alias Registry: разные написания одной команды у разных источников."""
    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("source_code", "alias", name="uq_alias_per_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    source_code: Mapped[str] = mapped_column(String(32))
    alias: Mapped[str] = mapped_column(String(128), index=True)

    team: Mapped[Team] = relationship()


# ---------------------------------------------------------- L2 CANONICAL
class Fixture(Base):
    """Канонический матч. Experiment Engine видит только это, не provider-записи."""
    __tablename__ = "fixtures"
    __table_args__ = (
        UniqueConstraint("league", "season", "home_team_id", "away_team_id",
                         name="uq_fixture_identity"),
        CheckConstraint("home_team_id <> away_team_id", name="ck_not_self_match"),
        CheckConstraint("kickoff_precision in ('EXACT','DATE_ONLY')", name="ck_kickoff_precision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    league: Mapped[str] = mapped_column(String(16), index=True)
    season: Mapped[str] = mapped_column(String(16), index=True)
    match_date: Mapped[dt.date] = mapped_column(Date, index=True)

    #: Всегда UTC. При DATE_ONLY час — соглашение, а не факт.
    kickoff_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    #: EXACT — время начала известно; DATE_ONLY — источник его не даёт.
    kickoff_precision: Mapped[str] = mapped_column(String(16))
    #: Синхронный блок: матчи одного блока не видят результатов друг друга.
    sync_batch: Mapped[int] = mapped_column(Integer, index=True)

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)

    fthg: Mapped[int | None] = mapped_column(Integer)
    ftag: Mapped[int | None] = mapped_column(Integer)
    ftr: Mapped[str | None] = mapped_column(String(1))
    hthg: Mapped[int | None] = mapped_column(Integer)
    htag: Mapped[int | None] = mapped_column(Integer)
    htr: Mapped[str | None] = mapped_column(String(1))
    #: Матчевая статистика. NULL означает «нет данных», никогда не 0.
    stats: Mapped[dict] = mapped_column(JSON, default=dict)

    #: provenance по каждому значимому полю: {field: {"source": code, "raw": value}}
    source_lineage: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_grade: Mapped[str] = mapped_column(String(8), default="A")
    conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    dataset_version: Mapped[str] = mapped_column(String(32), index=True)

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])


class SourceConflict(Base):
    """Расхождения источников. Молча не усредняются."""
    __tablename__ = "source_conflicts"
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"))
    field: Mapped[str] = mapped_column(String(64))
    values_by_source: Mapped[dict] = mapped_column(JSON)
    resolution: Mapped[str] = mapped_column(String(32), default="NO_AUTOMATIC_MERGE")
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ------------------------------------------------------------ Data Audit
class DataAuditReport(Base):
    __tablename__ = "data_audit_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    league: Mapped[str] = mapped_column(String(16))
    dataset_version: Mapped[str] = mapped_column(String(32), index=True)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    n_violations: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    report_hash: Mapped[str] = mapped_column(String(32))


# ------------------------------------------------------- Holdout Ledger
class HoldoutLedger(Base):
    """Разбор архитектуры, пункт 2: система обязана знать остаток неоткрытых сезонов.

    Обратного закрытия сезона не существует: SEEN нельзя вернуть в UNSEEN.
    """
    __tablename__ = "holdout_ledger"
    __table_args__ = (
        UniqueConstraint("league", "season", name="uq_holdout_season"),
        CheckConstraint("state in ('UNSEEN','SEEN')", name="ck_holdout_state"),
        CheckConstraint("block in ('DISCOVERY','VALIDATION','TEST')", name="ck_holdout_block"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    league: Mapped[str] = mapped_column(String(16), index=True)
    season: Mapped[str] = mapped_column(String(16))
    block: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), default="UNSEEN")
    opened_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    opened_by: Mapped[str | None] = mapped_column(String(128))
    note: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------- L4 FEATURES
class FeatureDefinition(Base):
    """Feature Registry по документу 03."""
    __tablename__ = "feature_definitions"
    __table_args__ = (UniqueConstraint("feature_id", "version", name="uq_feature_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(128))
    family: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    window: Mapped[int | None] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(16))                  # ALL / HOME_ONLY / AWAY_ONLY
    season_transition: Mapped[str] = mapped_column(String(24))      # SEASON_RESET / ROLLING_CONTINUOUS
    minimum_history: Mapped[int] = mapped_column(Integer)
    missing_data_policy: Mapped[str] = mapped_column(String(32), default="UNAVAILABLE")
    status: Mapped[str] = mapped_column(String(16), default="EXPERIMENTAL")
    leakage_test_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    definition_hash: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------- L5 RESEARCH
class Experiment(Base):
    """Immutable. Изменение входов создаёт новый experiment, а не правит этот."""
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    hypothesis: Mapped[str] = mapped_column(Text)
    league: Mapped[str] = mapped_column(String(16))
    seasons: Mapped[list] = mapped_column(JSON)
    target: Mapped[str] = mapped_column(String(64))
    conditions: Mapped[list] = mapped_column(JSON)

    n_eligible: Mapped[int] = mapped_column(Integer)
    n_signals: Mapped[int] = mapped_column(Integer)
    n_successes: Mapped[int] = mapped_column(Integer)
    signal_frequency: Mapped[float] = mapped_column(Float)
    baseline: Mapped[float] = mapped_column(Float)
    hit_rate: Mapped[float] = mapped_column(Float)
    absolute_uplift: Mapped[float] = mapped_column(Float)
    relative_uplift: Mapped[float] = mapped_column(Float)
    ci95_low: Mapped[float] = mapped_column(Float)
    ci95_high: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    per_season: Mapped[dict] = mapped_column(JSON)
    per_team_concentration: Mapped[dict] = mapped_column(JSON)

    dataset_version: Mapped[str] = mapped_column(String(32), index=True)
    feature_versions: Mapped[dict] = mapped_column(JSON)
    environment_lock: Mapped[dict] = mapped_column(JSON)
    policy_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="COMPLETED")
    result_hash: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ------------------------------------------------------- Validation (фаза 6)
class SearchBatchRecord(Base):
    """Единица учёта множественного тестирования.

    Порог значимости принадлежит батчу: он зависит от числа проверенных
    гипотез и их взаимной корреляции. Хранится вместе с батчем, а не глобально.
    """
    __tablename__ = "search_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    research_question: Mapped[str] = mapped_column(Text)
    league: Mapped[str] = mapped_column(String(16))
    seasons: Mapped[list] = mapped_column(JSON)
    n_candidates: Mapped[int] = mapped_column(Integer)
    n_negative_controls: Mapped[int] = mapped_column(Integer)
    dataset_version: Mapped[str] = mapped_column(String(32), index=True)
    statistical_policy_hash: Mapped[str] = mapped_column(String(32))
    null_world: Mapped[dict] = mapped_column(JSON)
    fwer_threshold: Mapped[float] = mapped_column(Float)
    n_passing: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Strategy(Base):
    """Отобранная сущность. Не каждый эксперимент получает Strategy ID."""
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(160))
    league: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(64))
    conditions: Mapped[list] = mapped_column(JSON)
    feature_versions: Mapped[dict] = mapped_column(JSON)

    #: Заморозка. Хэш критерия хранится наравне с хэшем формулы.
    formula_hash: Mapped[str] = mapped_column(String(32))
    strategy_hash: Mapped[str] = mapped_column(String(32), index=True)
    qualification_policy_hash: Mapped[str] = mapped_column(String(32))
    statistical_policy_hash: Mapped[str] = mapped_column(String(32))
    seen_seasons: Mapped[list] = mapped_column(JSON)
    frozen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))

    stage: Mapped[str] = mapped_column(String(24), default="CANDIDATE")
    strategy_class: Mapped[str] = mapped_column(String(24), default="CANDIDATE")
    action: Mapped[str | None] = mapped_column(String(16))
    park_kill_reason: Mapped[str | None] = mapped_column(Text)
    parent_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ValidationRun(Base):
    """Immutable запись одного прогона валидации."""
    __tablename__ = "validation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    strategy_hash: Mapped[str] = mapped_column(String(32))
    batch_id: Mapped[str | None] = mapped_column(String(32), index=True)

    engine_version: Mapped[str] = mapped_column(String(48), default="")
    oos_seasons: Mapped[list] = mapped_column(JSON)
    #: VALID_OOS или REPLAY_OF_SEEN. Второе не может дать ROBUST.
    oos_validity: Mapped[str] = mapped_column(String(24))
    outcome: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16))
    strategy_class: Mapped[str] = mapped_column(String(24))
    fwer_threshold: Mapped[float | None] = mapped_column(Float)
    criterion: Mapped[dict] = mapped_column(JSON)
    discovery: Mapped[dict] = mapped_column(JSON)
    oos: Mapped[dict] = mapped_column(JSON)
    robustness: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[list] = mapped_column(JSON)
    run_hash: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------- Research Memory (фаза 7)
class HypothesisRecord(Base):
    """Experiment Registry: практически всё, что проверялось, с отпечатками.

    Не каждая запись получает Strategy ID. Здесь лежит и то, что провалилось, —
    негативное знание не удаляется никогда.
    """
    __tablename__ = "hypothesis_registry"
    __table_args__ = (UniqueConstraint("exact_fingerprint", name="uq_exact_fingerprint"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    league: Mapped[str] = mapped_column(String(16), index=True)
    seasons: Mapped[list] = mapped_column(JSON)
    target: Mapped[str] = mapped_column(String(64), index=True)
    conditions: Mapped[list] = mapped_column(JSON)
    feature_versions: Mapped[dict] = mapped_column(JSON)

    exact_fingerprint: Mapped[str] = mapped_column(String(32), index=True)
    semantic_fingerprint: Mapped[str] = mapped_column(String(32), index=True)
    signal_fingerprint: Mapped[str | None] = mapped_column(String(32), index=True)
    region_key: Mapped[str] = mapped_column(String(160), index=True)

    origin: Mapped[str] = mapped_column(String(32), default="RULE_GENERATOR")
    batch_id: Mapped[str | None] = mapped_column(String(32), index=True)

    #: Поля генератора (фаза 8). Родословная мутаций живёт здесь.
    hypothesis_key: Mapped[str | None] = mapped_column(String(320), index=True)
    parent_hypothesis_key: Mapped[str | None] = mapped_column(String(320), index=True)
    htype: Mapped[str | None] = mapped_column(String(24))
    mode: Mapped[str | None] = mapped_column(String(24))
    complexity: Mapped[int | None] = mapped_column(Integer)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    mutation_reason: Mapped[str | None] = mapped_column(Text)
    dataset_version: Mapped[str] = mapped_column(String(32), index=True)

    n_signals: Mapped[int | None] = mapped_column(Integer)
    baseline: Mapped[float | None] = mapped_column(Float)
    hit_rate: Mapped[float | None] = mapped_column(Float)
    absolute_uplift: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float)
    passed_batch_threshold: Mapped[bool | None] = mapped_column(Boolean)

    status: Mapped[str] = mapped_column(String(24), default="EVALUATED")
    strategy_id: Mapped[str | None] = mapped_column(String(32), index=True)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StrategySignalSet(Base):
    """Множество сигналов отобранной стратегии — для Jaccard и семейств.

    Хранится только для того, что попало в Strategy Registry: для всех
    экспериментов это было бы дорого и не нужно (документ 06).
    """
    __tablename__ = "strategy_signal_sets"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    dataset_version: Mapped[str] = mapped_column(String(32))
    fixture_ids: Mapped[list] = mapped_column(JSON)
    signal_fingerprint: Mapped[str] = mapped_column(String(32), index=True)


class StrategyFamily(Base):
    """Кластер близких механизмов. Коррелированные стратегии — не независимые открытия."""
    __tablename__ = "strategy_families"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160))
    members: Mapped[list] = mapped_column(JSON)
    max_pairwise_jaccard: Mapped[float] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ParkRecord(Base):
    """PARK: идея жива, но ждёт условия. Ничего не удаляется."""
    __tablename__ = "park_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    revival_condition: Mapped[str] = mapped_column(Text)
    #: Сколько новых матчей должно появиться, прежде чем возвращаться к идее.
    min_new_fixtures: Mapped[int] = mapped_column(Integer, default=0)
    #: Снимок объёма данных на момент парковки — база для сравнения.
    fixtures_at_park: Mapped[int] = mapped_column(Integer, default=0)
    review_after: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    priority: Mapped[int] = mapped_column(Integer, default=5)
    revived_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class KillRecord(Base):
    """KILL: ветвь признана бесперспективной. Причина хранится вечно."""
    __tablename__ = "kill_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(48))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)
    policy_version: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExhaustedRegion(Base):
    """Участок пространства поиска, где уже искали и не нашли.

    Ретест разрешён только при реальном изменении данных, признака, версии,
    сезона или метода — иначе генератор будет ходить по кругу.
    """
    __tablename__ = "exhausted_regions"
    __table_args__ = (UniqueConstraint("region_key", "dataset_version",
                                       name="uq_region_dataset"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    region_key: Mapped[str] = mapped_column(String(160), index=True)
    league: Mapped[str] = mapped_column(String(16))
    dataset_version: Mapped[str] = mapped_column(String(32))
    hypotheses_tested: Mapped[int] = mapped_column(Integer)
    best_abs_z: Mapped[float] = mapped_column(Float)
    batch_threshold: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MetaFeatureStat(Base):
    """Meta Memory: что признак приносил лаборатории за всю историю."""
    __tablename__ = "meta_feature_stats"
    __table_args__ = (UniqueConstraint("feature_id", "target", name="uq_meta_feature_target"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(64))
    hypotheses: Mapped[int] = mapped_column(Integer, default=0)
    passed_threshold: Mapped[int] = mapped_column(Integer, default=0)
    candidates: Mapped[int] = mapped_column(Integer, default=0)
    robust: Mapped[int] = mapped_column(Integer, default=0)
    killed: Mapped[int] = mapped_column(Integer, default=0)
    parked: Mapped[int] = mapped_column(Integer, default=0)
    best_abs_z: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DecisionAudit(Base):
    """Рекомендация машины и решение человека хранятся раздельно."""
    __tablename__ = "decision_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32))     # STRATEGY / BATCH / REGION
    subject_id: Mapped[str] = mapped_column(String(48), index=True)
    machine_recommendation: Mapped[str] = mapped_column(String(32))
    human_override: Mapped[str | None] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(64), default="machine")
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GenerationRun(Base):
    """Прогон генератора. Воспроизводим по seed при тех же данных и памяти."""
    __tablename__ = "generation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    research_question: Mapped[str] = mapped_column(Text)
    league: Mapped[str] = mapped_column(String(16))
    dataset_version: Mapped[str] = mapped_column(String(32), index=True)
    search_policy_hash: Mapped[str] = mapped_column(String(32))
    seed: Mapped[int] = mapped_column(Integer)
    mode_mix: Mapped[dict] = mapped_column(JSON)
    n_pool: Mapped[int] = mapped_column(Integer)
    n_emitted: Mapped[int] = mapped_column(Integer)
    n_skipped: Mapped[int] = mapped_column(Integer)
    memory_verdicts: Mapped[dict] = mapped_column(JSON)
    budget: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
