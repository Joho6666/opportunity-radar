# Opportunity Radar Local Edition 使用手册

Local Edition 是 macOS 本机单用户工作台。Next.js、FastAPI、Worker 和 Scheduler 通过用户级 LaunchAgent 运行；PostgreSQL/pgvector 与 Redis 使用独立 Docker Compose Project。`scripts/local.sh start` 会将仓库代码及已安装依赖同步到 `~/Library/Application Support/Opportunity Radar/app`，再从该目录构建和运行，以兼容 macOS 对 `~/Documents` 中代码的后台访问限制。私有配置、日志、配对票据和备份保存在同一 Application Support 目录下。界面与 API 仅绑定 `127.0.0.1`；浏览器的规范地址为 `http://localhost:3004`。默认关闭付费 API、自动 AI、Mock 采集、本地模型和自动数据删除。

## 首次准备

需要 macOS、Node.js 20+、Python 3.12+ 与 Docker Desktop。先使用开发分支，安装依赖并准备私有配置：

```bash
git switch feat/local-edition
npm ci
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

私有配置位于 `~/Library/Application Support/Opportunity Radar/config/local.env`，目录权限应为 `700`，配置文件权限为 `600`。它不进入 Git。当前机器已存在权限合规的 Local Edition 配置；新安装时需要创建该文件，至少提供这些字段：

```text
LOCAL_DB_PASSWORD=<strong random password>
LOCAL_PROXY_TOKEN=<64 or more random characters>
LOCAL_SESSION_SECRET=<64 or more random characters>
LOCAL_USER_ID=<the UUID belonging to the isolated local database owner>
LOCAL_PG_PORT=54330
LOCAL_REDIS_PORT=6380
LOCAL_API_PORT=8015
LOCAL_UI_PORT=3004
LOCAL_DATABASE_URL=postgresql+psycopg://postgres:<url-encoded-password>@127.0.0.1:54330/opportunity_radar
LOCAL_REDIS_URL=redis://127.0.0.1:6380/0
```

`LOCAL_DB_PASSWORD` 必须与 `LOCAL_DATABASE_URL` 中 URL 编码后的密码一致。恢复已有备份时，沿用同一备份配套的 `LOCAL_USER_ID`，避免把另一用户的数据暴露到工作台。不要复用审计/开发数据库；Local Edition 应连接已从备份恢复的独立本地库。启动脚本会拒绝远程数据库地址、弱凭据、内存存储、`AUTH_DISABLED=true`、付费/自动 AI/Mock/自动删除配置。

## 启动、停止和查看状态

在仓库根目录执行：

```bash
scripts/local.sh start
scripts/local.sh status
```

打开 `http://localhost:3004`。本机版不需要配对：首次访问即自动建立本地会话（无感登录），直接进入工作台；`scripts/local.sh pair` 已退役，只会提示无需配对。不要通过端口转发、共享链接或反向代理暴露该页面。停止后重新启动会再次从当前仓库同步代码与依赖；`app/` 是专用运行副本，不要在其中存放数据库、备份或手工文件。

```bash
scripts/local.sh logs
scripts/local.sh logs api
scripts/local.sh stop
```

`stop` 会卸载 Local Edition 的用户级服务并停止 Local Edition Compose 数据库/Redis；不删除容器卷或业务数据。它不会停止审计、开发或其他 Compose Project。主要端口为 UI 3004、API 8015、PostgreSQL 54330、Redis 6380；端口冲突时脚本会失败，先用 `status`/`lsof` 检查，不要盲目改连其他数据库。

## 备份与恢复

备份保存在 `~/Library/Application Support/Opportunity Radar/backups/`，目录权限为 `700`，备份、清单及配套私有配置权限为 `600`。备份命令先用 `pg_dump` 生成 PostgreSQL 一致性快照，再验证归档可读性：

```bash
scripts/local.sh backup
```

先在 Local Edition 数据库中进行隔离恢复验证。该命令会创建一个新的恢复测试数据库，不覆盖当前数据库：

```bash
scripts/local.sh restore-test "/absolute/path/to/local-<timestamp>.dump"
```

若要从备份切换到恢复出的数据库，先执行 `scripts/local.sh stop`，再用配套的 `local-<timestamp>.env` 恢复对应数据库名和 `LOCAL_USER_ID`。实际恢复到一个**全新数据库名**的示例：

```bash
COMPOSE_PROJECT=opportunity-radar-local
RESTORE_DB=opportunity_radar_restore_20261016
BACKUP="/absolute/path/to/local-<timestamp>.dump"
docker compose -p "$COMPOSE_PROJECT" -f docker-compose.local.yml \
  --env-file "$HOME/Library/Application Support/Opportunity Radar/config/local.env" \
  exec -T postgres createdb -U postgres "$RESTORE_DB"
docker compose -p "$COMPOSE_PROJECT" -f docker-compose.local.yml \
  --env-file "$HOME/Library/Application Support/Opportunity Radar/config/local.env" \
  exec -T postgres pg_restore --exit-on-error --no-owner -U postgres \
  -d "$RESTORE_DB" < "$BACKUP"
```

验证迁移记录、关键表和用户归属后，再将私有 `LOCAL_DATABASE_URL` 的数据库路径切换到新库并重启。保留旧库及原卷直到确认恢复结果；不要对现有数据库执行 `DROP DATABASE`、`docker compose down -v` 或覆盖式恢复。备份含有业务数据与私有配置，应仅保存在本机加密磁盘或受控备份介质。

## Agent 接口与命令行

Agent 与命令行使用独立入口：HTTP `/api/agent/*`（Bearer 令牌）与 `scripts/or`（自动读取本机令牌）。
它与网页会话链路完全隔离——不带令牌一律 401，不回退 cookie；只接受 loopback 直连；写操作要求
`Idempotency-Key`；付费运行必须显式 `--confirm` / `{"confirm": true}`，并沿用设置页的预算与同一套
计费网关（不开放自动定时付费调度）。完整说明见 [Agent 接口文档](AGENT_API.md)。

```bash
# 生成令牌：http://localhost:3004/settings →「Agent 接入」（明文只显示一次）
scripts/or sources                                # 平台目录
scripts/or new --keywords "电商 视频 外包" --sources xiaohongshu --hours 168   # 建单
scripts/or run <雷达ID> --confirm                 # 手动运行一轮（真实付费，受预算限制）
scripts/or results <雷达ID> --json                # 读结果（严格/待确认/不匹配 + 链接 + 时间）
scripts/or status                                 # 预算与账本（只读）
```

令牌保存在 `config/agent-token.json`（目录 700 / 文件 600），生成/重置/吊销即时生效（热加载，无需重启）；
页面与接口只显示掩码，明文仅生成时出现一次且不写日志。直接调用示例：

```bash
curl -H "Authorization: Bearer <令牌>" http://127.0.0.1:8015/api/agent/sources
```

CLI 退出码：`0` 成功 / `1` 其他错误 / `2` 参数错误 / `3` 未鉴权 / `4` 受限被拒。
接口不提供：发私信/评论/关注、绕过计费、修改密钥或会话、读取密钥明文、自动定时付费采集。

## 四个受限平台模式（2026-10-18 实测）

这四个平台不是“全站关键词搜索”，界面与服务端目录都标明了模式、单价、请求ID与限制：

| 平台 | 模式 | 真实请求 | 单价 | 运行方式 |
|---|---|---|---|---|
| 微信视频号 | 搜一搜 video 垂类 + 分享链 | `39e3aaec-…` → `f16cd41b-…` → `5504d38b-…` | 搜索 USD 0.01；每条再加 2 次 × USD 0.01 | 在「微信搜一搜」选「视频号视频」，分享链条数默认 1、最多 3；单条约 30 秒 |
| Telegram | 指定频道内搜索 | `470e7602-…` | USD 0.001/频道 | 填 1–3 个频道用户名；每个频道 1 次请求；未填不能选中 |
| LinkedIn | 招聘信号（潜在客户线索） | `40c9e41e-…` | USD 0.05/次 | 只发 1 次职位搜索；结果不是买方直接需求 |
| 今日头条 | 按链接导入 | `4866abbb-…` | USD 0.001/条 | 粘贴 1–3 条 `/article/<id>/` 链接；不支持关键词搜索 |

- 视频号搜索行只有 `exportId`，必须 `fetch_video_detail` 拿到纯数字 `id`，再调 `fetch_video_share_url`；把 `hashDocID` 直接当 `object_id` 会返回 200 但 `share_url=null`。
- 每个付费请求都经 `HttpFetcher → billing_gateway` 预留/结算；分享链、频道、链接的附加调用都计入成本预估与单轮 10 次硬上限（6 次首屏查询 + 附加）。
- 招聘信号绕过“买方业务词”过滤（否则英文 Video Editor 会因正文没有“电商/广告”被全部丢弃），但仍受排除词约束；Inbox 分类显示「招聘信号」。
- 本机到 `api.tikhub.io` 的 IPv4 TLS 可能被重置，而 IPv6 正常；产品 `PublicNetworkBackend` 取 DNS 首地址（本机为 IPv6）。独立探测脚本若用 httpx 默认解析，需优先 IPv6。

真实响应回放：LinkedIn 应用内运行抓回 25 条、去重后 9 条；修复业务词过滤后用同一真实响应回放，9/9 保留并分类为 `hiring_signal`。

## 使用范围与验收边界

- 首页、雷达、情报 Inbox 和设置是 Local Edition 主入口；云端 CRM、报价与技能路由保留，但不在本地导航中展示。
- 新建雷达默认通用情报、手动运行、零预算。定时任务需显式开启；Local Scheduler 只处理本地用户明确开启的计划。
- 自动采集不加载模型。设置为“按需”后，用户可对单条内容发起分析；付费接口仍需原有授权、精确价格和配额，否则回退规则结果并说明原因。
- 已验证的免费来源流程使用 Hacker News RSS；它证明当前 RSS 适配器与公开源可端到端工作，不代表所有来源都已验证。
- 当前代码通过隔离 QA 完成迁移、API/CSRF/Host、队列、UI 和 Compose 持久化检查。真实 Local 实例的 `start`/`stop`、无配对访问控制、备份与新数据库隔离恢复已通过；macOS 重启后的 LaunchAgent 恢复尚未验证。页面为无感登录：清空 cookie 或换浏览器后直接打开 `http://localhost:3004` 即可进入工作台（2026-10-16 实测 `dashboard=200`，无需配对码）。
- Agent 链路已在真实实例上完成端到端付费验收（1 次请求 / USD 0.01）：建单 → `scripts/or run --confirm` → `scripts/or results --json` 读回 3 条真实小红书结果；run、TikHub 官方 request_id、预留金额与拒绝场景证据见 [Agent 接口文档](AGENT_API.md) 的「首次真实验收」。Ego Browser 截图超时，视觉截图复核缺口保留；性能前后对比和 7 天连续运行也尚未完成。

更完整的风险与测试记录见 [Local Edition 审计](LOCAL_EDITION_AUDIT.md)。
