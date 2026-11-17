/**
 * Opportunity Radar — DeepSeek Harness host plugin.
 *
 * Exposes READ-ONLY tools that drive the local `scripts/or` CLI and reports
 * service health. It never reads out or prints the agent token in plaintext,
 * never starts paid collection, and degrades to a clear offline/degraded report
 * when the Local Edition service or its database dependency is not running.
 *
 * One tool, `radar_list`, calls the read-only GET /api/agent/radars endpoint
 * directly because `scripts/or` has no `radars` subcommand; it authenticates
 * with the same loopback agent token the CLI uses and never surfaces it.
 *
 * Only Node built-ins are imported: a profile-installed bundle is resolved
 * from the workspace, so it must not depend on @deepseek-ai/* module paths.
 */
import { execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { promisify } from 'node:util';
import { access, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const execFileAsync = promisify(execFile);

/** Stable Loader identity. */
export const name = 'opportunity-radar';
/** Services this plugin needs; absent services keep it inactive. */
export const inject = ['tools', 'skills'];

const DEFAULT_REPO = '/Users/joho/Documents/Codex/2026-10-13/opportunity-radar-ai-agent-github-https/work/opportunity-radar';
const DEFAULT_APP_HOME = path.join(process.env.HOME ?? '', 'Library', 'Application Support', 'Opportunity Radar');
const BUNDLED_SKILL_RANK = 600;
const RESULT_CAP = 16000;
const RAW_TEXT_LIMIT = 900;
const STRING_LIMIT = 700;

const SKILL_BODY_URL = new URL('./assets/opportunity-radar.md', import.meta.url);
const ASSET_DIR_URL = new URL('./assets/', import.meta.url);
const RESOURCE_BASE = { kind: 'directory', path: fileURLToPath(ASSET_DIR_URL) };
const SKILL_NAME = 'opportunity-radar';
const PROVIDER_NAME = 'opportunity-radar';

const SKILL_DESCRIPTION = 'Query and search the local Opportunity Radar workbench: check service health, list radars and platforms, run a one-shot keyword search, read radar results and runs, and inspect billing/identity. Use when the user asks about 机会雷达、抓单、线索、雷达结果、看板、可视化、搜一搜某关键词的最新帖子, or wants to know whether the local radar service is running.';

const CANDIDATE = {
  name: SKILL_NAME,
  description: SKILL_DESCRIPTION,
  invocation: { modelInvocable: true, userInvocable: true },
  provider: PROVIDER_NAME,
  source: 'bundled',
  resourceBase: RESOURCE_BASE,
  rank: BUNDLED_SKILL_RANK,
  locator: SKILL_BODY_URL,
};

/** Tool result schema. Kept deliberately permissive but fully typed. */
const RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: true,
  properties: {
    ok: { type: 'boolean' },
    state: { type: 'string', enum: ['online', 'offline', 'degraded', 'misconfigured'] },
    command: { type: 'string' },
    exit_code: { type: 'integer' },
    http_status: { type: 'integer' },
    request_id: { type: 'string' },
    api_base: { type: 'string' },
    repo: { type: 'string' },
    data: { type: 'object' },
    error: { type: 'object' },
    hint: { type: 'string' },
    duration_ms: { type: 'integer' },
    checks: { type: 'object' },
  },
};

function settingsFrom(config) {
  const c = config && typeof config === 'object' ? config : {};
  const timeout = Number(c.timeoutMs);
  return {
    repo: String(c.repoPath || process.env.OPPORTUNITY_RADAR_REPO || DEFAULT_REPO),
    appHome: String(c.appHome || process.env.OPPORTUNITY_RADAR_HOME || DEFAULT_APP_HOME),
    apiPort: String(c.apiPort || process.env.LOCAL_API_PORT || '8015'),
    uiPort: String(c.uiPort || '3004'),
    python: String(c.python || process.env.OPPORTUNITY_RADAR_PYTHON || ''),
    timeoutMs: Number.isFinite(timeout) && timeout > 0 ? timeout : 12000,
  };
}

async function exists(target) {
  try {
    await access(target);
    return true;
  } catch {
    return false;
  }
}

/** Probe one loopback URL and return its HTTP status, or 0 when unreachable. */
async function probeStatus(host, port, pathname) {
  try {
    const res = await fetch(`http://${host}:${port}${pathname}`, {
      signal: AbortSignal.timeout(1500),
      redirect: 'manual',
    });
    return Number(res.status) || 0;
  } catch {
    return 0;
  }
}

async function gatherChecks(s) {
  // The UI enforces Host: localhost:3004 and answers 127.0.0.1 with 403, so probe
  // it by its canonical name; a 307 towards /dashboard is the healthy answer.
  const [script, localEnv, runtimeEnv, agentToken, apiStatus, uiStatus] = await Promise.all([
    exists(path.join(s.repo, 'scripts', 'or')),
    exists(path.join(s.appHome, 'config', 'local.env')),
    exists(path.join(s.appHome, 'config', 'local-runtime.env')),
    exists(path.join(s.appHome, 'config', 'agent-token.json')),
    probeStatus('127.0.0.1', s.apiPort, '/ready'),
    probeStatus('localhost', s.uiPort, '/'),
  ]);
  return {
    script,
    localEnv,
    runtimeEnv,
    agentToken,
    apiReachable: apiStatus !== 0,
    apiReady: apiStatus === 200,
    apiStatus,
    uiReachable: uiStatus !== 0,
    uiStatus,
  };
}

async function pythonFor(s) {
  if (s.python && await exists(s.python)) return s.python;
  const venv = path.join(s.repo, '.venv', 'bin', 'python');
  if (await exists(venv)) return venv;
  return 'python3';
}

function parseJson(text) {
  if (!text || typeof text !== 'string') return undefined;
  const trimmed = text.trim();
  if (!trimmed.startsWith('{')) return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    return undefined;
  }
}

function normalize(parsed, stderr, exitCode, apiBase) {
  const tail = (stderr || '').slice(0, 800);
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const rawData = parsed.data;
    const data = Array.isArray(rawData)
      ? { items: rawData }
      : rawData && typeof rawData === 'object' && !Array.isArray(rawData)
        ? rawData
        : {};
    const err = parsed.error && typeof parsed.error === 'object' ? parsed.error : {};
    return {
      ok: parsed.ok === true,
      exit_code: exitCode,
      http_status: Number(parsed.http_status) || 0,
      request_id: String(parsed.request_id || ''),
      api_base: String(parsed.api_base || apiBase),
      data,
      error: {
        code: String(err.code || ''),
        message: String(err.message || ''),
      },
      stderr: tail,
    };
  }
  return {
    ok: false,
    exit_code: exitCode,
    http_status: 0,
    request_id: '',
    api_base: apiBase,
    data: {},
    error: {
      code: 'OR_OUTPUT_INVALID',
      message: tail ? `or 未返回可解析的 JSON：${tail.slice(0, 300)}` : 'or 未返回可解析的 JSON',
    },
    stderr: tail,
  };
}

async function runOr(s, args, signal) {
  const script = path.join(s.repo, 'scripts', 'or');
  const apiBase = `http://127.0.0.1:${s.apiPort}`;
  if (!(await exists(script))) {
    return {
      ok: false,
      exit_code: -1,
      http_status: 0,
      request_id: '',
      api_base: apiBase,
      data: {},
      error: { code: 'OR_SCRIPT_MISSING', message: `未找到 ${script}` },
      stderr: '',
    };
  }
  const python = await pythonFor(s);
  // Pass the configured port explicitly: `or` otherwise resolves its own base
  // from the runtime env, so a `apiPort` override in cordis.patch.yml would
  // silently keep talking to 8015 while probes and hints reported the new port.
  const fullArgs = [script, ...args, '--json', '--timeout', '5', '--api-base', apiBase];
  try {
    const { stdout, stderr } = await execFileAsync(python, fullArgs, {
      cwd: s.repo,
      timeout: s.timeoutMs,
      maxBuffer: 4 * 1024 * 1024,
      windowsHide: true,
      ...(signal ? { signal } : {}),
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });
    return normalize(parseJson(stdout), stderr, 0, apiBase);
  } catch (error) {
    const stdout = typeof error?.stdout === 'string' ? error.stdout : '';
    const stderr = typeof error?.stderr === 'string' ? error.stderr : String(error?.message || '');
    const exitCode = typeof error?.code === 'number' ? error.code : -1;
    return normalize(parseJson(stdout), stderr, exitCode, apiBase);
  }
}

/** Read the loopback agent token for internal auth; the value never leaves this function. */
async function readAgentToken(s) {
  const file = path.join(s.appHome, 'config', 'agent-token.json');
  try {
    const parsed = JSON.parse(await readFile(file, 'utf8'));
    const token = typeof parsed === 'string' ? parsed : parsed && typeof parsed === 'object' ? parsed.token : '';
    if (typeof token !== 'string' || !token.trim()) return { error: 'AGENT_TOKEN_MISSING' };
    return { token: token.trim() };
  } catch (error) {
    if (error && error.code === 'ENOENT') return { error: 'AGENT_TOKEN_MISSING' };
    return { error: 'AGENT_TOKEN_UNREADABLE' };
  }
}

/**
 * Call the loopback agent API. Accepts a bare path (GET) or
 * `{ path, method, body, idempotent, timeoutMs }`. Writes carry an
 * Idempotency-Key because every mutating agent endpoint requires one.
 * Failures never echo the token.
 */
async function callAgentApi(s, target, signal) {
  const opts = typeof target === 'string' ? { path: target } : (target || {});
  const pathname = String(opts.path || '');
  const method = String(opts.method || 'GET').toUpperCase();
  const apiBase = `http://127.0.0.1:${s.apiPort}`;
  const auth = await readAgentToken(s);
  if (auth.error) {
    const message = auth.error === 'AGENT_TOKEN_MISSING'
      ? '缺少 config/agent-token.json；请在本机看板的设置页生成 Agent 令牌。'
      : 'config/agent-token.json 无法解析；请重新生成 Agent 令牌。';
    return { ok: false, exit_code: -1, http_status: 0, request_id: '', api_base: apiBase, data: {}, error: { code: auth.error, message }, stderr: '' };
  }
  const headers = { authorization: `Bearer ${auth.token}`, accept: 'application/json' };
  let body;
  if (opts.body !== undefined) {
    headers['content-type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  if (opts.idempotent) headers['idempotency-key'] = randomUUID();
  try {
    const res = await fetch(`${apiBase}${pathname}`, {
      method,
      headers,
      body,
      signal: signal ?? AbortSignal.timeout(Number(opts.timeoutMs) > 0 ? Number(opts.timeoutMs) : s.timeoutMs),
      redirect: 'manual',
    });
    const parsed = parseJson(await res.text()) ?? {};
    if (res.ok) {
      const payload = parsed && typeof parsed === 'object' ? parsed : {};
      const inner = payload.data && typeof payload.data === 'object' ? payload.data : payload;
      return {
        ok: payload.ok !== false,
        exit_code: 0,
        http_status: res.status,
        request_id: String(res.headers.get('x-request-id') || payload.request_id || ''),
        api_base: apiBase,
        data: inner && typeof inner === 'object' && !Array.isArray(inner) ? inner : {},
        error: { code: '', message: '' },
        stderr: '',
      };
    }
    const detail = parsed && typeof parsed === 'object' ? parsed.detail : undefined;
    const code = String(
      (detail && typeof detail === 'object' && detail.code)
      || (parsed && typeof parsed === 'object' && parsed.code)
      || `HTTP_${res.status}`,
    );
    const message = String(
      (detail && typeof detail === 'object' && detail.message)
      || (typeof detail === 'string' ? detail : '')
      || (parsed && typeof parsed === 'object' && parsed.message)
      || `HTTP ${res.status}`,
    );
    return { ok: false, exit_code: 2, http_status: res.status, request_id: '', api_base: apiBase, data: {}, error: { code, message }, stderr: '' };
  } catch (error) {
    return {
      ok: false,
      exit_code: -1,
      http_status: 0,
      request_id: '',
      api_base: apiBase,
      data: {},
      error: { code: 'API_UNREACHABLE', message: String(error?.message || error).slice(0, 300) },
      stderr: '',
    };
  }
}

const RUN_TERMINAL = new Set(['completed', 'partial', 'failed', 'cancelled']);

/** Poll `GET /runs?radar_id=` until the run reaches a terminal status or the budget elapses. */
async function waitForRun(s, radarId, runId, waitMs, signal) {
  const deadline = Date.now() + Math.max(0, waitMs);
  let run = null;
  for (;;) {
    if (signal?.aborted) throw new Error('aborted');
    const res = await callAgentApi(s, `/api/agent/runs?radar_id=${encodeURIComponent(radarId)}&limit=5`, signal);
    if (!res.ok) return { run, error: res, timedOut: false };
    const items = Array.isArray(res.data.items) ? res.data.items : [];
    run = items.find((entry) => String(entry.id) === String(runId)) || items[0] || run;
    if (run && RUN_TERMINAL.has(String(run.status))) return { run, timedOut: false };
    if (Date.now() >= deadline) return { run, timedOut: true };
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

const SEARCH_HOURS = [24, 72, 168, 720];
const SEARCH_DEFAULT_SOURCES = ['xiaohongshu'];

function localFailure(apiBase, code, message, data = {}) {
  // 400 keeps `classify` from blaming the service: the request was rejected,
  // not the configuration.
  return { ok: false, exit_code: -1, http_status: 400, request_id: '', api_base: apiBase, data, error: { code, message }, stderr: '' };
}

/**
 * One-shot keyword search: create a plain-mode radar (no lead_hunt business
 * terms, which would filter the results away), run it once, wait, then read
 * the results back. Always keeps the radar so history and dedupe stay usable.
 */
async function runSearch(s, a, exec) {
  const signal = signalFrom(exec);
  const apiBase = `http://127.0.0.1:${s.apiPort}`;
  const query = String(a.query || '').trim();
  if (!query || query.length > 100) {
    return localFailure(apiBase, 'QUERY_INVALID', 'query 必须是 1–100 字的搜索关键词。');
  }
  if (a.confirm !== true) {
    return localFailure(apiBase, 'CONFIRM_REQUIRED', '这会触发一次真实付费采集：请显式传 confirm: true。单次花费受 provider 配置的上限约束（默认 $0.10）。');
  }
  const sources = (Array.isArray(a.sources) && a.sources.length ? a.sources : SEARCH_DEFAULT_SOURCES)
    .map((id) => String(id)).slice(0, 4);
  const hours = SEARCH_HOURS.includes(Number(a.hours)) ? Number(a.hours) : 168;
  const limit = Math.min(50, Math.max(1, Number(a.limit) || 10));
  const waitMs = Math.min(90000, Math.max(5000, Number(a.waitMs) || 45000));

  const catalog = await callAgentApi(s, '/api/agent/sources', signal);
  if (!catalog.ok) return catalog;
  const usable = new Set((Array.isArray(catalog.data.items) ? catalog.data.items : [])
    .filter((item) => item && item.available).map((item) => String(item.id)));
  const blocked = sources.filter((id) => !usable.has(id));
  if (blocked.length) {
    return localFailure(apiBase, 'SOURCE_NOT_AVAILABLE',
      `平台不可用：${blocked.join('、')}。先运行 radar_provider_diagnose 看缺什么（通常是端点单价未核验）。`,
      { blocked, available: [...usable] });
  }

  const name = String(a.name || `搜索：${query}`).slice(0, 120);
  const created = await callAgentApi(s, {
    path: '/api/agent/radars',
    method: 'POST',
    idempotent: true,
    body: {
      name,
      description: '',
      goal: `按关键词「${query}」搜索最新内容`,
      mode: 'general',
      minimum_budget: 0,
      frequency: 'manual',
      freshness_hours: hours,
      keywords: [query],
      locations: [],
      sources,
      source_config: {},
      collection_policy: {
        required_terms: [],
        excluded_terms: ['招聘', '承接'],
        match_mode: 'any',
        time_basis: 'published',
        include_unknown_dates: false,
        sort: 'latest',
        activity_filter: 'any',
        min_interactions: 0,
      },
      listener_description: '',
      local_schedule_enabled: false,
    },
  }, signal);
  if (!created.ok) return created;
  const radar = created.data.radar || created.data;
  const radarId = String(radar && radar.id ? radar.id : '');
  if (!radarId) return localFailure(apiBase, 'RADAR_CREATE_NO_ID', '后端没有返回雷达 id。');

  const started = await callAgentApi(s, {
    path: `/api/agent/radars/${encodeURIComponent(radarId)}/run`,
    method: 'POST',
    idempotent: true,
    body: { confirm: true },
  }, signal);
  if (!started.ok) return started;

  const initial = started.data.run || {};
  const runId = String(initial.id || '');
  const waited = await waitForRun(s, radarId, runId, waitMs, signal);
  const run = waited.run || initial;
  const stage = run.stage_stats || {};
  // The API orders results by relevance; a keyword search wants the newest, so
  // pull a wider page and sort by publish time before slicing.
  const fetchLimit = Math.min(100, Math.max(limit, 50));
  const results = await callAgentApi(s, `/api/agent/radars/${encodeURIComponent(radarId)}/results?limit=${fetchLimit}`, signal);
  const fetched = Array.isArray(results.data.items) ? results.data.items : [];
  const items = [...fetched]
    .sort((left, right) => String(right.published_at || '').localeCompare(String(left.published_at || '')))
    .slice(0, limit);

  return {
    ok: results.ok,
    exit_code: 0,
    http_status: results.http_status,
    request_id: started.request_id,
    api_base: apiBase,
    data: {
      query,
      sources,
      hours,
      radar_id: radarId,
      radar_name: name,
      run_id: runId,
      run_status: String(run.status || (waited.timedOut ? 'running' : 'unknown')),
      timed_out: Boolean(waited.timedOut),
      stats: run.stats || null,
      source_stats: Array.isArray(stage.source_stats) ? stage.source_stats : [],
      run_error: run.error_message || null,
      fetched: fetched.length,
      items,
      page: results.data.page || null,
    },
    error: results.error,
    stderr: '',
  };
}

/** Search spends money, so its hint must say so instead of the read-only default. */
function searchHint(r) {
  const d = r.data || {};
  if (!r.ok) {
    const detail = r.error.message ? `：${r.error.message.replace(/[。．.]$/, '')}` : '';
    return `搜索未完成（${r.error.code || 'UNKNOWN'}）${detail}。已创建的雷达 ${d.radar_id || '-'} 与运行 ${d.run_id || '-'} 可以保留，也可在界面删除。`;
  }
  const requests = (Array.isArray(d.source_stats) ? d.source_stats : [])
    .reduce((sum, entry) => sum + (Number(entry.requests) || 0), 0);
  return `本次触发了 1 轮真实付费采集（${requests} 次请求，单次上限 $0.10，实际花费见 radar_status 的账本）。`
    + ` 雷达「${d.radar_name || '-'}」已保留；agent 接口没有删除入口，可在界面删。`
    + ' 结果已按发布时间倒序；match 为空表示这是内容帖、不是买方线索。要更窄就调 hours/limit 或换关键词。';
}

/** Read-only explanation of why paid platforms are unavailable. */
async function runDiagnose(s, _a, exec) {
  const signal = signalFrom(exec);
  const res = await callAgentApi(s, '/api/agent/sources', signal);
  if (!res.ok) return res;
  const items = (Array.isArray(res.data.items) ? res.data.items : []).filter((item) => item && item.id);
  const ready = [];
  const missingPrice = [];
  const missingKey = [];
  const other = [];
  for (const item of items) {
    const row = {
      id: item.id,
      available: Boolean(item.available),
      configured: Boolean(item.configured),
      paid_enabled: Boolean(item.paid_enabled),
      price_usd: item.price_usd == null ? null : item.price_usd,
      status: item.status || '',
    };
    if (row.available) ready.push(row);
    else if (!row.configured) missingKey.push(row);
    else if (row.price_usd == null) missingPrice.push(row);
    else other.push(row);
  }
  return {
    ok: true,
    exit_code: 0,
    http_status: res.http_status,
    request_id: res.request_id,
    api_base: res.api_base,
    data: {
      tally: {
        total: items.length,
        ready: ready.length,
        missing_key: missingKey.length,
        missing_price: missingPrice.length,
        other: other.length,
      },
      ready,
      missing_key: missingKey,
      missing_price: missingPrice,
      other,
      quote_rule: '端点单价必须 ≤ 0.1 USD/request，且 TIKHUB_ENDPOINT_PRICES_JSON 与 TIKHUB_PRICE_RECEIPTS_JSON 同键存在；receipt 需含 price_usd / unit=USD/request / source_url(https 且属 tikhub.io) / verified_at(带时区) / verified_by。缺失即 fail-closed。',
      where: 'https://user.tikhub.io/dashboard/api-marketplace',
      how: '把两个 JSON 写进 config/local.env（不要加引号），并在 scripts/local.sh 的 service 字典里透传，然后重启 api 与 worker。',
    },
    error: { code: '', message: '' },
    stderr: '',
  };
}

function classify(r, checks) {
  if (r.error.code === 'OR_SCRIPT_MISSING') return 'misconfigured';
  if (r.ok) return 'online';
  if (!checks.apiReachable) return 'offline';
  // The API process is up but a backing dependency is not (usually PostgreSQL
  // and Redis containers after Docker Desktop restarts). Any 5xx from /ready
  // means the service cannot serve, and that is a dependency fault rather than
  // a configuration fault.
  if (checks.apiStatus >= 500) return 'degraded';
  // The service is healthy and rejected the request itself (bad radar id, bad
  // page size). That is not a configuration fault, so do not blame the setup.
  if (checks.apiReady && r.http_status >= 400 && r.http_status < 500
    && r.http_status !== 401 && r.http_status !== 403) return 'online';
  return 'misconfigured';
}

function hintFor(state, s, checks, r) {
  if (state === 'online') {
    if (!r.ok && r.error.code) {
      const detail = r.error.message ? `：${r.error.message.replace(/[。．.]$/, '')}` : '';
      return `服务在线，但本次请求被拒绝（${r.error.code}）${detail}。`
        + '请检查参数：radar_id 需先用 radar_list 查到，limit 取 1-100，offset ≥ 0。'
        + '本插件只读，不触发采集或计费。';
    }
    return '服务在线。本插件只暴露只读工具，不触发任何采集或计费；付费开关与预算请以 radar_status 的 data 为准。';
  }
  if (state === 'degraded') {
    return `API 进程可达但返回 HTTP ${checks.apiStatus}：后台依赖（PostgreSQL 54330 / Redis 6380，Docker Compose 项目 opportunity-radar-local）未运行。`
      + '修复：先启动 Docker Desktop（open -a Docker），等待守护进程就绪后执行 '
      + `cd ${s.repo} && docker compose -p opportunity-radar-local -f docker-compose.local.yml --env-file "$HOME/Library/Application Support/Opportunity Radar/config/local.env" up -d --wait postgres redis。`
      + '容器恢复后 API 会自行重连，无需重启 LaunchAgent；确认：curl -s http://127.0.0.1:8015/ready。';
  }
  const missing = [];
  if (!checks.script) missing.push('scripts/or');
  if (!checks.localEnv) missing.push('config/local.env');
  if (!checks.runtimeEnv) missing.push('config/local-runtime.env');
  if (!checks.agentToken) missing.push('config/agent-token.json');
  const parts = [];
  if (state === 'offline') {
    parts.push(`本机服务未运行：127.0.0.1:${s.apiPort}（API）与 ${s.uiPort}（UI）不可达。`);
  } else {
    parts.push(`服务可达但配置/鉴权未就绪${r.error.code ? `（${r.error.code}）` : ''}。`);
  }
  parts.push(`检查：cd ${s.repo} && LC_ALL=C scripts/local.sh status；启动：cd ${s.repo} && LC_ALL=C scripts/local.sh start。`);
  if (missing.length) {
    parts.push(`缺失：${missing.join('、')}。需按 ${s.repo}/docs/LOCAL_EDITION_RUNBOOK.md 重建私有配置后才能启动；Docker 数据卷仍在，恢复时沿用原 LOCAL_USER_ID。`);
  }
  if (!checks.agentToken && state !== 'offline') {
    parts.push('请在设置页生成 Agent 令牌；本插件绝不读取或输出令牌明文。');
  }
  parts.push('scripts/local.sh 在 UTF-8 locale 下会因中文变量名报错，命令前需加 LC_ALL=C。');
  parts.push('付费运行未暴露为工具：须由用户明确确认后在终端手动执行 scripts/or run <雷达ID> --confirm。');
  return parts.join(' ');
}

function pick(source, keys) {
  const out = {};
  if (!source || typeof source !== 'object') return out;
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(source, key)) out[key] = source[key];
  }
  return out;
}

function jsonSize(value) {
  try {
    return JSON.stringify(value).length;
  } catch {
    return Number.POSITIVE_INFINITY;
  }
}

function truncate(text, limit) {
  return typeof text === 'string' && text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function trimStrings(value, limit = STRING_LIMIT, depth = 0) {
  if (typeof value === 'string') return truncate(value, limit);
  if (Array.isArray(value)) {
    if (depth > 8) return '[…]';
    return value.map((item) => trimStrings(item, limit, depth + 1));
  }
  if (value && typeof value === 'object') {
    if (depth > 8) return '[…]';
    const out = {};
    for (const [key, item] of Object.entries(value)) out[key] = trimStrings(item, limit, depth + 1);
    return out;
  }
  return value;
}

/** Fields worth keeping for a platform row; the rest is endpoint/capability detail. */
const SOURCE_KEYS = ['id', 'namespace', 'name', 'provider', 'available', 'configured', 'paid_enabled', 'selectable', 'price_usd', 'status', 'live_verified'];

/**
 * Fields worth keeping for a radar row in a list. Source/listener configuration
 * and generated queries dominate the payload and are only useful for one radar
 * at a time, which `radar_list` with `radar_id` returns unprojected.
 */
const RADAR_LIST_KEYS = [
  'id', 'name', 'description', 'status', 'mode', 'keywords', 'locations', 'sources',
  'frequency', 'freshness_hours', 'minimum_budget', 'collection_policy',
  'local_schedule_enabled', 'last_run_at', 'next_run_at', 'stats',
];

function summarizeAuthorizations(list) {
  if (!Array.isArray(list)) return list;
  const enabled = list.filter((entry) => entry && entry.enabled);
  const remainingRequests = enabled.reduce((sum, entry) => sum + (Number(entry.remaining_requests) || 0), 0);
  const remainingCost = enabled.reduce((sum, entry) => sum + (Number(entry.remaining_cost_usd) || 0), 0);
  return {
    count: list.length,
    enabled: enabled.length,
    total_remaining_requests: remainingRequests,
    total_remaining_cost_usd: Number(remainingCost.toFixed(4)),
    scopes: list.map((entry) => (entry ? entry.scope : undefined)).filter(Boolean).slice(0, 40),
  };
}

/**
 * Keep paged results useful instead of dropping everything but three items:
 * project verbose platform rows, truncate long raw_text, summarize oversized
 * authorization lists, and only then fall back to trimming and paging.
 */
function compactFor(command, data, cap = RESULT_CAP) {
  if (!data || typeof data !== 'object') return data;
  let out = data;
  const notes = [];
  // `reduced` means fields were projected but every row survived; `truncated`
  // means content or rows were actually dropped.
  let reduced = false;
  let truncated = false;

  if (Array.isArray(data.items) && command === 'radar_list') {
    out = {
      ...data,
      items: data.items.map((item) => ({
        ...pick(item, RADAR_LIST_KEYS),
        ...(item && typeof item.description === 'string' ? { description: truncate(item.description, 300) } : {}),
      })),
    };
    if (jsonSize(out) !== jsonSize(data)) {
      reduced = true;
      notes.push('雷达列表只保留名称/状态/关键词/平台/时间等字段；完整配置请用 radar_list 传 radar_id 读单个。');
    }
  }

  if (Array.isArray(data.items) && command === 'radar_sources') {
    out = { ...data, items: data.items.map((item) => pick(item, SOURCE_KEYS)) };
    if (jsonSize(out) !== jsonSize(data)) {
      reduced = true;
      notes.push('平台条目只保留 id/名称/可用性/单价/状态等字段，省略端点与能力明细；平台条数未删减。');
    }
  }

  if (Array.isArray(data.items) && (command === 'radar_results' || command === 'radar_search')) {
    let shortened = 0;
    const items = data.items.map((item) => {
      if (item && typeof item.raw_text === 'string' && item.raw_text.length > RAW_TEXT_LIMIT) {
        shortened += 1;
        return { ...item, raw_text: truncate(item.raw_text, RAW_TEXT_LIMIT) };
      }
      return item;
    });
    out = { ...out, items };
    if (shortened) {
      truncated = true;
      notes.push(`raw_text 已截断到 ${RAW_TEXT_LIMIT} 字符（${shortened} 条）；完整原文请打开 url。`);
    }
  }

  if (jsonSize(out) > cap && command === 'radar_status' && Array.isArray(out.authorizations)) {
    out = { ...out, authorizations: summarizeAuthorizations(out.authorizations) };
    truncated = true;
    notes.push('authorizations 已汇总为计数与额度合计。');
  }

  if (jsonSize(out) > cap) {
    out = trimStrings(out);
    truncated = true;
    notes.push('超长字符串已截断。');
  }

  if (jsonSize(out) > cap && Array.isArray(out.items)) {
    const total = out.items.length;
    const kept = [];
    for (const item of out.items) {
      if (jsonSize({ ...out, items: [...kept, item] }) > cap) break;
      kept.push(item);
    }
    out = { ...out, items: kept };
    truncated = true;
    notes.push(`仅保留前 ${kept.length}/${total} 条，请用 limit/offset 分页。`);
  }

  if (!notes.length) return data;
  return {
    ...out,
    ...(reduced ? { reduced: true } : {}),
    ...(truncated ? { truncated: true } : {}),
    note: notes.join(' '),
  };
}

const MAX_TABLE_ROWS = 30;

function fmtTime(value) {
  if (!value) return '-';
  return String(value).replace('T', ' ').slice(0, 16);
}

function row(cells) {
  return cells.map((cell) => (cell === null || cell === undefined || cell === '' ? '-' : String(cell))).join(' | ');
}

function oneLine(text, limit) {
  return truncate(String(text || '').replace(/\s+/g, ' ').trim(), limit);
}

/** Plain-text tables: 时间 | 来源 | 状态 | 标题, with the URL on its own line. */
function renderResult(_args, value) {
  const d = value.data || {};
  const cmd = value.command;
  const lines = [`机会雷达 · ${cmd} · ${String(value.state).toUpperCase()}`];

  if (cmd === 'radar_status') {
    lines.push(`paid_api_enabled=${d.paid_api_enabled} requests_today=${d.requests_today} reserved_usd=${d.reserved_cost_usd} actual_usd=${d.actual_cost_usd == null ? '-' : d.actual_cost_usd}`);
    const auths = Array.isArray(d.authorizations) ? d.authorizations : [];
    if (auths.length) {
      const enabled = auths.filter((entry) => entry && entry.enabled);
      const remaining = enabled.reduce((sum, entry) => sum + (Number(entry.remaining_cost_usd) || 0), 0);
      lines.push(`授权 ${auths.length} 条（启用 ${enabled.length}），剩余额度合计 $${remaining.toFixed(2)}`);
    }
    if (d.account_remaining_requests != null) lines.push(`账号剩余请求 ${d.account_remaining_requests}`);
  } else if (cmd === 'radar_search') {
    lines.push(`查询「${d.query || '-'}」 · 平台 ${(d.sources || []).join(',') || '-'} · 窗口 ${d.hours}h`);
    lines.push(`雷达 ${d.radar_name || '-'}（${d.radar_id || '-'}） · 运行 ${d.run_status || '-'}${d.timed_out ? '（等待超时，仍在后台跑）' : ''}`);
    const stats = d.stats || {};
    lines.push(`采集 ${stats.items_found == null ? '-' : stats.items_found} · 分析 ${stats.analyzed == null ? '-' : stats.analyzed} · 返回 ${(d.items || []).length} 条`);
    for (const entry of (Array.isArray(d.source_stats) ? d.source_stats : [])) {
      lines.push(`  ${entry.source}: 请求 ${entry.requests} 返回 ${entry.returned} 入库 ${entry.ingested}${(entry.errors || []).length ? ` 错误 ${entry.errors.join(',')}` : ''}`);
    }
    if (d.run_error) lines.push(`运行错误: ${d.run_error}`);
    lines.push('');
    lines.push(row(['时间(上海)', '来源', '状态', '标题']));
    for (const item of (d.items || []).slice(0, MAX_TABLE_ROWS)) {
      const match = item.match || {};
      lines.push(row([fmtTime(item.published_at_shanghai || item.published_at), item.source, match.status || '-', oneLine(item.title, 40)]));
      if (item.url) lines.push(`    ${item.url}`);
    }
    if ((d.items || []).length > MAX_TABLE_ROWS) lines.push(`… 另有 ${(d.items || []).length - MAX_TABLE_ROWS} 条，用 limit 调整`);
  } else if (cmd === 'radar_results') {
    const items = Array.isArray(d.items) ? d.items : [];
    const page = d.page || {};
    lines.push(`结果 ${items.length} 条${page.has_more ? '（还有更多，用 offset 翻页）' : ''}`);
    lines.push(row(['时间(上海)', '来源', '状态', '标题']));
    for (const item of items.slice(0, MAX_TABLE_ROWS)) {
      const match = item.match || {};
      lines.push(row([fmtTime(item.published_at_shanghai || item.published_at), item.source, match.status || '-', oneLine(item.title, 40)]));
      if (item.url) lines.push(`    ${item.url}`);
    }
  } else if (cmd === 'radar_list') {
    const items = Array.isArray(d.items) ? d.items : [];
    const page = d.page || {};
    lines.push(`雷达 ${items.length} 条${page.total == null ? '' : ` / 共 ${page.total}`}${page.has_more ? '（还有更多）' : ''}`);
    lines.push(row(['状态', '名称', '关键词', '平台', '最近运行']));
    for (const item of items.slice(0, MAX_TABLE_ROWS)) {
      lines.push(row([
        item.status || '-',
        oneLine(item.name, 20),
        oneLine((item.keywords || []).join('、'), 20),
        oneLine((item.sources || []).join(','), 24),
        fmtTime(item.last_run_at_shanghai || item.last_run_at),
      ]));
    }
  } else if (cmd === 'radar_sources') {
    const items = Array.isArray(d.items) ? d.items : [];
    const available = items.filter((item) => item && item.available).length;
    lines.push(`平台 ${items.length} 个，可用 ${available} 个`);
    lines.push(row(['可用', '平台', '单价', '状态']));
    for (const item of items.slice(0, MAX_TABLE_ROWS)) {
      lines.push(row([item.available ? 'Y' : 'N', item.id, item.price_usd == null ? '-' : item.price_usd, oneLine(item.status, 26)]));
    }
    if (items.length > MAX_TABLE_ROWS) lines.push(`… 另有 ${items.length - MAX_TABLE_ROWS} 个平台`);
  } else if (cmd === 'radar_provider_diagnose') {
    const tally = d.tally || {};
    lines.push(`平台 ${tally.total == null ? '-' : tally.total}：可用 ${tally.ready || 0} · 缺 key ${tally.missing_key || 0} · 缺单价 ${tally.missing_price || 0} · 其他 ${tally.other || 0}`);
    if ((d.ready || []).length) lines.push(`可用: ${(d.ready || []).map((x) => `${x.id}${x.price_usd == null ? '' : `( $${x.price_usd} )`}`).join(', ')}`);
    if ((d.missing_price || []).length) lines.push(`缺单价核验: ${(d.missing_price || []).map((x) => x.id).join(', ')}`);
    if ((d.missing_key || []).length) lines.push(`缺 key: ${(d.missing_key || []).map((x) => x.id).join(', ')}`);
    if ((d.other || []).length) lines.push(`其他不可用: ${(d.other || []).map((x) => `${x.id}[${x.status}]`).join(', ')}`);
    if ((d.missing_price || []).length) {
      lines.push(`查价: ${d.where}`);
      lines.push(`规则: ${d.quote_rule}`);
      lines.push(`做法: ${d.how}`);
    }
  } else if (cmd === 'radar_runs') {
    const items = Array.isArray(d.items) ? d.items : [];
    lines.push(`运行 ${items.length} 条`);
    lines.push(row(['时间(上海)', '状态', '雷达', '错误']));
    for (const item of items.slice(0, MAX_TABLE_ROWS)) {
      lines.push(row([fmtTime(item.started_at_shanghai || item.started_at), item.status || '-', oneLine(item.radar_id, 12), oneLine(item.error_message, 28)]));
    }
  } else if (cmd === 'radar_run_detail') {
    const run = d.run || d;
    lines.push(`运行 ${run.id || '-'} · ${run.status || '-'} · 雷达 ${run.radar_id || '-'}`);
    lines.push(`开始 ${fmtTime(run.started_at_shanghai || run.started_at)} · 结束 ${fmtTime(run.finished_at_shanghai || run.finished_at)}`);
    if (run.error_message) lines.push(`错误: ${run.error_message}`);
    lines.push(`stats: ${truncate(JSON.stringify(run.stats || {}), 300)}`);
    for (const entry of (((run.stage_stats || {}).source_stats) || [])) {
      lines.push(`  ${entry.source}: 请求 ${entry.requests} 返回 ${entry.returned} 入库 ${entry.ingested}${(entry.errors || []).length ? ` 错误 ${entry.errors.join(',')}` : ''}`);
    }
  } else {
    const json = JSON.stringify(d);
    if (json && json !== '{}') lines.push(`data: ${truncate(json, 1200)}`);
  }

  if (d.note) lines.push(`注意: ${d.note}`);
  if (value.error?.code) lines.push(`错误[${value.error.code}] ${value.error.message}`);
  if (value.request_id) lines.push(`request_id: ${value.request_id}`);
  lines.push(`提示: ${value.hint}`);
  return [{ type: 'text', text: lines.join('\n') }];
}

function signalFrom(exec) {
  const signal = exec?.signal;
  return typeof AbortSignal !== 'undefined' && signal instanceof AbortSignal ? signal : undefined;
}

const STRING = { type: 'string' };
const INTEGER = { type: 'integer' };

function pageArgs(a, defaultLimit = 20) {
  const limit = Number.isFinite(Number(a.limit)) ? Math.min(100, Math.max(1, Number(a.limit))) : defaultLimit;
  const offset = Number.isFinite(Number(a.offset)) ? Math.max(0, Number(a.offset)) : 0;
  return { limit, offset };
}

const TOOL_DEFS = [
  {
    name: 'radar_status',
    description: 'Check the local Opportunity Radar service: probe the API /ready and UI loopback ports, verify the CLI, private config and agent token files, and (when ready) return the billing/ledger status. Distinguishes an offline service from a degraded one whose PostgreSQL/Redis dependency is down. Read-only; never prints the token.',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    buildArgs: () => ['status'],
  },
  {
    name: 'radar_search',
    description: 'One-call keyword search: creates a plain-mode radar (no buyer-intent term filter), runs it once, waits for completion, then returns the newest items with publish time, source and URL. PAID — requires confirm=true; each run is capped by the provider budget (default $0.10). The radar is kept so history and cross-run dedupe keep working.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['query', 'confirm'],
      properties: {
        query: { ...STRING, description: 'Search keyword, 1–100 characters.' },
        confirm: { type: 'boolean', description: 'Must be true: acknowledges one real paid collection run.' },
        sources: { type: 'array', items: { type: 'string' }, description: 'Platform ids (default ["xiaohongshu"]); check radar_sources for availability.' },
        hours: { ...INTEGER, enum: [24, 72, 168, 720], description: 'Freshness window in hours (default 168).' },
        limit: { ...INTEGER, description: 'Items to return, 1-50 (default 10).' },
        waitMs: { ...INTEGER, description: 'How long to wait for the run, 5000-90000 ms (default 45000). Returns run_status=running if it expires.' },
        name: { ...STRING, description: 'Radar name (default 「搜索：<query>」).' },
      },
    },
    run: runSearch,
  },
  {
    name: 'radar_sources',
    description: 'List the Opportunity Radar platform catalog: id, name, availability, unit price and status for every platform in the catalog. Read-only.',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    buildArgs: () => ['sources'],
  },
  {
    name: 'radar_list',
    description: 'List saved Opportunity Radar radars with paging (id, name, keywords, platforms, status, counts), or read one radar by id. Read-only. Use this first to discover a radar_id for radar_results.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        limit: { ...INTEGER, description: 'Page size, 1-100 (default 20).' },
        offset: { ...INTEGER, description: 'Offset (default 0).' },
        radar_id: { ...STRING, description: 'Return only this radar instead of the page.' },
      },
    },
    httpPath: (a) => {
      if (a.radar_id) return `/api/agent/radars/${encodeURIComponent(String(a.radar_id))}`;
      const { limit, offset } = pageArgs(a);
      return `/api/agent/radars?limit=${limit}&offset=${offset}`;
    },
  },
  {
    name: 'radar_results',
    description: 'Read results for one Opportunity Radar radar: strict/pending/mismatch/hiring_signal matches with evidence, source, publish time and original URL. Read-only. Prefer status=strict and a small limit first; long raw_text is truncated and the full text is at url.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['radar_id'],
      properties: {
        radar_id: { ...STRING, description: 'Radar id to read results for.' },
        limit: { ...INTEGER, description: 'Page size, 1-100 (default 20).' },
        offset: { ...INTEGER, description: 'Result offset (default 0).' },
        status: { type: 'string', enum: ['strict', 'pending', 'mismatch', 'hiring_signal'], description: 'Only this match classification.' },
      },
    },
    buildArgs: (a) => {
      const { limit, offset } = pageArgs(a);
      return [
        'results', String(a.radar_id),
        '--limit', String(limit), '--offset', String(offset),
        ...(a.status ? ['--status', String(a.status)] : []),
      ];
    },
    // `scripts/or results --status` only accepts strict|pending|mismatch, while
    // the API also serves hiring_signal. Route just that one value over HTTP so
    // the capability stays available instead of failing in argparse.
    httpPath: (a) => {
      if (String(a.status || '') !== 'hiring_signal') return undefined;
      const { limit, offset } = pageArgs(a);
      return `/api/agent/radars/${encodeURIComponent(String(a.radar_id))}/results`
        + `?status=hiring_signal&limit=${limit}&offset=${offset}`;
    },
  },
  {
    name: 'radar_runs',
    description: 'List recent Opportunity Radar runs with status, start time, items found and radar id. Read-only.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        limit: { ...INTEGER, description: 'Number of runs, 1-100 (default 20).' },
        radar_id: { ...STRING, description: 'Only runs belonging to this radar id.' },
      },
    },
    buildArgs: (a) => {
      const { limit } = pageArgs(a);
      return ['runs', '--limit', String(limit), ...(a.radar_id ? ['--radar', String(a.radar_id)] : [])];
    },
  },
  {
    name: 'radar_run_detail',
    description: 'Read one run by id: status, timestamps, stats, and per-source request/returned/ingested counts with collector errors. Read-only. Use it when a run is partial or failed.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['run_id'],
      properties: {
        run_id: { ...STRING, description: 'Run id from radar_runs or radar_search.' },
      },
    },
    httpPath: (a) => `/api/agent/runs/${encodeURIComponent(String(a.run_id || ''))}`,
  },
  {
    name: 'radar_provider_diagnose',
    description: 'Explain why paid platforms are unavailable: which are ready, which lack an agent key, and which lack a verified endpoint price (fail-closed). Read-only; returns the quote rule and where to check prices.',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    run: runDiagnose,
  },
  {
    name: 'radar_identity',
    description: 'Read the local Opportunity Radar personal identity/profile settings. Read-only; never writes them.',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    buildArgs: () => ['identity'],
  },
  {
    name: 'radar_token_status',
    description: 'Report only the masked agent-token status and whether it validates against the local API. Never prints the token in plaintext.',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    buildArgs: () => ['token'],
  },
];

function makeResult(command, s, checks, r, state, durationMs) {
  return {
    ok: r.ok,
    state,
    command,
    exit_code: r.exit_code,
    http_status: r.http_status,
    request_id: r.request_id,
    api_base: r.api_base,
    repo: s.repo,
    data: compactFor(command, r.data),
    error: { code: r.error.code, message: r.error.message },
    hint: command === 'radar_search' ? searchHint(r) : hintFor(state, s, checks, r),
    duration_ms: durationMs,
    checks,
  };
}

function errorResult(command, s, error, durationMs) {
  return {
    ok: false,
    state: 'misconfigured',
    command,
    exit_code: -1,
    http_status: 0,
    request_id: '',
    api_base: `http://127.0.0.1:${s.apiPort}`,
    repo: s.repo,
    data: {},
    error: { code: 'PLUGIN_ERROR', message: String(error?.message || error).slice(0, 500) },
    hint: `插件内部错误，请检查 bundle 目录与配置。${hintFor('misconfigured', s, {
      script: true, localEnv: true, runtimeEnv: true, agentToken: true, apiReachable: false, apiReady: false, apiStatus: 0, uiReachable: false, uiStatus: 0,
    }, { error: { code: '' } })}`,
    duration_ms: durationMs,
    checks: {},
  };
}

function makeSkillProvider() {
  return {
    name: PROVIDER_NAME,
    list: () => Promise.resolve([CANDIDATE]),
    async get() {
      return {
        name: SKILL_NAME,
        description: SKILL_DESCRIPTION,
        invocation: CANDIDATE.invocation,
        provider: PROVIDER_NAME,
        source: 'bundled',
        resourceBase: RESOURCE_BASE,
        content: await readFile(SKILL_BODY_URL, 'utf8'),
      };
    },
  };
}

/** Register the read-only tools and the bundled skill on the Host context. */
export function apply(ctx, config) {
  const s = settingsFrom(config);
  ctx.skills.registerProvider(() => makeSkillProvider());

  for (const def of TOOL_DEFS) {
    ctx.tools.register({
      name: def.name,
      description: def.description,
      parameters: def.parameters,
      output: { schema: RESULT_SCHEMA, render: renderResult },
      async execute(args, exec) {
        const started = Date.now();
        const a = args || {};
        try {
          const checks = await gatherChecks(s);
          const httpPath = typeof def.httpPath === 'function' ? def.httpPath(a) : undefined;
          let result;
          if (typeof def.run === 'function') {
            result = await def.run(s, a, exec);
          } else if (httpPath) {
            result = await callAgentApi(s, httpPath, signalFrom(exec));
          } else {
            result = await runOr(s, def.buildArgs(a), signalFrom(exec));
          }
          return makeResult(def.name, s, checks, result, classify(result, checks), Date.now() - started);
        } catch (error) {
          return errorResult(def.name, s, error, Date.now() - started);
        }
      },
    });
  }
}
