"use client";
import { useState } from "react";
import { splitTerms, type CollectionPolicy } from "@/lib/collection-policy";

export function CollectionControls({ policy, onChange, hours, onHours, disabled = false }: {
  policy: CollectionPolicy; onChange: (next: CollectionPolicy) => void;
  hours: number; onHours: (hours: number) => void; disabled?: boolean;
}) {
  const [advanced, setAdvanced] = useState(false);
  const [required, setRequired] = useState(policy.required_terms.join("，"));
  const [excluded, setExcluded] = useState(policy.excluded_terms.join("，"));
  const field = "mt-1 w-full rounded border border-line bg-ink px-3 py-2 text-sm text-mist";
  return <fieldset disabled={disabled} className="mt-4 text-sm text-muted">
    <legend className="mb-2 text-sm font-medium text-mist">时间窗口</legend><div className="mb-3 flex flex-wrap gap-2">{[[24,"24 小时"],[72,"3 天"],[168,"7 天"],[720,"30 天"]].map(([value,label])=><button type="button" aria-pressed={hours===value} className={`rounded-md border px-3 py-2 text-xs ${hours===value?"border-ai bg-indigo-50 text-ai":"border-line bg-white"}`} key={value} onClick={()=>onHours(Number(value))}>{label}</button>)}</div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
    <label>最近多少小时<input aria-label="抓取时间窗口" className={field} type="number" min="1" max="720" value={hours || ""} onChange={e=>onHours(Number(e.target.value))}/></label>
    <button type="button" className="self-end rounded-md border border-line bg-white px-3 py-2 text-sm text-ai" aria-expanded={advanced} onClick={()=>setAdvanced(v=>!v)}>{advanced?"收起高级筛选":"高级筛选与来源说明"}</button></div><div hidden={!advanced} className="mt-3 grid gap-3 rounded-lg bg-ink p-3 sm:grid-cols-2 lg:grid-cols-3"><label>时间依据<select aria-label="抓取时间依据" className={field} value={policy.time_basis} onChange={e=>onChange({...policy,time_basis:e.target.value as CollectionPolicy["time_basis"]})}><option value="published">原帖发布时间</option><option value="activity">来源最近更新时间</option></select></label>
    <label>本次结果排序<select aria-label="采集排序" className={field} value={policy.sort} onChange={e=>onChange({...policy,sort:e.target.value as CollectionPolicy["sort"]})}><option value="latest">最新优先</option><option value="hot">热度优先（已采集结果）</option></select></label>
    <label>原文包含词（逗号分隔）<input aria-label="原文包含词" className={field} value={required} onChange={e=>{setRequired(e.target.value);onChange({...policy,required_terms:splitTerms(e.target.value)});}} placeholder="PPT，演示文稿"/></label>
    <label>包含词匹配<select aria-label="包含词匹配方式" className={field} value={policy.match_mode} onChange={e=>onChange({...policy,match_mode:e.target.value as CollectionPolicy["match_mode"]})}><option value="any">命中任意一个</option><option value="all">必须全部命中</option></select></label>
    <label>原文排除词<input aria-label="原文排除词" className={field} value={excluded} onChange={e=>{setExcluded(e.target.value);onChange({...policy,excluded_terms:splitTerms(e.target.value)});}} placeholder="教程，课程，接单广告"/></label>
    <label>公开活跃信号<select aria-label="活跃信号筛选" className={field} value={policy.activity_filter} onChange={e=>onChange({...policy,activity_filter:e.target.value as CollectionPolicy["activity_filter"]})}><option value="any">不限，未知保留标记</option><option value="author">窗口内帖子＋公开作者</option><option value="discussion">窗口内帖子＋作者＋累计评论</option></select></label>
    <label>最低公开互动数<input aria-label="最低公开互动数" className={field} type="number" min="0" max="10000000" value={policy.min_interactions} onChange={e=>onChange({...policy,min_interactions:Number(e.target.value)})}/></label>
    <label className="flex items-center gap-2 self-center"><input type="checkbox" aria-label="保留时间未知帖子" checked={policy.include_unknown_dates} onChange={e=>onChange({...policy,include_unknown_dates:e.target.checked})}/>保留时间未知帖子（单独标记）</label>
    <p className="leading-5 sm:col-span-2 lg:col-span-3">每次采集一页，再按以上条件筛选。热度按公开累计互动和来源时间估算，不能证明真人身份；互动高也不代表有购买意愿。来源未返回作者、时间或评论时，严格筛选可能没有结果，不会自动加抓。</p>
  </div></fieldset>;
}
