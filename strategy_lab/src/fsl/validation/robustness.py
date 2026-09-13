"""Проверки устойчивости (документ 05).

Ни одна из них не «доказывает» стратегию. Их задача — показать, чем результат
держится: реальным механизмом или одной командой, одним сезоном, одним удачно
подобранным порогом.
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np

from fsl.experiments.engine import TARGETS, Condition


def _outcomes(fixtures, feature_values, conditions, target):
    tf = TARGETS[target]
    rows = []
    for f in fixtures:
        y = tf(f)
        if y is None:
            continue
        vals = feature_values.get(f["fixture_id"], {})
        verdicts = [c.holds(vals.get(c.feature_key)) for c in conditions]
        if any(v is None for v in verdicts):
            rows.append((f, y, None))          # NOT_ELIGIBLE
        else:
            rows.append((f, y, bool(all(verdicts))))
    return rows


def _rate(pairs):
    return (sum(y for _, y in pairs) / len(pairs)) if pairs else None


def walk_forward(fixtures, feature_values, conditions, target, *, warmup: int = 200):
    """Базлайн берётся только из прошлого, экспандирующим окном по блокам."""
    rows = [(f, y, s) for f, y, s in _outcomes(fixtures, feature_values, conditions, target)
            if s is not None]
    rows.sort(key=lambda r: (r[0]["sync_batch"], r[0]["fixture_id"]))
    seen_sum = seen_n = 0
    diffs = []
    for f, y, sig in rows:
        if seen_n >= warmup and sig:
            diffs.append(y - seen_sum / seen_n)
        seen_sum += y
        seen_n += 1
    return {"n": len(diffs),
            "uplift": round(float(np.mean(diffs)), 4) if diffs else None}


def season_breakdown(fixtures, feature_values, conditions, target):
    rows = _outcomes(fixtures, feature_values, conditions, target)
    out = {}
    for season in sorted({f["season"] for f, _, _ in rows}):
        elig = [(f, y) for f, y, s in rows if s is not None and f["season"] == season]
        sig = [(f, y) for f, y, s in rows if s and f["season"] == season]
        b, h = _rate(elig), _rate(sig)
        out[season] = {"n_signals": len(sig), "baseline": b, "hit_rate": h,
                       "uplift": None if b is None or h is None else round(h - b, 4)}
    return out


def team_concentration(fixtures, feature_values, conditions, target):
    rows = _outcomes(fixtures, feature_values, conditions, target)
    sig = [f for f, _, s in rows if s]
    counts = Counter()
    for f in sig:
        counts[f["home_team"]] += 1
        counts[f["away_team"]] += 1
    if not sig:
        return {"distinct_teams": 0, "top1_share": None, "top5_share": None}
    top = counts.most_common(5)
    return {"distinct_teams": len(counts),
            "top1_share": round(top[0][1] / (2 * len(sig)), 4),
            "top5_share": round(sum(c for _, c in top) / (2 * len(sig)), 4),
            "top5": [{"team": t, "signals": c} for t, c in top]}


def leave_one_team_out(fixtures, feature_values, conditions, target, *, min_signals: int = 30):
    """Убираем по одной команде: не держится ли эффект на ней одной."""
    rows = _outcomes(fixtures, feature_values, conditions, target)
    teams = sorted({t for f, _, _ in rows for t in (f["home_team"], f["away_team"])})
    uplifts = {}
    for team in teams:
        elig = [(f, y) for f, y, s in rows
                if s is not None and team not in (f["home_team"], f["away_team"])]
        sig = [(f, y) for f, y, s in rows
               if s and team not in (f["home_team"], f["away_team"])]
        if len(sig) < min_signals:
            continue
        b, h = _rate(elig), _rate(sig)
        uplifts[team] = round(h - b, 4)
    if not uplifts:
        return {"evaluated_teams": 0, "min_uplift": None, "max_uplift": None,
                "sign_stable": None}
    vals = list(uplifts.values())
    return {"evaluated_teams": len(vals), "min_uplift": min(vals), "max_uplift": max(vals),
            "sign_stable": all(v > 0 for v in vals) or all(v < 0 for v in vals),
            "worst_team": min(uplifts, key=uplifts.get)}


def parameter_neighborhood(fixtures, feature_values, conditions, target,
                           *, deltas=(-0.2, -0.1, 0.1, 0.2), min_signals: int = 30):
    """Порог сдвигается вокруг заявленного. Устойчивый эффект не исчезает от шага."""
    if len(conditions) != 1:
        return {"supported": False, "reason": "поддерживается только одно условие"}
    base_c = conditions[0]
    grid = []
    for d in (0.0, *deltas):
        cond = Condition(base_c.feature_key, base_c.op, round(base_c.threshold + d, 4))
        rows = _outcomes(fixtures, feature_values, [cond], target)
        elig = [(f, y) for f, y, s in rows if s is not None]
        sig = [(f, y) for f, y, s in rows if s]
        if len(sig) < min_signals:
            grid.append({"threshold": cond.threshold, "n": len(sig), "uplift": None})
            continue
        b, h = _rate(elig), _rate(sig)
        grid.append({"threshold": cond.threshold, "n": len(sig), "uplift": round(h - b, 4)})
    got = [g["uplift"] for g in grid if g["uplift"] is not None]
    return {"supported": True, "grid": grid,
            "sign_stable": bool(got) and (all(u > 0 for u in got) or all(u < 0 for u in got)),
            "spread": round(max(got) - min(got), 4) if got else None}


def window_neighborhood(fixtures, feature_values, conditions, target,
                        alternatives: dict[str, str], *, min_signals: int = 30):
    """Тот же признак на соседнем окне: 5 против 10."""
    if len(conditions) != 1:
        return {"supported": False}
    base_c = conditions[0]
    out = {}
    for label, key in alternatives.items():
        cond = Condition(key, base_c.op, base_c.threshold)
        rows = _outcomes(fixtures, feature_values, [cond], target)
        elig = [(f, y) for f, y, s in rows if s is not None]
        sig = [(f, y) for f, y, s in rows if s]
        if len(sig) < min_signals:
            out[label] = {"n": len(sig), "uplift": None}
            continue
        b, h = _rate(elig), _rate(sig)
        out[label] = {"n": len(sig), "uplift": round(h - b, 4)}
    got = [v["uplift"] for v in out.values() if v["uplift"] is not None]
    return {"supported": True, "windows": out,
            "sign_stable": bool(got) and all(u > 0 for u in got)}


def temporal_clustering(fixtures, feature_values, conditions, target):
    """Сигналы размазаны по времени или собраны в несколько кусков."""
    rows = _outcomes(fixtures, feature_values, conditions, target)
    order = sorted([f["sync_batch"] for f, _, s in rows if s])
    if len(order) < 3:
        return {"n_signals": len(order), "dispersion_index": None}
    gaps = np.diff(np.array(order, dtype=float))
    mean = float(np.mean(gaps))
    # индекс дисперсии: 1 — пуассоновский поток, много больше 1 — сгустки
    di = float(np.var(gaps) / mean) if mean > 0 else None
    return {"n_signals": len(order), "mean_gap_batches": round(mean, 2),
            "dispersion_index": round(di, 2) if di is not None else None}


def missingness_bias(fixtures, feature_values, conditions, target):
    """Не связана ли сама пригодность матча с исходом.

    Если UNAVAILABLE случается чаще там, где таргет чаще срабатывает, выборка
    смещена, и базлайн eligible-множества уже не равен базлайну лиги.
    """
    tf = TARGETS[target]
    elig_y, inelig_y = [], []
    for f in fixtures:
        y = tf(f)
        if y is None:
            continue
        vals = feature_values.get(f["fixture_id"], {})
        verdicts = [c.holds(vals.get(c.feature_key)) for c in conditions]
        (inelig_y if any(v is None for v in verdicts) else elig_y).append(y)
    if not elig_y or not inelig_y:
        return {"eligible_rate": _rate([(None, y) for y in elig_y]),
                "ineligible_rate": None, "delta": None}
    a, b = float(np.mean(elig_y)), float(np.mean(inelig_y))
    n1, n2 = len(elig_y), len(inelig_y)
    p = (sum(elig_y) + sum(inelig_y)) / (n1 + n2)
    se = math.sqrt(max(p * (1 - p) * (1 / n1 + 1 / n2), 1e-12))
    return {"eligible_rate": round(a, 4), "ineligible_rate": round(b, 4),
            "delta": round(a - b, 4), "z": round((a - b) / se, 2),
            "n_eligible": n1, "n_ineligible": n2}
