"""Celery. Логические очереди: data, features, experiments, validation."""
from __future__ import annotations

from celery import Celery

from fsl.settings import get_settings

s = get_settings()
app = Celery("fsl", broker=s.redis_url, backend=s.redis_url,
             include=["fsl.worker.tasks"])
app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="data",
    task_routes={
        "fsl.worker.tasks.import_season": {"queue": "data"},
        "fsl.worker.tasks.build_features": {"queue": "features"},
        "fsl.worker.tasks.run_experiment_task": {"queue": "experiments"},
    },
    timezone="UTC",
)
