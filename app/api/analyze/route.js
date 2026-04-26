import Anthropic from "@anthropic-ai/sdk";
import { fetchOdds, formatOddsForPrompt } from "@/lib/odds";
import { webSearch } from "@/lib/search";
import { prisma } from "@/lib/prisma";
import { SYSTEM_PROMPT } from "@/lib/prompt";

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export async function POST(request) {
  const { league, matchDate, homeTeam, awayTeam } = await request.json();

  if (!process.env.ANTHROPIC_API_KEY) {
    return new Response(
      JSON.stringify({ error: "ANTHROPIC_API_KEY не задан в .env.local" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }

  // Параллельно запрашиваем коэффициенты и поиск
  const [oddsGame, homeNews, awayNews] = await Promise.allSettled([
    fetchOdds(league, homeTeam, awayTeam),
    webSearch(`${homeTeam} form injuries squad news ${matchDate}`),
    webSearch(`${awayTeam} form injuries squad news ${matchDate}`),
  ]);

  const oddsData = oddsGame.status === "fulfilled" ? oddsGame.value : null;
  const oddsText = formatOddsForPrompt(oddsData);
  const homeText = homeNews.status === "fulfilled" ? homeNews.value : null;
  const awayText = awayNews.status === "fulfilled" ? awayNews.value : null;

  const userMessage = buildUserMessage({ league, matchDate, homeTeam, awayTeam, oddsText, homeText, awayText });

  const encoder = new TextEncoder();
  let fullText = "";
  let savedId = null;

  const stream = new ReadableStream({
    async start(controller) {
      try {
        const anthropicStream = client.messages.stream({
          model: "claude-sonnet-4-6",
          max_tokens: 4096,
          system: SYSTEM_PROMPT,
          messages: [{ role: "user", content: userMessage }],
        });

        for await (const text of anthropicStream.textStream) {
          fullText += text;
          controller.enqueue(
            encoder.encode(`data: ${JSON.stringify({ type: "text", content: text })}\n\n`)
          );
        }

        // Сохраняем в БД после завершения стрима
        const saved = await prisma.analysis.create({
          data: {
            league,
            matchDate,
            homeTeam,
            awayTeam,
            result: fullText,
            odds: oddsData ? JSON.stringify(oddsData) : null,
          },
        });
        savedId = saved.id;

        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "done", id: savedId })}\n\n`)
        );
        controller.close();
      } catch (err) {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "error", message: err.message })}\n\n`)
        );
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  });
}

function buildUserMessage({ league, matchDate, homeTeam, awayTeam, oddsText, homeText, awayText }) {
  const parts = [`${league}, ${matchDate} — ${homeTeam} vs ${awayTeam}`];

  if (oddsText) {
    parts.push(`\n## 📊 Bookmaker Odds (live)\n${oddsText}`);
  } else {
    parts.push("\n## 📊 Bookmaker Odds\nOdds API key not configured — use historical averages.");
  }

  if (homeText) {
    parts.push(`\n## 🔍 ${homeTeam} — Recent news & form\n${homeText}`);
  }
  if (awayText) {
    parts.push(`\n## 🔍 ${awayTeam} — Recent news & form\n${awayText}`);
  }
  if (!homeText && !awayText) {
    parts.push("\n## 🔍 Web Search\nTavily API key not configured — base analysis on odds and knowledge.");
  }

  return parts.join("\n");
}
