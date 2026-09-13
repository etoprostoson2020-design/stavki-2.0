"""Отпечатки гипотез.

Документ 06 требует различать три вопроса, на которые память отвечает по-разному:

* **exact** — «это ровно тот же эксперимент на тех же данных и политиках?»
  Совпадение означает дубликат: считать заново нечего.
* **semantic** — «такая логика вообще уже проверялась?» Пороги и версии окон
  выброшены; остаются признак, направление и таргет. Совпадение означает, что
  мы ходили в эту область, пусть и с другими числами.
* **signal** — «а не то же ли это множество матчей?» Две формулы могут выглядеть
  по-разному и отбирать одни и те же матчи. Тогда это не два открытия, а одно.

Тот же вопрос на новых данных — не дубликат, а продолжение (rerun/extension):
поэтому dataset_version входит только в exact.
"""
from __future__ import annotations

from fsl.hashing import stable_hash


def _norm_conditions(conditions) -> list[dict]:
    out = []
    for c in conditions:
        d = c.as_dict() if hasattr(c, "as_dict") else dict(c)
        out.append({"feature": d["feature"], "op": d["op"],
                    "threshold": round(float(d["threshold"]), 6)})
    return sorted(out, key=lambda d: (d["feature"], d["op"], d["threshold"]))


def exact_fingerprint(conditions, target: str, dataset_version: str,
                      feature_versions: dict, policy_hashes: dict) -> str:
    """Полное совпадение: формула + данные + политики."""
    return stable_hash({
        "conditions": _norm_conditions(conditions), "target": target,
        "dataset_version": dataset_version,
        "feature_versions": dict(sorted(feature_versions.items())),
        "policies": dict(sorted(policy_hashes.items()))})


def semantic_fingerprint(conditions, target: str) -> str:
    """Логика без чисел: какой признак, в какую сторону, против какого исхода.

    Версия признака и порог отброшены намеренно — «то же самое, но с окном 10
    и порогом 1.2» должно узнаваться как уже исследованная область.
    """
    shape = sorted({(d["feature"].split(".")[0], d["op"])
                    for d in _norm_conditions(conditions)})
    return stable_hash({"shape": [list(x) for x in shape], "target": target})


def signal_fingerprint(fixture_ids) -> str:
    """Отпечаток самого множества сигналов."""
    return stable_hash(sorted(int(x) for x in fixture_ids))


def jaccard(a: set[int], b: set[int]) -> float:
    if not a and not b:
        return 1.0
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def region_key(conditions, target: str) -> str:
    """Ключ области поиска: семейство признака x направление x таргет.

    По нему индексируются исчерпанные регионы — не отдельные пороги, а участки
    пространства, где уже искали и не нашли.
    """
    fams = sorted({d["feature"].split(".")[0] for d in _norm_conditions(conditions)})
    ops = sorted({d["op"] for d in _norm_conditions(conditions)})
    return f"{'+'.join(fams)}|{''.join(ops)}|{target}"
