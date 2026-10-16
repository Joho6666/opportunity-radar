"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Loader2, Radar } from "lucide-react";
import { Button, Panel } from "@/components/ui";

export default function PairPage() {
  const router = useRouter();
  const [ticket, setTicket] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function pair() {
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/local/pair", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticket: ticket.trim() }), cache: "no-store" });
      const payload = await response.json().catch(() => null) as { error?: string } | null;
      if (!response.ok) throw new Error(payload?.error ?? "配对失败，请重新检查配对码。");
      router.replace("/dashboard"); router.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "配对失败，请稍后重试。"); }
    finally { setBusy(false); }
  }
  return <main className="grid min-h-screen place-items-center bg-page px-4 py-8 text-ink"><div className="w-full max-w-md">
    <div className="mb-7 flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-lg bg-ai text-white"><Radar size={21}/></span><div><h1 className="text-xl font-semibold">Opportunity Radar</h1><p className="text-sm text-muted">Local Edition</p></div></div>
    <Panel className="p-6"><div className="flex items-center gap-2"><KeyRound size={18} className="text-ai"/><h2 className="font-semibold">配对本机工作台</h2></div><p className="mt-3 text-sm leading-6 text-muted">在本机终端运行 <code className="rounded bg-slate-100 px-1.5 py-0.5">scripts/local.sh pair</code> 获取一次性配对码。配对码短时有效，使用后立即作废。</p>
      <label className="mt-5 block text-sm"><span className="mb-1 block text-muted">一次性配对码</span><input autoComplete="one-time-code" value={ticket} onChange={event => setTicket(event.target.value)} onKeyDown={event => { if (event.key === "Enter") void pair(); }} className="h-11 w-full rounded-md border border-line bg-white px-3 font-mono text-sm"/></label>
      {error && <p role="alert" className="mt-3 text-sm text-red-800">{error}</p>}
      <Button className="mt-4 w-full" disabled={busy || ticket.trim().length < 32} onClick={() => void pair()}>{busy ? <><Loader2 size={16} className="animate-spin"/>正在配对</> : "连接本机工作台"}</Button>
      <p className="mt-4 text-xs leading-5 text-muted">只允许本机浏览器使用。Cookie 为 HttpOnly、SameSite Strict；写入请求使用 CSRF 校验。请勿把此页面或配对码转发给他人。</p>
    </Panel>
  </div></main>;
}
