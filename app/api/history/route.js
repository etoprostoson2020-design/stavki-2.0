import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const analyses = await prisma.analysis.findMany({
    orderBy: { createdAt: "desc" },
    take: 100,
    select: {
      id: true,
      league: true,
      matchDate: true,
      homeTeam: true,
      awayTeam: true,
      createdAt: true,
    },
  });
  return NextResponse.json(analyses);
}
