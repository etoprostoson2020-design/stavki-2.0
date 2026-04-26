// The Odds API — https://the-odds-api.com/
// Маппинг лиг на sport_key
const SPORT_KEYS = {
  "Premier League": "soccer_epl",
  "UEFA Champions League": "soccer_uefa_champs_league",
  "UEFA Europa League": "soccer_uefa_europa_league",
  "La Liga": "soccer_spain_la_liga",
  "Bundesliga": "soccer_germany_bundesliga",
  "Serie A": "soccer_italy_serie_a",
  "Ligue 1": "soccer_france_ligue_one",
  "NBA": "basketball_nba",
  "NHL": "icehockey_nhl",
};

function normalizeName(name) {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function teamMatch(a, b) {
  return normalizeName(a).includes(normalizeName(b)) ||
    normalizeName(b).includes(normalizeName(a));
}

export async function fetchOdds(leagueName, homeTeam, awayTeam) {
  const apiKey = process.env.ODDS_API_KEY;
  if (!apiKey) return null;

  const sportKey = SPORT_KEYS[leagueName] || "soccer_epl";

  try {
    const res = await fetch(
      `https://api.the-odds-api.com/v4/sports/${sportKey}/odds/?apiKey=${apiKey}&regions=uk,eu&markets=h2h,totals,btts&oddsFormat=decimal`,
      { next: { revalidate: 0 } }
    );
    if (!res.ok) return null;

    const data = await res.json();
    const game = data.find(
      (g) => teamMatch(g.home_team, homeTeam) && teamMatch(g.away_team, awayTeam)
    );

    return game || null;
  } catch {
    return null;
  }
}

export function formatOddsForPrompt(game) {
  if (!game) return null;

  const lines = [`Match: ${game.home_team} vs ${game.away_team}`];

  for (const bm of game.bookmakers.slice(0, 4)) {
    lines.push(`\n### ${bm.title}`);
    for (const market of bm.markets) {
      lines.push(`${market.key.toUpperCase()}:`);
      for (const o of market.outcomes) {
        lines.push(`  ${o.name}: ${o.price}`);
      }
    }
  }

  return lines.join("\n");
}
