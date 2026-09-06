"""ШИМ загрузчика для воспроизведения ЛАБОРАТОРИИ без сырых CSV.

Если сырые сезонные CSV лежат в uploads_dir -- делегируем ОРИГИНАЛЬНОМУ
загрузчику (побайтово тот же файл, что в скилле laliga-loader).
Если их нет -- блок lab восстанавливается из laliga_v4/blind_dataset.csv,
чья sha256 совпала с blind_dataset_manifest.json. Закрытые блоки
(val/test) без сырых файлов восстановить нельзя -- PermissionError/FileNotFound.
"""
import os, sys, importlib.util
import numpy as np, pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORIG = os.path.join(_HERE, "_orig_load_footballdata.py")
_spec = importlib.util.spec_from_file_location("_orig_lfd", _ORIG)
_orig = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_orig)

SEASON_ORDER = _orig.SEASON_ORDER
LAB, VAL, TEST = _orig.LAB, _orig.VAL, _orig.TEST
BLOCKS = _orig.BLOCKS
team_matches = _orig.team_matches
audit = _orig.audit

BLIND = os.environ.get("BLIND_CSV",
    os.path.join(os.path.dirname(_HERE), "laliga_v4", "blind_dataset.csv"))

# границы сезонов из laliga_v4/source_manifest.csv (date_min..date_max) -- непересекающиеся
SEASON_SPAN = {
    "16-17": ("2016-08-19", "2017-05-21"), "17-18": ("2017-08-18", "2018-05-20"),
    "18-19": ("2018-08-17", "2019-05-19"), "19-20": ("2019-08-16", "2020-07-19"),
    "20-21": ("2020-09-12", "2021-05-23"), "21-22": ("2021-08-13", "2022-05-22"),
}
ALLOW = ["Div","Date","Time","HomeTeam","AwayTeam","FTHG","FTAG","FTR","HTHG","HTAG","HTR",
         "HS","AS","HST","AST","HF","AF","HC","AC","HY","AY","HR","AR"]


def _raw_present(uploads_dir, seasons):
    return all(os.path.exists(os.path.join(uploads_dir, s + ".csv")) for s in seasons)


def _from_blind(block):
    if block != "lab":
        raise PermissionError(
            f"блок '{block}' невозможно восстановить из blind_dataset (в нём только сезоны {LAB}); "
            "нужны сырые CSV")
    b = pd.read_csv(BLIND, dtype=str, keep_default_na=False, na_values=[""])
    for c in ["FTHG","FTAG","HTHG","HTAG","HS","AS","HST","AST","HF","AF","HC","AC","HY","AY","HR","AR"]:
        b[c] = b[c].astype("int64")
    b["Time"] = b["Time"].astype(object).where(b["Time"].notna(), np.nan)
    for c in ["Div","Date","HomeTeam","AwayTeam","FTR","HTR"]:
        b[c] = b[c].astype(object)
    d = pd.to_datetime(b["Date"], dayfirst=True, format="mixed")
    season = pd.Series(pd.NA, index=b.index, dtype=object)
    for s, (lo, hi) in SEASON_SPAN.items():
        season[(d >= pd.Timestamp(lo)) & (d <= pd.Timestamp(hi))] = s
    if season.isna().any():
        raise ValueError(f"{int(season.isna().sum())} матчей не попали ни в один сезонный интервал")
    b["Season"] = season
    b["SeasonIdx"] = b["Season"].map(SEASON_ORDER.index).astype("int64")
    b["D"] = d
    b["HasTime"] = b["Time"].notna()
    b["Block"] = "lab"
    b = b.sort_values(["D", "Time", "HomeTeam"], na_position="first").reset_index(drop=True)
    return b


def load_all(uploads_dir, block="all", strict=True):
    if block not in BLOCKS:
        raise ValueError(f"block должен быть одним из {list(BLOCKS)}")
    wanted = BLOCKS[block]
    closed = [s for s in wanted if s in VAL + TEST]
    if strict and closed and os.environ.get("LAB_UNLOCK") != "1":
        raise PermissionError(
            f"Блок '{block}' содержит закрытые сезоны {closed}. Поиск закономерностей запрещён протоколом.")
    if uploads_dir and os.path.isdir(uploads_dir) and _raw_present(uploads_dir, wanted):
        return _orig.load_all(uploads_dir, block=block, strict=strict)
    return _from_blind(block)
