"""ШАГ 5. Открытие блока валидации (22-23, 23-24) РОВНО ОДИН РАЗ.

Правила заморожены: признаки, пороги, окна, таргеты берутся из
strategies_*.json и сверяются по хэшу ДО расчёта. Ничего не подбирается.
Baseline берётся ИЗ БЛОКА ВАЛИДАЦИИ.
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd

if os.environ.get("LAB_UNLOCK") != "1":
    sys.exit("LAB_UNLOCK=1 не установлен — блок валидации остаётся закрытым.")

PKG = os.environ.get("PKG", "/home/user/work/laliga_v4")
OUT = os.environ.get("OUT", "/home/user/stavki-2.0/laliga_validation")
CRIT = json.load(open(os.path.join(OUT, "validation_criterion.json")))
VAL_SEASONS = CRIT["block_under_test"]

import engine, features, targets

# ---------- 1. замороженные правила + сверка хэшей ----------
S = {}
for f in ("strategies_confirmed.v4.json", "strategies_candidates.v4.json"):
    for s in json.load(open(os.path.join(PKG, f))):
        S[s["id"]] = s
S = [S[k] for k in sorted(S)]
assert len(S) == 7, f"ожидалось 7 стратегий, найдено {len(S)}"
# хэши, подтверждённые на ШАГЕ 3 повторным прогоном freeze.py на воспроизведённой
# лаборатории (7/7 совпали побитово). Здесь — только сверка, без пересчёта.
VERIFIED_HASHES = {
    "S01": "065519ad2a0d423b", "S02": "583c93802305c0d7", "S03": "3fbfc37820907583",
    "S04": "d117867e8b920bfb", "S05": "98d6b896cb0d8a8a", "S06": "daa06a526f194e09",
    "S07": "61a5a64be62bb851",
}
FROZEN_RULES = {   # признак, оператор, порог, таргет, инверсия — из текста задачи
    "S01": ("D_PTS_m15", "<=", -0.333, "RES_AWAY", False),
    "S02": ("X_shH_allA_5", ">=", 26.5, "TS_O22", False),
    "S03": ("X_shH_allA_5", "<=", 20.0, "CK_H_O45", True),
    "S04": ("S_FL_m15", ">=", 29.0, "FL_O26", False),
    "S05": ("A_ST_m10", ">=", 5.4, "AG_O25", False),
    "S06": ("D_CK_m10", "<=", -1.0, "CK_HOME_MORE", True),
    "S07": ("S_YC_m10", ">=", 5.6, "YC_O5", False),
}
for s in S:
    i = s["id"]
    assert s["hash"] == VERIFIED_HASHES[i], f"{i}: хэш не совпал с подтверждённым на ШАГЕ 3"
    got = (s["feature"], s["op"], float(s["thr"]), s["target"], bool(s.get("invert", False)))
    assert got == FROZEN_RULES[i], f"{i}: правило разошлось с заморозкой: {got} != {FROZEN_RULES[i]}"
print("сверка заморозки: 7/7 хэшей и 7/7 правил совпали")

# ---------- 2. данные валидации ----------
df = engine.load_blind("val")
assert sorted(df.Season.unique()) == sorted(VAL_SEASONS), df.Season.unique()
tm = engine.long_table(df)
M = features.build_match_features(df, features.team_rolling(tm), features.league_state(df))
Y = targets.build(df)
print(f"блок val: {len(df)} матчей, {df.batch.nunique()} батчей, сезоны {sorted(df.Season.unique())}")


def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def miss_chains(sig_outcomes):
    ch = []; c = 0
    for r in sig_outcomes:
        if r == 0: c += 1
        else: ch.append(c); c = 0
    ch.append(c)
    return np.array(ch)


rows = []
for s in S:
    feat, op, thr, tgt = s["feature"], s["op"], float(s["thr"]), s["target"]
    inv = bool(s.get("invert", False))
    v = M[feat].values; ok = ~np.isnan(v)
    m = ((v >= thr) if op == ">=" else (v <= thr)) & ok
    y_raw = Y[tgt].values
    y = (1 - y_raw) if inv else y_raw          # эффективный исход = предсказываемое событие

    n = int(m.sum()); k = int(y[m].sum())
    base = float(y[ok].mean()); cond = k / n if n else np.nan
    z = (cond - base) / np.sqrt(base * (1 - base) / n) if n else np.nan
    # freeze.py считает uplift по УЖЕ округлённым до 3 знаков долям
    # (absolute_uplift = round(round(cond,3) - round(base,3), 3)).
    # Повторяем ту же арифметику, чтобы лаборатория и валидация сравнивались
    # одинаково посчитанными величинами.
    base_r = round(base, 3); cond_r = round(cond, 3)
    lo, hi = wilson(k, n)

    per = {}
    for ss in VAL_SEASONS:
        sm = (df.Season.values == ss)
        ns = int((m & sm).sum())
        per[ss] = dict(n=ns,
                       cond=round(float(y[m & sm].mean()), 3) if ns else None,
                       base=round(float(y[ok & sm].mean()), 3) if (ok & sm).sum() else None)
        per[ss]["uplift"] = (round(per[ss]["cond"] - per[ss]["base"], 3)
                             if ns and per[ss]["base"] is not None else None)
        per[ss]["base_n"] = int((ok & sm).sum())

    order = np.argsort(df.batch.values)
    ch = miss_chains(y[order][m[order]])

    lab_up = float(s["absolute_uplift"]); up = round(cond_r - base_r, 3)
    c1 = np.sign(up) == np.sign(lab_up)
    c2 = up >= 0.5 * lab_up
    c3 = z >= 2.0
    c4 = all(per[ss]["uplift"] is not None and per[ss]["uplift"] > 0 for ss in VAL_SEASONS)
    verdict = "INDEPENDENTLY_CONFIRMED" if (c1 and c2 and c3 and c4) else "FAILED_VALIDATION"

    rows.append(dict(id=s["id"], name=s["name"], hash=s["hash"], status_lab=s["status"],
                     feature=feat, op=op, thr=thr, target=tgt, invert=inv,
                     lab_n=s["n_signals"], lab_freq=s["signal_frequency"],
                     lab_base=s["base_rate"], lab_cond=s["conditional_rate"],
                     lab_uplift=lab_up, lab_rel=s["relative_uplift"], lab_z=s["z"],
                     val_n=n, val_freq=round(n / int(ok.sum()), 3), val_eligible=int(ok.sum()),
                     val_base=base_r, val_cond=cond_r,
                     val_uplift=up, val_rel=round(cond / base, 2) if base else None,
                     val_z=round(float(z), 2), val_ci95=f"[{lo};{hi}]",
                     per_season=per,
                     longest_miss_chain=int(ch.max()), q95_miss_chain=int(np.quantile(ch, 0.95)),
                     n_sequences=int(len(ch)),
                     C1_sign=bool(c1), C2_magnitude=bool(c2), C3_z=bool(c3), C4_both_seasons=bool(c4),
                     verdict=verdict))

os.makedirs(OUT, exist_ok=True)
json.dump(rows, open(os.path.join(OUT, "validation_results.json"), "w"),
          ensure_ascii=False, indent=1, default=str)
flat = pd.DataFrame([{k: v for k, v in r.items() if k != "per_season"} for r in rows])
flat.to_csv(os.path.join(OUT, "validation_results.csv"), index=False)
print(flat[["id", "val_n", "val_base", "val_cond", "val_uplift", "val_z",
            "C1_sign", "C2_magnitude", "C3_z", "C4_both_seasons", "verdict"]].to_string(index=False))
