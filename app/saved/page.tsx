"use client";
import { useMemo } from "react";
import { AppShell } from "@/components/app-shell";
import { OpportunityCard } from "@/components/opportunity-card";
import { EmptyState, PageHeader } from "@/components/ui";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
export default function Saved(){
  const opportunities = useOpportunityStore((state) => state.opportunities);
  const items = useMemo(() => opportunities.filter((item) => item.status === "saved"), [opportunities]);
  return <AppShell><PageHeader title="已收藏" description="你标记为值得持续跟进的机会。"/>{items.length ? <div className="space-y-3">{items.map((item) => <OpportunityCard opportunity={item} key={item.id}/>)}</div> : <EmptyState title="你还没有收藏任何机会。"/>}</AppShell>;
}
