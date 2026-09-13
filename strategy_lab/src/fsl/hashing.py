"""Канонический хэш и лок окружения.

Разбор архитектуры, пункт 5: воспроизводимость хэша нельзя строить на сырых
float. Версии библиотек и порядок арифметики меняют последний знак, и это
неотличимо от изменения правила. Поэтому:

* всякое число перед хэшированием приводится к строке с фиксированным числом
  знаков (`canonical`);
* лок окружения входит в `dataset_version` и в `result_hash`.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import math
from typing import Any

ROUND_NDIGITS = 6

#: Пакеты, версия которых способна изменить численный результат.
NUMERIC_PACKAGES = ("numpy", "pandas", "scipy", "pyarrow", "duckdb")


def canonical(value: Any) -> Any:
    """Приводит значение к форме, устойчивой к версии библиотек."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        # format, а не round: убирает представимость двоичной дроби
        return format(round(value, ROUND_NDIGITS), f".{ROUND_NDIGITS}f")
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    if hasattr(value, "item"):  # numpy-скаляры
        return canonical(value.item())
    return str(value)


def stable_hash(payload: Any, length: int = 16) -> str:
    blob = json.dumps(canonical(payload), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:length]


def environment_lock() -> dict[str, str]:
    """Версии пакетов, влияющих на численный результат."""
    out = {}
    for pkg in NUMERIC_PACKAGES:
        try:
            out[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            out[pkg] = "absent"
    return out


def environment_lock_hash(length: int = 12) -> str:
    return stable_hash(environment_lock(), length)


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
