#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api_scout_test.py — живой тест 3 футбольных API под line-shopping + HT-признаки.
Чистый stdlib, без pip.

Провайдеры и free-планы (ключи только через env, НЕ хардкодить):
  1. API-Football v3   https://www.api-football.com/      free: 100 req/DAY     env APIFOOTBALL_KEY
  2. The Odds API v4   https://the-odds-api.com/          free: 500 credits/MO  env ODDS_API_KEY
  3. OddsPapi v4       https://oddspapi.io/en/docs        free: 250 req/MO      env ODDSPAPI_KEY

Опционально для OddsPapi (есть рабочие дефолты из доков):
  ODDSPAPI_BASE    URL-шаблон с {league} и/или {key}
  ODDSPAPI_EPL     tournamentId EPL      (док: 17)
  ODDSPAPI_LALIGA  tournamentId La Liga  (док: 8)

Запуск:  python3 api_scout_test.py
Вывод:   ./api_scout_out/<provider>_<probe>.json  (сырые ответы)
         ./api_scout_out/report.json              (сводные метрики)

Метрика, ради которой всё затевалось: не цена одного запроса, а
REQUESTS_PER_ROUND — сколько вызовов нужно на весь тур со ВСЕМИ книгами.
"""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_scout_out")
TIMEOUT = 25
UA = "api-scout-test/1.0 (+stdlib)"

# Размер тура для расчёта расхода запросов: EPL 10 матчей + La Liga 10 матчей.
MATCHES_PER_ROUND = 10
LEAGUES_TRACKED = 2

# ---------------------------------------------------------------- helpers ---


def _ctx():
    # Уважаем корпоративный CA, если он подсунут через env (прокси-окружения).
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if ca and os.path.exists(ca):
        return ssl.create_default_context(cafile=ca)
    return ssl.create_default_context()


def http_get(url, headers=None):
    """GET → (status, headers_dict, parsed_json_or_text, latency_ms, error)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx()) as r:
            raw = r.read().decode("utf-8", "replace")
            lat = int((time.time() - t0) * 1000)
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            try:
                return r.status, hdrs, json.loads(raw), lat, None
            except json.JSONDecodeError:
                return r.status, hdrs, raw[:2000], lat, "non-json body"
    except urllib.error.HTTPError as e:
        lat = int((time.time() - t0) * 1000)
        body = e.read().decode("utf-8", "replace")[:2000]
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
        return e.code, hdrs, body, lat, "HTTP %s" % e.code
    except Exception as e:  # noqa: BLE001 - разведка, любая ошибка информативна
        return 0, {}, None, int((time.time() - t0) * 1000), "%s: %s" % (type(e).__name__, e)


def save_raw(name, payload):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "%s.json" % name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def season_for(d):
    """Европейский футбольный сезон: с июля — новый год."""
    return d.year if d.month >= 7 else d.year - 1


def date_window(days=14):
    today = datetime.now(timezone.utc).date()
    return today, today + timedelta(days=days)


def pick(d, *path, default=None):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        elif isinstance(cur, list) and isinstance(p, int) and len(cur) > p:
            cur = cur[p]
        else:
            return default
    return cur


def rl(hdrs, *names):
    for n in names:
        if n in hdrs:
            return hdrs[n]
    return None


# ------------------------------------------------- 1. API-Football (v3) ----

AF_HOST = "https://v3.football.api-sports.io"
AF_LEAGUES = {"EPL": 39, "LaLiga": 140}


def _scan_markets_apifootball(bookmakers):
    """bookmakers[] -> bets[] -> values[]. Ищем Over/Under 2.5."""
    books, ou25 = set(), False
    for bm in bookmakers or []:
        if bm.get("name"):
            books.add(bm["name"])
        for bet in bm.get("bets") or []:
            if "over/under" in (bet.get("name") or "").lower():
                for v in bet.get("values") or []:
                    if "2.5" in str(v.get("value", "")):
                        ou25 = True
    return sorted(books), ou25


def probe_apifootball():
    key = os.environ.get("APIFOOTBALL_KEY")
    res = {"provider": "API-Football v3", "skipped": None, "probes": {}}
    if not key:
        res["skipped"] = "APIFOOTBALL_KEY не задан"
        return res

    hdr = {"x-apisports-key": key}
    frm, to = date_window()
    season = season_for(frm)
    res["season_detected"] = season

    # --- fixtures: ближайшее окно по обеим лигам -------------------------
    fixtures_seen, fx_probe = {}, {}
    for lname, lid in AF_LEAGUES.items():
        url = ("%s/fixtures?league=%d&season=%d&from=%s&to=%s"
               % (AF_HOST, lid, season, frm.isoformat(), to.isoformat()))
        st, h, body, lat, err = http_get(url, hdr)
        save_raw("apifootball_fixtures_%s" % lname, body)
        arr = pick(body, "response", default=[]) if isinstance(body, dict) else []
        fx_probe[lname] = {
            "status": st, "latency_ms": lat, "error": err or pick(body, "errors"),
            "fixtures_returned": len(arr),
            "rate_limit_day_remaining": rl(h, "x-ratelimit-requests-remaining"),
            "rate_limit_min_remaining": rl(h, "x-ratelimit-remaining"),
        }
        if arr:
            fixtures_seen[lname] = arr

    res["probes"]["fixtures"] = fx_probe

    # --- поля fixtures + HT-счёт (главный gate) --------------------------
    sample_fx_id, ht_report = None, {}
    for lname, arr in fixtures_seen.items():
        # берём последний сыгранный, иначе первый предстоящий
        finished = [f for f in arr if pick(f, "fixture", "status", "short") in ("FT", "AET", "PEN")]
        target = finished[-1] if finished else arr[0]
        sample_fx_id = sample_fx_id or pick(target, "fixture", "id")
        ht_report[lname] = {
            "fixture_id": pick(target, "fixture", "id"),
            "status": pick(target, "fixture", "status", "short"),
            "kickoff_iso": pick(target, "fixture", "date"),
            "timestamp": pick(target, "fixture", "timestamp"),
            "timezone": pick(target, "fixture", "timezone"),
            "venue": pick(target, "fixture", "venue", "name"),
            "referee": pick(target, "fixture", "referee"),
            "round": pick(target, "league", "round"),
            "HT": pick(target, "score", "halftime"),
            "FT": pick(target, "score", "fulltime"),
            "ET": pick(target, "score", "extratime"),
            "PEN": pick(target, "score", "penalty"),
        }
    res["probes"]["halftime_and_fields"] = ht_report
    res["has_halftime_score"] = any(
        isinstance(v.get("HT"), dict) and v["HT"].get("home") is not None
        for v in ht_report.values()
    )

    # --- odds: сколько книг на матч --------------------------------------
    if sample_fx_id:
        url = "%s/odds?fixture=%s" % (AF_HOST, sample_fx_id)
        st, h, body, lat, err = http_get(url, hdr)
        save_raw("apifootball_odds", body)
        bms = pick(body, "response", 0, "bookmakers", default=[]) if isinstance(body, dict) else []
        books, ou25 = _scan_markets_apifootball(bms)
        res["probes"]["odds"] = {
            "status": st, "latency_ms": lat, "error": err or pick(body, "errors"),
            "fixture_id": sample_fx_id,
            "books_on_match": len(books), "books": books[:60],
            "has_over_under_2_5": ou25,
            "paging": pick(body, "paging"),
            "rate_limit_day_remaining": rl(h, "x-ratelimit-requests-remaining"),
        }
        res["books_per_match"] = len(books)

    # --- расход на тур ----------------------------------------------------
    # /odds?league=&season= отдаёт лигу целиком, но пагинация ~10 матчей/стр.
    res["requests_per_round"] = {
        "fixtures": LEAGUES_TRACKED,
        "odds_all_books": LEAGUES_TRACKED * 1,  # + пагинация, см. paging в сыром JSON
        "results_with_HT": LEAGUES_TRACKED,     # HT приходит внутри fixtures — бесплатно
        "total_estimate": LEAGUES_TRACKED * 2,
        "note": "HT-счёт входит в fixtures, отдельных запросов на результаты не нужно",
    }
    return res


# -------------------------------------------------- 2. The Odds API (v4) ---

TOA_HOST = "https://api.the-odds-api.com/v4"
TOA_SPORTS = {"EPL": "soccer_epl", "LaLiga": "soccer_spain_la_liga"}
TOA_REGIONS = "uk,eu"
TOA_MARKETS = "h2h,totals"


def _scan_markets_theoddsapi(event):
    """bookmakers[] -> markets[] -> outcomes[]. Ищем totals с point=2.5."""
    books, ou25 = set(), False
    for bm in event.get("bookmakers") or []:
        books.add(bm.get("title") or bm.get("key"))
        for mk in bm.get("markets") or []:
            if mk.get("key") == "totals":
                for o in mk.get("outcomes") or []:
                    if str(o.get("point")) == "2.5":
                        ou25 = True
    return sorted(b for b in books if b), ou25


def probe_theoddsapi():
    key = os.environ.get("ODDS_API_KEY")
    res = {"provider": "The Odds API v4", "skipped": None, "probes": {}}
    if not key:
        res["skipped"] = "ODDS_API_KEY не задан"
        return res

    odds_probe, books_max = {}, 0
    for lname, sk in TOA_SPORTS.items():
        url = ("%s/sports/%s/odds/?apiKey=%s&regions=%s&markets=%s&oddsFormat=decimal"
               % (TOA_HOST, sk, urllib.parse.quote(key), TOA_REGIONS, TOA_MARKETS))
        st, h, body, lat, err = http_get(url)
        save_raw("theoddsapi_odds_%s" % lname, body)
        events = body if isinstance(body, list) else []
        per_event = []
        for ev in events:
            books, ou25 = _scan_markets_theoddsapi(ev)
            per_event.append({
                "id": ev.get("id"),
                "commence_time": ev.get("commence_time"),  # ISO8601 UTC (Z)
                "match": "%s vs %s" % (ev.get("home_team"), ev.get("away_team")),
                "books": len(books), "has_ou_2_5": ou25,
            })
            books_max = max(books_max, len(books))
        odds_probe[lname] = {
            "status": st, "latency_ms": lat, "error": err,
            "events_in_one_request": len(events),
            "books_per_match_max": max([e["books"] for e in per_event] or [0]),
            "books_per_match_min": min([e["books"] for e in per_event] or [0]),
            "sample": per_event[:10],
            "credits_used_by_this_call": rl(h, "x-requests-last"),
            "credits_remaining": rl(h, "x-requests-remaining"),
            "credits_used_total": rl(h, "x-requests-used"),
        }
    res["probes"]["odds"] = odds_probe
    res["books_per_match"] = books_max

    # --- scores: есть ли HT? (ожидаем: НЕТ, только текущий/финальный) ----
    sk = TOA_SPORTS["EPL"]
    url = "%s/sports/%s/scores/?apiKey=%s&daysFrom=3" % (TOA_HOST, sk, urllib.parse.quote(key))
    st, h, body, lat, err = http_get(url)
    save_raw("theoddsapi_scores", body)
    games = body if isinstance(body, list) else []
    completed = [g for g in games if g.get("completed")]
    sample = completed[0] if completed else (games[0] if games else {})
    # HT определяем как наличие period/half разбивки в структуре ответа
    blob = json.dumps(games)[:200000].lower()
    ht_markers = [m for m in ("halftime", "half_time", "period", "\"1h\"", "first_half") if m in blob]
    res["probes"]["scores"] = {
        "status": st, "latency_ms": lat, "error": err,
        "games_returned": len(games), "completed_returned": len(completed),
        "score_shape": sample.get("scores"),
        "halftime_markers_found": ht_markers,
        "credits_remaining": rl(h, "x-requests-remaining"),
    }
    res["has_halftime_score"] = bool(ht_markers)

    # --- расход на тур ----------------------------------------------------
    n_markets = len(TOA_MARKETS.split(","))
    n_regions = len(TOA_REGIONS.split(","))
    cost_per_call = n_markets * n_regions
    res["requests_per_round"] = {
        "odds_calls": LEAGUES_TRACKED,
        "credit_cost_formula": "markets(%d) x regions(%d) = %d credits/call"
                               % (n_markets, n_regions, cost_per_call),
        "credits_per_round": LEAGUES_TRACKED * cost_per_call,
        "scores_calls": LEAGUES_TRACKED,
        "scores_credits": LEAGUES_TRACKED * 1,
        "total_credits_estimate": LEAGUES_TRACKED * cost_per_call + LEAGUES_TRACKED,
        "note": "1 запрос = ВСЯ лига (все матчи тура) x все книги региона",
    }
    return res


# ------------------------------------------------------ 3. OddsPapi (v4) ---
# Док: https://oddspapi.io/en/docs  (endpoints: fixtures, odds, odds-by-tournaments,
# scores, settlements, historical-odds, bookmakers, tournaments, markets)
# Авторизация: ?apiKey=...   sportId=10 — футбол.  EPL tournamentId=17, La Liga=8.

OP_HOST = "https://api.oddspapi.io/v4"
OP_SPORT_ID = 10
OP_DEFAULT_BASE = OP_HOST + "/odds-by-tournaments?tournamentIds={league}&apiKey={key}"


def _scan_markets_oddspapi(fixture):
    """
    OddsPapi: fixture['bookmakerOdds'] = { "<slug>": {bookmakerIsActive, markets:[...] } }
    markets[] -> {marketName/marketId, outcomes:[{...}]}. Ищем totals 2.5.
    """
    books, ou25 = set(), False
    bo = fixture.get("bookmakerOdds") or fixture.get("bookmakers") or {}
    items = bo.items() if isinstance(bo, dict) else [(b.get("slug") or b.get("name"), b) for b in bo]
    for slug, payload in items:
        if slug:
            books.add(slug)
        markets = (payload or {}).get("markets") or []
        mk_iter = markets.values() if isinstance(markets, dict) else markets
        for mk in mk_iter:
            if not isinstance(mk, dict):
                continue
            name = str(mk.get("marketName") or mk.get("name") or mk.get("key") or "").lower()
            hay = json.dumps(mk)[:20000]
            if ("total" in name or "over" in name or "under" in name) and "2.5" in hay:
                ou25 = True
    return sorted(books), ou25


def probe_oddspapi():
    key = os.environ.get("ODDSPAPI_KEY")
    res = {"provider": "OddsPapi v4", "skipped": None, "probes": {}}
    if not key:
        res["skipped"] = "ODDSPAPI_KEY не задан"
        return res

    epl = os.environ.get("ODDSPAPI_EPL", "17")
    laliga = os.environ.get("ODDSPAPI_LALIGA", "8")
    base = os.environ.get("ODDSPAPI_BASE", OP_DEFAULT_BASE)
    leagues = "%s,%s" % (epl, laliga)
    res["config"] = {"base_template": base, "EPL": epl, "LaLiga": laliga}

    # --- fixtures ---------------------------------------------------------
    frm, to = date_window()
    fx_url = ("%s/fixtures?apiKey=%s&sportId=%d&tournamentId=%s&from=%s&to=%s"
              % (OP_HOST, urllib.parse.quote(key), OP_SPORT_ID, epl,
                 frm.isoformat(), to.isoformat()))
    st, h, body, lat, err = http_get(fx_url)
    save_raw("oddspapi_fixtures_EPL", body)
    fx_list = body if isinstance(body, list) else pick(body, "data", default=[]) or pick(body, "fixtures", default=[])
    res["probes"]["fixtures"] = {
        "status": st, "latency_ms": lat, "error": err,
        "fixtures_returned": len(fx_list) if isinstance(fx_list, list) else None,
        "sample_fields": sorted((fx_list[0] or {}).keys()) if isinstance(fx_list, list) and fx_list else None,
        "sample": fx_list[0] if isinstance(fx_list, list) and fx_list else None,
        "rate_limit_remaining": rl(h, "x-ratelimit-remaining", "x-requests-remaining"),
    }
    sample_fixture_id = None
    if isinstance(fx_list, list) and fx_list:
        sample_fixture_id = fx_list[0].get("fixtureId") or fx_list[0].get("id")

    # --- ГЛАВНАЯ ПРОВЕРКА: «1 запрос = весь board по 350+ книгам»? --------
    # A) odds-by-tournaments БЕЗ bookmaker  B) С bookmaker=pinnacle
    claim = {}
    for tag, extra in (("no_bookmaker_param", ""), ("bookmaker_pinnacle", "&bookmaker=pinnacle")):
        url = base.format(league=leagues, key=urllib.parse.quote(key)) + extra
        st, h, body, lat, err = http_get(url)
        save_raw("oddspapi_odds_by_tournaments_%s" % tag, body)
        arr = body if isinstance(body, list) else pick(body, "data", default=[]) or []
        books_union, per_fx = set(), []
        for fx in arr if isinstance(arr, list) else []:
            if not isinstance(fx, dict):
                continue
            books, ou25 = _scan_markets_oddspapi(fx)
            books_union.update(books)
            per_fx.append({
                "fixtureId": fx.get("fixtureId"),
                "startTime": fx.get("startTime"),
                "tournamentId": fx.get("tournamentId"),
                "hasOdds": fx.get("hasOdds"),
                "books": len(books), "has_ou_2_5": ou25,
            })
        claim[tag] = {
            "status": st, "latency_ms": lat, "error": err,
            "fixtures_in_one_request": len(per_fx),
            "distinct_books_in_response": len(books_union),
            "books_per_match_max": max([p["books"] for p in per_fx] or [0]),
            "sample": per_fx[:10],
            "rate_limit_remaining": rl(h, "x-ratelimit-remaining", "x-requests-remaining"),
        }
    res["probes"]["odds_by_tournaments"] = claim
    res["claim_1req_all_books"] = {
        "claimed": "1 request = whole board across 350+ bookmakers",
        "measured_distinct_books_without_bookmaker_param":
            claim["no_bookmaker_param"]["distinct_books_in_response"],
        "verdict": None,  # заполняется ниже
    }

    # --- odds по одному матчу: реальная глубина книг ----------------------
    if sample_fixture_id:
        url = "%s/odds?apiKey=%s&fixtureId=%s" % (OP_HOST, urllib.parse.quote(key), sample_fixture_id)
        st, h, body, lat, err = http_get(url)
        save_raw("oddspapi_odds_single_fixture", body)
        fx = body if isinstance(body, dict) else {}
        if isinstance(body, list) and body:
            fx = body[0]
        books, ou25 = _scan_markets_oddspapi(fx)
        res["probes"]["odds_single_fixture"] = {
            "status": st, "latency_ms": lat, "error": err,
            "fixtureId": sample_fixture_id,
            "books_on_match": len(books), "books": books[:60],
            "has_over_under_2_5": ou25,
            "rate_limit_remaining": rl(h, "x-ratelimit-remaining", "x-requests-remaining"),
        }
        res["books_per_match"] = len(books)

        # --- scores: HT по периодам --------------------------------------
        url = "%s/scores?apiKey=%s&fixtureId=%s" % (OP_HOST, urllib.parse.quote(key), sample_fixture_id)
        st, h, body, lat, err = http_get(url)
        save_raw("oddspapi_scores", body)
        scores = pick(body, "scores", default=body if isinstance(body, dict) else {})
        res["probes"]["scores"] = {
            "status": st, "latency_ms": lat, "error": err,
            "fixtureId": sample_fixture_id,
            "periods_returned": sorted(scores.keys()) if isinstance(scores, dict) else None,
            "raw": scores,
            "note": "периоды — числовые ключи (0=match,1=1H,2=2H...); HT = период 1",
        }
        res["has_halftime_score"] = bool(isinstance(scores, dict) and len(scores) > 1)

    # --- вердикт по заявлению + расход на тур -----------------------------
    d = res["claim_1req_all_books"]["measured_distinct_books_without_bookmaker_param"]
    res["claim_1req_all_books"]["verdict"] = (
        "CONFIRMED" if d >= 100 else
        "PARTIAL (%s книг в ответе — это не 350+)" % d if d > 1 else
        "REFUTED (endpoint отдаёт одну книгу за запрос)"
    )
    res["requests_per_round"] = {
        "fixtures": 1,
        "odds_all_books": "%d (endpoint /odds требует fixtureId → 1 запрос на матч)"
                          % (MATCHES_PER_ROUND * LEAGUES_TRACKED),
        "results_with_HT": "%d (/scores тоже требует fixtureId)"
                           % (MATCHES_PER_ROUND * LEAGUES_TRACKED),
        "total_estimate": 1 + 2 * MATCHES_PER_ROUND * LEAGUES_TRACKED,
        "free_quota_month": 250,
        "note": "odds-by-tournaments = 1 книга x N турниров; /odds = все книги x 1 матч",
    }
    return res


# ------------------------------------------------------------------ main ---


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    missing = [k for k in ("APIFOOTBALL_KEY", "ODDS_API_KEY", "ODDSPAPI_KEY")
               if not os.environ.get(k)]
    if missing:
        print("[!] Нет ключей в env: %s — эти провайдеры будут пропущены.\n"
              "    export APIFOOTBALL_KEY=...  ODDS_API_KEY=...  ODDSPAPI_KEY=...\n"
              % ", ".join(missing), file=sys.stderr)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "round_model": {"matches_per_league": MATCHES_PER_ROUND,
                        "leagues": LEAGUES_TRACKED},
        "providers": {},
    }

    for name, fn in (("apifootball", probe_apifootball),
                     ("theoddsapi", probe_theoddsapi),
                     ("oddspapi", probe_oddspapi)):
        print("→ probing %s ..." % name)
        try:
            report["providers"][name] = fn()
        except Exception as e:  # noqa: BLE001
            report["providers"][name] = {"fatal": "%s: %s" % (type(e).__name__, e)}
        p = report["providers"][name]
        if p.get("skipped"):
            print("   SKIP: %s" % p["skipped"])
        else:
            print("   HT=%s  books/match=%s  req/round=%s"
                  % (p.get("has_halftime_score"), p.get("books_per_match"),
                     pick(p, "requests_per_round", "total_estimate")))

    path = save_raw("report", report)
    print("\n✔ report: %s\n  raw: %s/" % (path, OUT_DIR))


if __name__ == "__main__":
    main()
