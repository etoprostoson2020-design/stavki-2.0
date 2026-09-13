import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fsl.models import Base


@pytest.fixture
def sess():
    """Изолированная БД в памяти: тесты не зависят от развёрнутого PostgreSQL."""
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, expire_on_commit=False, future=True)()
    try:
        yield s
        s.commit()
    finally:
        s.close()


def fx(fid, season, batch, home, away, fthg, ftag, *, day=None, stats=None,
       precision="EXACT"):
    return {
        "fixture_id": fid, "league": "ESP_1", "season": season,
        "kickoff_utc": dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
                       + dt.timedelta(days=day if day is not None else batch),
        "kickoff_precision": precision, "sync_batch": batch,
        "home_team": home, "away_team": away,
        "fthg": fthg, "ftag": ftag,
        "ftr": "H" if fthg > ftag else "A" if fthg < ftag else "D",
        "hthg": 0, "htag": 0,
        "stats": stats or {"HS": 10, "AS": 8, "HST": 4, "AST": 3, "HF": 12, "AF": 11,
                           "HC": 5, "AC": 4, "HY": 2, "AY": 2, "HR": 0, "AR": 0},
    }


@pytest.fixture
def tiny():
    """Крошечный детерминированный датасет: признаки считаются на бумаге.

    A играет 6 матчей подряд, побеждая первые три и проигрывая следующие два.
    """
    return [
        fx(1, "S1", 1, "A", "X", 2, 0),
        fx(2, "S1", 2, "A", "Y", 1, 0),
        fx(3, "S1", 3, "A", "Z", 3, 1),
        fx(4, "S1", 4, "A", "X", 0, 1),
        fx(5, "S1", 5, "A", "Y", 0, 2),
        fx(6, "S1", 6, "A", "Z", 1, 1),
    ]
