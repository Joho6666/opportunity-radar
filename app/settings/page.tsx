"use client";

import { useState } from "react";
import { BillingPanel } from "@/components/billing-panel";
import { Database, RotateCcw, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, PageHeader, Panel } from "@/components/ui";
import { useMockMode } from "@/lib/api-client";
import { useOpportunityStore } from "@/stores/use-opportunity-store";

export default function Settings() {
  const reset = useOpportunityStore((state) => state.reset);
  const [notice, setNotice] = useState("");
  const localAuthDisabled = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";
  const mode = useMockMode ? "演示模式：不会产生真实采集" : "真实数据模式：连接本地 API";
  return <AppShell>
    <PageHeader title="设置" description="只展示当前真正生效的配置，不用虚假数据填充页面。" />
    {notice && <p className="mb-4 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-300">{notice}</p>}
    <div className="max-w-3xl space-y-4"><BillingPanel editable />
      <Panel className="p-5"><div className="flex items-start gap-3"><Database className="mt-0.5 text-indigo-300" size={19}/><div><p className="font-medium text-mist">运行模式</p><p className="mt-1 text-sm text-muted">{mode}</p><p className="mt-3 text-xs text-muted">真实模式下，页面只显示 API 返回的数据；没有数据时显示空状态，不会自动补 Demo。</p></div></div></Panel>
      <Panel className="p-5"><div className="flex items-start justify-between gap-4"><div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 text-emerald-300" size={19}/><div><p className="font-medium text-mist">访问方式</p><p className="mt-1 text-sm text-muted">{localAuthDisabled ? "本机单用户模式，未启用登录。不要把服务暴露到公网。" : "使用 Supabase 登录和会话校验。"}</p></div></div><span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-xs text-emerald-300">{localAuthDisabled ? "本地免登录" : "需要登录"}</span></div></Panel>
      <Panel className="flex items-center justify-between gap-4 p-5"><div><p className="font-medium text-mist">清空界面缓存</p><p className="mt-1 text-sm text-muted">只清除浏览器里的列表和配置缓存，不会删除后端数据库记录。</p></div><Button variant="secondary" onClick={() => { reset(); setNotice("界面缓存已清空，请重新加载数据。"); }}><RotateCcw size={15}/> 清空缓存</Button></Panel>
    </div>
  </AppShell>;
}