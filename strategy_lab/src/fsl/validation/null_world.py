"""Null World на каждый батч.

Документы 01 и 04 говорят «периодически». Это ошибка: порог зависит от размера
и корреляционной структуры конкретного батча. Замер на реальных масках Ла Лиги
дал 4.17 при 2500 кандидатах и 5.66 при 214150 — фиксированный порог на большом
батче пропускает мусор, на малом режет живое.

Здесь null-world обязателен для каждого батча, и его результат становится
частью записи о батче.
"""
from __future__ import annotations

import dataclasses as dc

import numpy as np

from fsl.logging import get_logger
from fsl.validation.search_batch import BatchMatrices, z_scores

log = get_logger(__name__)


@dc.dataclass
class NullWorldResult:
    method: str
    worlds: int
    fwer_threshold: float
    median_max_z: float
    max_abs_z_real: float
    n_real_passing: int
    n_negative_controls: int
    n_negative_passing: int
    max_abs_z_negative: float | None
    percentile: int

    def as_dict(self) -> dict:
        return dc.asdict(self)


def _permute_within_season(seasons: np.ndarray, rng: np.random.Generator,
                           method: str) -> np.ndarray:
    idx = np.arange(len(seasons))
    out = idx.copy()
    for s in np.unique(seasons):
        pos = np.where(seasons == s)[0]
        if method == "circular_shift_within_season":
            out[pos] = np.roll(pos, int(rng.integers(1, max(len(pos), 2))))
        else:
            out[pos] = rng.permutation(pos)
    return out


def run_null_world(bm: BatchMatrices, *, worlds: int = 300,
                   method: str = "circular_shift_within_season",
                   percentile: int = 95, seed: int = 2024) -> NullWorldResult:
    """Прогоняет весь батч по нулевым мирам и возвращает порог FWER.

    Сравнивается не отдельная стратегия, а поиск целиком: max|z| по всему
    батчу в каждом мире (документ 05).
    """
    rng = np.random.default_rng(seed)
    maxima = np.empty(worlds, dtype=np.float64)
    for r in range(worlds):
        perm = _permute_within_season(bm.season_of_fixture, rng, method)
        z = z_scores(bm, targets=bm.targets[:, perm])
        maxima[r] = np.nanmax(np.abs(z))

    thr = float(np.percentile(maxima, percentile))
    z_real = z_scores(bm)
    az = np.abs(z_real)

    kinds = np.array([c.kind for c in bm.candidates])
    is_neg = kinds != "REAL"
    n_neg = int(is_neg.sum())

    res = NullWorldResult(
        method=method, worlds=worlds, fwer_threshold=round(thr, 2),
        median_max_z=round(float(np.median(maxima)), 2),
        max_abs_z_real=round(float(np.nanmax(az[~is_neg])) if (~is_neg).any() else float("nan"), 2),
        n_real_passing=int(np.nansum(az[~is_neg] >= thr)),
        n_negative_controls=n_neg,
        n_negative_passing=int(np.nansum(az[is_neg] >= thr)) if n_neg else 0,
        max_abs_z_negative=round(float(np.nanmax(az[is_neg])), 2) if n_neg else None,
        percentile=percentile)
    log.info("null_world.done", method=method, worlds=worlds,
             threshold=res.fwer_threshold, real_passing=res.n_real_passing,
             negative_passing=res.n_negative_passing)
    return res


def make_negative_controls(feature_values: dict[int, dict[str, float | None]],
                           fixture_ids: list[int], *, n_permuted: int = 25,
                           n_noise: int = 15, seed: int = 11
                           ) -> dict[str, np.ndarray]:
    """Перестановки реальных признаков и чистый шум.

    Ни один не обязан пройти порог. Прошедший — отказ батча целиком.
    """
    rng = np.random.default_rng(seed)
    keys = sorted({k for v in feature_values.values() for k in v})
    out: dict[str, np.ndarray] = {}

    for i in range(n_permuted):
        key = keys[i % len(keys)]
        col = np.array([feature_values.get(fid, {}).get(key, np.nan)
                        for fid in fixture_ids], dtype=np.float64)
        col = np.array([np.nan if v is None else v for v in col], dtype=np.float64)
        ok = ~np.isnan(col)
        shuffled = col.copy()
        shuffled[ok] = rng.permutation(col[ok])
        centred = shuffled - np.nanmedian(shuffled)      # порог контроля = медиана
        out[f"NEG_perm_{i:02d}_{key}"] = centred

    for i in range(n_noise):
        out[f"NEG_noise_{i:02d}"] = rng.normal(size=len(fixture_ids))
    return out
