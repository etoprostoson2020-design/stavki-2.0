"use client";

import { useState } from "react";
import Link from "next/link";
import MatchForm from "@/components/MatchForm";
import AnalysisDisplay from "@/components/AnalysisDisplay";

export default function Home() {
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState("");
  const [analysisId, setAnalysisId] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async (formData) => {
    setLoading(true);
    setAnalysis("");
    setAnalysisId(null);
    setError(null);

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Server error");
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
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "text") {
              setAnalysis((prev) => prev + event.content);
            } else if (event.type === "done") {
              setAnalysisId(event.id);
            } else if (event.type === "error") {
              throw new Error(event.message);
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0a0e1a", color: "#e8eaf0", fontFamily: "'DM Mono','Courier New',monospace" }}>
      {/* Header */}
      <header style={{
        background: "linear-gradient(135deg,#0d1b2a 0%,#1a0a2e 50%,#0d1b2a 100%)",
        borderBottom: "1px solid #1e3a5f",
        padding: "28px 24px",
        position: "relative",
        overflow: "hidden",
      }}>
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: "linear-gradient(rgba(0,200,255,0.04) 1px,transparent 1px),linear-gradient(90deg,rgba(0,200,255,0.04) 1px,transparent 1px)",
          backgroundSize: "40px 40px",
        }} />
        <div style={{ position: "relative", zIndex: 1, maxWidth: "860px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <div style={{ fontSize: "10px", letterSpacing: "3px", color: "#00c8ff", textTransform: "uppercase", marginBottom: "6px" }}>
              AI Betting Analyst
            </div>
            <h1 style={{ margin: 0, fontSize: "clamp(18px,4vw,28px)", fontWeight: "800", fontFamily: "'Arial Black',Impact,sans-serif", letterSpacing: "-0.5px", background: "linear-gradient(135deg,#fff 0%,#00c8ff 50%,#bf5fff 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              SPORTS BETTING ANALYST
            </h1>
          </div>
          <Link href="/history" style={{ textDecoration: "none" }}>
            <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "6px", padding: "8px 16px", fontSize: "11px", letterSpacing: "1px", color: "#4a6a8a", textTransform: "uppercase", cursor: "pointer" }}>
              History →
            </div>
          </Link>
        </div>
      </header>

      <main style={{ maxWidth: "860px", margin: "0 auto", padding: "32px 16px", display: "flex", flexDirection: "column", gap: "24px" }}>
        {/* Form card */}
        <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "12px", padding: "24px" }}>
          <div style={{ fontSize: "10px", letterSpacing: "2px", color: "#00c8ff", textTransform: "uppercase", marginBottom: "18px" }}>
            Match Details
          </div>
          <MatchForm onSubmit={handleSubmit} loading={loading} />
        </div>

        {/* Error */}
        {error && (
          <div style={{ background: "rgba(255,60,60,0.06)", border: "1px solid rgba(255,60,60,0.25)", borderRadius: "8px", padding: "14px 18px", fontSize: "12px", color: "#c86060" }}>
            ⚠️ {error}
          </div>
        )}

        {/* Analysis */}
        {(analysis || loading) && (
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
              <div style={{ fontSize: "10px", letterSpacing: "2px", color: "#00c8ff", textTransform: "uppercase" }}>
                Analysis
              </div>
              {analysisId && (
                <Link href={`/history/${analysisId}`} style={{ textDecoration: "none", fontSize: "10px", letterSpacing: "1px", color: "#4a6a8a", textTransform: "uppercase" }}>
                  Saved to history ↗
                </Link>
              )}
            </div>
            <AnalysisDisplay text={analysis} loading={loading} />
          </div>
        )}

        {/* Info cards */}
        {!analysis && !loading && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(200px,1fr))", gap: "10px", marginTop: "8px" }}>
            {[
              { icon: "📊", label: "Live Odds", desc: "Bet365, Pinnacle via The Odds API" },
              { icon: "🔍", label: "Web Search", desc: "Form, injuries, team news via Tavily" },
              { icon: "💹", label: "Value Bets", desc: "Edge = true prob − implied prob" },
              { icon: "🗄️", label: "History", desc: "All analyses saved to local SQLite DB" },
            ].map((c, i) => (
              <div key={i} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: "8px", padding: "14px" }}>
                <div style={{ fontSize: "20px", marginBottom: "6px" }}>{c.icon}</div>
                <div style={{ fontSize: "10px", fontWeight: "700", color: "#00c8ff", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "3px" }}>{c.label}</div>
                <div style={{ fontSize: "11px", color: "#4a6a8a", lineHeight: "1.5" }}>{c.desc}</div>
              </div>
            ))}
          </div>
        )}
      </main>

      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        select option { background: #0d1b2a; }
      `}</style>
    </div>
  );
}
