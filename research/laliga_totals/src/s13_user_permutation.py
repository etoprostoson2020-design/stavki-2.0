"""Stage 13 -- the decisive test for the three user strategies.

Null hypothesis: the half-by-half pattern of EARLIER matches carries no
information about the next match's total.

Permutation design: inside each season the match RECORDS (goals by half plus
their own Over/Under prices, kept together) are reassigned across the fixed
timetable of kickoff slots.  This destroys only the ordering -- which match
follows which, and therefore every "previous match" the rules read -- while
leaving each match's own price/outcome coupling untouched.  That coupling is
what drives blind-bet ROI, so preserving it is what makes the test about the
pattern claim rather than about the price.

Everything is vectorised: 2000 permutations instead of 400.
"""
from __future__ import annotations
import sys, os, warnings
sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import lal_data as D
import s03_features as FEAT

RNG = np.random.default_rng(90210)
MATCH_MINUTES = 105


def prepare(dev: pd.DataFrame) -> dict:
    """Per-season arrays: the timetable (fixed) and the match records (permutable)."""
    out = {}
    for season, d in dev.groupby("season", sort=False):
        d = d.sort_values(["kickoff_dt", "date", "home"], kind="mergesort")
        teams = pd.concat([d["home"], d["away"]]).astype("category").cat.categories
        tix = {t: i for i, t in enumerate(teams)}
        out[season] = {
            "ko": d["kickoff_dt"].values.astype("datetime64[m]").astype(np.int64),
            "has_t": d["has_kickoff"].values.astype(bool),
            "home": d["home"].map(tix).values.astype(int),
            "away": d["away"].map(tix).values.astype(int),
            "g1": (d["G_ht"]).values.astype(float),
            "g2": (d["G"] - d["G_ht"]).values.astype(float),
            "state": d["state"].values,
            "o25": d["O25_PRI"].values.astype(float),
            "u25": d["U25_PRI"].values.astype(float),
            "n_teams": len(teams),
        }
    return out


def evaluate(season_data: dict, perm: np.ndarray | None, only: str | None = None) -> tuple[float, int]:
    """Run the combined S2>S3>S1 rule over one season. Returns (pnl, bets).

    ``only`` restricts to a single rule ("S1"/"S2"/"S3") for per-rule testing.
    """
    ko, has_t = season_data["ko"], season_data["has_t"]
    n = len(ko)
    idx = np.arange(n) if perm is None else perm
    # records travel together; the timetable stays put
    home, away = season_data["home"][idx], season_data["away"][idx]
    g1, g2 = season_data["g1"][idx], season_data["g2"][idx]
    state = season_data["state"][idx]
    o25, u25 = season_data["o25"][idx], season_data["u25"][idx]

    # ---- per-team previous match halves, in the (possibly permuted) order ----
    nt = season_data["n_teams"]
    last1 = np.full(nt, np.nan)
    last2 = np.full(nt, np.nan)
    prev_g1_h = np.full(n, np.nan); prev_g2_h = np.full(n, np.nan)
    prev_g1_a = np.full(n, np.nan); prev_g2_a = np.full(n, np.nan)
    for i in range(n):
        h, a = home[i], away[i]
        prev_g1_h[i], prev_g2_h[i] = last1[h], last2[h]
        prev_g1_a[i], prev_g2_a[i] = last1[a], last2[a]
        last1[h] = last1[a] = g1[i]
        last2[h] = last2[a] = g2[i]

    # ---- league's last COMPLETED match (timetable is fixed) -----------------
    prev_done_g2 = np.full(n, np.nan)
    for i in range(n):
        k = np.searchsorted(ko, ko[i] - MATCH_MINUTES, side="right")
        if k == 0:
            continue
        tied = g2[:k][ko[:k] == ko[k - 1]]
        prev_done_g2[i] = 0.0 if np.all(tied == 0) else np.max(tied)

    # ---- the rules, in the user's priority order ---------------------------
    priced = np.isfinite(o25) & np.isfinite(u25)
    cheaper = priced & (o25 < u25)

    s2 = (prev_g2_h >= 2) & (prev_g2_a == 0) & cheaper & (u25 >= 2.00)
    s3 = (prev_g1_h == 0) & (prev_g1_a >= 2) & cheaper & (o25 >= 1.55)
    s1 = has_t & (prev_done_g2 == 0) & priced & (u25 >= 1.80) & (u25 <= 1.89)

    take_s2 = s2
    take_s3 = s3 & ~take_s2
    take_s1 = s1 & ~take_s2 & ~take_s3
    if only == "S1":
        take_s2 = take_s3 = np.zeros(n, bool); take_s1 = s1
    elif only == "S2":
        take_s3 = take_s1 = np.zeros(n, bool); take_s2 = s2
    elif only == "S3":
        take_s2 = take_s1 = np.zeros(n, bool); take_s3 = s3

    isC = state == "C"
    pnl = 0.0
    # UNDER 2.5 legs
    for mask in (take_s2, take_s1):
        pnl += np.sum(np.where(isC[mask], -1.0, u25[mask] - 1.0))
    # OVER 2.5 leg
    pnl += np.sum(np.where(isC[take_s3], o25[take_s3] - 1.0, -1.0))
    bets = int(take_s2.sum() + take_s3.sum() + take_s1.sum())
    return float(pnl), bets


def run(season_data: dict, perms: np.ndarray | None, only: str | None = None):
    tot_pnl, tot_bets = 0.0, 0
    for s, sd in season_data.items():
        p = None if perms is None else RNG.permutation(len(sd["ko"]))
        pnl, bets = evaluate(sd, p, only)
        tot_pnl += pnl
        tot_bets += bets
    return tot_pnl, tot_bets


def perm_p(sd, only, n=2000):
    pnl, bets = run(sd, None, only)
    if bets == 0:
        return None
    obs = pnl / bets
    null = np.empty(n)
    for t in range(n):
        p, b = run(sd, True, only)
        null[t] = p / b if b else np.nan
    null = null[np.isfinite(null)]
    return {"bets": bets, "pnl": pnl, "roi": obs,
            "null_mean": float(null.mean()), "null_p95": float(np.percentile(null, 95)),
            "p": float((np.sum(null >= obs) + 1) / (len(null) + 1))}


def main():
    m = FEAT.build()
    dev = m[m["block"] == "dev"].copy()
    sd = prepare(dev)

    pnl, bets = run(sd, None)
    obs_roi = pnl / bets
    print("=== ПЕРЕСТАНОВОЧНЫЙ ТЕСТ ТРЁХ СТРАТЕГИЙ (development) ===\n")
    print(f"  фактически: {bets} ставок, PnL {pnl:+.2f}u, ROI {100*obs_roi:+.2f}%\n")
    print("  Нулевая гипотеза: рисунок таймов предыдущих матчей не несёт")
    print("  информации о тотале следующего. Перемешивается ТОЛЬКО порядок:")
    print("  записи матчей (голы + их собственные цены вместе) переставляются")
    print("  по фиксированному расписанию. Связь цена-исход сохраняется.\n")

    N = 2000
    roi_null = np.empty(N)
    bets_null = np.empty(N)
    for t in range(N):
        p, b = run(sd, True)
        roi_null[t] = p / b if b else np.nan
        bets_null[t] = b
    ok = np.isfinite(roi_null)
    roi_null = roi_null[ok]

    p_val = float((np.sum(roi_null >= obs_roi) + 1) / (len(roi_null) + 1))
    print(f"  перестановок: {len(roi_null)}")
    print(f"  ставок в среднем при перемешивании: {bets_null.mean():.1f} (факт {bets})")
    print(f"  ROI нулевого распределения: среднее {100*roi_null.mean():+.2f}%, "
          f"ст.откл {100*roi_null.std():.2f}%")
    print(f"  перцентили нуля: 50% {100*np.percentile(roi_null,50):+.2f}%   "
          f"90% {100*np.percentile(roi_null,90):+.2f}%   "
          f"95% {100*np.percentile(roi_null,95):+.2f}%   "
          f"99% {100*np.percentile(roi_null,99):+.2f}%")
    print(f"\n  ФАКТИЧЕСКИЙ ROI {100*obs_roi:+.2f}%   ->   p = {p_val:.4f}")
    verdict = ("порядок НЕСЁТ информацию" if p_val < 0.05 else
               "порядок НЕ несёт информации — результат внутри шума")
    print(f"  ВЕРДИКТ: {verdict}")

    print("\n=== ПО КАЖДОЙ СТРАТЕГИИ ОТДЕЛЬНО ===\n")
    per_rule = {}
    for rule in ("S1", "S2", "S3"):
        r = perm_p(sd, rule, n=2000)
        per_rule[rule] = r
        if r is None:
            print(f"  {rule}: нет ставок")
            continue
        print(f"  {rule}: {r['bets']:3d} ставок  ROI {100*r['roi']:+7.2f}%  "
              f"нуль {100*r['null_mean']:+6.2f}%  95%-перцентиль {100*r['null_p95']:+6.2f}%  "
              f"p={r['p']:.4f}  {'ЗНАЧИМО' if r['p']<0.05 else 'в пределах шума'}")

    D.write_json("s13_user_permutation.json", {
        "per_rule": per_rule,
        "observed_roi": float(obs_roi), "observed_bets": int(bets),
        "observed_pnl": float(pnl),
        "n_permutations": int(len(roi_null)),
        "null_mean_roi": float(roi_null.mean()),
        "null_sd_roi": float(roi_null.std()),
        "null_p50": float(np.percentile(roi_null, 50)),
        "null_p90": float(np.percentile(roi_null, 90)),
        "null_p95": float(np.percentile(roi_null, 95)),
        "null_p99": float(np.percentile(roi_null, 99)),
        "p_permutation": p_val,
        "verdict": verdict,
        "design": "match records permuted across the fixed kickoff timetable "
                  "within each season; price-outcome coupling preserved",
    })
    print("\n[written] out/s13_user_permutation.json")


if __name__ == "__main__":
    main()
