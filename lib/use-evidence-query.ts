"use client";
import { useCallback, useEffect, useState } from "react";
import type { EvidenceCategory } from "./evidence-client";
import type { SortMode, StatusFilter } from "./evidence-view";
import { parseEvidenceQuery, type EvidenceQuery } from "./evidence-query";
export function useEvidenceQuery() {
  const [value,setValue]=useState<EvidenceQuery>(parseEvidenceQuery(""));const [ready,setReady]=useState(false);
  useEffect(()=>{const read=()=>setValue(parseEvidenceQuery(location.search));read();setReady(true);window.addEventListener("popstate",read);return ()=>window.removeEventListener("popstate",read);},[]);
  const update=useCallback((key:keyof EvidenceQuery,next:string|null,replace=false)=>{setValue(previous=>({...previous,[key]:next}));const q=new URLSearchParams(location.search);if(next)q.set(key,next);else q.delete(key);const url=`${location.pathname}${q.size?`?${q}`:""}`;if(url!==location.pathname+location.search)history[replace?"replaceState":"pushState"]({...history.state},"",url);},[]);
  return {category:value.category,setCategory:useCallback((v:EvidenceCategory)=>update("category",v),[update]),status:value.status,setStatus:useCallback((v:StatusFilter)=>update("status",v),[update]),search:value.q,setSearch:useCallback((v:string)=>update("q",v,true),[update]),sort:value.sort,setSort:useCallback((v:SortMode)=>update("sort",v),[update]),sourceFilter:value.source,setSourceFilter:useCallback((v:string|null)=>update("source",v),[update]),selectedId:value.selected,setSelectedId:useCallback((v:string|null,replace=false)=>update("selected",v,replace),[update]),ready};
}
