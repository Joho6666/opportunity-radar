import { NextResponse } from "next/server";

// Legacy endpoint: tickets no longer grant sessions. The client uses the
// same-origin, JSON + custom-header guarded /api/local/session bootstrap.
export async function POST() {
  return NextResponse.json({ error: "本机配对已移除，请直接打开工作台。" }, { status: 410, headers: { "Cache-Control": "no-store" } });
}
