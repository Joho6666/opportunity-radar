# Agent 接口与命令行（Local Edition）

本机版给 **agent 与人** 提供两个等价入口：HTTP API（`/api/agent/*`，Bearer 令牌鉴权）与
命令行 `scripts/or`（自动读取本机令牌）。两者只绑定 loopback，与网页工作台共用同一份
抓单、计费与账本数据；人在页面上做的任何操作与 agent 调用互相可见。

安全边界（先读）：

- 仅 `APP_ENV=local` 且请求直连 `127.0.0.1` / `localhost` 时可用；带 `x-forwarded-*`、
  错误 Host、非 loopback 客户端一律 403。
- 鉴权只认 `Authorization: Bearer <Agent 令牌>`。**不带令牌、错令牌一律 401，绝不回退网页会话或
  cookie**（避免 CSRF 协同攻击）。网页的 `/api/local/*` 与 `/api/agent/*` 是两套完全隔离开关。
- 写操作必须携带 `Idempotency-Key`（8–200 位），同一键重放复用首次响应，不会重复建单、重复扣费。
- 付费运行必须显式 `{"confirm": true}`，仍走既有计费网关（预留 + 账本 + 每雷达授权行），
  预算沿用设置页配置（默认单轮 ≤ USD 0.10、每日 ≤ USD 1 / 20 请求）；授权行固定
  `allow_scheduled=false`，**不开放自动定时付费调度**。
- 不开放：发私信/评论/关注、绕过计费、修改密钥或会话、读取密钥明文、修改数据库配置。
- 令牌只存于本机私密配置（目录 700 / 文件 600），页面与任何 API 只显示掩码；
  明文仅在“生成/重置”响应中出现一次，需立即复制，且不写入日志。

## 快速开始

1. 打开 `http://localhost:3004/settings` → 「Agent 接入」→ 点「生成令牌」，复制一次性明文
   （或直接用 CLI 的 `token` 子命令查看掩码与有效性）。令牌保存在
   `~/Library/Application Support/Opportunity Radar/config/agent-token.json`（0600），
   生成/重置/吊销立即生效，无需重启服务。
2. 用命令行验证（自动读取上面的令牌文件）：

```bash
scripts/or sources                    # 平台目录与状态
scripts/or status                     # 预算与账本（只读）
scripts/or key test                   # TikHub 官方免费端点连通性（不采集内容）
```

3. 也可直接 curl（仅限本机）：

```bash
curl -H "Authorization: Bearer <令牌>" http://127.0.0.1:8015/api/agent/sources
```

前缀省略时也可走 UI 端口（透传，同样是 Bearer、同样不回退 cookie）：
`http://localhost:3004/api/agent/sources`。

## 典型工作流（agent 抓单）

```bash
# 1) 建单：小红书 · 关键词「电商 视频 外包」（含空格视为一个关键词）· 最近 7 天 · 远程优先
scripts/or new --name "agent链路验证" --business video \
  --keywords "电商 视频 外包" --sources xiaohongshu --hours 168 --match-mode remote

# 2) 运行一轮（必须 --confirm；会按已核验单价真实付费，受预算上限约束）
scripts/or run <雷达ID> --confirm

# 3) 读结果（严格匹配 / 待确认 / 不匹配 + 证据 + 原文链接 + 发布时间）
scripts/or results <雷达ID> --status strict --limit 20
scripts/or results <雷达ID> --json          # 给 agent 解析

# 4) 查看运行与预算
scripts/or runs --radar <雷达ID>
scripts/or status
```

`--json` 输出固定信封，便于机器解析：

```json
{"ok": true, "http_status": 200, "request_id": "...", "api_base": "http://127.0.0.1:8015", "data": { ... }}
```

失败时同样输出 JSON（`ok=false` 且带 `error.code` / `error.message`），退出码仍然有效。

## 端点表（前缀 `/api/agent`）

| 方法 | 路径 | 说明 | 写操作幂等键 |
| --- | --- | --- | --- |
| GET | `/sources` | 平台目录与状态（含已实测标记、单价、能力） | — |
| GET | `/identity` | 个人身份设定（业务/角色/地区/时效/关键词/排除词） | — |
| PUT | `/identity` | 覆盖身份设定 | 需要 |
| GET | `/radars?limit=&offset=` | 雷达列表（新→旧，`limit` 默认 20 / 最大 100） | — |
| POST | `/radars` | 新建抓单雷达（自动补齐身份默认值） | 需要 |
| GET | `/radars/{id}` | 单个雷达 | — |
| POST | `/radars/{id}/run` | 手动运行一轮，请求体必须 `{"confirm": true}` | 需要 |
| GET | `/radars/{id}/results?status=&limit=&offset=` | 结果：严格/待确认/不匹配 + 证据 + 原文链接 + 发布时间 | — |
| GET | `/runs?radar_id=&limit=` | 最近运行 | — |
| GET | `/runs/{run_id}` | 运行明细（阶段统计、错误、时间） | — |
| GET | `/billing/status` | 预算、今日账本、剩余额度（只读） | — |
| POST | `/provider/test` | TikHub 官方免费端点连通性（不采集、只回掩码） | 需要 |

返回约定：

- 时间统一 ISO8601 UTC（`Z`），并同时给出 `*_shanghai` 上海时间字段（如
  `published_at` / `published_at_shanghai`）。
- 分页统一 `limit`（默认 20 / 最大 100）+ `offset`，响应带 `page.{limit,offset,count,has_more,next_offset}`。
- 结果排序固定：`相关度 DESC → 发现时间 DESC → 证据 id ASC`，翻页稳定不重复。
- 错误统一 `{"error": {"code": "<英文 CODE>", "message": "<中文说明>"}}`。

### 结果字段（`/radars/{id}/results` 的 items[]）

```json
{
  "evidence_id": "…",
  "source": "xiaohongshu",
  "title": "原文标题（如解析得到）",
  "url": "https://…",                        // 原文链接
  "published_at": "2026-10-15T03:00:00Z",     // 原帖发布时间（UTC）
  "published_at_shanghai": "2026-10-15T11:00:00+08:00",
  "captured_at": "…", "captured_at_shanghai": "…",
  "raw_text": "完整正文（证据原文）",
  "match": {
    "status": "strict|pending|mismatch",       // 匹配分类
    "label": "严格匹配|待确认|不匹配",
    "score": 92,
    "evidence": {"业务": "电商", "买方需求": "…"},   // 字段级原文证据
    "missing": ["需求地区"], "conflicts": ["正文未命中业务匹配词"],
    "evidence_level": "完整正文（规则核验）",
    "match_mode": "remote",
    "hunt_match": { …原始规则判定对象… }
  }
}
```

## 鉴权与常见错误码

| HTTP | code | 含义 / 处理 |
| --- | --- | --- |
| 401 | `AGENT_TOKEN_REQUIRED` | 没带 Bearer；到设置页生成并附带 |
| 401 | `AGENT_TOKEN_INVALID` | 令牌错/已吊销；重新生成 |
| 403 | `AGENT_LOCAL_ONLY` | 非 loopback、Host 不匹配或带转发头；直连本机不要走代理 |
| 403 | `AGENT_API_LOCAL_ONLY` | 非本机版（云端）不存在该接口 |
| 400 | `IDEMPOTENCY_KEY_REQUIRED` | 写操作缺 `Idempotency-Key` |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 同一把幂等键换了请求内容；换新键 |
| 400 | `CONFIRM_REQUIRED` | 运行未显式 `{"confirm": true}` |
| 422 | `VALIDATION_ERROR` | 参数非法（含 limit 越界 1–100） |
| 429 | `PAID_QUOTA_EXHAUSTED` 等 | 预算/配额拒绝；看 `/billing/status`（不重试、不加价） |
| 409 | `BILLING_PERSISTENCE_REQUIRED` | 内存存储禁止付费 |

### CLI 退出码

`0` 成功 · `1` 其他错误（网络/服务不可用）· `2` 参数错误 · `3` 未鉴权 · `4` 受限被拒（预算、确认、限流、幂等冲突）。

## 幂等与重试

- CLI 每次写操作自动生成新的 `Idempotency-Key`；agent 需要自己重试时，**用同一个键**重发，
  服务端返回首次响应（响应头 `Idempotency-Replayed: true`），不会产生第二次运行或第二次扣费。
- 键存在 PostgreSQL 表 `agent_idempotency`；键 + 请求内容指纹绑定，内容变了会 409，防止把两个请求混为一次。
- 运行派发本身也有雷达级互斥：同一雷达已有 `queued/running` 运行时再次触发会复用该运行。

## 常见坑

- **含空格的关键词**：CLI 的 `--keywords` 按逗号/、拆分（不按空格），`电商 视频 外包` 是一个关键词、
  一次首屏请求；写成 `a,b,c` 才是 3 个关键词 × 平台数，受 6 次首屏请求上限约束。
- **CLI 默认连 `127.0.0.1:8015`**（读本机私密配置的 `LOCAL_API_PORT`）；只有显式 `--api-base` 才改地址。
  请勿把 8015/3004 端口转发到公网——接口虽然要令牌，仍以“只在本机”为设计前提。
- **付费运行前**先 `scripts/or key test` 与 `scripts/or status` 确认密钥与剩余额度；
  运行后 `scripts/or runs` 看 `stats`，用 `/billing/status` 核对预留金额，不要凭界面猜测花费。
- **运行是异步的**：`run` 返回 202 + run id，采集在后台 worker 完成；轮询 `runs/{id}` 或
  `results` 即可，不要重复触发同一轮。
- 令牌明文**只出现一次**；页面不会把它写进浏览器存储。丢了就重置（旧令牌立即失效，
  使用旧令牌的 agent 需要更新）。
- 需要自动化“无人值守”的定时付费采集时，本接口**不提供**；请保持人工点击/人工确认的边界。

## 验证记录

本接口随 `feat/local-edition` 提供：后端契约测试 `backend/tests/test_agent_api.py`、
CLI 测试 `backend/tests/test_or_cli.py`（离线）、前端 `tests/local-agent.test.ts` 与
`tests/agent-proxy.test.ts`。真实付费端到端验收（建单 → 运行 → 读结果）记录见
[LOCAL_EDITION_RUNBOOK.md](LOCAL_EDITION_RUNBOOK.md) 的「Agent 接口」一节。

## 首次真实验收（2026-10-16）

在真实本机实例上执行（1 次付费首屏请求，USD 0.01）：

| 项目 | 值 |
| --- | --- |
| 雷达 | `agent链路验证` · id `23fb8040-7a46-4597-ab5d-68b91501f04b`（小红书 · 关键词「电商 视频 外包」· 最近 168 小时 · 远程优先） |
| 运行 | run id `be6fdbc7-ac01-4ecf-bf77-81b5d27c20f4` · completed · 1 查询 / 20 条命中 / 14 条通过时效过滤 |
| 计费 | 预留下单 `reserved_micros=10000`（USD 0.01，与官方核验单价一致）· `status=succeeded` · `scheduled=false` |
| Provider | `/api/v1/xiaohongshu/app_v2/search_notes` · HTTP 200 · TikHub 官方 `request_id=179a9662-b593-482f-8a54-7a6f6dc39fb4` |
| 结果 | 3 条（全部「待确认」，证据字段命中业务词、缺买方采购意图原文）含原文链接与 UTC / 上海双时间 |
| 幂等 | 同键重放返回 `Idempotency-Replayed: true` 与同一 radar id；同键改内容 → 409 |
| 鉴权 | 无令牌 401、错令牌 401、网页会话 cookie 无令牌 401、带转发头 403、跨站 Origin 403（均实测） |

验收雷达保留在库中供页面查看（未删除）；测试期间的临时雷达已用人工会话路径清理。

