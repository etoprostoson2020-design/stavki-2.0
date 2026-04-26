"use client";

import { useRouter } from "next/navigation";

export default function MatchesList({ matches, leagueLabel }) {
  const router = useRouter();

  if (!matches.length) return null;

  const handleAnalyze = (match) => {
    sessionStorage.setItem("pendingMatch", JSON.stringify(match));
    sessionStorage.setItem("pendingLeague", leagueLabel);
    router.push("/analysis");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {matches.map((match) => {
        const date = new Date(match.commence_time);
        const h2h = match.bookmakers?.[0]?.markets?.find((m) => m.key === "h2h");
        const outcomes = h2h?.outcomes || [];
        const homeOdds = outcomes.find((o) => o.name === match.home_team)?.price;
        const awayOdds = outcomes.find((o) => o.name === match.away_team)?.price;
        const drawOdds = outcomes.find((o) => o.name === "Draw")?.price;

        return (
          <div
            key={match.id}
            style={{
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: "12px",
              padding: "16px 20px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "16px",
              flexWrap: "wrap",
              boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
            }}
          >
            <div style={{ flex: 1, minWidth: "200px" }}>
              <div style={{ fontSize: "15px", fontWeight: "700", color: "#0f172a", marginBottom: "4px" }}>
                {match.home_team} — {match.away_team}
              </div>
              <div style={{ fontSize: "12px", color: "#94a3b8" }}>
                {date.toLocaleString("ru-RU", { day: "2-digit", month: "long", hour: "2-digit", minute: "2-digit" })}
              </div>
            </div>

            {(homeOdds || drawOdds || awayOdds) && (
              <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
                {[
                  { label: "П1", value: homeOdds },
                  { label: "X", value: drawOdds },
                  { label: "П2", value: awayOdds },
                ].map(({ label, value }) =>
                  value ? (
                    <div key={label} style={{
                      background: "#f8fafc", border: "1px solid #e2e8f0",
                      borderRadius: "8px", padding: "6px 10px", textAlign: "center", minWidth: "44px",
                    }}>
                      <div style={{ fontSize: "10px", color: "#94a3b8", marginBottom: "2px" }}>{label}</div>
                      <div style={{ fontSize: "13px", fontWeight: "700", color: "#0ea5e9" }}>{value.toFixed(2)}</div>
                    </div>
                  ) : null
                )}
              </div>
            )}

            <button
              onClick={() => handleAnalyze(match)}
              style={{
                background: "#0ea5e9",
                border: "none", borderRadius: "8px",
                padding: "10px 22px", color: "#ffffff",
                fontSize: "13px", fontWeight: "600",
                cursor: "pointer", flexShrink: 0,
                fontFamily: "inherit", transition: "background 0.2s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#0284c7")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "#0ea5e9")}
            >
              Анализировать →
            </button>
          </div>
        );
      })}
    </div>
  );
}
