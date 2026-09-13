"""Backend API. Группы по документу 09."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select, text

from fsl import logging as fsl_logging
from fsl.db import session
from fsl.hashing import environment_lock, environment_lock_hash
from fsl.models import DataAuditReport, Experiment, Fixture, RawSnapshot, Team
from fsl.research.holdout import remaining
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
