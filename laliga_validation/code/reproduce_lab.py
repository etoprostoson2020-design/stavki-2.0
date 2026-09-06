"""ШАГ 2 + ШАГ 3: воспроизведение лаборатории и сверка хэшей заморозки.

Запускается из папки, где лежат модули пакета (code/*.py) и шим загрузчика
под именем load_footballdata.py. Пишет df/tm/M/Y/reg/Mm/Em в текущую папку.
"""
import numpy as np, pandas as pd
import engine, features, targets, scan

df = engine.load_blind("lab")
print("матчей:", len(df), "| батчей:", df.batch.nunique(), "| сезонов:", df.Season.nunique())
for s, sub in df.groupby("Season"):
    vc = pd.concat([sub.HomeTeam, sub.AwayTeam]).value_counts()
    assert len(sub) == 380 and len(vc) == 20 and (vc == 38).all(), s
print("в каждом сезоне 380 матчей, 20 команд, 38 матчей у команды: OK")

df.to_pickle("df.pkl")
tm = engine.long_table(df); tm.to_pickle("tm.pkl")
M = features.build_match_features(df, features.team_rolling(tm), features.league_state(df))
Y = targets.build(df)
M.to_pickle("M.pkl"); Y.to_pickle("Y.pkl")
print("признаков:", M.shape[1], "| таргетов:", Y.shape[1])

reg, Mm, Em = scan.make_masks(M, df)
np.save("Mm.npy", Mm); np.save("Em.npy", Em); reg.to_pickle("reg.pkl")
print("масок:", len(reg), "| кандидатов:", len(reg) * Y.shape[1],
      "| негативных масок:", int((reg.family == "NEGATIVE").sum()))
print("\nдалее: python leaktest.py && python wave_main.py && python freeze.py")
