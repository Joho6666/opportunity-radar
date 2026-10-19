"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CircleAlert, CircleCheck, ClipboardCopy, KeyRound, Loader2 } from "lucide-react";
import { Button, Panel } from "@/components/ui";
import { agentTokenStatusText, generateAgentToken, revokeAgentToken, type AgentTokenGenerated, type AgentTokenState } from "@/lib/local-agent";
import { localRequest } from "@/lib/local-edition";

/** 设置页的 Agent 接入：生成/重置/吊销本机 Agent 令牌，只显示掩码；明文仅生成时出现一次。 */
export function LocalAgentSection() {
  const [state, setState] = useState<AgentTokenState | null>(null);
  const [generated, setGenerated] = useState<AgentTokenGenerated | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState(false);
  const plaintextRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setError("");
    try { setState(await localRequest<AgentTokenState>("/api/local/agent-token")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Agent 令牌状态暂不可用。"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function run(action: string, work: () => Promise<void>) {
    setBusy(action); setError("");
    try { await work(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败，请重试。"); }
    finally { setBusy(""); }
  }

  async function generate() {
    if (state?.configured && typeof window !== "undefined" && !window.confirm("重新生成会立即吊销旧令牌（agent / 命令行需要换用新令牌）。继续？")) return;
    await run("generate", async () => {
      const data = await generateAgentToken();
      setGenerated(data);
      setState({ ...data });
      setNotice("新令牌已生成并立即生效（无需重启）。明文只显示这一次：请现在复制，离开或刷新后无法再查看。");
      queueMicrotask(() => plaintextRef.current?.focus());
    });
  }

  async function revoke() {
    if (typeof window !== "undefined" && !window.confirm("吊销 Agent 令牌？所有使用该令牌的 agent / 命令行调用会立刻收到 401。")) return;
    await run("revoke", async () => {
      setState(await revokeAgentToken());
      setGenerated(null);
      setNotice("已吊销：令牌文件已删除，agent 调用立即失效（无需重启）。");
    });
  }

  async function copyPlaintext() {
    if (!generated?.plaintext) return;
    try {
      await navigator.clipboard.writeText(generated.plaintext);
      setCopied(true);
    } catch {
      setCopied(false);
      setError("复制失败：请手动选中文本框内容复制（明文不会再次显示）。");
    }
  }

  const apiBase = state?.api_base ?? "http://127.0.0.1:8015/api/agent";

  return <Panel className="space-y-4 p-5">
    <p className="text-sm leading-6 text-muted">Agent 接口只在本机 loopback 开放，使用独立令牌鉴权（与网页会话完全隔离：不带令牌一律 401，不接受 cookie 回退）。写操作需要 <span className="mono">Idempotency-Key</span>，付费运行必须显式确认并沿用同一套预算与账本；不开放自动定时付费调度、发私信/评论等能力。</p>
    {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {notice && <p className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}

    <section>
      <h3 className="inline-flex items-center gap-2 text-sm font-medium"><KeyRound size={15}/>Agent 令牌</h3>
      {!state && !error && <p className="mt-2 flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin"/>读取令牌状态…</p>}
      {state && <div className="mt-2 rounded-md bg-slate-50 p-3 text-sm leading-6">
        <p className="flex flex-wrap items-center gap-2">
          <span className={state.configured ? "inline-flex items-center gap-1 text-emerald-700" : "inline-flex items-center gap-1 text-muted"}>
            {state.configured ? <CircleCheck size={15}/> : <CircleAlert size={15}/>}
            令牌：<span className="mono">{state.masked_token || "未配置"}</span>
          </span>
        </p>
        <p className="mt-1 text-xs text-muted">{agentTokenStatusText(state)}</p>
        <p className="mt-1 text-xs text-muted">接口地址：<span className="mono">{apiBase}</span> · 例：<span className="mono">scripts/or sources</span>（命令行自动读取本机令牌）</p>
      </div>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button disabled={!!busy} onClick={() => void generate()}>{busy === "generate" ? "生成中…" : state?.configured ? "重置令牌" : "生成令牌"}</Button>
        <Button variant="secondary" disabled={!!busy || !state?.configured} onClick={() => void revoke()}>{busy === "revoke" ? "吊销中…" : "吊销令牌"}</Button>
      </div>

      {generated && <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3">
        <p className="text-sm text-amber-900">{generated.notice}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input ref={plaintextRef} readOnly aria-label="Agent 令牌明文（只显示一次）" value={generated.plaintext} className="mono h-10 flex-1 rounded border border-amber-300 bg-white px-2 text-sm" onFocus={event => event.currentTarget.select()}/>
          <Button variant="secondary" onClick={() => void copyPlaintext()}><ClipboardCopy size={15}/> {copied ? "已复制" : "复制"}</Button>
          <Button variant="secondary" onClick={() => { setGenerated(null); setNotice("明文已从页面移除；需要再次获取请重置令牌。"); }}>隐藏</Button>
        </div>
        <p className="mt-2 text-xs text-amber-900">页面不会保存明文（不写浏览器存储、不写日志）；请现在粘贴到 agent 的私密配置或命令行环境变量。</p>
      </div>}
    </section>

    <section className="text-xs leading-5 text-muted">
      <p>命令行示例：<span className="mono">scripts/or new --keywords &quot;电商 视频 外包&quot; --sources xiaohongshu</span> · <span className="mono">scripts/or run &lt;雷达ID&gt; --confirm</span> · <span className="mono">scripts/or results &lt;雷达ID&gt; --json</span></p>
      <p className="mt-1">直接调用：<span className="mono">curl -H &quot;Authorization: Bearer &lt;令牌&gt;&quot; {apiBase}/sources</span>（仅限本机；令牌泄露请立即吊销重发）</p>
    </section>
  </Panel>;
}
