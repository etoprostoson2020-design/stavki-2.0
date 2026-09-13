"""Синхронные блоки: хронология по стартовому свистку, не по туру."""
import datetime as dt

from fsl.canonical.builder import assign_sync_batches


def _row(day, hour=None, home="A"):
    if hour is None:
        ko = dt.datetime(2020, 5, day, 12, tzinfo=dt.timezone.utc)
        prec = "DATE_ONLY"
    else:
        ko = dt.datetime(2020, 5, day, hour, tzinfo=dt.timezone.utc)
        prec = "EXACT"
    return {"kickoff_utc": ko, "kickoff_precision": prec, "home_team_raw": home}


def test_date_only_day_is_one_block():
    """Без времени начала вся календарная дата — один синхронный блок."""
    rows = [_row(1, home=h) for h in "ABCDE"]
    assign_sync_batches(rows)
    assert len({r["sync_batch"] for r in rows}) == 1


def test_exact_times_split_when_gap_exceeds_match_length():
    """Матч в 16:00 и матч в 21:00 — разные блоки: первый уже закончился."""
    rows = [_row(1, 16, "A"), _row(1, 21, "B")]
    assign_sync_batches(rows)
    assert rows[0]["sync_batch"] != rows[1]["sync_batch"]


def test_overlapping_kickoffs_stay_in_one_block():
    """16:00 и 17:00 идут одновременно — один блок."""
    rows = [_row(1, 16, "A"), _row(1, 17, "B")]
    assign_sync_batches(rows)
    assert rows[0]["sync_batch"] == rows[1]["sync_batch"]


def test_different_days_are_different_blocks():
    rows = [_row(1, 16), _row(2, 16)]
    assign_sync_batches(rows)
    assert rows[0]["sync_batch"] != rows[1]["sync_batch"]
