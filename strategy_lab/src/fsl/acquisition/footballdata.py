"""Football-Data.co.uk. Обязательный независимый исторический источник."""
from __future__ import annotations

import shutil
from pathlib import Path

import httpx

from fsl.acquisition.base import FetchResult, SourceAdapter
from fsl.hashing import file_sha256
from fsl.logging import get_logger
from fsl.settings import get_settings

log = get_logger(__name__)

#: Код дивизиона Football-Data → внутренний код лиги.
DIVISION = {"SP1": "ESP_1", "E0": "ENG_1", "I1": "ITA_1", "D1": "GER_1", "F1": "FRA_1"}
DIVISION_BY_LEAGUE = {v: k for k, v in DIVISION.items()}


def season_to_path_token(season: str) -> str:
    """'23-24' -> '2324' — так устроены URL источника."""
    a, b = season.split("-")
    return f"{a}{b}"


class FootballDataAdapter(SourceAdapter):
    code = "FOOTBALL_DATA"

    def __init__(self, settings=None):
        self.s = settings or get_settings()
        self.s.ensure_dirs()

    def _target(self, league: str, season: str) -> Path:
        d = self.s.raw_dir / self.code / league / season
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{DIVISION_BY_LEAGUE[league]}.csv"

    def fetch_season(self, league: str, season: str, *, local_file: Path | None = None) -> FetchResult:
        """Скачивает сезон или принимает локальный файл.

        Повторно не качает: если снапшот на месте, возвращает его с reused=True.
        """
        target = self._target(league, season)

        if target.exists():
            sha = file_sha256(target)
            log.info("raw.reuse", league=league, season=season, sha256=sha[:16])
            return FetchResult(league, season, target, sha, target.stat().st_size,
                               origin=f"cached:{target}", reused=True)

        if local_file is not None:
            src = Path(local_file)
            if not src.exists():
                raise FileNotFoundError(f"локальный файл не найден: {src}")
            shutil.copyfile(src, target)
            origin = f"file:{src}"
        else:
            url = (f"{self.s.footballdata_base_url}/"
                   f"{season_to_path_token(season)}/{DIVISION_BY_LEAGUE[league]}.csv")
            log.info("raw.download", url=url)
            with httpx.Client(timeout=60, follow_redirects=True) as c:
                r = c.get(url)
                r.raise_for_status()
                target.write_bytes(r.content)
            origin = url

        sha = file_sha256(target)
        log.info("raw.stored", league=league, season=season, sha256=sha[:16],
                 bytes=target.stat().st_size)
        return FetchResult(league, season, target, sha, target.stat().st_size,
                           origin=origin, reused=False)
