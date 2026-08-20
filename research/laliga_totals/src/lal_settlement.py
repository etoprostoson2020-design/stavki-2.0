"""
Settlement algebra for the four goal-total markets, plus de-vigging.

States (total goals G):  A: G<=1     B: G==2     C: G>=3
                         pA + pB + pC = 1

Settlement, per 1 unit staked, in NET terms (stake excluded from the return):

  OVER 2.5   C -> +(o-1)      A,B -> -1
  UNDER 2.5  A,B -> +(o-1)    C   -> -1
  OVER 2.0   C -> +(o-1)      B -> 0 (push)   A -> -1
  UNDER 2.0  A -> +(o-1)      B -> 0 (push)   C -> -1

Fair odds are the price at which EV == 0.

  OVER 2.5:  pC(o-1) - (pA+pB) = 0
             pC*o = pC + pA + pB = 1            ->  o = 1/pC
  UNDER 2.5: (pA+pB)(o-1) - pC = 0
             (pA+pB)o = 1                        ->  o = 1/(pA+pB)
  OVER 2.0:  pC(o-1) - pA = 0
             pC*o = pA + pC = 1 - pB             ->  o = (1-pB)/pC
  UNDER 2.0: pA(o-1) - pC = 0
             pA*o = pA + pC = 1 - pB             ->  o = (1-pB)/pA

The 2.0 line is the 2.5 line conditioned on "no push": its fair price is the
2.5-style price computed inside the reduced universe {A, C} and then scaled by
the probability (1-pB) that the bet is live at all.  All of the difference
between the two lines is the price of that conditioning -- nothing else.
"""
from __future__ import annotations

import numpy as np

MARKETS = ("OVER_2.0", "OVER_2.5", "UNDER_2.0", "UNDER_2.5")


def fair_odds(pA, pB, pC):
    pA, pB, pC = np.asarray(pA, float), np.asarray(pB, float), np.asarray(pC, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            "OVER_2.5": 1.0 / pC,
            "UNDER_2.5": 1.0 / (pA + pB),
            "OVER_2.0": (1.0 - pB) / pC,
            "UNDER_2.0": (1.0 - pB) / pA,
        }


def ev(market: str, o, pA, pB, pC):
    """Expected net profit per 1 unit staked at decimal price ``o``."""
    o = np.asarray(o, float)
    pA, pB, pC = np.asarray(pA, float), np.asarray(pB, float), np.asarray(pC, float)
    if market == "OVER_2.5":
        return pC * (o - 1.0) - (pA + pB)
    if market == "UNDER_2.5":
        return (pA + pB) * (o - 1.0) - pC
    if market == "OVER_2.0":
        return pC * (o - 1.0) - pA
    if market == "UNDER_2.0":
        return pA * (o - 1.0) - pC
    raise ValueError(market)


def wpl(market: str, pA, pB, pC):
    """(win, push, loss) probabilities for a market."""
    pA, pB, pC = np.asarray(pA, float), np.asarray(pB, float), np.asarray(pC, float)
    z = np.zeros_like(pA)
    return {
        "OVER_2.5": (pC, z, pA + pB),
        "UNDER_2.5": (pA + pB, z, pC),
        "OVER_2.0": (pC, pB, pA),
        "UNDER_2.0": (pA, pB, pC),
    }[market]


def settle(market: str, price, state):
    """Realised net profit per 1 unit for one actual match outcome."""
    price = np.asarray(price, float)
    state = np.asarray(state)
    if market == "OVER_2.5":
        return np.where(state == "C", price - 1.0, -1.0)
    if market == "UNDER_2.5":
        return np.where(state == "C", -1.0, price - 1.0)
    if market == "OVER_2.0":
        return np.where(state == "C", price - 1.0, np.where(state == "B", 0.0, -1.0))
    if market == "UNDER_2.0":
        return np.where(state == "A", price - 1.0, np.where(state == "B", 0.0, -1.0))
    raise ValueError(market)


def min_price(market: str, pA, pB, pC, edge: float = 0.0):
    """Smallest decimal price making EV >= ``edge`` per unit staked."""
    f = fair_odds(pA, pB, pC)[market]
    w, p, _ = wpl(market, pA, pB, pC)
    with np.errstate(divide="ignore", invalid="ignore"):
        return f + edge / w


# ---------------------------------------------------------------- de-vigging

def devig_two_way(o1, o2, method: str = "proportional"):
    """Remove margin from a two-outcome price pair.

    proportional : normalise implied probabilities (multiplicative)
    shin         : Shin (1992) insider-trading model, solved numerically
    log          : power/odds-ratio free 'logarithmic' method
    """
    o1 = np.asarray(o1, float)
    o2 = np.asarray(o2, float)
    q1, q2 = 1.0 / o1, 1.0 / o2
    s = q1 + q2
    if method == "proportional":
        return q1 / s, q2 / s
    if method == "shin":
        return _shin(q1, q2, s)
    if method == "log":
        # find k with q1^k + q2^k = 1
        k = np.ones_like(q1)
        for _ in range(80):
            f = q1 ** k + q2 ** k - 1.0
            df = (q1 ** k) * np.log(q1) + (q2 ** k) * np.log(q2)
            k = k - f / df
        return q1 ** k, q2 ** k
    raise ValueError(method)


def _shin(q1, q2, s):
    """Shin (1992) de-vig for a 2-way book, solved numerically for z.

    Under Shin's model the observed q_i = 1/o_i relate to the true p_i by

        q_i / s = [ z * p_i^2 + (1 - z) * p_i ] ... inverted as

        p_i(z) = ( sqrt( z^2 + 4(1-z) q_i^2 / s ) - z ) / ( 2 (1 - z) )

    with the insider fraction z in [0, 1) fixed by sum_i p_i(z) == 1.
    Bisection is used because the sum is monotone decreasing in z.
    """
    q1 = np.atleast_1d(np.asarray(q1, float))
    q2 = np.atleast_1d(np.asarray(q2, float))
    s = np.atleast_1d(np.asarray(s, float))

    def p_of(z):
        with np.errstate(invalid="ignore", divide="ignore"):
            a = (np.sqrt(z ** 2 + 4.0 * (1.0 - z) * q1 ** 2 / s) - z) / (2.0 * (1.0 - z))
            b = (np.sqrt(z ** 2 + 4.0 * (1.0 - z) * q2 ** 2 / s) - z) / (2.0 * (1.0 - z))
        return a, b

    lo = np.zeros_like(q1)
    hi = np.full_like(q1, 0.999)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        a, b = p_of(mid)
        too_big = (a + b) > 1.0
        lo = np.where(too_big, mid, lo)
        hi = np.where(too_big, hi, mid)
    a, b = p_of(0.5 * (lo + hi))
    tot = a + b
    return a / tot, b / tot


def overround(*odds):
    return float(np.sum([1.0 / np.asarray(o, float) for o in odds], axis=0))


# ------------------------------------------------------------ break-even map

def breakeven_2p0_vs_2p5(pA, pB, pC, o25):
    """Price on the 2.0 line that matches the EV of the 2.5 line at ``o25``.

    Returns (over_2p0_needed, under_2p0_needed): the 2.0 price at which the
    punter is indifferent between the two lines on the same side.
    """
    pA, pB, pC = map(lambda x: np.asarray(x, float), (pA, pB, pC))
    o25 = np.asarray(o25, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        # EV_O2.0(x) = EV_O2.5(o25)  ->  pC(x-1) - pA = pC(o-1) - (pA+pB)
        #                            ->  pC*x = pC*o - pB  -> x = o - pB/pC
        over = o25 - pB / pC
        # EV_U2.0(x) = EV_U2.5(o25)  ->  pA(x-1) - pC = (pA+pB)(o-1) - pC
        #                            ->  pA*x = (pA+pB)*o - pB
        under = ((pA + pB) * o25 - pB) / pA
    return over, under
