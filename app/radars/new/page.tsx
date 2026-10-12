"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { Button, PageHeader, Panel } from "@/components/ui";
import { createRadar } from "@/services/radar.service";
import { useOpportunityStore } from "@/stores/use-opportunity-store";

const sources = [["github", "GitHub"], ["hackernews", "Hacker News"], ["rss", "RSS"], ["tikhub", "TikHub / TikTok"], ["web_search", "Web Search"]] as const;

export default function NewRadar() {
  const router = useRouter();
  const addRadar = useOpportunityStore((s) => s.addRadar);
  const [name, setName] = useState("AI 视频广告客户");
  const [goal, setGoal] = useState("寻找明确表达视频广告、短视频批量制作或视频复刻需求的潜在客户");
  const [keywords, setKeywords] = useState("AI视频广告, 视频复刻, 短视频制作");
  const [locations, setLocations] = useState("线上, 桂林");
  const [budget, setBudget] = useState("200");
  const [source, setSource] = useState("github");
  const [freshness, setFreshness] = useState("72");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setLoading(true); setError("");
    try {
      const radar = await createRadar({ name: name.trim(), goal: goal.trim(), keywords: keywords.split(",").map((x) => x.trim()).filter(Boolean), locations: locations.split(",").map((x) => x.trim()).filter(Boolean), minimumBudget: Number(budget) || 0, freshnessHours: Number(freshness) || 72, sources: [source], listenerDescription: goal.trim() });
      addRadar(radar); router.push(`/radars/${radar.id}`);
    } catch (err) { setError(err instanceof Error ? err.message : "雷达创建失败，请检查后端状态。"); }
    finally { setLoading(false); }
  }

  return <AppShell>
    <PageHeader title="创建一个真实雷达" description="明确来源、关键词和筛选条件，保存后再手动运行；不会自动使用虚假数据。" />
    <Panel className="max-w-3xl p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm"><span className="mb-1 block text-muted">雷达名称</span><input value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded border border-line bg-ink px-3 py-2" /></label>
        <label className="text-sm"><span className="mb-1 block text-muted">数据源</span><select value={source} onChange={(e) => setSource(e.target.value)} className="w-full rounded border border-line bg-ink px-3 py-2">{sources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="text-sm sm:col-span-2"><span className="mb-1 block text-muted">你要找什么</span><textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} className="w-full rounded border border-line bg-ink px-3 py-2 leading-6" /></label>
        <label className="text-sm"><span className="mb-1 block text-muted">关键词（逗号分隔）</span><input value={keywords} onChange={(e) => setKeywords(e.target.value)} className="w-full rounded border border-line bg-ink px-3 py-2" /></label>
        <label className="text-sm"><span className="mb-1 block text-muted">地区（逗号分隔）</span><input value={locations} onChange={(e) => setLocations(e.target.value)} className="w-full rounded border border-line bg-ink px-3 py-2" /></label>
        <label className="text-sm"><span className="mb-1 block text-muted">最低预算（元）</span><input type="number" min="0" value={budget} onChange={(e) => setBudget(e.target.value)} className="w-full rounded border border-line bg-ink px-3 py-2" /></label>
        <label className="text-sm"><span className="mb-1 block text-muted">信息新鲜度（小时）</span><input type="number" min="1" max="720" value={freshness} onChange={(e) => setFreshness(e.target.value)} className="w-full rounded border border-line bg-ink px-3 py-2" /></label>
      </div>
      <div className="mt-5 rounded-lg border border-amber-400/20 bg-amber-400/10 p-3 text-sm text-amber-100">TikHub / TikTok 和 Web Search 可能产生费用。当前页面只保存配置，不会自动触发付费采集。</div>
      {error && <p className="mt-4 rounded border border-red-400/30 bg-red-400/10 px-3 py-2 text-sm text-red-200">{error}</p>}
      <div className="mt-5 flex justify-end gap-2"><Button variant="secondary" onClick={() => router.back()}>取消</Button><Button onClick={() => void submit()} disabled={loading || name.trim().length < 1 || goal.trim().length < 10}>{loading ? "保存中…" : "保存雷达"}</Button></div>
    </Panel>
  </AppShell>;
}