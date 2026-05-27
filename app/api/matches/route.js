import { NextResponse } from "next/server";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const sport = searchParams.get("sport") || "soccer_epl";
  const apiKey = process.env.ODDS_API_KEY;

  if (!apiKey) {
    return NextResponse.json({ error: "ODDS_API_KEY не настроен в .env.local" }, { status: 400 });
  }

  try {
    const res = await fetch(
      `https://api.the-odds-api.com/v4/sports/${sport}/odds?apiKey=${apiKey}&regions=eu,uk&markets=h2h,spreads,btts&oddsFormat=decimal`,
      { next: { revalidate: 300 } }
    );

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json({ error: `Ошибка Odds API: ${text}` }, { status: 502 });
    }

    const data = await res.json();

    const now = new Date();
    const in7days = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);

    const matches = data
      .filter((g) => {
        const t = new Date(g.commence_time);
        return t >= now && t <= in7days;
      })
      .sort((a, b) => new Date(a.commence_time) - new Date(b.commence_time));

    return NextResponse.json(matches);
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
