"use client";
import { budgetLabel } from "@/lib/utils";
import { useState } from "react";
import { getAccessToken } from "@/lib/auth";
import { apiRequest } from "@/lib/api-client";
import { Button, Panel } from "@/components/ui";
import type { Opportunity } from "@/types/domain";

export const PIPELINE_STAGES = [["new","新发现"],["pending_verification","待核实"],["verified","已核实"],["ready_to_contact","待联系"],["contacted","已联系"],["replied","已回复"],["quoted","已报价"],["negotiating","洽谈中"],["won","已成交"],["lost","已流失"],["saved","已收藏"],["ignored","已忽略"]] as const;

export function LeadEditor({ item, onSaved, onClose }: { item: Opportunity; onSaved: () => Promise<void>; onClose: () => void }) {
  const p = item.pipeline ?? {};
  const [status,setStatus] = useState<string>(item.status);
  const [notes,setNotes] = useState(String(p.notes ?? ""));
  const [service,setService] = useState(String(p.service_type ?? "文档服务"));
  const [clearFollowUp,setClearFollowUp] = useState(false);
  const [followUp,setFollowUp] = useState("");
  const [channel,setChannel] = useState(String(p.public_contact_channel ?? ""));
  const [revenue,setRevenue] = useState(item.actualRevenue === undefined ? "" : String(item.actualRevenue));
  const [cost,setCost] = useState(p.actual_cost === undefined ? "" : String(p.actual_cost));
  const [hours,setHours] = useState(item.actualHours === undefined || item.actualHours === null ? "" : String(item.actualHours));
  const [loss,setLoss] = useState(String(p.loss_reason ?? ""));
  const [rate,setRate] = useState("100");
  const [quoteHours,setQuoteHours] = useState("");
  const [scope,setScope] = useState(item.summary);
  const [draft,setDraft] = useState(p.quote_draft ? JSON.stringify(p.quote_draft,null,2) : "");
  const [message,setMessage] = useState(String(p.communication_draft ?? ""));
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const [verify,setVerify] = useState(false);
  async function call(path: string, body?: unknown) {
    const token = await getAccessToken(); if (!token) throw new Error("请先登录");
    return apiRequest(path, {method:body === undefined ? "POST" : "PATCH", ...(body === undefined ? {} : {body:JSON.stringify(body)})}, token);
  }
  async function save() {
    setBusy(true); setError("");
    try { await call(`/api/pipeline/${item.id}`, {status,notes,clear_follow_up:clearFollowUp,service_type:service,public_contact_channel:channel,loss_reason:loss,
      ...(verify ? {verification_status:"verified"} : {}), ...(followUp ? {next_follow_up_at:new Date(followUp).toISOString()} : {}),
      ...(revenue !== "" ? {actual_revenue:Number(revenue)} : {}), ...(cost !== "" ? {actual_cost:Number(cost)} : {}), ...(hours !== "" ? {actual_hours:Number(hours)} : {}),
      ...(draft ? {quote_draft:JSON.parse(draft)} : {}), communication_draft:message}); await onSaved(); }
    catch(e) { setError(e instanceof Error ? e.message : "保存失败"); } finally { setBusy(false); }
  }
  async function generate(kind: "quote" | "communication") {
    setBusy(true);setError("");
    try { const token=await getAccessToken();if(!token)throw new Error("请先登录");
      const response=await apiRequest<{text?:string}>(`/api/pipeline/${item.id}/${kind}`,{method:"POST",...(kind === "quote" ? {body:JSON.stringify({hourly_rate:Number(rate),estimated_hours:Number(quoteHours),scope,service_type:service})} : {})},token);
      if(kind === "quote")setDraft(JSON.stringify(response,null,2));else setMessage(response.text ?? "");await onSaved();
    } catch(e) { setError(e instanceof Error ? e.message : "草案生成失败"); } finally { setBusy(false); }
  }
  const input="mt-1 w-full rounded border border-line bg-ink px-3 py-2";
  return <Panel className="mt-5 p-5"><div className="flex justify-between gap-3"><h2 className="font-semibold">{item.title}</h2><Button variant="secondary" onClick={onClose}>关闭</Button></div>
    <a className="mt-2 block break-all text-sm text-indigo-300 underline" href={item.sourceUrl} target="_blank" rel="noreferrer">{item.source} · 查看原文</a><p className="mt-2 text-sm text-muted">{item.summary}</p>
    <p className="mt-2 text-xs text-muted">预算：{budgetLabel(item)} · 真实性：{item.verificationStatus === "verified" ? "人工已核实" : "待人工核实"} · 优先级预测 {item.opportunityScore}（非成交概率）</p>
    <ul className="mt-2 text-xs text-amber-200">{[...item.reasons,...item.warnings].map((x,i)=><li key={i}>{x}</li>)}</ul>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <label>状态<select aria-label="线索状态" className={input} value={status} onChange={e=>setStatus(e.target.value)}>{PIPELINE_STAGES.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      <label>服务类型<input className={input} value={service} onChange={e=>setService(e.target.value)}/></label>
      <label>公开允许的联系渠道<input className={input} value={channel} onChange={e=>setChannel(e.target.value)}/></label>
      <label>下次跟进（本机时间）<input type="datetime-local" className={input} value={followUp} onChange={e=>setFollowUp(e.target.value)}/>{Boolean(p.next_follow_up_at)&&<><span className="text-xs text-muted">已保存：{String(p.next_follow_up_at)}</span><span className="mt-1 block text-xs"><input type="checkbox" checked={clearFollowUp} onChange={e=>setClearFollowUp(e.target.checked)}/> 清除已保存的跟进时间</span></>}</label>
      <label>实际到账（元）<input className={input} type="number" min="0" value={revenue} onChange={e=>setRevenue(e.target.value)}/></label>
      <label>实际成本（元）<input className={input} type="number" min="0" value={cost} onChange={e=>setCost(e.target.value)}/></label>
      <label>实际工时<input className={input} type="number" min="0" value={hours} onChange={e=>setHours(e.target.value)}/></label>
      <label>流失原因<input className={input} value={loss} onChange={e=>setLoss(e.target.value)}/></label>
      <label className="sm:col-span-2">核实依据与跟进备注<textarea className={input} rows={3} value={notes} onChange={e=>setNotes(e.target.value)}/></label>
    </div>
    {!item.fromEvidence && <label className="mt-3 block text-sm"><input type="checkbox" checked={verify} onChange={e=>setVerify(e.target.checked)}/> 我已人工核实原文是有效买方需求（填写依据）</label>}
    {item.fromEvidence && item.verificationStatus !== "verified" && <a href="/evidence" className="mt-3 block text-sm text-indigo-300 underline">先到证据收件箱核实</a>}
    <div className="mt-5 border-t border-line pt-4"><h3 className="font-semibold">报价草案（人工设定）</h3><div className="mt-2 grid gap-3 sm:grid-cols-2"><label>内部报价时薪<input type="number" className={input} value={rate} onChange={e=>setRate(e.target.value)}/></label><label>标准交付预计工时<input type="number" className={input} value={quoteHours} onChange={e=>setQuoteHours(e.target.value)}/></label></div><label className="mt-3 block">交付范围<textarea className={input} value={scope} onChange={e=>setScope(e.target.value)}/></label><Button className="mt-3" disabled={busy || Number(quoteHours)<=0} onClick={()=>void generate("quote")}>生成三档方案</Button>{draft&&<textarea aria-label="可编辑报价草案" className={`${input} mono text-xs`} rows={10} value={draft} onChange={e=>setDraft(e.target.value)}/>}</div>
    <div className="mt-5 border-t border-line pt-4"><h3 className="font-semibold">客户沟通草案</h3><Button className="mt-3" disabled={busy} onClick={()=>void generate("communication")}>生成个性化草案</Button><textarea aria-label="可编辑沟通草案" className={input} rows={5} value={message} onChange={e=>setMessage(e.target.value)}/><p className="mt-2 text-xs text-amber-200">草案需要人工审核。本系统不发送消息，也不会自动标记已联系或已报价。</p></div>
    {error&&<p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}<Button className="mt-4" disabled={busy} onClick={()=>void save()}>{busy ? "处理中…" : "保存真实跟进记录"}</Button>
  </Panel>;
}
