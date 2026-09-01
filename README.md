# 机会雷达 · Opportunity Radar

面向中文用户的 AI 机会发现 Web SaaS。围绕「发现机会 → 判断机会 → 管理机会 → 采取行动」设计，包含 Next.js 前端与可独立运行的 FastAPI Opportunity Engine。

## 功能

- Landing、Onboarding（偏好持久化）、Dashboard（真实统计）、机会列表与分析详情
- 机会列表按**类型**筛选（工作/客户/项目/商机/GitHub），按推荐度/最新/预算/风险排序
- 雷达创建、运行/暂停、搜索策略预览；联机模式走 GitHub / Hacker News / RSS / Web Search 真实采集
- 机会收藏、联系、忽略与 Pipeline 看板/列表联动（成交收入用**实际成交额**；潜在收入按预算 × 成交概率估算）
- 每日简报、技能模块、用户画像（可编辑地区/收入/预算/时间）与设置页（重置数据/退出登录）
- FastAPI Profile、Radar、Opportunity、Pipeline、Daily Brief API 与 OpenAPI 文档
- Collector Registry → RawItem 标准化 → **跨运行 PostgreSQL 去重** → LLM 分析 → 风险规则 → 偏好加权评分 → Opportunity
- Redis + Arq Worker / Scheduler：手动 Run 与 hourly/daily/weekly 定时扫描，Web 重启不丢已入队任务
- FeedbackService：根据 viewed/saved/ignored/contacted/applied/won/lost 学习关键词与来源偏好
- **LLM 真实路径**：配置 `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` 后自动接入 OpenAI-compatible 模型，失败时回退确定性分析
- Supabase PostgreSQL schema、RLS migration、本地 Auth 登录页与可替换服务层
- 演示模式（`NEXT_PUBLIC_USE_MOCK=true`）开箱即用；联机模式（`false`）启用 middleware 路由保护

## 技术栈

前端：Next.js 15 App Router、TypeScript、Tailwind CSS、Zustand（hydrate from API）、Supabase SSR、Lucide Icons。
后端：FastAPI、Pydantic、SQLAlchemy（预留）、Supabase PostgreSQL、httpx、python-jose、Docker。

## 本地运行

```bash
npm install
npm run dev
```

打开 `http://localhost:3000`。默认演示模式（Mock 数据），无需后端或 Supabase。

## 联机模式

### 启动后端

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8011
```

健康检查：`http://127.0.0.1:8011/health`；OpenAPI：`http://127.0.0.1:8011/docs`。

设置 `NEXT_PUBLIC_USE_MOCK=false` 和 `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8011` 后，前端会自动从后端拉取数据，所有操作（创建雷达、运行、收藏、修改状态、编辑画像）均同步到后端。

### 可选：接入 LLM

在 `backend/.env` 中设置：

```
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini
```

AI 分析将优先调用 LLM，返回无效时自动回退到确定性分析。

### 启动 Supabase（可选）

```bash
supabase start
supabase db reset
```

端口 55421（API）/ 55422（Postgres）/ 55423（Studio）。写入 `.env.local`：

```bash
NEXT_PUBLIC_USE_MOCK=false
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8011
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:55421
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<local-publishable-key>
```

启用联机模式后，middleware 自动拦截未登录用户跳转到 `/login`。数据库结构、RLS 和 seed 位于 `supabase/migrations/` 与 `supabase/seed.sql`。

## 校验

```bash
npm run lint      # ESLint
npm test           # Vitest（9 个测试：mock 数据、筛选逻辑、字段映射）
npm run build      # Next.js production build
```

后端测试：

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

生产/联机建议在 `backend/.env` 中设置：

```
USE_IN_MEMORY_STORE=false
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55422/postgres
REDIS_URL=redis://127.0.0.1:6379
GITHUB_TOKEN=
FIRECRAWL_API_KEY=
RSS_FEEDS=https://hnrss.org/newest,https://github.blog/feed/
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

`USE_IN_MEMORY_STORE=true`（默认）仍可用于无数据库的演示和单测。

## Docker

```bash
Copy-Item backend/.env.example backend/.env
docker compose up --build
```

Compose 会启动 API、Redis、Arq worker 与 scheduler。Worker 消费雷达任务；scheduler 每 60 秒把到期且未暂停的雷达入队。

## CI

推送到 `main`/`master` 或发起 PR 时自动运行：前端 lint + test + build，后端 pytest。

## 架构

```
创建雷达（GitHub + HN + RSS + Web）
  → plan_queries 生成搜索词
  → Scheduler / 手动 Run 入队 Arq
  → Worker 抓取真实数据
  → RawItem 标准化与去重
  → LLM 分析 + Opportunity Score
  → PostgreSQL
  → Dashboard 新机会
  → 收藏 / 忽略 / 联系
  → FeedbackService 更新偏好
  → 下一次扫描更符合用户
```

```
app/              → Next.js 页面和 middleware
components/       → UI 组件（AppShell、OpportunityCard、Button/Panel 等）
features/         → Dashboard 等复杂页面组合
lib/              → api-client、transform（后端字段映射）、auth、filters
services/         → 业务服务（mock/real 双模式）
stores/           → Zustand 状态（hydrate from API on mount）
backend/app/      → FastAPI 路由、Repository、采集器、Arq worker、AI provider
supabase/         → migrations、seed SQL
```

切换模式只需改 `NEXT_PUBLIC_USE_MOCK` 环境变量：
- `true`（默认）：所有页面使用本地 mock 数据和 zustand 持久化
- `false`：AppShell 挂载时从后端 hydrate，所有操作同步到 Opportunity Engine API
