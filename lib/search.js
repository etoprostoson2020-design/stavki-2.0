// Tavily API — https://tavily.com/
export async function webSearch(query) {
  const apiKey = process.env.TAVILY_API_KEY;
  if (!apiKey) return null;

  try {
    const res = await fetch("https://api.tavily.com/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: apiKey,
        query,
        search_depth: "basic",
        max_results: 5,
        include_answer: true,
      }),
    });
    if (!res.ok) return null;

    const data = await res.json();
    const parts = [];

    if (data.answer) parts.push(`Summary: ${data.answer}`);

    if (data.results) {
      for (const r of data.results) {
        parts.push(`\n[${r.title}]\n${r.content}`);
      }
    }

    return parts.join("\n\n") || null;
  } catch {
    return null;
  }
}
