"use client";

import { useState } from "react";
import Link from "next/link";
import MatchesList from "@/components/MatchesList";
import AnalysisDisplay from "@/components/AnalysisDisplay";

const LEAGUES = [
  { sport: "soccer_epl", label: "Английская Премьер-лига" },
  { sport: "soccer_spain_la_liga", label: "Ла Лига (Испания)" },
  { sport: "soccer_germany_bundesliga", label: "Бундеслига (Германия)" },
  { sport: "soccer_italy_serie_a", label: "Серия А (Италия)" },
  { sport: "soccer_france_ligue_one", label: "Лига 1 (Франция)" },
  { sport: "soccer_uefa_champs_league", label: "Лига чемпионов УЕФА" },
  { sport: "soccer_uefa_europa_league", label: "Лига Европы УЕФА" },
  { sport: "basketball_nba", label: "НБА" },
  { sport: "icehockey_nhl", label: "НХЛ" },
];

export default function Home() {
  const [sport, setSport] = useState("soccer_epl");
  const [matches, setMatches] = useState(null);
  const [loadingMatches, setLoadingMatches] = useState(false);
  const [matchesError, setMatchesError] = useState(null);

  const [analyzingId, setAnalyzingId] = useState(null);
  const [selectedMatch, setSelectedMatch] = useState(null);
  const [analysis, setAnalysis] = useState("");
  const [analysisId, setAnalysisId] = useState(null);
  const [analysisError, setAnalysisError] = useState(null);

  const fetchMatches = async () => {
    setLoadingMatches(true);
    setMatchesError(null);
    setMatches(null);
    setSelectedMatch(null);
    setAnalysis("");
    setAnalysisId(null);

    try {
      const res = await fetch(`/api/matches?sport=${sport}`);
      const data = await res.json();
      if (data.error) {
        setMatchesError(data.error);
      } else if (data.length === 0) {
        setMatchesError("Нет предстоящих матчей в ближайшие 7 дней");
      } else {
        setMatches(data);
      }
    } catch {
      setMatchesError("Ошибка при загрузке матчей");
    } finally {
      setLoadingMatches(false);
    }
  };

  const analyzeMatch = async (match) => {
    setSelectedMatch(match);
    setAnalysis("");
    setAnalysisId(null);
    setAnalysisError(null);
    setAnalyzingId(match.id);

    const leagueLabel = LEAGUES.find((l) => l.sport === sport)?.label || sport;
    const matchDate = new Date(match.commence_time).toLocaleString("ru-RU", {
      day: "2-digit", month: "long", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          league: leagueLabel,
          matchDate,
          homeTeam: match.home_team,
          awayTeam: match.away_team,
          matchBookmakers: match.bookmakers || [],
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Ошибка сервера");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let event;
          try {
            event = JSON.parse(line.slice(6));
          } catch {
            continue;
          }
          if (event.type === "text") setAnalysis((p) => p + event.content);
          else if (event.type === "done") setAnalysisId(event.id);
          else if (event.type === "error") throw new Error(event.message);
        }
      }
    } catch (err) {
      setAnalysisError(err.message);
    } finally {
      setAnalyzingId(null);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f0f4f8", fontFamily: "'Inter','Segoe UI',sans-serif", color: "#0f172a" }}>

      {/* Шапка */}
      <header style={{
        background: "linear-gradient(135deg,#0f172a 0%,#1e1040 50%,#0f172a 100%)",
        padding: "24px",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px",
      }}>
        <div>
          <div style={{ fontSize: "11px", letterSpacing: "3px", color: "#38bdf8", textTransform: "uppercase", marginBottom: "4px" }}>
            AI Аналитик ставок
          </div>
          <h1 style={{ margin: 0, fontSize: "clamp(18px,4vw,26px)", fontWeight: "800", color: "#ffffff", letterSpacing: "-0.5px" }}>
            Спортивный аналитик
          </h1>
        </div>
        <Link href="/history" style={{ textDecoration: "none" }}>
          <div style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: "8px", padding: "8px 16px", fontSize: "13px", color: "#94a3b8", cursor: "pointer" }}>
            История →
          </div>
        </Link>
      </header>

      <main style={{ maxWidth: "900px", margin: "0 auto", padding: "32px 16px", display: "flex", flexDirection: "column", gap: "24px" }}>

        {/* Выбор лиги */}
        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "16px", padding: "24px", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
          <div style={{ fontSize: "13px", fontWeight: "600", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "16px" }}>
            Выберите лигу
          </div>
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            <select
              value={sport}
              onChange={(e) => { setSport(e.target.value); setMatches(null); setSelectedMatch(null); setAnalysis(""); }}
              style={{
                flex: 1, minWidth: "220px",
                background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "10px",
                padding: "12px 16px", fontSize: "14px", color: "#0f172a",
                fontFamily: "inherit", outline: "none", cursor: "pointer",
              }}
            >
              {LEAGUES.map((l) => (
                <option key={l.sport} value={l.sport}>{l.label}</option>
              ))}
            </select>
            <button
              onClick={fetchMatches}
              disabled={loadingMatches}
              style={{
                background: loadingMatches ? "#e2e8f0" : "#0ea5e9",
                border: "none", borderRadius: "10px",
                padding: "12px 28px", fontSize: "14px", fontWeight: "600",
                color: loadingMatches ? "#94a3b8" : "#ffffff",
                cursor: loadingMatches ? "not-allowed" : "pointer",
                fontFamily: "inherit", transition: "all 0.2s", whiteSpace: "nowrap",
              }}
            >
              {loadingMatches ? "Загрузка..." : "Показать матчи"}
            </button>
          </div>
        </div>

        {/* Ошибка матчей */}
        {matchesError && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "10px", padding: "14px 18px", fontSize: "13px", color: "#dc2626" }}>
            ⚠️ {matchesError}
          </div>
        )}

        {/* Список матчей */}
        {matches && (
          <div>
            <div style={{ fontSize: "13px", fontWeight: "600", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "12px" }}>
              Предстоящие матчи — {LEAGUES.find((l) => l.sport === sport)?.label}
            </div>
            <MatchesList matches={matches} onAnalyze={analyzeMatch} analyzingId={analyzingId} />
          </div>
        )}

        {/* Ошибка анализа */}
        {analysisError && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "10px", padding: "14px 18px", fontSize: "13px", color: "#dc2626" }}>
            ⚠️ {analysisError}
          </div>
        )}

        {/* Анализ */}
        {(analysis || analyzingId) && (
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px", flexWrap: "wrap", gap: "8px" }}>
              <div style={{ fontSize: "13px", fontWeight: "600", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px" }}>
                {selectedMatch && `${selectedMatch.home_team} — ${selectedMatch.away_team}`}
              </div>
              {analysisId && (
                <Link href={`/history/${analysisId}`} style={{ textDecoration: "none", fontSize: "12px", color: "#0ea5e9" }}>
                  Сохранено в историю ↗
                </Link>
              )}
            </div>
            <AnalysisDisplay text={analysis} loading={!!analyzingId} />
          </div>
        )}

        {/* Стартовый экран */}
        {!matches && !loadingMatches && !matchesError && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(200px,1fr))", gap: "12px" }}>
            {[
              { icon: "📊", label: "Живые коэффициенты", desc: "Bet365, Pinnacle и другие через The Odds API" },
              { icon: "🔍", label: "Веб-поиск", desc: "Форма команд, травмы, новости через Tavily" },
              { icon: "💹", label: "Поиск Value Bets", desc: "Преимущество = реальная вероятность − котировка" },
              { icon: "🗄️", label: "История", desc: "Все анализы сохраняются в локальную БД" },
            ].map((c, i) => (
              <div key={i} style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "12px", padding: "16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ fontSize: "22px", marginBottom: "8px" }}>{c.icon}</div>
                <div style={{ fontSize: "12px", fontWeight: "700", color: "#0ea5e9", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "4px" }}>{c.label}</div>
                <div style={{ fontSize: "12px", color: "#94a3b8", lineHeight: "1.5" }}>{c.desc}</div>
              </div>
            ))}
          </div>
        )}
      </main>

      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0}} @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}`}</style>
    </div>
  );
}
