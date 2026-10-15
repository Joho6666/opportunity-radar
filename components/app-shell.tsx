"use client";
import { Bookmark, BriefcaseBusiness, ChevronRight, CircleUserRound, House, Inbox, ListTodo, Menu, Radar, Settings, Sparkles, UserRound } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
import { Button, DetailDrawer } from "@/components/ui";
const groups: {title:string;items:[string,string,LucideIcon][]}[] = [
  {title:"发现与筛选",items:[["首页","/dashboard",House],["证据收件箱","/evidence",Inbox],["我的雷达","/radars",Radar],["每日简报","/daily-brief",ListTodo]]},
  {title:"机会与客户",items:[["机会列表","/opportunities",BriefcaseBusiness],["客户跟进","/pipeline",CircleUserRound],["已收藏","/saved",Bookmark]]},
  {title:"辅助与设置",items:[["机会技能","/skills",Sparkles],["我的画像","/profile",UserRound],["设置","/settings",Settings]]},
];
function Navigation({ onSelect }: { onSelect?: () => void }) {
  const path = usePathname();
  return <nav aria-label="主导航" className="space-y-6">{groups.map(group=><div key={group.title}><p className="mb-2 px-3 text-xs font-medium text-muted">{group.title}</p><div className="space-y-1">{group.items.map(([label,href,Icon])=><Link key={href} onClick={onSelect} href={href} className={cn("flex min-h-10 items-center gap-3 rounded-md px-3 text-sm transition-colors",path===href||path.startsWith(href+"/")?"bg-indigo-50 font-medium text-ai":"text-muted hover:bg-slate-100 hover:text-mist")}><Icon size={17}/>{label}</Link>)}</div></div>)}</nav>;
}
function Brand(){return <Link href="/dashboard" className="mb-8 flex items-center gap-2.5 px-2 font-semibold"><span className="grid h-8 w-8 place-items-center rounded-lg bg-ai text-white"><Radar size={18}/></span><span>机会雷达<small className="block text-xs font-normal text-muted">Opportunity Radar</small></span></Link>;}
export function AppShell({children}:{children:React.ReactNode}) {
  const [open,setOpen]=useState(false);const path=usePathname();
  const {error,loading,profile,hydrated}=useOpportunityStore();
  useEffect(()=>{void useOpportunityStore.getState().hydrate().catch(()=>undefined);},[]);
  const label=groups.flatMap(g=>g.items).find(([,href])=>path===href||path.startsWith(href+"/"))?.[0]??"工作台";
  const local=process.env.NODE_ENV==="development"&&process.env.NEXT_PUBLIC_AUTH_DISABLED==="true";
  return <div className="min-h-screen bg-ink"><a href="#main-content" className="sr-only z-[60] bg-white p-3 focus:not-sr-only focus:fixed">跳到主要内容</a>
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 border-r border-line bg-white px-3 py-5 lg:block"><Brand/><Navigation/><div className="absolute bottom-5 left-5 right-5 border-t border-line pt-4 text-xs leading-5 text-muted">公开需求 · 人工核实<br/>让每次跟进都有依据</div></aside>
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-2 border-b border-line bg-white px-4 lg:ml-56 lg:px-6"><div className="flex min-w-0 items-center gap-2"><Button variant="ghost" aria-label="打开导航" className="-ml-2 lg:hidden" onClick={()=>setOpen(true)}><Menu size={20}/></Button><span className="hidden text-sm text-muted sm:inline">工作台</span><ChevronRight size={14} className="hidden text-muted sm:block"/><span className="truncate text-sm font-medium">{label}</span></div><div className="flex items-center gap-3 text-xs text-muted"><span className="hidden sm:inline">{local?"本机开发身份":"账户会话"}</span><Link href="/profile" className="flex min-h-10 items-center gap-2 rounded-md px-1"><UserRound size={17}/><span className="max-w-24 truncate">{hydrated?profile.name||"未填写姓名":"加载中…"}</span></Link></div></header>
    <DetailDrawer open={open} onClose={()=>setOpen(false)} title="工作台导航" className="right-auto left-0 max-w-[280px]"><div className="p-4"><Navigation onSelect={()=>setOpen(false)}/></div></DetailDrawer>
    <main id="main-content" className="min-w-0 p-4 sm:p-5 lg:ml-56 lg:p-6">{error&&<div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><span>数据加载或保存失败：{error}</span><Button variant="secondary" disabled={loading} onClick={()=>{void useOpportunityStore.getState().retry().catch(()=>undefined);}}>{loading?"重试中…":"重新加载数据"}</Button></div>}{children}</main>
  </div>;
}
