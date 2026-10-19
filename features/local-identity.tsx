"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button, Panel } from "@/components/ui";
import { RegionPicker } from "@/features/region-picker";
import { splitTerms } from "@/lib/collection-policy";
import { localRequest } from "@/lib/local-edition";
import { DEFAULT_IDENTITY, IDENTITY_BUSINESS_PRESETS, IDENTITY_FRESHNESS_CHOICES, IDENTITY_ROLE_PRESETS, IDENTITY_SOURCE_CHOICES, validateIdentity, type LocalIdentity } from "@/lib/identity";
import { HUNT_ROLE_GROUPS } from "@/lib/lead-hunt";

/** 个人身份设定：一次配置，新建抓单自动预填；服务端在保存抓单时同样补齐缺省条件。 */
export function LocalIdentitySection() {
  const [identity, setIdentity] = useState<LocalIdentity>(DEFAULT_IDENTITY);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [customBusiness, setCustomBusiness] = useState("");
  const [customRole, setCustomRole] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const data = await localRequest<{ identity: LocalIdentity | null }>("/api/local/identity");
      setIdentity(data.identity ?? DEFAULT_IDENTITY);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "身份设定暂不可用。"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  function update(values: Partial<LocalIdentity>) { setIdentity(current => ({ ...current, ...values })); setNotice(""); }

  function toggleBusiness(id: string) {
    const preset = IDENTITY_BUSINESS_PRESETS.find(item => item.id === id)!;
    update({ businesses: identity.businesses.some(item => item.id === id) ? identity.businesses.filter(item => item.id !== id) : [...identity.businesses, { id: preset.id, name: preset.name, remote_deliverable: preset.remote_deliverable }] });
  }
  function toggleRemote(id: string) { update({ businesses: identity.businesses.map(item => item.id === id ? { ...item, remote_deliverable: !item.remote_deliverable } : item) }); }
  function addCustomBusiness() {
    const name = customBusiness.trim();
    if (!name) return;
    update({ businesses: [...identity.businesses, { id: `custom-${Date.now().toString(36)}`, name, remote_deliverable: true }] });
    setCustomBusiness("");
  }

  async function save() {
    const invalid = validateIdentity(identity);
    if (invalid) { setError(invalid); return; }
    setBusy(true); setError("");
    try {
      const data = await localRequest<{ identity: LocalIdentity }>("/api/local/identity", { method: "PUT", body: JSON.stringify(identity) });
      setIdentity(data.identity);
      setNotice("已保存并通过 API 读回一致：新建抓单会按这些默认值预填，服务端也会为未填写的抓单条件补齐。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "身份保存失败，请重试。"); }
    finally { setBusy(false); }
  }

  const field = "mt-1 w-full rounded border border-line px-3 py-2 text-sm";
  return <Panel className="space-y-6 p-5">
    <p className="text-sm leading-6 text-muted">只记录公开的经营角色与服务偏好（业务、目标客户、地区、时效、关键词），不采集也不推断年龄、收入、性别等个人敏感属性。保存后：新建抓单页面自动预填；服务端在创建/编辑抓单时补齐缺省的角色、地区、业务词与排除词。</p>
    {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {notice && <p className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
    {loading && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin"/>读取身份设定…</p>}

    <fieldset>
      <legend className="text-sm font-medium">我的业务能力（可多选 + 自定义）</legend>
      <div className="mt-2 space-y-2">{IDENTITY_BUSINESS_PRESETS.map(preset => {
        const selected = identity.businesses.find(item => item.id === preset.id);
        return <div key={preset.id} className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={!!selected} onChange={() => toggleBusiness(preset.id)}/>{preset.name}</label>
          {selected && <label className="flex items-center gap-1 text-xs text-muted"><input type="checkbox" checked={selected.remote_deliverable} onChange={() => toggleRemote(preset.id)}/>可远程交付</label>}
        </div>;
      })}
        {identity.businesses.filter(item => item.id.startsWith("custom-")).map(item => <div key={item.id} className="flex flex-wrap items-center gap-3 text-sm">
          <span className="rounded bg-slate-100 px-2 py-1 text-xs">{item.name}</span>
          <label className="flex items-center gap-1 text-xs text-muted"><input type="checkbox" checked={item.remote_deliverable} onChange={() => toggleRemote(item.id)}/>可远程交付</label>
          <button type="button" className="text-xs text-red-700 underline" onClick={() => update({ businesses: identity.businesses.filter(entry => entry.id !== item.id) })}>移除</button>
        </div>)}
      </div>
      <div className="mt-2 flex gap-2"><input value={customBusiness} onChange={e => setCustomBusiness(e.target.value)} placeholder="自定义业务，如：直播切片" aria-label="自定义业务" className={`${field} max-w-xs`}/><Button variant="secondary" onClick={addCustomBusiness}>添加业务</Button></div>
      <p className="mt-2 text-xs text-muted">“可远程交付”参与默认匹配模式：全部业务都可远程时保持远程优先；存在不能远程的业务且配置了地区时，新抓单默认严格本地。</p>
    </fieldset>

    <fieldset>
      <legend className="text-sm font-medium">目标客户角色（可多选 + 自定义）</legend>
      <div className="mt-2 space-y-2">{HUNT_ROLE_GROUPS.map(group => <div key={group.label}><p className="text-xs text-muted">{group.label}</p><div className="mt-1 flex flex-wrap gap-4 text-sm">{group.roles.map(role => <label key={role} className="flex items-center gap-2"><input type="checkbox" checked={identity.target_roles.includes(role)} onChange={() => update({ target_roles: identity.target_roles.includes(role) ? identity.target_roles.filter(item => item !== role) : [...identity.target_roles, role] })}/>{role}</label>)}</div></div>)}
        <div className="flex flex-wrap gap-2">{identity.target_roles.filter(role => !IDENTITY_ROLE_PRESETS.includes(role)).map(role => <span key={role} className="flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs">{role}<button type="button" className="text-red-700 underline" onClick={() => update({ target_roles: identity.target_roles.filter(item => item !== role) })}>移除</button></span>)}</div></div>
      <div className="mt-2 flex gap-2"><input value={customRole} onChange={e => setCustomRole(e.target.value)} placeholder="自定义角色，如：跨境卖家" aria-label="自定义角色" className={`${field} max-w-xs`}/><Button variant="secondary" onClick={() => { const role = customRole.trim(); if (!role) return; update({ target_roles: [...identity.target_roles, role] }); setCustomRole(""); }}>添加角色</Button></div>
      <p className="mt-2 text-xs text-muted">学生、自由职业、自媒体等只在对方自己写出身份时算命中，不凭年龄或昵称猜测。自定义角色会保留作参考，新建抓单只写入上面这些标准角色。</p>
    </fieldset>

    <fieldset>
      <legend className="text-sm font-medium">服务地域</legend>
      <div className="mt-2 flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="radio" name="service-mode" checked={identity.service_mode === "remote"} onChange={() => update({ service_mode: "remote" })}/>远程优先（不限地区）</label>
        <label className="flex items-center gap-2"><input type="radio" name="service-mode" checked={identity.service_mode === "unspecified"} onChange={() => update({ service_mode: "unspecified" })}/>不限（保留未知）</label>
        <label className="flex items-center gap-2"><input type="radio" name="service-mode" checked={identity.service_mode === "regions"} onChange={() => update({ service_mode: "regions" })}/>指定国家或地区</label>
      </div>
      <div className="mt-3"><RegionPicker value={identity.regions} onChange={regions => update({ regions })}/></div>
      <p className="mt-2 text-xs text-muted">指定国家或地区时，新建抓单默认带上这些地点；确认不可远程的业务后默认按“严格本地”匹配。</p>
    </fieldset>

    <div className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm">默认可接受时效<select aria-label="默认时效" value={identity.default_freshness_hours} onChange={e => update({ default_freshness_hours: Number(e.target.value) as LocalIdentity["default_freshness_hours"] })} className={field}>{IDENTITY_FRESHNESS_CHOICES.map(choice => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select></label>
      <fieldset><legend className="text-sm">默认平台偏好（新建抓单预勾选）</legend><div className="mt-2 flex flex-wrap gap-3 text-sm">{IDENTITY_SOURCE_CHOICES.map(choice => <label key={choice.id} className="flex items-center gap-1"><input type="checkbox" checked={identity.preferred_sources.includes(choice.id)} onChange={() => update({ preferred_sources: identity.preferred_sources.includes(choice.id) ? identity.preferred_sources.filter(item => item !== choice.id) : [...identity.preferred_sources, choice.id] })}/>{choice.name}</label>)}</div></fieldset>
    </div>

    <label className="block text-sm">买方关键词库（逗号分隔，新建抓单取前 3 个作为搜索词）<textarea aria-label="买方关键词库" rows={2} value={identity.buyer_keywords.join("，")} onChange={e => update({ buyer_keywords: splitTerms(e.target.value) })} placeholder="例如：找人做视频，求视频制作，视频外包" className={field}/></label>
    <label className="block text-sm">排除词（招聘/教程/承接等，命中即过滤）<textarea aria-label="排除词" rows={2} value={identity.exclude_words.join("，")} onChange={e => update({ exclude_words: splitTerms(e.target.value) })} placeholder="例如：教程，招聘，代做，承接，招生" className={field}/><span className="mt-1 block text-xs text-muted">排除词写入每次抓单的采集策略，由现有采后过滤真实生效；老抓单在你再次编辑前不受影响。</span></label>
    <label className="block text-sm">业务匹配词（正文/标题至少命中一个）<input aria-label="业务匹配词" value={identity.business_match_words.join("，")} onChange={e => update({ business_match_words: splitTerms(e.target.value) })} placeholder="例如：视频，信息流" className={field}/></label>
    <label className="block text-sm">报价 / 交付风格偏好（可选，用于后续联系草稿）<textarea aria-label="报价风格" rows={2} value={identity.quote_style} onChange={e => update({ quote_style: e.target.value })} placeholder="例如：先确认需求量与交期，再给区间报价；不承诺无法兑现的时效。" className={field}/><span className="mt-1 block text-xs text-muted">本轮只保存，不自动发送任何消息。</span></label>

    <div className="flex items-center justify-end gap-3"><span className="text-xs text-muted">保存即生效，无需重启服务。</span><Button disabled={busy || loading} onClick={() => void save()}>{busy ? "保存中…" : "保存身份设定"}</Button></div>
  </Panel>;
}
