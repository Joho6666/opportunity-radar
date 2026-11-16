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

const SKILL_DESCRIPTION = 'Query the local Opportunity Radar workbench: check service health, list radars and platforms, read radar results and runs, and inspect billing/identity. Use when the user asks about 机会雷达、抓单、线索、雷达结果、看板、可视化, or wants to know whether the local radar service is running.';

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
 * Read-only GET against the loopback agent API. Used only by `radar_list`,
 * whose endpoint has no `scripts/or` subcommand. Failures never echo the token.
 */
async function callAgentApi(s, pathname, signal) {
  const apiBase = `http://127.0.0.1:${s.apiPort}`;
  const auth = await readAgentToken(s);
  if (auth.error) {
    const message = auth.error === 'AGENT_TOKEN_MISSING'
      ? '缺少 config/agent-token.json；请在本机看板的设置页生成 Agent 令牌。'
      : 'config/agent-token.json 无法解析；请重新生成 Agent 令牌。';
    return { ok: false, exit_code: -1, http_status: 0, request_id: '', api_base: apiBase, data: {}, error: { code: auth.error, message }, stderr: '' };
  }
  try {
    const res = await fetch(`${apiBase}${pathname}`, {
      headers: { authorization: `Bearer ${auth.token}`, accept: 'application/json' },
      signal: signal ?? AbortSignal.timeout(s.timeoutMs),
      redirect: 'manual',
    });
    const parsed = parseJson(await res.text()) ?? {};
    if (res.ok) {
      const payload = parsed && typeof parsed === 'object' ? parsed : {};
      const data = payload.data && typeof payload.data === 'object' ? payload.data : payload;
      return {
        ok: payload.ok !== false,
        exit_code: 0,
        http_status: res.status,
        request_id: String(res.headers.get('x-request-id') || payload.request_id || ''),
        api_base: apiBase,
        data: data && typeof data === 'object' && !Array.isArray(data) ? data : {},
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

  if (Array.isArray(data.items) && command === 'radar_results') {
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

function renderResult(_args, value) {
  const lines = [
    `机会雷达 · ${value.command} · ${String(value.state).toUpperCase()}`,
    `ok=${value.ok} exit=${value.exit_code} http=${value.http_status} request_id=${value.request_id || '-'}`,
    `api_base=${value.api_base} repo=${value.repo}`,
  ];
  const page = value.data && value.data.page;
  if (page && typeof page === 'object') lines.push(`page: ${JSON.stringify(page)}`);
  const items = value.data && value.data.items;
  if (Array.isArray(items)) lines.push(`items: ${items.length}`);
  if (value.data && value.data.note) lines.push(`注意: ${value.data.note}`);
  if (value.error?.code) lines.push(`错误[${value.error.code}] ${value.error.message}`);
  if (value.data && Object.keys(value.data).length) {
    const json = JSON.stringify(value.data);
    lines.push(`data: ${json.slice(0, 3000)}${json.length > 3000 ? ' …（此处显示已截断，完整内容见返回值 data 字段）' : ''}`);
  }
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
    hint: hintFor(state, s, checks, r),
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
          const result = httpPath
            ? await callAgentApi(s, httpPath, signalFrom(exec))
            : await runOr(s, def.buildArgs(a), signalFrom(exec));
          return makeResult(def.name, s, checks, result, classify(result, checks), Date.now() - started);
        } catch (error) {
          return errorResult(def.name, s, error, Date.now() - started);
        }
      },
    });
  }
}
