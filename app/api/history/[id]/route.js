import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(request, { params }) {
  const analysis = await prisma.analysis.findUnique({
    where: { id: params.id },
  });
  if (!analysis) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json(analysis);
}

export async function DELETE(request, { params }) {
  await prisma.analysis.delete({ where: { id: params.id } });
  return NextResponse.json({ ok: true });
}
