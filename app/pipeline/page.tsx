"use client";
import { budgetLabel } from "@/lib/utils";
import { useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { Button, MetricCard, PageHeader, Panel } from "@/components/ui";
import { LeadEditor, PIPELINE_STAGES } from "@/components/lead-editor";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
import { matchesFollowUp } from "@/lib/pipeline-view";
export default function Pipeline() {
  const { opportunities, loading, error, retry } = useOpportunityStore();
  const [selected,setSelected] = useState<string | null>(null);
  const [filter,setFilter] = useState("all");
  const [search,setSearch] = useState("");
  const [dueFilter,setDueFilter] = useState("all");
  const items = opportunities.filter(x => x.type !== "job" && matchesFollowUp(x,dueFilter) && (filter === "all" || x.status === filter) && `${x.title} ${x.summary}`.toLowerCase().includes(search.toLowerCase()));
  const income = opportunities.filter(x => x.type !== "job").reduce((sum,x) => sum + (x.actualRevenue ?? 0),0);
  const lead = opportunities.find(x => x.id === selected);
  return <AppShell><PageHeader title="客户获客工作台" description="核实需求、记录真实跟进、编辑报价与沟通草案。" />
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="待核实" value={opportunities.filter(x => x.verificationStatus !== "verified").length}/><MetricCard label="待联系" value={opportunities.filter(x => x.status === "ready_to_contact").length}/><MetricCard label="洽谈中" value={opportunities.filter(x => x.status === "negotiating").length}/><MetricCard label="已记录实收" value={opportunities.some(x => x.actualRevenue !== undefined && x.actualRevenue !== null) ? `¥${income}` : "暂无数据"}/></div>
    <div className="mt-5 flex flex-wrap gap-3"><input aria-label="搜索客户线索" className="rounded border border-line bg-ink p-2 text-sm" placeholder="搜索客户需求" value={search} onChange={e=>setSearch(e.target.value)}/><select aria-label="筛选跟进状态" className="rounded border border-line bg-ink p-2 text-sm" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部状态</option>{PIPELINE_STAGES.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select><Button variant="secondary" onClick={()=>void retry()}>刷新</Button></div>
    {loading&&<p className="mt-3 text-sm text-muted">加载中…</p>}{error&&<p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
    <label className="mt-3 block text-sm">跟进到期（本机日期）<select aria-label="筛选到期跟进" className="ml-2 rounded border border-line bg-ink p-2" value={dueFilter} onChange={e=>setDueFilter(e.target.value)}><option value="all">全部</option><option value="today">今日</option><option value="overdue">逾期</option></select></label>
    {lead&&<LeadEditor key={lead.id} item={lead} onSaved={async()=>{await retry();}} onClose={()=>setSelected(null)}/>}
    {!items.length&&!loading?<Panel className="mt-5 p-6"><p>暂无客户线索。</p><Link href="/evidence" className="mt-2 inline-block text-indigo-300 underline">到证据收件箱核实需求</Link></Panel>:<div className="mt-5 flex flex-col gap-4 pb-4 sm:flex-row sm:overflow-x-auto">{PIPELINE_STAGES.filter(([key])=>filter === "all" ? items.some(item => item.status === key) : key === filter).map(([status,label])=><section className="w-full shrink-0 sm:w-72" key={status}><h2 className="mb-3 flex justify-between text-sm font-semibold">{label}<span>{items.filter(x=>x.status === status).length}</span></h2><div className="space-y-3">{items.filter(x=>x.status === status).map(item=><Panel className="p-4" key={item.id}><p className="text-sm font-medium">{item.title}</p><p className="mt-2 text-xs text-muted">{item.source} · {budgetLabel(item)}</p><p className="mt-2 text-xs text-muted">{item.verificationStatus === "verified" ? "人工已核实" : "待核实"} · {item.pipeline?.next_follow_up_at ? `跟进 ${String(item.pipeline.next_follow_up_at)}` : "未设跟进时间"}</p><Button variant="secondary" className="mt-3 w-full" onClick={()=>setSelected(item.id)}>查看与跟进</Button></Panel>)}</div></section>)}</div>}
  </AppShell>;
}
