"use client";
import { useMemo, useState } from "react";
import { OpportunityCard } from "@/components/opportunity-card";
import { EmptyState, PageHeader, Panel } from "@/components/ui";
import { filterOpportunities, type OpportunitySort } from "@/lib/filters";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
import type { OpportunityType } from "@/types/domain";
export function OpportunityList({saved=false}:{saved?:boolean}){
 const {opportunities,loading,error,hydrated}=useOpportunityStore();const [query,setQuery]=useState(""),[type,setType]=useState<OpportunityType|"all">("all"),[sort,setSort]=useState<OpportunitySort>("AI 推荐");
 const items=useMemo(()=>filterOpportunities(saved?opportunities.filter(x=>x.status==="saved"):opportunities,{query,type,sort}),[opportunities,saved,query,type,sort]);
 return <><PageHeader title={saved?"已收藏":"机会列表"} description={saved?"持续跟进你关注的需求。":"比较需求、预算和预测分数，再查看原文核实。"}/><Panel className="mb-4 flex flex-wrap gap-2 p-3"><input aria-label="搜索机会" placeholder="搜索标题、需求或技能" className="min-w-40 flex-1 rounded-md border border-line px-3 py-2 text-sm" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="机会类型" className="rounded-md border border-line px-3 text-sm" value={type} onChange={e=>setType(e.target.value as typeof type)}>{[["all","全部类型"],["job","工作"],["client","客户"],["project","项目"],["business","商机"],["github","GitHub"]].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><select aria-label="机会排序" className="rounded-md border border-line px-3 text-sm" value={sort} onChange={e=>setSort(e.target.value as OpportunitySort)}>{["AI 推荐","最新","预算","风险"].map(x=><option key={x}>{x}</option>)}</select></Panel>{loading&&!hydrated?<p role="status" className="p-4 text-muted">加载中…</p>:error?<p role="alert" className="p-4 text-red-700">机会暂不可用，请通过顶部提示重试。</p>:items.length?<div className="space-y-2">{items.map(item=><OpportunityCard opportunity={item} key={item.id}/>)}</div>:<EmptyState title={query?"没有符合条件的机会":saved?"暂无收藏":"暂无机会"}><p>调整筛选，或到证据收件箱查看公开需求。</p></EmptyState>}</>;
}
