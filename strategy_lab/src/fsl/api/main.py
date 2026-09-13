"""Backend API. Группы по документу 09."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select, text

from fsl import logging as fsl_logging
from fsl.db import session
from fsl.hashing import environment_lock, environment_lock_hash
from fsl.models import (DataAuditReport, Experiment, Fixture, RawSnapshot,
                        SearchBatchRecord, Strategy, Team, ValidationRun)
from fsl.research.holdout import remaining
from fsl.validation.policy import qualification_policy, statistical_policy
from fsl.settings import get_settings

settings = get_settings()
fsl_logging.configure(settings.log_level)

app = FastAPI(title="Football Strategy Lab", version="0.1.0",
              description="Исследовательская лаборатория футбольных стратегий")


@app.get("/system/health")
def health():
    db_ok = True
    try:
        with session() as s:
            s.execute(text("select 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "env": settings.env,
            "database": db_ok, "environment_lock_hash": environment_lock_hash()}


@app.get("/system/config")
def config():
    return {"settings": settings.safe_dump(), "environment_lock": environment_lock()}


@app.get("/data/snapshots")
def snapshots():
    with session() as s:
        rows = s.scalars(select(RawSnapshot).order_by(RawSnapshot.season)).all()
        return [{"league": r.league, "season": r.season, "rows": r.n_rows,
                 "cols": r.n_cols, "sha256": r.sha256[:16], "origin": r.origin}
                for r in rows]


@app.get("/data/audit/{league}")
def audit(league: str):
    with session() as s:
        rep = s.scalars(select(DataAuditReport).where(DataAuditReport.league == league)
                        .order_by(DataAuditReport.generated_at.desc())).first()
        if rep is None:
            raise HTTPException(404, "аудит для этой лиги ещё не выполнялся")
        return rep.payload


@app.get("/data/summary")
def summary():
    with session() as s:
        n_fix = s.scalar(select(func.count()).select_from(Fixture))
        n_team = s.scalar(select(func.count()).select_from(Team))
        return {"fixtures": n_fix, "teams": n_team}


@app.get("/research/holdout/{league}")
def holdout(league: str):
    with session() as s:
        return remaining(s, league)


@app.get("/experiments")
def experiments(limit: int = 50):
    with session() as s:
        rows = s.scalars(select(Experiment).order_by(Experiment.created_at.desc())
                         .limit(limit)).all()
        return [{"experiment_id": r.experiment_id, "hypothesis": r.hypothesis,
                 "target": r.target, "n_signals": r.n_signals,
                 "baseline": round(r.baseline, 4), "hit_rate": round(r.hit_rate, 4),
                 "absolute_uplift": round(r.absolute_uplift, 4), "z": round(r.z, 2),
                 "result_hash": r.result_hash} for r in rows]


@app.get("/research/policies")
def policies():
    """Хэши политик. Критерий прохода версионируется наравне с формулой."""
    q, st = qualification_policy(), statistical_policy()
    return {p.name: {"version": p.version, "hash": p.hash} for p in (q, st)}


@app.get("/research/batches")
def batches(limit: int = 50):
    with session() as s:
        rows = s.scalars(select(SearchBatchRecord)
                         .order_by(SearchBatchRecord.created_at.desc()).limit(limit)).all()
        return [{"batch_id": r.batch_id, "question": r.research_question,
                 "candidates": r.n_candidates, "negative_controls": r.n_negative_controls,
                 "fwer_threshold": r.fwer_threshold, "passing": r.n_passing,
                 "null_world": r.null_world} for r in rows]


@app.get("/strategies")
def strategies(limit: int = 50):
    with session() as s:
        rows = s.scalars(select(Strategy).order_by(Strategy.created_at.desc())
                         .limit(limit)).all()
        return [{"strategy_id": r.strategy_id, "version": r.version, "name": r.name,
                 "stage": r.stage, "class": r.strategy_class, "action": r.action,
                 "target": r.target, "conditions": r.conditions,
                 "strategy_hash": r.strategy_hash,
                 "qualification_policy_hash": r.qualification_policy_hash,
                 "reason": r.park_kill_reason} for r in rows]


@app.get("/research/validation-runs")
def validation_runs(limit: int = 50):
    with session() as s:
        rows = s.scalars(select(ValidationRun).order_by(ValidationRun.created_at.desc())
                         .limit(limit)).all()
        return [{"run_id": r.run_id, "strategy_id": r.strategy_id,
                 "oos_seasons": r.oos_seasons, "oos_validity": r.oos_validity,
                 "outcome": r.outcome, "action": r.action, "class": r.strategy_class,
                 "fwer_threshold": r.fwer_threshold, "criterion": r.criterion,
                 "notes": r.notes} for r in rows]


# ------------------------------------------------------ Research Memory (фаза 7)
@app.get("/memory/stats")
def memory_stats():
    from fsl.memory import registry as _reg
    with session() as s:
        return _reg.registry_stats(s)


@app.get("/memory/features")
def memory_features():
    """Meta Memory: что каждый признак принёс лаборатории за всю историю."""
    from fsl.memory import registry as _reg
    with session() as s:
        return _reg.meta_summary(s)


@app.get("/memory/exhausted")
def memory_exhausted():
    from fsl.memory import regions as _rg
    with session() as s:
        return _rg.list_exhausted(s)


@app.get("/memory/revival")
def memory_revival():
    from fsl.memory import lifecycle as _lc
    with session() as s:
        return _lc.revival_candidates(s)


@app.get("/memory/families")
def memory_families():
    from fsl.memory import families as _fam
    with session() as s:
        return {"families": _fam.rebuild_families(s),
                "similarity": _fam.similarity_matrix(s)}


@app.get("/memory/failures/{strategy_id}")
def memory_failures(strategy_id: str):
    from fsl.memory import lifecycle as _lc
    with session() as s:
        return _lc.failure_history(s, strategy_id)


@app.get("/memory/ask")
def memory_ask(feature: str, op: str, threshold: float, target: str):
    """«Мы это уже проверяли и чем кончилось?» — одним запросом."""
    from fsl.experiments.engine import Condition
    from fsl.memory.context import what_do_we_know
    if op not in (">=", "<="):
        raise HTTPException(400, "op должен быть >= или <=")
    with session() as s:
        return what_do_we_know(s, [Condition(feature, op, threshold)], target)


# ------------------------------------------------ Hypothesis Generator (фаза 8)
@app.get("/research/generation-runs")
def generation_runs(limit: int = 50):
    from fsl.models import GenerationRun
    with session() as s:
        rows = s.scalars(select(GenerationRun)
                         .order_by(GenerationRun.created_at.desc()).limit(limit)).all()
        return [{"batch_key": r.batch_key, "question": r.research_question,
                 "seed": r.seed, "pool": r.n_pool, "emitted": r.n_emitted,
                 "skipped": r.n_skipped, "memory_verdicts": r.memory_verdicts,
                 "budget": r.budget, "mode_mix": r.mode_mix,
                 "search_policy_hash": r.search_policy_hash} for r in rows]


@app.get("/research/lineage/{hypothesis_key:path}")
def hypothesis_lineage(hypothesis_key: str):
    """Родословная гипотезы: от корня до текущей мутации."""
    from fsl.models import HypothesisRecord
    with session() as s:
        chain, seen, cur = [], set(), hypothesis_key
        while cur and cur not in seen:
            seen.add(cur)
            rec = s.scalar(select(HypothesisRecord).where(
                HypothesisRecord.hypothesis_key == cur))
            if rec is None:
                break
            chain.append({"hypothesis_key": rec.hypothesis_key,
                          "origin": rec.origin, "generation": rec.generation,
                          "mutation_reason": rec.mutation_reason, "z": rec.z})
            cur = rec.parent_hypothesis_key
        if not chain:
            raise HTTPException(404, "гипотеза не найдена в реестре")
        return {"lineage": list(reversed(chain))}
