# 机会雷达 · Opportunity Radar

面向中文用户的 AI 机会发现 Web SaaS。围绕「发现机会 → 判断机会 → 管理机会 → 采取行动」设计，包含 Next.js 前端与可独立运行的 FastAPI Opportunity Engine。

## 功能

- Landing、Onboarding（偏好持久化）、Dashboard（真实统计）、机会列表与分析详情
- 机会列表按**类型**筛选（工作/客户/项目/商机/GitHub），按推荐度/最新/预算/风险排序
- 雷达创建、运行/暂停、搜索策略预览，**运行后真正触发 Mock Collector 闭环**
- 机会收藏、联系、忽略与 Pipeline 看板/列表联动（收入用**实际成交额**统计）
- 每日简报、技能模块、用户画像（可编辑地区/收入/预算/时间）与设置页（重置数据/退出登录）
- FastAPI Profile、Radar、Opportunity、Pipeline、Daily Brief API 与 OpenAPI 文档
- Mock Collector → **跨运行去重** → 结构化分析 → 风险规则 → 稳定评分 → Opportunity 的端到端闭环
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
.\.venv\Scripts\python.exe -m pytest -q  # 11 个测试：引擎、去重、收入、级联、API
```

## Docker

```bash
Copy-Item backend/.env.example backend/.env
docker compose up --build
```

Redis 是未来后台 worker 的预留服务，可通过 `docker compose --profile workers up` 启动。

## CI

推送到 `main`/`master` 或发起 PR 时自动运行：前端 lint + test + build，后端 pytest。

## 架构

```
app/              → Next.js 页面和 middleware
components/       → UI 组件（AppShell、OpportunityCard、Button/Panel 等）
features/         → Dashboard 等复杂页面组合
lib/              → api-client、transform（后端字段映射）、auth、filters
services/         → 业务服务（mock/real 双模式）
stores/           → Zustand 状态（hydrate from API on mount）
backend/app/      → FastAPI 路由、服务、采集器、AI provider
supabase/         → migrations、seed SQL
```

切换模式只需改 `NEXT_PUBLIC_USE_MOCK` 环境变量：
- `true`（默认）：所有页面使用本地 mock 数据和 zustand 持久化
- `false`：AppShell 挂载时从后端 hydrate，所有操作同步到 Opportunity Engine API
