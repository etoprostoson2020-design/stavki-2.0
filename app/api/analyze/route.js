import Anthropic from "@anthropic-ai/sdk";
import { webSearch } from "@/lib/search";
import { prisma } from "@/lib/prisma";
import { SYSTEM_PROMPT } from "@/lib/prompt";

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export async function POST(request) {
  const { league, matchDate, homeTeam, awayTeam, matchBookmakers } = await request.json();

  if (!process.env.ANTHROPIC_API_KEY) {
    return new Response(
      JSON.stringify({ error: "ANTHROPIC_API_KEY не задан в .env.local" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }

  // Веб-поиск формы и новостей (параллельно)
  const [homeNews, awayNews] = await Promise.allSettled([
    webSearch(`${homeTeam} последние матчи форма травмы состав`),
    webSearch(`${awayTeam} последние матчи форма травмы состав`),
  ]);

  const homeText = homeNews.status === "fulfilled" ? homeNews.value : null;
  const awayText = awayNews.status === "fulfilled" ? awayNews.value : null;
  const oddsText = formatBookmakers(matchBookmakers, homeTeam, awayTeam);

  const userMessage = buildUserMessage({ league, matchDate, homeTeam, awayTeam, oddsText, homeText, awayText });

  const encoder = new TextEncoder();
  let fullText = "";

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

        const saved = await prisma.analysis.create({
          data: {
            league,
            matchDate,
            homeTeam,
            awayTeam,
            result: fullText,
            odds: matchBookmakers ? JSON.stringify(matchBookmakers) : null,
          },
        });

        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "done", id: saved.id })}\n\n`)
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

function formatBookmakers(bookmakers, homeTeam, awayTeam) {
  if (!bookmakers || !bookmakers.length) return null;

  const lines = [];
  for (const bm of bookmakers.slice(0, 5)) {
    lines.push(`\n### ${bm.title}`);
    for (const market of bm.markets) {
      const label = { h2h: "Исход (1X2)", totals: "Тотал", btts: "Обе забьют" }[market.key] || market.key;
      lines.push(`**${label}:**`);
      for (const o of market.outcomes) {
        const name = o.name === homeTeam ? `П1 (${homeTeam})` :
                     o.name === awayTeam ? `П2 (${awayTeam})` :
                     o.name === "Draw" ? "Ничья" :
                     o.name === "Over" ? `ТБ ${o.point}` :
                     o.name === "Under" ? `ТМ ${o.point}` : o.name;
        lines.push(`  ${name}: **${o.price}**`);
      }
    }
  }
  return lines.join("\n");
}

function buildUserMessage({ league, matchDate, homeTeam, awayTeam, oddsText, homeText, awayText }) {
  const parts = [
    `## Матч: ${homeTeam} — ${awayTeam}`,
    `**Лига:** ${league}`,
    `**Дата:** ${matchDate}`,
  ];

  if (oddsText) {
    parts.push(`\n## 📊 Коэффициенты букмекеров (актуальные)\n${oddsText}`);
  } else {
    parts.push("\n## 📊 Коэффициенты\nДанные букмекеров недоступны — используй исторические средние.");
  }

  if (homeText) {
    parts.push(`\n## 🔍 Новости и форма: ${homeTeam}\n${homeText}`);
  }
  if (awayText) {
    parts.push(`\n## 🔍 Новости и форма: ${awayTeam}\n${awayText}`);
  }
  if (!homeText && !awayText) {
    parts.push("\n## 🔍 Веб-поиск\nTavily API не настроен — анализируй на основе коэффициентов и своих знаний.");
  }

  return parts.join("\n");
}
