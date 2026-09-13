"""Data Acquisition Manager. Только он ходит во внешний мир.

Эксперименты никогда не делают сетевых запросов сами (документ 02).
"""
from __future__ import annotations

import dataclasses as dc
from pathlib import Path


@dc.dataclass(frozen=True)
class FetchResult:
    league: str
    season: str
    path: Path
    sha256: str
    size_bytes: int
    origin: str
    reused: bool          # True — снапшот уже был, повторно не качали


class SourceAdapter:
    code: str = "ABSTRACT"

    def fetch_season(self, league: str, season: str, *, local_file: Path | None = None) -> FetchResult:
        raise NotImplementedError
