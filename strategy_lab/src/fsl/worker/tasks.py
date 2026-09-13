"""Задачи воркера. Эксперименты никогда не ходят в сеть сами."""
from __future__ import annotations

from fsl.acquisition.manager import import_seasons
from fsl.db import session
from fsl.logging import get_logger
from fsl.worker.celery_app import app

log = get_logger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=30)
def import_season(self, league: str, season: str) -> dict:
    try:
        with session() as s:
            snaps = import_seasons(s, league, [season])
            return {"league": league, "season": season, "sha256": snaps[0].sha256[:16]}
    except Exception as exc:                      # retry/backoff по документу 02
        raise self.retry(exc=exc)


@app.task
def build_features(league: str, seasons: list[str]) -> dict:
    from scripts.run_slice import slice_features
    return slice_features(league, seasons)


@app.task
def run_experiment_task(league: str, seasons: list[str]) -> dict:
    from scripts.run_slice import main
    return main(league=league, seasons=seasons, persist=True)
