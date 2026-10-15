"use client";
import { useEffect, useRef, useState } from "react";
import { apiRequest } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";
import { quoteObject } from "@/lib/quote-draft";
import { Button } from "@/components/ui";
type Package = {name:string;quantity:number;deliverables:string[];scope:string;exclusions:string;revisions:number;estimated_hours:number;delivery_days:number};
type Draft = {plans:(Package & {price:number;profit_before_tax:number|null})[];[key:string]:unknown};
export function QuoteComposer({id,service,scope,onDraft,onPending,initial}:{id:string;service:string;scope:string;initial?:unknown;onDraft:(draft:Draft)=>void;onPending:(pending:boolean)=>void}) {
  const old=quoteObject(initial);const oldPlans=Array.isArray(old?.plans)&&old.plans.every(p=>{const v=quoteObject(p);return v&&Array.isArray(v.deliverables)&&typeof v.estimated_hours==="number";})?old.plans as Package[]:null;
  const [rate,setRate]=useState(String(old?.selling_hourly_rate??"")); const [cost,setCost]=useState(String(old?.internal_hourly_cost??""));const [direct,setDirect]=useState(String(quoteObject(oldPlans?.[0])?.direct_cost??0));const [hours,setHours]=useState(String(oldPlans?.[0]?.estimated_hours??""));
  const [days,setDays]=useState(String(oldPlans?.[0]?.delivery_days??7));const [valid,setValid]=useState(String(old?.created_at&&old?.valid_until?Math.max(1,Math.round((Date.parse(String(old.valid_until))-Date.parse(String(old.created_at)))/86400000)):14));
  const [milestones,setMilestones]=useState<{label:string;percent:number}[]>(Array.isArray(old?.payment_milestones)?old.payment_milestones.map(x=>{const m=quoteObject(x);return {label:String(m?.label??""),percent:Number(m?.percent??0)};}):[{label:"确认范围后预付款",percent:50},{label:"验收交付后尾款",percent:50}]);
  const [plans,setPlans]=useState<Package[]|null>(oldPlans);const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [previewDraft,setPreviewDraft]=useState<Draft|null>(null);
  const previousScope=useRef({service,scope});
  useEffect(()=>{if(previousScope.current.service!==service||previousScope.current.scope!==scope){onPending(true);setPreviewDraft(null);previousScope.current={service,scope};}},[service,scope,onPending]);
  const input="mt-1 w-full rounded border border-line bg-ink px-3 py-2";
  async function preview() {
    setBusy(true);setError("");
    try {const token=await getAccessToken();if(!token)throw new Error("请先登录");
      const draft=await apiRequest<Draft>(`/api/pipeline/${id}/quote/preview`,{method:"POST",body:JSON.stringify({hourly_rate:Number(rate),internal_hourly_cost:cost === "" ? null : Number(cost),direct_cost:Number(direct),estimated_hours:Number(hours),delivery_days:Number(days),valid_days:Number(valid),service_type:service,scope,...(plans?{packages:plans}:{}),payment_milestones:milestones})},token);
      setPlans(draft.plans.map(({name,quantity,deliverables,scope,exclusions,revisions,estimated_hours,delivery_days})=>({name,quantity,deliverables,scope,exclusions,revisions,estimated_hours,delivery_days})));setPreviewDraft(draft);onDraft(draft);onPending(false);
    } catch(e) {setError(e instanceof Error?e.message:"预览失败");}finally{setBusy(false);}
  }
  function edit(index:number,key:keyof Package,value:string|number|string[]) {setPlans(previous=>previous?.map((p,i)=>i===index?{...p,[key]:value}:p) ?? null);}
  return <div className="mt-3" onChange={()=>{if(plans){onPending(true);setPreviewDraft(null);}}}><div className="grid gap-3 sm:grid-cols-2">
    <label>销售时薪（本人设定，元）<input aria-label="销售时薪" type="number" min="0" className={input} value={rate} onChange={e=>setRate(e.target.value)}/></label>
    <label>内部工时成本（元/小时，可未知）<input aria-label="内部工时成本" type="number" min="0" className={input} value={cost} onChange={e=>setCost(e.target.value)}/></label>
    <label>每包直接成本（元）<input aria-label="报价直接成本" type="number" min="0" className={input} value={direct} onChange={e=>setDirect(e.target.value)}/></label>
    <label>基础包预计总工时<input aria-label="报价基础工时" type="number" min="0" className={input} value={hours} onChange={e=>setHours(e.target.value)}/></label>
    <label>基础交付天数<input aria-label="报价交付天数" type="number" min="1" className={input} value={days} onChange={e=>setDays(e.target.value)}/></label>
    <label>报价有效天数<input aria-label="报价有效天数" type="number" min="1" className={input} value={valid} onChange={e=>setValid(e.target.value)}/></label>
    {milestones.map((m,i)=><div key={i} className="grid grid-cols-[minmax(0,1fr)_100px] gap-2 sm:col-span-2"><label>付款节点 {i+1}<input aria-label={`付款节点${i+1}`} className={input} value={m.label} onChange={e=>setMilestones(items=>items.map((x,j)=>j===i?{...x,label:e.target.value}:x))}/></label><label>百分比<input aria-label={`付款比例${i+1}`} className={input} type="number" min="0" max="100" value={m.percent} onChange={e=>setMilestones(items=>items.map((x,j)=>j===i?{...x,percent:Number(e.target.value)}:x))}/></label></div>)}
    <p className="text-xs text-muted sm:col-span-2">付款比例合计 {milestones.reduce((sum,m)=>sum+m.percent,0)}%，需要等于 100%。</p>
  </div><p className="mt-2 text-xs text-muted">工时按整包估计，应包含全部数量。利润为税前估算；内部成本未知时利润未知。预览不保存，保存线索时生成报价版本。</p>
  {plans&&<div className="mt-3 grid gap-3 xl:grid-cols-3">{plans.map((p,i)=><fieldset key={i} className="rounded border border-line p-3"><legend className="px-1">{p.name}</legend><label>数量<input aria-label={`${p.name}数量`} type="number" min="1" className={input} value={p.quantity} onChange={e=>edit(i,"quantity",Number(e.target.value))}/></label><label>交付物（每行一项）<textarea aria-label={`${p.name}交付物`} className={input} value={p.deliverables.join("\n")} onChange={e=>edit(i,"deliverables",e.target.value.split("\n"))}/></label><label>交付范围<textarea aria-label={`${p.name}范围`} className={input} value={p.scope} onChange={e=>edit(i,"scope",e.target.value)}/></label><label>排除项<textarea aria-label={`${p.name}排除项`} className={input} value={p.exclusions} onChange={e=>edit(i,"exclusions",e.target.value)}/></label>{([['revisions','修改次数'],['estimated_hours','总工时'],['delivery_days','交付天数']] as const).map(([key,label])=><label key={key}>{label}<input aria-label={`${p.name}${label}`} type="number" min="0" className={input} value={p[key]} onChange={e=>edit(i,key,Number(e.target.value))}/></label>)}</fieldset>)}</div>}
  <div className="mt-3 flex flex-wrap gap-2"><Button aria-label="预览报价" disabled={busy||Number(rate)<=0||Number(hours)<=0||milestones.reduce((sum,m)=>sum+m.percent,0)!==100} onClick={()=>void preview()}>{busy?"计算中…":plans?"重新计算报价预览":"预览三档方案"}</Button>{plans&&<Button variant="secondary" onClick={()=>{setPlans(null);setPreviewDraft(null);onPending(true);}}>重置套餐模板</Button>}</div>{previewDraft&&<div className="mt-3 grid gap-2 sm:grid-cols-3">{previewDraft.plans.map(p=><p key={p.name} className="rounded border border-line p-3 text-sm">{p.name}：¥{p.price} · 税前利润估算：{p.profit_before_tax === null ? "未知" : `¥${p.profit_before_tax}`}</p>)}</div>}{error&&<p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}</div>;
}
