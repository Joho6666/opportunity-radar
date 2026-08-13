import { NextResponse } from "next/server";
import { mockOpportunities } from "@/data/mock-opportunities";
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const item = mockOpportunities.find((opportunity) => opportunity.id === id);
  return item ? NextResponse.json(item) : NextResponse.json({ error: "Not found" }, { status: 404 });
}
