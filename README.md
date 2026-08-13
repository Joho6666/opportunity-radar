# 机会雷达 · Opportunity Radar

面向中文用户的 AI 机会发现 Web SaaS。它围绕「发现机会 → 判断机会 → 管理机会 → 采取行动」设计，包含 Next.js 前端与可独立运行的 FastAPI Opportunity Engine。

![Dashboard 预览](public/screenshots/dashboard.png)

## 功能

- 中文 Landing、Onboarding、Dashboard、机会列表与分析详情
- 雷达创建、运行/暂停、搜索策略预览
- 机会收藏、联系、忽略与 Pipeline 看板/列表联动
- 每日简报、技能模块、用户画像与设置页
- FastAPI Profile、Radar、Opportunity、Pipeline、Daily Brief API 与 OpenAPI 文档
- Mock Collector → 去重 → 结构化分析 → 风险规则 → 稳定评分 → Opportunity 的端到端运行闭环
- Supabase PostgreSQL schema、RLS migration、本地 Auth 登录页与可替换服务层

## 技术栈

前端：Next.js App Router、TypeScript、Tailwind CSS、Zustand、Supabase SSR、Lucide Icons。  
后端：FastAPI、Pydantic、SQLAlchemy、Supabase PostgreSQL、httpx、Docker。

## 本地运行

```bash
npm install
npm run dev
```

打开 `http://localhost:3000`。如端口被占用，请使用 `npm run dev -- --port 3001`。

## 后端运行

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8011
```

健康检查：`http://127.0.0.1:8011/health`；OpenAPI：`http://127.0.0.1:8011/docs`。

默认 `USE_IN_MEMORY_STORE=true`，可在没有 Supabase/LLM 凭据时完成 Mock Collector 闭环。设置 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 后可切换到 OpenAI-compatible 模型；未配置时会使用确定性分析回退。

## 本地 Supabase

安装 Supabase CLI 后，在仓库根目录执行：

```bash
supabase start
supabase db reset
```

项目配置使用 API `55421`、Postgres `55422`、Studio `55423`，避免影响默认本地端口。将 CLI 输出的 URL 和 publishable key 写入 `.env.local`，再设置：

```bash
NEXT_PUBLIC_USE_MOCK=false
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8011
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:55421
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<local-publishable-key>
```

然后访问 `/login` 注册本地测试账户。数据库结构、RLS 和 seed 位于 `supabase/migrations/` 与 `supabase/seed.sql`。

## 校验

```bash
npm run lint
npm run test
npm run build
```

后端测试：

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

## Docker

```bash
Copy-Item backend/.env.example backend/.env
docker compose up --build
```

Redis 是未来后台 worker 的预留服务，可通过 `docker compose --profile workers up` 启动。
