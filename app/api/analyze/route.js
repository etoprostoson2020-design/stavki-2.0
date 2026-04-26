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
  const oddsText = formatAllOdds(matchBookmakers, homeTeam, awayTeam);

  const userMessage = buildUserMessage({ league, matchDate, homeTeam, awayTeam, oddsText, homeText, awayText });

  const encoder = new TextEncoder();
  let fullText = "";

  const stream = new ReadableStream({
    async start(controller) {
      try {
        // Используем stream:true — наиболее стабильный метод
        const response = await client.messages.create({
          model: "claude-sonnet-4-6",
          max_tokens: 4096,
          system: SYSTEM_PROMPT,
          messages: [{ role: "user", content: userMessage }],
          stream: true,
        });

        for await (const chunk of response) {
          if (chunk.type === "content_block_delta" && chunk.delta.type === "text_delta") {
            const text = chunk.delta.text;
            fullText += text;
            controller.enqueue(
              encoder.encode(`data: ${JSON.stringify({ type: "text", content: text })}\n\n`)
            );
          }
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

// Форматируем ВСЕ рынки от ВСЕХ букмекеров
function formatAllOdds(bookmakers, homeTeam, awayTeam) {
  if (!bookmakers?.length) return null;

  const lines = [`Всего букмекеров: ${bookmakers.length}\n`];

  for (const bm of bookmakers) {
    lines.push(`\n### ${bm.title}`);
    for (const market of bm.markets) {
      const marketName = {
        h2h: "Исход матча (1X2)",
        totals: "Тотал голов",
        btts: "Обе команды забьют",
        spreads: "Азиатский гандикап",
      }[market.key] || market.key;

      lines.push(`**${marketName}:**`);

      for (const o of market.outcomes) {
        let name = o.name;
        if (market.key === "h2h") {
          name = o.name === homeTeam ? `П1 — ${homeTeam}` :
                 o.name === awayTeam ? `П2 — ${awayTeam}` :
                 o.name === "Draw" ? "Ничья" : o.name;
        } else if (market.key === "totals") {
          name = o.name === "Over" ? `ТБ ${o.point}` :
                 o.name === "Under" ? `ТМ ${o.point}` : o.name;
        } else if (market.key === "btts") {
          name = o.name === "Yes" ? "Да (обе забьют)" :
                 o.name === "No" ? "Нет" : o.name;
        } else if (market.key === "spreads" && o.point !== undefined) {
          name = `${o.name} (${o.point > 0 ? "+" : ""}${o.point})`;
        }
        // Неявная вероятность = 1 / коэф
        const impliedProb = ((1 / o.price) * 100).toFixed(1);
        lines.push(`  ${name}: **${o.price}** (вероятность по рынку: ${impliedProb}%)`);
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
    parts.push(`\n## 📊 ВСЕ КОЭФФИЦИЕНТЫ БУКМЕКЕРОВ\n${oddsText}`);
  } else {
    parts.push("\n## 📊 Коэффициенты\nДанные букмекеров недоступны — используй исторические средние.");
  }

  if (homeText) {
    parts.push(`\n## 🔍 Форма и новости: ${homeTeam}\n${homeText}`);
  }
  if (awayText) {
    parts.push(`\n## 🔍 Форма и новости: ${awayTeam}\n${awayText}`);
  }
  if (!homeText && !awayText) {
    parts.push("\n## 🔍 Веб-поиск\nTavily API не настроен — анализируй на основе коэффициентов и своих знаний.");
  }

  return parts.join("\n");
}
