"use client";
import { useEffect, useState, useCallback } from "react";
import { apiRequest } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";
import { Button, MetricCard, Panel } from "@/components/ui";
import { BillingPanel } from "@/components/billing-panel";
type Funnel = { today_collected:number; today_unique_evidence:number; buyer_evidence:number; verified_buyer:number; contactable:number; contacted:number; replied:number; quoted:number; won:number; reply_rate:number|null; quote_rate:number|null; win_rate:number|null; actual_revenue:number|null; source_yield:Record<string,{evidence:number;buyer:number;verified_buyer:number;buyer_ratio:number|null}> };
export function AcquisitionDashboard() {
  const [data,setData]=useState<Funnel|null>(null);
  const [error,setError]=useState("");
  const load=useCallback(async()=>{try{const token=await getAccessToken();if(!token)return;setData(await apiRequest<Funnel>("/api/dashboard/acquisition",{},token));setError("");}catch(e){setError(e instanceof Error ? e.message : "漏斗指标暂不可用");}},[]);
  useEffect(()=>{void load();},[load]);
  const percent=(v:number|null|undefined)=>v==null ? "暂无数据" : `${(v*100).toFixed(1)}%`;
  return <div className="mb-6 space-y-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    <MetricCard label="今日采集数量（含重复 / UTC）" value={data?.today_collected ?? "暂无数据"}/><MetricCard label="候选买方需求" value={data?.buyer_evidence ?? "暂无数据"}/><MetricCard label="人工核实买方" value={data?.verified_buyer ?? "暂无数据"}/><MetricCard label="待联系客户" value={data?.contactable ?? "暂无数据"}/>
    <MetricCard label="回复率（回复 / 联系）" value={percent(data?.reply_rate)}/><MetricCard label="报价率（报价 / 回复）" value={percent(data?.quote_rate)}/><MetricCard label="成交率（成交 / 报价）" value={percent(data?.win_rate)}/><MetricCard label="已记录实际到账" value={data?.actual_revenue == null ? "暂无数据" : `¥${data.actual_revenue}`}/>
  </div><BillingPanel />{error&&<div role="alert" className="text-sm text-red-300">{error}<Button className="ml-3" variant="secondary" onClick={()=>void load()}>重试获客指标</Button></div>}
  {data&&<Panel className="p-4"><h2 className="font-semibold">客户跟进漏斗</h2><p className="mt-2 text-sm text-muted">候选需求 {data.buyer_evidence} → 人工核实 {data.verified_buyer} → 待联系 {data.contactable} → 已联系 {data.contacted} → 已回复 {data.replied} → 已报价 {data.quoted} → 已成交 {data.won}</p><p className="mt-2 text-xs text-muted">分类结果是候选需求；无人工记录时不推断联系、回复或成交。比率仅描述已记录数据。</p><div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="py-2">来源</th><th>证据</th><th>候选买方</th><th>人工核实</th><th>买方占比</th></tr></thead><tbody>{Object.entries(data.source_yield).map(([source,row])=><tr key={source} className="border-t border-line"><td className="py-2">{source}</td><td>{row.evidence}</td><td>{row.buyer}</td><td>{row.verified_buyer}</td><td>{percent(row.buyer_ratio)}</td></tr>)}</tbody></table></div></Panel>}
  </div>;
}
