# Opportunity Radar · 机会雷达

个人优先的公开商机情报与获客工作台。保留 Next.js 15 与 FastAPI：采集 → 证据 → 分类预测 → 人工核实 → Opportunities / Pipeline → 报价与沟通草案 → 人工跟进 → 实际结果反馈。

当前能力和限制：[CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md)；本轮升级：[docs/PRODUCTION_UPGRADE.md](docs/PRODUCTION_UPGRADE.md)；长期方向：[MONEY_INTELLIGENCE_ROADMAP.md](MONEY_INTELLIGENCE_ROADMAP.md)。没有数据时显示暂无数据；任何分类分数均不代表成交概率。

## 本机使用（持久化、付费关闭）

需要 Node 20+、Python 3.12、Docker Compose。所有命令在仓库根目录执行。

```bash
npm ci
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
cp .env.example .env.local
# 不覆盖已有 .env；已有配置请手工合并新增项。
docker compose up -d postgres redis
cd backend
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/opportunity_radar ../.venv/bin/python -m app.database.migrate
AUTH_DISABLED=true USE_IN_MEMORY_STORE=false DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/opportunity_radar REDIS_URL='' ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8011 --no-proxy-headers
```

另一终端：

```bash
NEXT_PUBLIC_USE_MOCK=false NEXT_PUBLIC_AUTH_DISABLED=true npm run dev -- --hostname 127.0.0.1 --port 3000
```

打开 `http://127.0.0.1:3000/dashboard`；API `/docs`、`/health`（进程存活）、`/ready`（数据库/配置的 Redis 可用）。`.env.local` 的 API 地址应对应后端端口。端口已占用时使用独立端口；Compose 可设置 API_PORT、PG_PORT、REDIS_PORT。本机免登录只接受直接 loopback 请求，不适用于 Docker 的宿主访问或反向代理。

个人雷达可使用 PPT / Word 排版 / PDF / 简历 / 论文规范辅导关键词；企业雷达可使用 AI 视频广告 / 商品宣传 / 网站 / 小程序。先用公开 RSS、HN，或 GitHub `issues:` 查询。GitHub Issue/普通讨论通常不是付费客户，必须人工辨别。HN 评论查询使用 `comments:` 前缀。证据收件箱支持五类、修正备注、原文查看、人工核实及转化；Pipeline 编辑服务类型、公开渠道、下次跟进、实际金额/成本/工时、流失原因和草案。

显式演示用 `NEXT_PUBLIC_USE_MOCK=true`；服务端 Mock 另需 `INCLUDE_MOCK_COLLECTOR=true`。应使用独立测试数据库/身份。生产拒绝 Mock。请勿把演示截图或离线模拟成交当成真实业绩。

## Docker / 生产

```bash
cp backend/.env.example backend/.env  # 仅新安装；保留已有配置
# 配置 SUPABASE_JWT_SECRET，并以真实 Supabase 用户 JWT 访问。
API_PORT=8011 docker compose up -d --build
```

Compose 包括 pgvector PostgreSQL、迁移、API、Redis AOF、Arq Worker 和 Scheduler，数据库与 Redis 使用 named volume。服务端口仅监听宿主 loopback，API 禁用代理头信任。Docker 的 API 身份模式必须使用 JWT，AUTH_DISABLED 的宿主请求会被拒绝。生产部署另需真实 Supabase Auth 与前端公开 publishable key，`APP_ENV=production`、`AUTH_DISABLED=false`、`USE_IN_MEMORY_STORE=false`、`INCLUDE_MOCK_COLLECTOR=false`、`ALLOW_FAKE_IP_DNS=false`；服务端 JWT 密钥不进入前端。

生产请替换 Compose 的开发数据库密码、使用专用后台数据库角色、配置 TLS/反向代理和备份。迁移使用数据库管理角色；后台业务查询始终 tenant-scoped。不要运行 `supabase db reset` 或 `docker compose down -v` 删除已有业务数据。

已有数据库如果缺少 schema_migrations 账本，工具会拒绝重放历史。先备份，在隔离副本对照历史迁移和 Supabase 迁移记录逐项审计；只有确认实际已应用文件与当前文件一致后，管理员才能写入对应文件 SHA256 账本。没有自动猜测/一键接管操作。若已有多个 queued/running 任务，新的唯一索引会失败：先确认进程已停止，人工将确实失效的任务标记 failed 并保留历史，再执行迁移。

失效任务超过 15 分钟可用 `POST /api/radars/runs/{id}/recover` 和至少 10 字的 reason 标记失败并暂停 Radar。先确认 Worker 已停止该任务；恢复接口不重发付费请求。之后由用户决定是否重新运行。

## 付费与 AI

真实 TikHub、Firecrawl、LLM 和 embedding 默认 `PAID_API_ENABLED=false`。配置密钥不等于授权。必须先由管理员确认启用、配置保守 USD 单价，再在 Settings 保存 evidence、assistant 或所属 Radar ID 的 provider 范围、单次和每日请求/费用额度，以及独立定时授权。AI 第二层分类另需 ENABLE_AI_CLASSIFICATION=true、LLM_FAST_MODEL；低置信或高价值冲突才升级 LLM_MODEL。

每日额度按 UTC。并发调用由 PostgreSQL 原子预留；错误不退还预留，付费不自动重试。额度是保守上限，实际成本只有服务商明确报告才记录，否则未知。支持 API 查询 `/api/billing/status` 与 `/api/billing/authorizations/{scope}`。数据库或授权缺失拒绝调用，不退回内存模式。自动数据保留删除默认关闭，只有显式 ALLOW_RETENTION_DELETE=true 才执行。

## 验证

```bash
npm run lint
npm run typecheck
npm test
npm run build
cd backend
REDIS_URL='' TEST_REDIS_URL=redis://127.0.0.1:6379 ../.venv/bin/python -m pytest -q
REDIS_URL='' ../.venv/bin/python -m app.services.evaluate_classifier
cd ..
COMPOSE_PROJECT_NAME=opportunity-radar-smoke API_PORT=8012 ./scripts/compose-smoke.sh
```

Compose smoke 只能用于独立测试 project/端口/卷，会写入明确的测试用户记录。测试 HTTP 禁止网络，使用 MockTransport/ASGI。配置数据库时迁移或 schema 错误会失败，不用 skip 掩盖。Golden Dataset 是 64 条中英文合成回归样本，开发过程中使用过，不能代表留出集或真实平台准确率。

手动免费探针：在 backend 运行 `REDIS_URL='' ../.venv/bin/python ../scripts/live_free_probe.py /absolute/output.json`。最多四次 HN/GitHub 请求，无付费、人工核实、联系或成交；创建独立测试身份和暂停的 Radar。重放保存结果使用 replay_free_probe.py，不增加网络请求。国内付费 schema、实际付费模型、正式 Supabase 登录与真实业务转化尚需本人授权/操作后验收。
