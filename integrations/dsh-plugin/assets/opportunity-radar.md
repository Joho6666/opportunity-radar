---
name: opportunity-radar
description: Query the local Opportunity Radar workbench from DeepSeek Harness — service health, radar list and platform catalog, radar results, runs, billing and identity, plus how to open its board in the Harness right Sidebar. Use when the user asks about 机会雷达、抓单、线索、雷达结果、看板、可视化、本机服务是否还在 or wants to work with Opportunity Radar data.
---

# 机会雷达（DeepSeek Harness 只读接入）

「机会雷达」是本机独立的 Local Edition 工作台（Next.js + FastAPI + PostgreSQL/Redis），
**不是**这个插件自带的进程。本技能通过 `@local/opportunity-radar` bundle 提供的
**9 个只读工具 + 1 个付费搜索工具**工作：多数代理仓库里的 `scripts/or` CLI，
`radar_list` / `radar_run_detail` / `radar_provider_diagnose` 直接调用后端只读接口
（CLI 没有对应子命令），`radar_search` 走写接口建雷达+跑一轮。鉴权都用同一份 loopback
令牌且绝不输出。仓库：

```
/Users/joho/Documents/Codex/2026-10-13/opportunity-radar-ai-agent-github-https/work/opportunity-radar
```

工具与 CLI 共享同一份数据；页面（设置 / 雷达 / 情报 Inbox）看到的就是这里读到的东西。

## 可视化看板

插件在输入框下方停靠区放了一个「机会雷达看板」按钮。点击后，Harness 自带的右侧栏
Browser tab 会打开 `http://localhost:3004`，**完整 Next.js 工作台原样呈现**（雷达列表、
情报 Inbox、图表、设置页），可与当前会话并排查看。

- 用户说「打开看板 / 在 Harness 里看看 / 可视化」时，指引他点这个按钮；本技能的工具只返回
  JSON，不要试图用文本描述代替界面。
- **侧栏能否显示取决于 Harness 的访问主机名**：必须用 `http://localhost:<当前端口>` 打开
  Harness。用 `http://127.0.0.1:<当前端口>` 时 iframe 属于 cross-site，会被 3004 的 middleware
  返回 403「Local Edition only accepts direct loopback requests.」；此时请用旁边的「↗ 新窗口」
  按钮，或让用户把地址里的 `127.0.0.1` 改成 `localhost` 后刷新。插件只在 `localhost` 环境
  自动弹出侧栏，在 127.0.0.1 环境会跳过以免弹出 403 页面。
- 看板是独立的本机网页，主题 / 深浅色不跟随 Harness，这是复用现成应用的正常取舍。
- 看板要能加载，前提是 Local Edition 服务在线（见下文当前状态）；离线时先用 `radar_status`。
- 看板里的写操作（新建雷达、运行采集、保存 TikHub key）由用户在界面上自己完成，
  本技能与插件工具都不代做。

## 何时使用

- 用户问「机会雷达还在吗 / 服务起来没 / 今天有什么新线索 / 某个雷达的结果」。
- 用户要挑平台、看预算账本、看最近运行、看个人身份设定。
- 不适用于云端版；不适用于自动定时付费采集（该能力被有意关闭）。

## 工具

| 工具 | 作用 | 对应接口 |
|---|---|---|
| `radar_status` | **先调它**。探测 8015 的 `/ready` 与 3004、检查 `scripts/or`、私有配置与令牌文件是否齐全；就绪时返回预算账本 | `or status --json` |
| `radar_search` | **一次调用完成「搜索」**：建普通模式雷达 → 跑一轮 → 等到结束 → 返回结果。付费，必须 `confirm: true` | `POST /radars` + `/run` |
| `radar_sources` | 平台目录：可用 / 已实测 / 单价 / 状态（保留全部平台，省略端点与能力明细） | `or sources --json` |
| `radar_list` | **雷达列表**（`limit`/`offset` 分页，或传 `radar_id` 读单个）：拿 `radar_id` 的正规入口。列表只给名称/状态/关键词/平台/时间等字段，单条才带完整 `source_config` | `GET /api/agent/radars` |
| `radar_results` | 某雷达的结果（`strict` / `pending` / `mismatch` / `hiring_signal` + 证据 + 原文链接 + 发布时间） | `or results <id> --json` |
| `radar_runs` | 最近运行列表与阶段统计 | `or runs --json` |
| `radar_run_detail` | **单次运行详情**：状态、时间、`stats`、逐源 `requests/returned/ingested` 与采集错误 | `GET /api/agent/runs/{id}` |
| `radar_provider_diagnose` | **付费平台为什么不可用**：可用 / 缺 key / 缺单价核验的清单，附查价页与写入规则 | `GET /api/agent/sources` |
| `radar_identity` | 读取个人身份设定（不写入） | `or identity --json` |
| `radar_token_status` | 令牌掩码与有效性（**绝不显示明文**） | `or token --json` |

`radar_search` 是唯一会花钱的工具：它必须显式 `confirm: true`，单次花费受 provider 配置上限
约束（默认 $0.10），并会**保留**新建的雷达（agent 接口没有删除入口，删雷达只能去界面）。
它建的是普通模式雷达（`required_terms` 为空），因为 CLI 的 `or new` 会写死 `lead_hunt` 与
业务必需词（视频/电商/带货…），那会把「单片机毕设」这类内容帖全过滤掉。

每个工具都返回 `state`：`online` / `degraded` / `offline` / `misconfigured`，以及 `checks`、
`error.code`、`data` 和一段可执行的 `hint`。**先把 `state` 和 `hint` 如实告诉用户，不要把离线包装成"没有数据"。**
`degraded` 表示 API 进程在、但后台依赖（PostgreSQL 54330 / Redis 6380）没起来 —— 最常见的原因是
Docker Desktop 重启后容器没自启，**不是**配置或令牌问题，别让用户去重新生成令牌。
参数被拒（如 `CONFIRM_REQUIRED`、`RADAR_NOT_FOUND`）仍然是 `online`：服务是好的，是这次请求不合法。

## 安全红线（必须遵守）

- **付费运行只能由用户明确确认触发**：终端 `or run` 必须带 `--confirm`；插件里唯一会花钱的是
  `radar_search`，它必须收到 `confirm: true`，且单次花费受 provider 上限约束。除此之外本插件
  **不暴露** `key` / 预算修改 / 删雷达 / 改身份等写操作。不要为了跑通而改预算、放开调度或绕过计费。
- **不碰密钥明文**：任何时刻不要读取并输出 `provider-config.json`、`agent-token.json`、`local.env` 的内容；令牌只回掩码。令牌丢失让用户去设置页重置，不要写进日志、提交或聊天记录。
- **只连 loopback**：不要用端口转发 / 代理 / 公网地址访问 3004 或 8015。
- **写操作重试必须复用同一 `Idempotency-Key`**，否则会产生第二次运行。本插件不做写操作，这条用于手动执行 CLI 时。
- 不要用「热度」代替「买方证据」： seller 广告、失效/已关闭/不适用记录不应因为互动高就变成线索。
- 用户自定义关键词是权威输入，不要追加合成词破坏 RSS / 搜索运算符。

## 当前状态与离线排障

**2026-11-16 复核**：Local Edition 服务在线（4 个 LaunchAgent + PG16/Redis Compose，
`http://localhost:3004`，API `127.0.0.1:8015/ready` 返回 `{"status":"ready"}`），私有配置与
Agent 令牌均已就位；原数据保住（库 `opportunity_radar_copy`、owner
`00000000-0000-0000-0000-000000000001`，13 个雷达 / 309 条证据）。7 个工具实测 `ONLINE`。

**仍待完成**：TikHub key 未配置（`provider-config.json` 缺失），因此 `radar_sources`
里各平台 `available=false`、`paid_api_enabled=false`。付费采集默认关闭，不要擅自开启；
`run` 必须由用户明确确认后手动执行 `scripts/or run <雷达ID> --confirm`。

### 先分清是「degraded」还是「offline」

`radar_status` 的 `state` 不同，修法完全不同：

- `state=degraded`（`checks.apiStatus=503`，`/ready` 返回 `{"status":"not_ready"}`）：
  API 进程活着但连不上 PostgreSQL/Redis。最常见原因是 **Docker Desktop 重启后容器没起来**
  （报错形如 `connection to server at "127.0.0.1", port 54330 failed: Connection refused`）。
  先 `open -a Docker` 等守护进程就绪，再**只拉起容器**（不必 `local.sh start`，那样会重建 Next）：

  ```bash
  cd /Users/joho/Documents/Codex/2026-10-13/opportunity-radar-ai-agent-github-https/work/opportunity-radar
  docker compose -p opportunity-radar-local -f docker-compose.local.yml \
    --env-file "$HOME/Library/Application Support/Opportunity Radar/config/local.env" \
    up -d --wait postgres redis
  curl -s http://127.0.0.1:8015/ready   # 期望 {"status":"ready","storage":"postgresql"}
  ```

  容器恢复后 API 会自行重连，**不需要**重启 LaunchAgent，也不要重置令牌或重建配置。

- `state=offline`（端口不可达）：LaunchAgent 没跑。用 `LC_ALL=C`（`scripts/local.sh` 在 UTF-8
  locale 下会因中文变量名报 `LOCAL_ENV?: unbound variable`）：

  ```bash
  LC_ALL=C scripts/local.sh status
  LC_ALL=C scripts/local.sh start   # 若提示「服务已注册」，先 stop 再 start
  ```

- `state=misconfigured`：API 可达但配置/鉴权有问题（如 `AGENT_TOKEN_MISSING`）。
  重建私有配置参见仓库 `docs/LOCAL_EDITION_RUNBOOK.md`。**关键**：本机版库名是
  `opportunity_radar_copy`（不是默认的 `opportunity_radar`），且必须沿用原
  `LOCAL_USER_ID`，否则会连到一个空用户、把旧数据「藏起来」；不要复用审计/QA 数据库。

界面规范地址 `http://localhost:3004`（用 `127.0.0.1:3004` 会被 Host 校验拒 403），
API `http://127.0.0.1:8015`。

## 结果判读

- `match.status`：`strict` 所有必要字段有原文证据；`pending` 有缺失（地区未知、只有摘要等）；
  `mismatch` 有冲突（服务推广、时间不符）。这是规则判定，**不是人工确认**，交付时要注明。
- `radar_results` 的 `status=hiring_signal` 走 HTTP（`scripts/or --status` 只接受
  `strict|pending|mismatch`），其余三个值走 CLI；返回结构一致。
- 时间字段成对：`*_at`（UTC）与 `*_at_shanghai`（上海时间）；评论时间不能代替原帖发布时间。
- `results` 的 items 带完整 `raw_text`，条数一多就很大。先 `radar_results` 带小 `limit` 与
  `status: "strict"`，按需 `offset` 翻页；插件会在结果过大时自动截断并提示。
- 一次运行「找到 N 条、只链接 M 条（M≪N）」是正常的：采集过滤器与雷达关联规则会筛掉普通内容。
  判断健康看 `radar_runs` 的 `stage_stats`（collected / after_freshness / collection_filtered）与
  `collector_errors`，别把 M 小当成失败；`collector_errors` 为空也不代表每个平台都有产出。

## 预热顺序

```
radar_status  →  radar_token_status  →  radar_provider_diagnose  →  radar_sources
             →  radar_search（付费，需确认）  →  radar_results / radar_runs / radar_run_detail
```

用户说「帮我找某关键词的最新帖子」时，直接 `radar_search`（默认小红书，1 次请求约 $0.01）；
若报 `SOURCE_NOT_AVAILABLE`，先跑 `radar_provider_diagnose` 看是缺 key 还是缺端点单价核验。

不要靠猜 `radar_id`：先用 `radar_list` 拿列表（`limit`/`offset` 翻页，或传 `radar_id` 读单个），
再用 `radar_results` 读该雷达的结果。

用 `radar_status` 的 `data`（今日请求数 / 已预留与已消费费用 / 账号剩余额度 / 授权条目）做计划，
不要把旧版「20 次本地上限」当成系统事实：本机每日请求硬上限已取消，仍保留每日费用上限与逐次人工确认。
额度不足被拒时如实报告，不重试加价。
