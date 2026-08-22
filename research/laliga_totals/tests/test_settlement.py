"""Numeric unit tests for the settlement algebra."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import lal_settlement as S


def test_fair_odds_zero_ev():
    """At the fair price the EV of every market is exactly zero."""
    rng = np.random.default_rng(7)
    for _ in range(2000):
        p = rng.dirichlet([2, 2, 3])
        pA, pB, pC = p
        f = S.fair_odds(pA, pB, pC)
        for m in S.MARKETS:
            assert abs(float(S.ev(m, f[m], pA, pB, pC))) < 1e-10, (m, p)


def test_fair_odds_closed_forms():
    pA, pB, pC = 0.30, 0.25, 0.45
    f = S.fair_odds(pA, pB, pC)
    assert abs(f["OVER_2.5"] - 1 / 0.45) < 1e-12
    assert abs(f["UNDER_2.5"] - 1 / 0.55) < 1e-12
    assert abs(f["OVER_2.0"] - 0.75 / 0.45) < 1e-12
    assert abs(f["UNDER_2.0"] - 0.75 / 0.30) < 1e-12


def test_settlement_matches_ev():
    """Monte-Carlo settlement must converge on the analytic EV."""
    rng = np.random.default_rng(11)
    pA, pB, pC = 0.28, 0.24, 0.48
    states = rng.choice(["A", "B", "C"], size=400_000, p=[pA, pB, pC])
    for m, price in [("OVER_2.5", 1.9), ("UNDER_2.5", 2.0),
                     ("OVER_2.0", 1.55), ("UNDER_2.0", 2.6)]:
        realised = S.settle(m, price, states).mean()
        analytic = float(S.ev(m, price, pA, pB, pC))
        assert abs(realised - analytic) < 5e-3, (m, realised, analytic)


def test_push_returns_stake_exactly():
    assert S.settle("OVER_2.0", 1.75, np.array(["B"]))[0] == 0.0
    assert S.settle("UNDER_2.0", 2.10, np.array(["B"]))[0] == 0.0
    # a push is not a win
    assert S.settle("OVER_2.5", 1.75, np.array(["B"]))[0] == -1.0
    assert S.settle("UNDER_2.5", 2.10, np.array(["B"]))[0] == 1.10


def test_wpl_sums_to_one():
    rng = np.random.default_rng(3)
    for _ in range(500):
        pA, pB, pC = rng.dirichlet([2, 2, 3])
        for m in S.MARKETS:
            w, p, l = S.wpl(m, pA, pB, pC)
            assert abs(float(w + p + l) - 1.0) < 1e-12


def _scalar(t):
    return float(np.ravel(t[0])[0]), float(np.ravel(t[1])[0])


def test_devig_proportional_and_shin():
    p1, p2 = _scalar(S.devig_two_way(1.90, 1.95, "proportional"))
    assert abs(p1 + p2 - 1.0) < 1e-12
    s1, s2 = _scalar(S.devig_two_way(1.90, 1.95, "shin"))
    assert abs(s1 + s2 - 1.0) < 1e-12
    # Favourite-longshot bias: on a lopsided book the de-vigged favourite
    # probability rises going proportional -> Shin -> logarithmic.
    f1, _ = _scalar(S.devig_two_way(1.20, 5.00, "proportional"))
    g1, _ = _scalar(S.devig_two_way(1.20, 5.00, "shin"))
    l1, _ = _scalar(S.devig_two_way(1.20, 5.00, "log"))
    assert f1 < g1 < l1
    # On a symmetric book all three agree
    a, _ = _scalar(S.devig_two_way(2.0, 2.0, "proportional"))
    b, _ = _scalar(S.devig_two_way(2.0, 2.0, "shin"))
    assert abs(a - b) < 1e-6


def test_devig_fair_book_is_identity():
    p1, p2 = _scalar(S.devig_two_way(2.0, 2.0, "proportional"))
    assert abs(p1 - 0.5) < 1e-12 and abs(p2 - 0.5) < 1e-12


def test_min_price_gives_requested_edge():
    pA, pB, pC = 0.27, 0.25, 0.48
    for m in S.MARKETS:
        o = float(S.min_price(m, pA, pB, pC, edge=0.02))
        assert abs(float(S.ev(m, o, pA, pB, pC)) - 0.02) < 1e-10


def test_breakeven_map_is_indifference():
    rng = np.random.default_rng(5)
    for _ in range(500):
        pA, pB, pC = rng.dirichlet([2, 2, 3])
        o25_over = 1.0 / pC * 1.05
        o25_under = 1.0 / (pA + pB) * 1.05
        ov, _ = S.breakeven_2p0_vs_2p5(pA, pB, pC, o25_over)
        assert abs(float(S.ev("OVER_2.0", ov, pA, pB, pC))
                   - float(S.ev("OVER_2.5", o25_over, pA, pB, pC))) < 1e-10
        _, un2 = S.breakeven_2p0_vs_2p5(pA, pB, pC, o25_under)
        assert abs(float(S.ev("UNDER_2.0", un2, pA, pB, pC))
                   - float(S.ev("UNDER_2.5", o25_under, pA, pB, pC))) < 1e-10


def test_two_point_zero_is_conditional_two_point_five():
    """fair_O2.0 == fair price of C inside {A,C}, scaled by (1-pB)."""
    pA, pB, pC = 0.31, 0.26, 0.43
    cond = (pA + pC) / pC          # 1 / P(C | not B)
    assert abs(S.fair_odds(pA, pB, pC)["OVER_2.0"] - cond) < 1e-12


def test_proportional_margin_theorem():
    """If a book applies the SAME multiplicative margin m to both lines, then

        EV(OVER_2.0)  = (1 - pB) * EV(OVER_2.5)
        EV(UNDER_2.0) = (1 - pB) * EV(UNDER_2.5)

    i.e. the 2.0 bet is exactly the 2.5 bet scaled to (1-pB) of the stake,
    with the remaining pB of the stake held in cash.  The push therefore buys
    nothing and costs nothing per unit of money actually at risk.
    """
    rng = np.random.default_rng(13)
    for _ in range(1000):
        pA, pB, pC = rng.dirichlet([2, 2, 3])
        f = S.fair_odds(pA, pB, pC)
        for m in (0.90, 0.95, 0.98, 1.0, 1.03):
            e25o = float(S.ev("OVER_2.5", f["OVER_2.5"] * m, pA, pB, pC))
            e20o = float(S.ev("OVER_2.0", f["OVER_2.0"] * m, pA, pB, pC))
            assert abs(e20o - (1 - pB) * e25o) < 1e-10
            e25u = float(S.ev("UNDER_2.5", f["UNDER_2.5"] * m, pA, pB, pC))
            e20u = float(S.ev("UNDER_2.0", f["UNDER_2.0"] * m, pA, pB, pC))
            assert abs(e20u - (1 - pB) * e25u) < 1e-10


def test_roi_per_live_unit_is_identical():
    """Dividing by the money actually at risk, the two lines are the same bet."""
    pA, pB, pC = 0.27, 0.25, 0.48
    f = S.fair_odds(pA, pB, pC)
    m = 0.95
    e25 = float(S.ev("OVER_2.5", f["OVER_2.5"] * m, pA, pB, pC))
    e20 = float(S.ev("OVER_2.0", f["OVER_2.0"] * m, pA, pB, pC))
    assert abs(e20 / (1 - pB) - e25) < 1e-12


def test_two_point_zero_only_wins_via_relative_margin():
    """The 2.0 line beats the 2.5 line only when its own margin is smaller."""
    pA, pB, pC = 0.27, 0.25, 0.48
    f = S.fair_odds(pA, pB, pC)
    # same margin -> 2.5 has the larger (less negative) EV per unit STAKED?  No:
    # 2.0 is less negative, but only because less money is at risk.
    e25 = float(S.ev("OVER_2.5", f["OVER_2.5"] * 0.95, pA, pB, pC))
    e20 = float(S.ev("OVER_2.0", f["OVER_2.0"] * 0.95, pA, pB, pC))
    assert e20 > e25                      # smaller absolute loss
    assert abs(e20 / (1 - pB) - e25) < 1e-12   # identical per live unit
    # a 2.0 price with a genuinely smaller margin does win outright
    e20_better = float(S.ev("OVER_2.0", f["OVER_2.0"] * 0.99, pA, pB, pC))
    assert e20_better > e25
