"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { Button, PageHeader, Panel } from "@/components/ui";
import { useMockMode } from "@/lib/api-client";
import { signOut } from "@/lib/auth";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
export default function Settings(){ const router=useRouter(); const reset=useOpportunityStore(s=>s.reset); const [notice, setNotice]=useState(""); const mode=useMockMode?"演示模式（本地 Mock 数据）":"联机模式（Supabase + Opportunity Engine）"; return <AppShell><PageHeader title="设置" description={`当前运行模式：${mode}`}/>{notice&&<p className="mb-3 rounded border border-line bg-panel px-4 py-2 text-sm text-signal">{notice}</p>}<div className="max-w-3xl space-y-3"><Panel className="flex items-center justify-between p-5"><div><p className="font-medium">数据</p><p className="mt-1 text-sm text-muted">重置为演示数据。联机模式下重新登录后可从后端拉取最新数据。</p></div><Button variant="secondary" onClick={()=>{reset(); setNotice("已重置为演示数据。");}}>重置数据</Button></Panel><Panel className="flex items-center justify-between p-5"><div><p className="font-medium">账户</p><p className="mt-1 text-sm text-muted">退出当前登录会话并返回登录页。</p></div><Button variant="secondary" onClick={async()=>{await signOut(); router.push("/login");}}>退出登录</Button></Panel><Panel className="flex items-center justify-between p-5"><span className="font-medium">通知</span><span className="text-sm text-muted">即将支持</span></Panel><Panel className="flex items-center justify-between p-5"><span className="font-medium">雷达默认设置</span><span className="text-sm text-muted">即将支持</span></Panel></div></AppShell>; }
