"use client";

import { useState } from "react";
import { Button } from "@/components/ui";
import { REGION_TREE, addRegion, regionLabel, regionNodes } from "@/lib/region-tree";

const selectClass = "mt-1 h-11 w-full rounded-md border border-line bg-white px-3 text-sm disabled:bg-slate-50 disabled:text-muted";

/** 国家 → 省/州 → 城市。可以停在任一层；保存最后一级名称，芯片上显示完整路径。 */
export function RegionPicker({ value, onChange }: { value: string[]; onChange: (regions: string[]) => void }) {
  const [country, setCountry] = useState("");
  const [province, setProvince] = useState("");
  const [city, setCity] = useState("");
  const [custom, setCustom] = useState("");
  const [error, setError] = useState("");
  const provinces = country ? regionNodes([country]) : [];
  const cities = country && province ? regionNodes([country, province]) : [];

  function commit(path: string[]) {
    const result = addRegion(value, path);
    setError(result.error ?? "");
    if (!result.error) onChange(result.regions);
    return !result.error;
  }

  return <div>
    <p className="text-sm">项目 / 服务所在地（不是作者 IP）</p>
    <div className="mt-2 grid gap-2 sm:grid-cols-3">
      <label className="text-sm">国家 / 地区
        <select aria-label="国家或地区" value={country} onChange={event => { setCountry(event.target.value); setProvince(""); setCity(""); }} className={selectClass}>
          <option value="">请选择</option>
          {REGION_TREE.map(node => <option key={node.name} value={node.name}>{node.name}</option>)}
        </select>
      </label>
      <label className="text-sm">省 / 州
        <select aria-label="省或州" value={province} disabled={!provinces.length} onChange={event => { setProvince(event.target.value); setCity(""); }} className={selectClass}>
          <option value="">{provinces.length ? "不细分" : "无下一级"}</option>
          {provinces.map(node => <option key={node.name} value={node.name}>{node.name}</option>)}
        </select>
      </label>
      <label className="text-sm">城市
        <select aria-label="城市" value={city} disabled={!cities.length} onChange={event => setCity(event.target.value)} className={selectClass}>
          <option value="">{cities.length ? "不细分" : "无下一级"}</option>
          {cities.map(node => <option key={node.name} value={node.name}>{node.name}</option>)}
        </select>
      </label>
    </div>
    <div className="mt-2 flex flex-wrap gap-2">
      <Button variant="secondary" disabled={!country} onClick={() => commit([country, province, city])}>加入所选</Button>
      <Button variant="secondary" disabled={!value.length} onClick={() => { onChange([]); setError(""); }}>清空（全国）</Button>
    </div>
    <div className="mt-2 flex gap-2">
      <input aria-label="自定义地区" value={custom} onChange={event => setCustom(event.target.value)} placeholder="列表没有时直接填写，如：清远" className="h-11 min-w-0 flex-1 rounded-md border border-line px-3 text-sm"/>
      <Button variant="secondary" onClick={() => { if (commit([custom])) setCustom(""); }}>添加</Button>
    </div>
    {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
    <div className="mt-2 flex flex-wrap gap-2">{value.map(token => <span key={token} className="inline-flex items-center gap-1 rounded bg-indigo-50 px-2 py-1 text-xs">{regionLabel(token)}<button type="button" className="text-red-700 underline" aria-label={`移除${token}`} onClick={() => onChange(value.filter(item => item !== token))}>移除</button></span>)}</div>
    <p className="mt-2 text-xs text-muted">按国家、省州、城市逐级选择，可以停在任一层。多个地区是“或”，匹配只用最后一级名称，不把省展开成全部城市。只核实原文里的项目或服务地点，不从昵称、IP、简介或查询词推断。留空表示全国。</p>
  </div>;
}
