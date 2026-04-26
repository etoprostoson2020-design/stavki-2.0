"use client";

import { useState } from "react";

const prompt = `You are an expert sports betting analyst application. Your task is to analyze bookmaker lines and provide the most statistically justified betting recommendations.

## INPUT DATA
The user provides:
- Championship / League (e.g., Premier League, UEFA Champions League, NBA, NHL)
- Match date and time
- Home team
- Away team

## YOUR ANALYSIS PROCESS

### Step 1 — Web Search
Use the web_search tool to find:
1. Current bookmaker odds from major bookmakers (Bet365, William Hill, 1xBet, Pinnacle, etc.) for this match
2. Recent form of both teams (last 5-10 matches): wins, losses, goals scored/conceded
3. Head-to-head statistics for the last 3-5 years
4. Key player injuries and suspensions
5. Motivational factors: tournament position, importance of the match, relegation/title fight
6. Home/away performance statistics for each team
7. Average goals per match, BTTS (Both Teams to Score) statistics
8. Corner kicks, yellow cards statistics (for specific markets)
9. Odds movement — how the line has changed since opening (sharp money signals)

### Step 2 — Line Analysis
Analyze the full bookmaker line across all markets:
- Match result (1X2)
- Asian handicaps
- Total goals (Over/Under): 0.5, 1.5, 2.5, 3.5, 4.5
- Both Teams to Score (BTTS)
- Correct score
- First goal scorer
- Half-time result
- Double chance (1X, X2, 12)
- Draw No Bet
- Corners, cards (if data available)

### Step 3 — Value Detection
For each market calculate:
- **True probability** based on statistics (your assessment)
- **Implied probability** from bookmaker odds (1 / decimal odds)
- **Value** = True probability − Implied probability
- Positive value (>5%) = VALUE BET

### Step 4 — Output

Return recommendations in the following structured format:

---
## ⚽ [TEAM A] vs [TEAM B]
### 📅 [Championship] | [Date] [Time]

---
### 📊 MATCH ANALYSIS

**Form (last 5 matches):**
- [Team A]: W-W-D-L-W | Avg goals: 1.8 scored / 0.9 conceded
- [Team B]: L-D-W-L-D | Avg goals: 1.1 scored / 1.4 conceded

**Head-to-head (last 5):** [brief stats]
**Key absences:** [injuries/suspensions]
**Motivational context:** [brief analysis]

---
### 🎯 TOP RECOMMENDATIONS (sorted by confidence)

#### ✅ BET #1 — [Market Name]
| Parameter | Value |
|-----------|-------|
| Bet | [exact bet, e.g., "Total Over 2.5"] |
| Odds | [e.g., 1.85] |
| Our probability | [e.g., 62%] |
| Implied probability | [e.g., 54%] |
| Value (edge) | [e.g., +8%] |
| Confidence | ⭐⭐⭐⭐⭐ (5/5) |
| Recommended stake | [e.g., 3% of bankroll] |
| Justification | [2-3 sentences explaining why] |

#### ✅ BET #2 — [Market Name]
[same structure]

#### ✅ BET #3 — [Market Name]
[same structure]

---
### ⚠️ RISKS & CONTRA-INDICATORS
- [What could go wrong]
- [Factors reducing confidence]

---
### 💡 EXPRESS/PARLAY OPTION
[If 2+ bets have high confidence, suggest a parlay with combined odds]

---
### 📌 SUMMARY
**Best single bet:** [Market] — [Odds]
**Risk level:** Low / Medium / High
**Overall confidence in analysis:** [X]%

---

## RULES & CONSTRAINTS
1. NEVER recommend a bet without positive value (+EV)
2. Minimum confidence to include a recommendation: 55% true probability
3. Maximum 5 recommendations per match
4. Always specify bankroll management (stake as % of bankroll)
5. If data is insufficient — explicitly state it and lower confidence rating
6. Never fabricate statistics — only use data found via web search
7. If bookmaker odds are unavailable — indicate this and use historical averages
8. Always mention the most important risk factor

## TONE & STYLE
- Professional, analytical, data-driven
- No hype, no guarantees ("this is certain to win")
- Honest about uncertainty
- Use tables and structured formatting for readability
`;

export default function SportsBettingPrompt() {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState("prompt");

  const handleCopy = () => {
    navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const features = [
    { icon: "🔍", title: "Web Search", desc: "Automatically searches for current odds, team form, injuries across bookmakers" },
    { icon: "📊", title: "Full Line Analysis", desc: "Covers all markets: 1X2, Asian handicap, totals, BTTS, correct score and more" },
    { icon: "💹", title: "Value Detection", desc: "Calculates edge between true probability and bookmaker's implied probability" },
    { icon: "🎯", title: "Ranked Picks", desc: "Returns top 3–5 bets sorted by confidence with stake sizing recommendations" },
    { icon: "⚠️", title: "Risk Disclosure", desc: "Always highlights contra-indicators and factors that reduce confidence" },
    { icon: "📌", title: "Bankroll Mgmt", desc: "Each pick includes recommended stake as % of bankroll using Kelly-style sizing" },
  ];

  const howToUse = [
    { step: "1", text: "Copy the prompt below" },
    { step: "2", text: 'Paste it into Claude as a System Prompt (or start a conversation with it)' },
    { step: "3", text: 'Input a match: "Premier League, 27 April 2026, 17:30 — Arsenal vs Chelsea"' },
    { step: "4", text: "Claude searches the web, analyzes the full bookmaker line and returns ranked value bets" },
  ];

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0a0e1a",
      color: "#e8eaf0",
      fontFamily: "'DM Mono', 'Courier New', monospace",
      padding: "0",
    }}>
      {/* Header */}
      <div style={{
        background: "linear-gradient(135deg, #0d1b2a 0%, #1a0a2e 50%, #0d1b2a 100%)",
        borderBottom: "1px solid #1e3a5f",
        padding: "40px 24px 32px",
        textAlign: "center",
        position: "relative",
        overflow: "hidden",
      }}>
        {/* Background grid */}
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: "linear-gradient(rgba(0,200,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,200,255,0.04) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }} />

        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{
            display: "inline-block",
            background: "rgba(0,200,255,0.08)",
            border: "1px solid rgba(0,200,255,0.25)",
            borderRadius: "4px",
            padding: "4px 14px",
            fontSize: "11px",
            letterSpacing: "3px",
            color: "#00c8ff",
            marginBottom: "16px",
            textTransform: "uppercase",
          }}>AI Prompt Engineering</div>

          <h1 style={{
            fontSize: "clamp(26px, 5vw, 48px)",
            fontWeight: "800",
            margin: "0 0 12px",
            fontFamily: "'Arial Black', 'Impact', sans-serif",
            letterSpacing: "-1px",
            background: "linear-gradient(135deg, #ffffff 0%, #00c8ff 50%, #bf5fff 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}>
            SPORTS BETTING<br />ANALYST PROMPT
          </h1>

          <p style={{
            color: "#7a8fa8",
            fontSize: "14px",
            maxWidth: "500px",
            margin: "0 auto",
            lineHeight: "1.6",
          }}>
            A structured system prompt that turns Claude into a professional betting analyst — with live web search, value calculation, and full bookmaker line coverage.
          </p>
        </div>
      </div>

      <div style={{ maxWidth: "860px", margin: "0 auto", padding: "32px 16px" }}>

        {/* Features grid */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
          gap: "12px",
          marginBottom: "32px",
        }}>
          {features.map((f, i) => (
            <div key={i} style={{
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.07)",
              borderRadius: "8px",
              padding: "16px",
            }}>
              <div style={{ fontSize: "22px", marginBottom: "6px" }}>{f.icon}</div>
              <div style={{ fontSize: "12px", fontWeight: "700", color: "#00c8ff", letterSpacing: "1px", marginBottom: "4px", textTransform: "uppercase" }}>{f.title}</div>
              <div style={{ fontSize: "12px", color: "#6b7a8d", lineHeight: "1.5" }}>{f.desc}</div>
            </div>
          ))}
        </div>

        {/* How to use */}
        <div style={{
          background: "rgba(0,200,255,0.04)",
          border: "1px solid rgba(0,200,255,0.15)",
          borderRadius: "10px",
          padding: "20px 24px",
          marginBottom: "28px",
        }}>
          <div style={{ fontSize: "11px", letterSpacing: "2px", color: "#00c8ff", marginBottom: "14px", textTransform: "uppercase" }}>How to use</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {howToUse.map((h, i) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
                <div style={{
                  minWidth: "24px", height: "24px",
                  background: "rgba(0,200,255,0.15)",
                  border: "1px solid rgba(0,200,255,0.3)",
                  borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "11px", fontWeight: "700", color: "#00c8ff",
                  flexShrink: 0,
                }}>{h.step}</div>
                <div style={{ fontSize: "13px", color: "#a0b0c0", lineHeight: "1.5", paddingTop: "3px" }}>{h.text}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: "4px", marginBottom: "16px" }}>
          {["prompt", "example"].map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              background: activeTab === tab ? "rgba(0,200,255,0.12)" : "transparent",
              border: activeTab === tab ? "1px solid rgba(0,200,255,0.35)" : "1px solid rgba(255,255,255,0.08)",
              borderRadius: "6px",
              padding: "8px 20px",
              color: activeTab === tab ? "#00c8ff" : "#5a6a7a",
              fontSize: "12px",
              letterSpacing: "1px",
              textTransform: "uppercase",
              cursor: "pointer",
              fontFamily: "inherit",
              transition: "all 0.2s",
            }}>
              {tab === "prompt" ? "📋 System Prompt" : "💬 Example Input"}
            </button>
          ))}
        </div>

        {/* Prompt box */}
        {activeTab === "prompt" && (
          <div style={{ position: "relative" }}>
            <div style={{
              background: "#080d18",
              border: "1px solid #1a2a3a",
              borderRadius: "10px",
              padding: "20px",
              maxHeight: "480px",
              overflowY: "auto",
              fontSize: "12px",
              lineHeight: "1.7",
              color: "#8fa8bf",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}>
              {prompt}
            </div>
            <button onClick={handleCopy} style={{
              position: "absolute",
              top: "12px",
              right: "12px",
              background: copied ? "rgba(0,200,100,0.15)" : "rgba(0,200,255,0.1)",
              border: copied ? "1px solid rgba(0,200,100,0.4)" : "1px solid rgba(0,200,255,0.3)",
              borderRadius: "6px",
              padding: "6px 14px",
              color: copied ? "#00c864" : "#00c8ff",
              fontSize: "11px",
              letterSpacing: "1px",
              textTransform: "uppercase",
              cursor: "pointer",
              fontFamily: "inherit",
              transition: "all 0.25s",
            }}>
              {copied ? "✓ Copied!" : "Copy"}
            </button>
          </div>
        )}

        {activeTab === "example" && (
          <div style={{
            background: "#080d18",
            border: "1px solid #1a2a3a",
            borderRadius: "10px",
            padding: "24px",
            fontSize: "13px",
            lineHeight: "1.8",
            color: "#8fa8bf",
          }}>
            <div style={{ color: "#00c8ff", marginBottom: "16px", fontSize: "11px", letterSpacing: "2px", textTransform: "uppercase" }}>User input example</div>
            <div style={{
              background: "rgba(0,200,255,0.06)",
              border: "1px solid rgba(0,200,255,0.15)",
              borderRadius: "6px",
              padding: "14px 16px",
              marginBottom: "20px",
              color: "#c8daea",
            }}>
              Premier League, 27 April 2026, 17:30 — Arsenal vs Chelsea
            </div>

            <div style={{ color: "#bf5fff", marginBottom: "12px", fontSize: "11px", letterSpacing: "2px", textTransform: "uppercase" }}>What Claude does</div>
            {[
              "🔍 Searches current odds on Bet365, Pinnacle, 1xBet",
              "📈 Analyses Arsenal's last 10 home matches (form, goals, xG)",
              "📉 Analyses Chelsea's last 10 away matches",
              "🤝 Checks head-to-head record for the last 5 years",
              "🏥 Searches for confirmed injuries and suspensions",
              "💹 Calculates value for each market across the full bookmaker line",
              "🎯 Returns top 3–5 picks with confidence ratings and stake sizing",
            ].map((item, i) => (
              <div key={i} style={{ padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "13px" }}>{item}</div>
            ))}
          </div>
        )}

        {/* Disclaimer */}
        <div style={{
          marginTop: "24px",
          padding: "14px 18px",
          background: "rgba(255,180,0,0.05)",
          border: "1px solid rgba(255,180,0,0.2)",
          borderRadius: "8px",
          fontSize: "11px",
          color: "#7a6840",
          lineHeight: "1.6",
        }}>
          ⚠️ <strong style={{ color: "#c8a040" }}>Disclaimer:</strong> This prompt and the generated recommendations are for informational purposes only. Sports betting involves financial risk. Past statistical patterns do not guarantee future results. Bet responsibly.
        </div>
      </div>
    </div>
  );
}
