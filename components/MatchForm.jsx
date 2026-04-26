"use client";

import { useState } from "react";

const LEAGUES = [
  "Premier League",
  "UEFA Champions League",
  "UEFA Europa League",
  "La Liga",
  "Bundesliga",
  "Serie A",
  "Ligue 1",
  "NBA",
  "NHL",
  "Other",
];

export default function MatchForm({ onSubmit, loading }) {
  const [form, setForm] = useState({
    league: "Premier League",
    leagueCustom: "",
    matchDate: "",
    homeTeam: "",
    awayTeam: "",
  });

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    const league = form.league === "Other" ? form.leagueCustom : form.league;
    onSubmit({ league, matchDate: form.matchDate, homeTeam: form.homeTeam, awayTeam: form.awayTeam });
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>League / Championship</label>
          <select value={form.league} onChange={set("league")} style={inputStyle} required>
            {LEAGUES.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>

        {form.league === "Other" && (
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={labelStyle}>Custom league name</label>
            <input
              value={form.leagueCustom}
              onChange={set("leagueCustom")}
              style={inputStyle}
              placeholder="e.g. MLS, RPL..."
              required
            />
          </div>
        )}

        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>Match date & time</label>
          <input
            type="datetime-local"
            value={form.matchDate}
            onChange={set("matchDate")}
            style={inputStyle}
            required
          />
        </div>

        <div>
          <label style={labelStyle}>Home team</label>
          <input
            value={form.homeTeam}
            onChange={set("homeTeam")}
            style={inputStyle}
            placeholder="e.g. Arsenal"
            required
          />
        </div>

        <div>
          <label style={labelStyle}>Away team</label>
          <input
            value={form.awayTeam}
            onChange={set("awayTeam")}
            style={inputStyle}
            placeholder="e.g. Chelsea"
            required
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={loading}
        style={{
          background: loading ? "rgba(0,200,255,0.04)" : "rgba(0,200,255,0.12)",
          border: `1px solid ${loading ? "rgba(0,200,255,0.1)" : "rgba(0,200,255,0.4)"}`,
          borderRadius: "8px",
          padding: "13px",
          color: loading ? "#2a4a5a" : "#00c8ff",
          fontSize: "12px",
          letterSpacing: "2px",
          textTransform: "uppercase",
          cursor: loading ? "not-allowed" : "pointer",
          fontFamily: "inherit",
          transition: "all 0.2s",
          width: "100%",
        }}
      >
        {loading ? "⚡ Analyzing..." : "Analyze Match →"}
      </button>
    </form>
  );
}

const labelStyle = {
  display: "block",
  fontSize: "10px",
  letterSpacing: "2px",
  color: "#4a6a8a",
  textTransform: "uppercase",
  marginBottom: "6px",
};

const inputStyle = {
  width: "100%",
  background: "rgba(255,255,255,0.03)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "6px",
  padding: "10px 12px",
  color: "#c8daea",
  fontSize: "13px",
  fontFamily: "'DM Mono', 'Courier New', monospace",
  outline: "none",
  boxSizing: "border-box",
  colorScheme: "dark",
};
