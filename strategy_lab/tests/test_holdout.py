"""Holdout Ledger: остаток неоткрытых сезонов считается явно."""
import pytest

from fsl.research.holdout import HoldoutExhausted, guard_discovery, mark_seen, remaining, seed

BLOCKS = {"DISCOVERY": ["16-17", "17-18"], "VALIDATION": ["22-23"],
          "TEST": ["24-25", "25-26"]}


def test_seed_and_remaining(sess):
    seed(sess, "ESP_1", BLOCKS)
    st = remaining(sess, "ESP_1")
    assert st["total_seasons"] == 5 and st["unseen_count"] == 5


def test_seen_is_irreversible(sess):
    seed(sess, "ESP_1", BLOCKS)
    mark_seen(sess, "ESP_1", ["16-17"], by="test")
    mark_seen(sess, "ESP_1", ["16-17"], by="test")     # повторно — без эффекта
    st = remaining(sess, "ESP_1")
    assert st["seen"] == ["16-17"] and st["unseen_count"] == 4


def test_guard_allows_batch_that_leaves_reserve(sess):
    seed(sess, "ESP_1", BLOCKS)
    res = guard_discovery(sess, "ESP_1", ["16-17"])
    assert res["unseen_after"] == 4


def test_guard_blocks_batch_that_exhausts_holdout(sess):
    """Батч, после которого не остаётся запаса, не запускается."""
    seed(sess, "ESP_1", BLOCKS)
    with pytest.raises(HoldoutExhausted):
        guard_discovery(sess, "ESP_1", ["16-17", "17-18", "22-23", "24-25"])
