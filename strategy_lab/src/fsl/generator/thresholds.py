"""Сетка порогов.

Документ 04: начальная сетка грубая. Тонкое соседство разрешено только вокруг
уже многообещающего кандидата и служит проверкой устойчивости, а не скрытой
оптимизацией — поэтому оно требует явного родителя.
"""
from __future__ import annotations

import numpy as np


def coarse_grid(values: dict[int, dict[str, float | None]], feature_key: str,
                quantiles: list[float]) -> list[tuple[str, float]]:
    """Квантильные пороги признака. Ниже медианы — '<=', выше — '>='."""
    col = np.array([v[feature_key] for v in values.values()
                    if v.get(feature_key) is not None], dtype=float)
    if col.size < 100:
        return []
    out = []
    for q in quantiles:
        thr = float(np.round(np.quantile(col, q), 3))
        out.append(("<=" if q < 0.5 else ">=", thr))
    # разные квантили могут дать один порог после округления
    seen, uniq = set(), []
    for op, thr in out:
        if (op, thr) in seen:
            continue
        seen.add((op, thr))
        uniq.append((op, thr))
    return uniq


def fine_neighborhood(op: str, threshold: float, deltas: list[float]
                      ) -> list[tuple[str, float]]:
    """Шаги вокруг заявленного порога. Только для проверки устойчивости."""
    return [(op, round(threshold + d, 4)) for d in deltas]
