"use client";
import { AppShell } from "@/components/app-shell";
import { Button, PageHeader, Panel } from "@/components/ui";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
export default function Skills() { const {skills,toggleSkill}=useOpportunityStore(); return <AppShell><PageHeader title="机会技能" description="这些开关仅保存当前浏览器的场景偏好，不会安装或启用后端模型能力。"/><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{skills.map(s=><Panel className="p-5" key={s.id}><span className="text-2xl">{s.icon}</span><h2 className="mt-4 font-semibold">{s.name}</h2><p className="mt-2 text-sm text-muted">{s.description}</p><Button className="mt-5" variant={s.installed?"secondary":"primary"} onClick={()=>toggleSkill(s.id)}>{s.installed?"停用":"启用"}</Button></Panel>)}</div></AppShell>; }
