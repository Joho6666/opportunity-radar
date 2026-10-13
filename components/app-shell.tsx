"use client";

import { Database, Menu, Radar } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
import { Button } from "@/components/ui";

const nav = [
  ["首页", "/dashboard"],
  ["证据收件箱", "/evidence"],
  ["机会列表", "/opportunities"],
  ["我的雷达", "/radars"],
  ["每日简报", "/daily-brief"],
  ["机会进度", "/pipeline"],
  ["已收藏", "/saved"],
  ["机会技能", "/skills"],
  ["我的画像", "/profile"],
  ["设置", "/settings"],
] as const;

const pageLabels = Object.fromEntries(nav.map(([label, href]) => [href, label]));

function Navigation({ onSelect }: { onSelect?: () => void }) {
  const path = usePathname();
  return <nav className="space-y-1">{nav.map(([label, href]) => <Link key={href} onClick={onSelect} href={href} className={cn("block rounded-lg px-3 py-2.5 text-sm transition", path === href || (href !== "/dashboard" && path.startsWith(href)) ? "border-l-2 border-ai bg-white/5 text-white" : "text-muted hover:bg-white/5 hover:text-mist")}>{label}</Link>)}</nav>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const path = usePathname();
  const error = useOpportunityStore((state) => state.error);
  const loading = useOpportunityStore((state) => state.loading);
  useEffect(() => { void useOpportunityStore.getState().hydrate().catch(() => undefined); }, []);
  return <div className="min-h-screen bg-ink">
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-line bg-[#061728] p-4 lg:block">
      <Link href="/dashboard" className="mb-8 flex items-center gap-2 text-sm font-semibold text-white"><span className="grid h-8 w-8 place-items-center rounded-lg bg-ai shadow-glow"><Radar size={17}/></span><span>机会雷达 <small className="block font-normal text-muted">Opportunity Radar</small></span></Link>
      <p className="mb-2 px-3 text-[11px] font-semibold tracking-widest text-muted">工作台</p>
      <Navigation/>
      <div className="absolute bottom-4 left-4 right-4 border-t border-line pt-4 text-xs text-muted">AI 每天替你发现机会</div>
    </aside>
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-line bg-ink/95 px-4 backdrop-blur lg:ml-60 lg:px-8">
      <button aria-label="打开导航" className="lg:hidden" onClick={() => setOpen(true)}><Menu/></button>
      <div className="flex items-center gap-2 text-sm text-mist"><span className="text-muted">工作台</span><span className="text-muted">/</span><span>{pageLabels[path] ?? "机会雷达"}</span></div>
      <div className="flex items-center gap-3"><span className="hidden items-center gap-1.5 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-xs text-emerald-300 sm:flex"><Database size={12}/> 本地模式</span><span className="grid h-8 w-8 place-items-center rounded-full bg-panel text-xs text-mist">小何</span></div>
    </header>
    {open && <div className="fixed inset-0 z-50 lg:hidden"><button className="absolute inset-0 bg-black/60" aria-label="关闭导航" onClick={() => setOpen(false)}/><aside className="relative h-full w-72 border-r border-line bg-[#061728] p-5"><div className="mb-8 flex items-center gap-2 font-semibold"><Radar className="text-indigo-300"/>机会雷达</div><Navigation onSelect={() => setOpen(false)}/></aside></div>}
    <main className="min-h-[calc(100vh-64px)] p-4 sm:p-6 lg:ml-60 lg:p-8">
      {error && <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100">
        <span>数据加载或保存失败：{error}</span>
        <Button variant="secondary" disabled={loading} onClick={() => { void useOpportunityStore.getState().retry().catch(() => undefined); }}>{loading ? "重试中…" : "重新加载数据"}</Button>
      </div>}
      {children}
    </main>
  </div>;
}
