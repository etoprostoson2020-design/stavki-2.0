"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AnalysisDisplay from "@/components/AnalysisDisplay";

export default function AnalysisPage() {
  const router = useRouter();
  const [match, setMatch] = useState(null);
  const [league, setLeague] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [savedId, setSavedId] = useState(null);
  const [bestOdds, setBestOdds] = useState(null);

  useEffect(() => {
    const raw = sessionStorage.getItem("pendingMatch");
    const lg = sessionStorage.getItem("pendingLeague") || "";
    if (!raw) { router.replace("/"); return; }

    const m = JSON.parse(raw);
    setMatch(m);
    setLeague(lg);
    setBestOdds(extractBestOdds(m));
    startAnalysis(m, lg);
  }, []);

  const startAnalysis = async (m, lg) => {
    const matchDate = new Date(m.commence_time).toLocaleString("ru-RU", {
      day: "2-digit", month: "long", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          league: lg,
          matchDate,
          homeTeam: m.home_team,
          awayTeam: m.away_team,
          matchBookmakers: m.bookmakers || [],
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
          try { event = JSON.parse(line.slice(6)); } catch { continue; }
          if (event.type === "text") setAnalysis((p) => p + event.content);
          else if (event.type === "done") setSavedId(event.id);
          else if (event.type === "error") throw new Error(event.message);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!match) return null;

  const matchDate = new Date(match.commence_time).toLocaleString("ru-RU", {
    day: "2-digit", month: "long", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });

  return (
    <div style={{ minHeight: "100vh", background: "#f0f4f8", fontFamily: "'Inter','Segoe UI',sans-serif", color: "#0f172a" }}>

      {/* Шапка */}
      <header style={{
        background: "linear-gradient(135deg,#0f172a 0%,#1e1040 50%,#0f172a 100%)",
        padding: "24px",
      }}>
        <div style={{ maxWidth: "900px", margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap", marginBottom: "16px" }}>
            <Link href="/" style={{ textDecoration: "none" }}>
              <div style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: "8px", padding: "7px 14px", fontSize: "13px", color: "#94a3b8" }}>
                ← Назад
              </div>
            </Link>
            {savedId && (
              <Link href={`/history/${savedId}`} style={{ textDecoration: "none", fontSize: "12px", color: "#38bdf8" }}>
                Сохранено в историю ↗
              </Link>
            )}
          </div>

          <div style={{ fontSize: "11px", letterSpacing: "3px", color: "#38bdf8", textTransform: "uppercase", marginBottom: "6px" }}>{league}</div>
          <h1 style={{ margin: "0 0 4px", fontSize: "clamp(18px,4vw,28px)", fontWeight: "800", color: "#ffffff" }}>
            {match.home_team} — {match.away_team}
          </h1>
          <div style={{ fontSize: "13px", color: "#64748b" }}>{matchDate}</div>
        </div>
      </header>

      <main style={{ maxWidth: "900px", margin: "0 auto", padding: "28px 16px", display: "flex", flexDirection: "column", gap: "20px" }}>

        {/* Лучшие коэффициенты */}
        {bestOdds && (
          <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "16px", padding: "20px", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
            <div style={{ fontSize: "12px", fontWeight: "700", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "16px" }}>
              Лучшие коэффициенты
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: "10px" }}>
              {bestOdds.map((o, i) => (
                <div key={i} style={{
                  background: o.highlight ? "linear-gradient(135deg,#f0fdf4,#dcfce7)" : "#f8fafc",
                  border: `1px solid ${o.highlight ? "#86efac" : "#e2e8f0"}`,
                  borderRadius: "12px", padding: "14px", textAlign: "center",
                }}>
                  <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: "4px", fontWeight: "600" }}>{o.market}</div>
                  <div style={{ fontSize: "22px", fontWeight: "800", color: o.highlight ? "#16a34a" : "#0ea5e9", marginBottom: "2px" }}>
                    {o.price.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "10px", color: "#94a3b8" }}>{o.bookmaker}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Ошибка */}
        {error && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "12px", padding: "16px 20px", fontSize: "13px", color: "#dc2626" }}>
            ⚠️ {error}
          </div>
        )}

        {/* Анализ */}
        <div>
          <div style={{ fontSize: "12px", fontWeight: "700", color: "#64748b", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "12px" }}>
            {loading ? "⚡ Анализирую..." : "Анализ"}
          </div>
          <AnalysisDisplay text={analysis} loading={loading} />
        </div>

      </main>
    </div>
  );
}

function extractBestOdds(match) {
  if (!match.bookmakers?.length) return null;

  const best = {};

  for (const bm of match.bookmakers) {
    for (const market of bm.markets) {
      for (const o of market.outcomes) {
        const key = market.key === "h2h"
          ? (o.name === match.home_team ? "П1" : o.name === match.away_team ? "П2" : "Ничья")
          : market.key === "totals"
          ? (o.name === "Over" ? `ТБ ${o.point}` : `ТМ ${o.point}`)
          : null;

        if (!key) continue;
        if (!best[key] || o.price > best[key].price) {
          best[key] = { market: key, price: o.price, bookmaker: bm.title };
        }
      }
    }
  }

  const order = ["П1", "Ничья", "П2", "ТБ 2.5", "ТМ 2.5"];
  const result = order
    .filter((k) => best[k])
    .map((k) => ({ ...best[k], highlight: best[k].price >= 2.0 }));

  return result.length ? result : null;
}
