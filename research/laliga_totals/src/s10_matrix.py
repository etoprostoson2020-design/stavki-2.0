"""Stage 10 -- the mandatory decision matrix.

One row per required segment, one of five actions per row.  Probabilities and
prices come from development; validation contributed only the single sanctioned
structural read; holdout is untouched.
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd

import lal_data as D
import lal_classes as C
import lal_eval as E
import lal_settlement as S
import s03_features as FEAT

pd.set_option("display.width", 320)
pd.set_option("display.max_columns", 60)

MIN_EDGE = 0.02        # a bet must clear 2% EV to be worth placing


def season_stability(d: pd.DataFrame) -> str:
    """Sign consistency of the market's pC error across development seasons."""
    if len(d) < 60:
        return "n/a"
    b = d.groupby("season").apply(
        lambda g: g["mkt_pC"].mean() - g["is_C"].mean(), include_groups=False)
    b = b.dropna()
    if len(b) < 3:
        return "n/a"
    pos = int((b > 0).sum())
    return f"{max(pos, len(b)-pos)}/{len(b)} same sign"


def row_for(name: str, d: pd.DataFrame, seq_note: str | None = None) -> dict:
    n = len(d)
    if n < 40:
        return {"segment": name, "n": n, "evidence": "SAMPLE TOO SMALL",
                "action": "NO_BET", "conditional_rule": "NO_BET at any price",
                "why_20_vs_25": "not assessable",
                "why_over_vs_under": "not assessable", "risk": "unquantified"}
    pA, pB, pC = d["is_A"].mean(), d["is_B"].mean(), d["is_C"].mean()
    f = S.fair_odds(pA, pB, pC)
    pr = d[d["O25_PRI"].notna()]
    o25 = float(pr["O25_PRI"].mean()) if len(pr) else np.nan
    u25 = float(pr["U25_PRI"].mean()) if len(pr) else np.nan
    o25m = float(pr["O25_ROB"].mean()) if len(pr) else np.nan
    u25m = float(pr["U25_ROB"].mean()) if len(pr) else np.nan

    # Realised per-match settlement, NOT EV evaluated at the mean price.
    # Those two differ whenever the price co-varies with the outcome -- and it
    # does: the under is quoted long exactly in the matches most likely to go
    # over.  Plugging the segment's average price into the segment's average
    # probabilities therefore flatters the under side badly (for the whole
    # league it reports +2.8% where blind betting actually returned -3.0%).
    def _roi(mk, col):
        if not len(pr):
            return float("nan")
        return float(S.settle(mk, pr[col].values, pr["state"].values).mean())

    ev_o25 = _roi("OVER_2.5", "O25_PRI")
    ev_u25 = _roi("UNDER_2.5", "U25_PRI")
    ev_o25m = _roi("OVER_2.5", "O25_ROB")
    ev_u25m = _roi("UNDER_2.5", "U25_ROB")

    # Closing-price evidence, where it exists (2019/20 onward).
    prc = d[d["OV25_PC"].notna() & d["UN25_PC"].notna()]
    if len(prc) >= 40:
        roi_o_cl = float(S.settle("OVER_2.5", prc["OV25_PC"].values, prc["state"].values).mean())
        roi_u_cl = float(S.settle("UNDER_2.5", prc["UN25_PC"].values, prc["state"].values).mean())
        n_cl = len(prc)
    else:
        roi_o_cl = roi_u_cl = float("nan")
        n_cl = len(prc)

    # Ranking by IN-SAMPLE EV at the price that actually existed.  These EVs use
    # the segment's own realised frequencies, so they are descriptive only: they
    # say where the book was wrong in 2016-2022, not where it will be wrong next.
    cand = {"OVER_2.5": ev_o25, "UNDER_2.5": ev_u25}   # by realised ROI
    order = sorted(cand, key=cand.get, reverse=True)
    best, second = order[0], order[1]

    # minimum price each of the four markets needs for a 2% edge
    minp = {mk: float(S.min_price(mk, pA, pB, pC, MIN_EDGE)) for mk in S.MARKETS}

    # why the 2.0 line is stronger or weaker here
    over_gap = pB / pC                      # absolute price the 2.0 over must give up
    under_stretch = (pA + pB) / pA          # multiplicative stretch the 2.0 under needs
    why20 = (f"push worth pB={pB:.3f}; an OVER 2.0 quote must sit exactly "
             f"{over_gap:.3f} below the OVER 2.5 quote to be equivalent, and an "
             f"UNDER 2.0 quote must be about {under_stretch:.2f}x the UNDER 2.5 "
             f"quote. At an equal percentage margin the 2.0 bet is simply the "
             f"same bet at {1-pB:.2f} stake, so it is neither stronger nor weaker.")
    why_side = (f"pC={pC:.3f} vs pA+pB={1-pC:.3f}; the book priced pC at "
                f"{pr['mkt_pC'].mean():.3f} "
                f"({'over' if pr['mkt_pC'].mean() > pC else 'under'}-stating it by "
                f"{abs(pr['mkt_pC'].mean()-pC):.3f}), so the "
                f"{'under' if pr['mkt_pC'].mean() > pC else 'over'} side carried the "
                f"smaller loss on development.")

    # ---- the certified decision --------------------------------------------
    # Nothing survived the frozen gates on development, and the one candidate
    # carried into validation by explicit exception failed there.  No segment
    # therefore has an out-of-sample warrant, and the certified action is
    # NO_BET everywhere.  The conditional rule below is the actionable part:
    # it states the price at which each market would become worth taking IF the
    # segment's estimated probabilities were the true ones.
    action = "NO_BET"
    best_ev = max(ev_o25, ev_u25, ev_o25m, ev_u25m)
    if best_ev >= MIN_EDGE:
        evidence = (f"in-sample only: {best} realised +{100*best_ev:.1f}% ROI on "
                    "development, but no candidate built on this survived the "
                    "frozen gates, and the strongest one failed validation")
    else:
        evidence = "no market cleared +2% realised ROI in sample at any available price"

    cA = E.wilson(int(d["is_A"].sum()), n)
    cB = E.wilson(int(d["is_B"].sum()), n)
    cC = E.wilson(int(d["is_C"].sum()), n)
    conditional = (
        f"OVER_2.0 only at >= {minp['OVER_2.0']:.2f}; "
        f"OVER_2.5 only at >= {minp['OVER_2.5']:.2f}; "
        f"UNDER_2.0 only at >= {minp['UNDER_2.0']:.2f}; "
        f"UNDER_2.5 only at >= {minp['UNDER_2.5']:.2f}; otherwise NO_BET")

    w, p, l = S.wpl(best, pA, pB, pC)
    return {
        "segment": name, "n": n,
        "pA": round(float(pA), 4), "pB": round(float(pB), 4), "pC": round(float(pC), 4),
        "second_market": second,
        "why_20_vs_25": why20, "why_over_vs_under": why_side,
        "fair_OVER_2.0": round(float(f["OVER_2.0"]), 3),
        "fair_OVER_2.5": round(float(f["OVER_2.5"]), 3),
        "fair_UNDER_2.0": round(float(f["UNDER_2.0"]), 3),
        "fair_UNDER_2.5": round(float(f["UNDER_2.5"]), 3),
        "min_odds_OVER_2.0": round(minp["OVER_2.0"], 3),
        "min_odds_OVER_2.5": round(minp["OVER_2.5"], 3),
        "min_odds_UNDER_2.0": round(minp["UNDER_2.0"], 3),
        "min_odds_UNDER_2.5": round(minp["UNDER_2.5"], 3),
        "offered_OVER_2.5_PRIMARY": round(o25, 3), "offered_UNDER_2.5_PRIMARY": round(u25, 3),
        "offered_OVER_2.5_MARKETMAX": round(o25m, 3), "offered_UNDER_2.5_MARKETMAX": round(u25m, 3),
        "ROI_OVER_2.5_PRIMARY_REALISED": round(ev_o25, 4), "ROI_UNDER_2.5_PRIMARY_REALISED": round(ev_u25, 4),
        "ROI_OVER_2.5_MARKETMAX_REALISED": round(ev_o25m, 4), "ROI_UNDER_2.5_MARKETMAX_REALISED": round(ev_u25m, 4),
        "n_closing_priced": n_cl,
        "ROI_OVER_2.5_PINNACLE_CLOSING": round(roi_o_cl, 4),
        "ROI_UNDER_2.5_PINNACLE_CLOSING": round(roi_u_cl, 4),
        "win_push_loss_best": f"{float(w):.3f}/{float(p):.3f}/{float(l):.3f}",
        "pA_ci95": f"{cA[0]:.3f}-{cA[1]:.3f}",
        "pB_ci95": f"{cB[0]:.3f}-{cB[1]:.3f}",
        "pC_ci95": f"{cC[0]:.3f}-{cC[1]:.3f}",
        "best_market_insample": best,
        "conditional_rule": conditional,
        "season_stability": season_stability(pr),
        "evidence": evidence,
        "risk": ("variance of a ~50/50 proposition; the 2.0 variant would cut both "
                 f"EV and variance by the factor {1-pB:.2f}"),
        "action": action,
    }


def main():
    m = FEAT.build()
    dev = m[m["block"] == "dev"].copy()
    th = C.load_thresholds()
    dev = C.apply_classes(dev, th)
    masks = C.segment_masks(dev)

    seq = {}
    p = D.OUT / "totals_sequential_tests.json"
    if p.exists():
        seq = json.loads(p.read_text())
    surviving = seq.get("surviving_effects", [])

    rows = []
    order = ["ALL_LA_LIGA", "STRONG_TEAM_HOME", "STRONG_TEAM_AWAY", "HEAVY_FAV_VS_WEAK",
             "MODERATE_FAV", "EVEN_MATCH", "TWO_ATTACKING", "TWO_DEFENSIVE",
             "STRONG_ATK_VS_STRONG_DEF", "WEAK_ATK_VS_WEAK_ATK",
             "HIGH_MARKET_TOTAL", "LOW_MARKET_TOTAL", "OPEN_PACE", "CLOSED_PACE"]
    for name in order:
        rows.append(row_for(name, dev[masks[name]]))

    # the two mandatory extra rows
    if surviving:
        d = dev.dropna(subset=["seqC_5"])
        r = row_for("CONFIRMED_SEQUENTIAL_STATE", d)
        r["evidence"] = f"sequential effects surviving FDR: {surviving}"
    else:
        r = {"segment": "CONFIRMED_SEQUENTIAL_STATE", "n": 0,
             "evidence": "NO sequential effect survived permutation, placebo and "
                         "FDR control -- there is no confirmed sequential state",
             "why_20_vs_25": "not applicable", "why_over_vs_under": "not applicable",
             "risk": "acting on a sequence here is the gambler's fallacy",
             "conditional_rule": "NO_BET at any price -- there is no state to condition on",
             "action": "NO_BET"}
    rows.append(r)
    rows.append({
        "segment": "NO_CONFIRMED_EDGE", "n": int(len(dev)),
        "evidence": "default row: everything not listed above",
        "why_20_vs_25": "no real 2.0 price history exists, so the 2.0 line cannot "
                        "be economically certified at all",
        "why_over_vs_under": "both 2.5 sides carry a negative expectation at the "
                             "Bet365 pre-match price",
        "risk": "certain loss of the margin",
        "conditional_rule": "NO_BET at any price offered by a margined book",
        "action": "NO_BET"})

    mx = pd.DataFrame(rows)
    cols = ["segment", "n", "pA", "pB", "pC", "pA_ci95", "pB_ci95", "pC_ci95",
            "best_market_insample", "second_market",
            "fair_OVER_2.0", "fair_OVER_2.5", "fair_UNDER_2.0", "fair_UNDER_2.5",
            "min_odds_OVER_2.0", "min_odds_OVER_2.5", "min_odds_UNDER_2.0",
            "min_odds_UNDER_2.5", "offered_OVER_2.5_PRIMARY", "offered_UNDER_2.5_PRIMARY",
            "offered_OVER_2.5_MARKETMAX", "offered_UNDER_2.5_MARKETMAX",
            "ROI_OVER_2.5_PRIMARY_REALISED", "ROI_UNDER_2.5_PRIMARY_REALISED",
            "ROI_OVER_2.5_MARKETMAX_REALISED", "ROI_UNDER_2.5_MARKETMAX_REALISED",
            "n_closing_priced", "ROI_OVER_2.5_PINNACLE_CLOSING",
            "ROI_UNDER_2.5_PINNACLE_CLOSING",
            "win_push_loss_best", "season_stability", "conditional_rule",
            "evidence", "why_20_vs_25", "why_over_vs_under", "risk", "action"]
    mx = mx.reindex(columns=cols)

    print("=== FINAL DECISION MATRIX (compact view) ===")
    show = ["segment", "n", "pA", "pB", "pC", "best_market_insample",
            "min_odds_OVER_2.0", "min_odds_OVER_2.5", "min_odds_UNDER_2.0",
            "min_odds_UNDER_2.5", "ROI_OVER_2.5_PRIMARY_REALISED",
            "ROI_UNDER_2.5_PRIMARY_REALISED", "ROI_UNDER_2.5_PINNACLE_CLOSING", "action"]
    print(mx[show].to_string(index=False))

    mx.to_json(D.OUT / "totals_verdict_matrix.json", orient="records", indent=2)
    try:
        with pd.ExcelWriter(D.OUT / "totals_verdict_matrix.xlsx", engine="openpyxl") as xl:
            mx.to_excel(xl, sheet_name="verdict_matrix", index=False)
            pd.DataFrame(json.loads((D.OUT / "totals_frozen_gates.json").read_text())
                         ["gates"]).T.reset_index().to_excel(
                xl, sheet_name="frozen_gates", index=False)
            if (D.OUT / "s07_breakeven.json").exists():
                be = json.loads((D.OUT / "s07_breakeven.json").read_text())
                pd.DataFrame(be["over_indifference"]).to_excel(
                    xl, sheet_name="breakeven_over", index=False)
                pd.DataFrame(be["under_indifference"]).to_excel(
                    xl, sheet_name="breakeven_under", index=False)
                pd.DataFrame(be["decision_surface_by_market_total"]).to_excel(
                    xl, sheet_name="decision_surface", index=False)
        print("\n[written] out/totals_verdict_matrix.xlsx")
    except Exception as e:
        print(f"\n[xlsx skipped: {e}]")
    print("[written] out/totals_verdict_matrix.json")


if __name__ == "__main__":
    main()
