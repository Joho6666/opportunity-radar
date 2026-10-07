# CURRENT_ARCHITECTURE — 机会雷达现状审计（Phase 0）

> 审计时间：2026-10-06 · 审计方式：全量阅读 main@ce46b1e 源码 + GitHub code search 交叉验证
> 结论一句话：这是一个**可演示的「机会发现 SaaS」原型**——采集→去重→LLM 判定→评分→简报的链路已打通，但 Intelligence 层完全缺失，且存在多处会在生产环境造成错误结果的真实缺陷。

---

## 1. 当前真实架构

```
┌────────────────────────── Next.js 15 (App Router) ──────────────────────────┐
│  mock 模式为默认（NEXT_PUBLIC_USE_MOCK !== "false"）                          │
│  lib/transform.ts 是承重墙：snake_case→camelCase + 字段补默认值               │
│  data/mock-*.ts 提供假数据；services/collector.service.ts 是一行的 stub       │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ lib/api-client.ts (fetch, ApiError)
┌──────────────────────────────▼──────────────────────────────────────────────┐
│ FastAPI :8011  backend/app/main.py                                          │
│  api/: profile / radars / opportunities / skills / pipeline / briefs /       │
│        dashboard   （auth: Supabase JWT → core/security.py CurrentUser）     │
│  repositories/: Protocol(base) → MemoryRepository | PostgresRepository       │
│    factory.get_repository_singleton() 按 USE_IN_MEMORY_STORE 选择            │
│    ⚠ 无 ORM、无 Alembic。Postgres 走手写 text() SQL；内存实现镜像 schema 约束  │
│  services/: radar_run_service（编排）/ ai_service（LLM+规则兜底）/            │
│    score_engine / dedup_service / feedback_service / risk_rules / income     │
│  collectors/: SourceAdapter(ABC).search() + registry（别名+异常隔离）         │
│    github / hackernews / rss / web_search(Firecrawl) / mock（生产注册表内！）  │
│  ai/: OpenAICompatibleProvider（chat/completions + json_object）             │
└───────────┬─────────────────────────────┬──────────────────────────────────┘
            │ enqueue_radar_run            │ 同步读
┌───────────▼──────────┐   ┌──────────────▼───────────┐   ┌─────────────────┐
│ Redis 7 + Arq worker │   │ scheduler: 60s tick      │   │ Supabase PG     │
│ max_tries=3          │   │ list_due_radars → enqueue│   │ 3 个原生 SQL 迁移│
│ 无 Redis 时进程内直跑 │   └──────────────────────────┘   │ + RLS           │
└──────────────────────┘                                  └─────────────────┘
```

数据流（一次 run）：
`POST /radars/{id}/run` → create_run → enqueue → `RadarRunService.run()`：
plan queries（LLM≤10 条，兜底模板）→ 逐 query `registry.search()`（单源失败不炸 run）→ `deduplicate()`（url_hash+content_hash 组合签名）→ **新鲜度过滤（published_at ≥ now-freshness_hours）** → `has_raw()` 跨 run 去重（仅 url_hash）→ 逐条 `analyze_raw_item()`（LLM，失败走关键词兜底）→ is_opportunity 则 `calculate_score()` → `add_opportunity` + `mark_raw` → stats + next_run_at。

## 2. 已实现的能力（真实可用）

| 能力 | 位置 | 状态 |
|---|---|---|
| 5 个 collector + 注册表 + 别名 | `collectors/` | ✅ 可用（见 §5 缺陷） |
| Collector 失败隔离 | `registry.py:32-37` | ✅ 有测试覆盖 |
| 同 run 去重（URL+内容 hash） | `dedup_service.py:22-28` | ✅ |
| 跨 run 去重（url_hash，DB 约束兜底） | `postgres.py:222-258` | ✅（见 §5 漏洞） |
| LLM 结构化输出 + 兜底标记 | `ai_service.py:_llm_structured` | ✅ fallbacked 落 llm_calls |
| 上下文传播（user/radar/run → llm_calls） | `ai_service.py` ContextVar | ✅ |
| 评分引擎（7 维加权 + 偏好 boost） | `score_engine.py` | ✅ 公式见 §7 |
| 风险规则（7 条中文诈骗关键词，封顶 60） | `risk_rules.py` | ✅ |
| 反馈学习（8 种事件→5 张权重表，衰减 0.98，钳 ±10） | `feedback_service.py` | ✅ |
| Arq 幂等入队（_job_id=radar-run:{id}）+ 60s 调度器 | `workers/` | ✅ |
| RLS 全表启用 + 三份原生 SQL 迁移 | `supabase/migrations/` | ✅ |
| SSRF 防护（DNS 解析级）+ 限速重试 fetcher | `collectors/http.py` | ✅ |
| 前端 mock/API 双模式 + 9 个 vitest | `lib/`, `tests/` | ✅ |
| CI（前端 lint/test/build；后端 pytest） | `.github/workflows/ci.yml` | ✅（见 §10） |

## 3. Mock / 占位 / 硬编码清单

1. **MockCollector 在生产注册表**（`registry.py:default_collectors()`）——`sources=["mock"]` 的雷达跑的是 4 条硬编码中文接单数据，`published_at=now()` 永远"新鲜"。
2. **默认内存存储**：`USE_IN_MEMORY_STORE=true` → API/worker/scheduler 三个进程各持一份单例，重启全丢；`docker-compose.yml` 里**根本没有 Postgres 服务**。
3. **`ai_service.py` 兜底全是硬编码人设**：PPT/实习/n8n 三个关键词分支给固定预算/时长/分数，地点写死"桂林"；`plan_queries` 兜底生成 `"{地点} {技能} 有偿"` 模板查询；`analyze_profile` 兜底只认 6 个技能词。
4. **Daily Brief 内容 100% 硬编码**：summary/signals/avoid 是固定中文字符串（`postgres.py:476-479` 与 `memory.py:144-147` 双份重复）；`GET /api/daily-brief/{date}` 不读历史，只是把今天的 brief 改个日期返回。
5. `LLMProvider.embed()` 返回 `[]`；`semantic_duplicate()` 返回 `False`——语义层只有接口位。
6. 死代码/死表：`collectors/firecrawl.py`（PublicWebCollector 未注册，"public_web" 被别名指到 web_search）；`opportunity_analysis` 表无代码写入；`opportunities.raw_item_id` 永不填充；`PageMeta`、`radar_queries.last_run_at/enabled`、`raw_items.processing_status`（恒 'processed'）未使用；`SourceAdapter.fetch/normalize` 无人调用。
7. 前端：`services/collector.service.ts` 一行 stub；`deadline/workload/sourceType` 为纯前端占位字段；dashboard 页根本不调 `/api/dashboard`，而是从 store + brief 自算。
8. `_ensure_user`（`postgres.py:31-44`）在 Supabase `auth.users` 里伪造用户行——开发 hack 进了生产路径。
9. `daily_brief` 的 `potential_income_range` 只对"强烈推荐"求和，`budget×conversion/100`——可接受的启发式，但 summary 文案让人以为背后有 AI。

## 4. 抓取扩展瓶颈

- **硬上限 10**：每 run ≤10 条 query、每个 collector 单页 `per_page=10`、无分页/cursor/backfill → 单源单 run 最多 10 条。做情报系统这是数量级不够。
- fetcher 每个**请求新建一个 AsyncClient**（无连接池）；`follow_redirects=False`，会跟丢重定向的 RSS。
- 无 per-source 健康记录、无 429 统计、无退避熔断——挂了只能靠 run 的 collector_errors 数组。
- 无 Agent 化的登录态/账号池管理（接小红书/抖音/X 必需）。
- GitHub collector 不读 `updated_at/pushed_at/stars` 增量；HN/RSS 只取首页 10 条。

## 5. 影响生产使用的真实缺陷（按严重度）

### P0-1 GitHub 时间逻辑 bug（已确认）
`collectors/github.py:34`：
```python
published_at=_parse_dt(repo.get("created_at") or repo.get("pushed_at"))
```
`radar_run_service.py:50-51` 用它做新鲜度过滤：
```python
cutoff = datetime.now(UTC) - timedelta(hours=radar.freshness_hours)
unique = [item for item in unique if item.published_at is None or _aware(item.published_at) >= cutoff]
```
组合效果：**搜索明明按 `sort=updated` 排序（github.py:18），结果一个 2019 年创建、今天因为爆发性 push 被搜出来的仓库，因 created_at 太旧被静默丢弃**。`updated_at` 从未被读取（连 metadata 都没存）。freshness 上限 720h（30 天），意味着 GitHub 源**永远只可能看到 30 天内新建的仓库**——整个"老项目突然爆发"的高价值信号面被系统性排除。
且被过滤的条目不计入任何统计（duplicates_removed/known 都不含它们），静默消失。

### P0-2 Web Search published_at=None（已确认）
`collectors/web_search.py:32` 硬编码 `published_at=None`；Firecrawl 返回里的日期字段从不解析。后果：(a) 所有 web 结果**永远绕过**新鲜度过滤（`published_at is None` 放行）→ 陈旧页面永不过期；(b) opportunity 表带进 NULL published_at；(c) 未传任何日期范围搜索参数。

### P0-3 默认部署丢数据 + compose 无 PG
USE_IN_MEMORY_STORE 默认 true；三个进程各自内存。docker-compose 只有 backend/worker/scheduler/redis。没有 PG 容器、没有迁移执行机制（要 `supabase db reset` 手工跑）。

### P1-1 同内容不同 URL 重复生成 opportunity（PG 路径）
`has_raw` 只查 `url_hash`（`postgres.py:222-226`），但 INSERT 受 `unique(radar_id, content_hash)` 约束。转载文（不同 URL、同内容）通过 has_raw → **完整 LLM 分析 → 生成 opportunity → mark_raw 静默被约束吞掉**。100 篇转载 = 100 个"机会"。内存路径没有 content 约束所以测试发现不了。

### P1-2 mark_raw 只插不更
`ON CONFLICT DO NOTHING`（`postgres.py:243`）——同一个 URL 再次被抓到（= 持续活跃/趋势证据）**不更新任何时间戳**。系统无法区分"见过一次"和"天天见"。没有 first_seen_at/last_seen_at/seen_count，趋势检测的原料在写入层就丢了。

### P1-3 新鲜度过滤不对称
`published_at is None` 放行（web_search 全放行）、mock 恒 now()、GitHub 用错字段。三条源三种行为。

### P2-1 无语义去重/聚类
组合签名 `{url_hash}:{content_hash}` 比数据库约束更严（同 URL 不同内容会在 run 内存活，入库时又被约束吞）→ 统计失真；转发/改写/摘要类内容全部漏过。

### P2-2 radar 级去重范围
去重 scope 是 `(radar_id, url_hash)`——两个雷达抓同一 URL 会各自完整走一遍 LLM 分析并各生成一个 opportunity（成本 ×2、结果重复）。

### P2-3 LLM 成本无漏斗
每条存活 item 无差别调强模型；`llm_calls` 只有 latency/fallbacked，无 token/cost/stage/input_count。10 query × 10 条 = 每 run 最多 100 次 LLM 调用，其中大量是垃圾。

### P3 杂项
- per-item 分析抛异常 → 整个 run failed（Arq 重试 3 次 → 重复 LLM 花费）；剩余条目未分析也未 mark → 部分重扫。
- `radar_runs.status` 是无约束 text，其他状态都是 enum。
- opportunity 的 match_score/conversion_probability 直接是 LLM 自报值，非引擎计算。
- `commercial_intent` LLM 产出后从未被使用。
- 无 token 用量/成本限制，无 per-user 配额。
- 每请求新建 httpx client；AI provider 绕过 fetcher（无 SSRF 防护、无统一重试）。

## 6. 信息分析瓶颈

- **RawItem → Opportunity 单跳**：没有 Signal/Cluster/Trend/Gap 中间层。一条"求推荐"评论和一篇深度评测被同等对待；100 篇同一事件的转载 = 100 个候选。
- 分析视角单一：只问"是不是接单机会"，不问需求是否增长、有没有付费证据、供给是否饱和、信息差是否存在。
- 无时间维度：没有任何表存历史快照，"和昨天比发生了什么"在当前 schema 下无法回答。
- 无跨平台证据聚合：payment/hiring/tender 信号无独立表达。
- Opportunity type 只有 5 种（job/client/project/business/github），表达不了"内容机会/监控/学习"等动作。

## 7. 评分现状（记录基线，供 MoneyScore 对比）

`score_engine.py`：
- `opportunity_score = skill_match×.25 + income_score×.20 + hourly_rate_score×.15 + conversion×.15 + urgency×.10 + (100-competition)×.10 + (100-risk)×.05 + 偏好boost`
- `income_score = min(100, budget/max(minimum_budget,1)×50)`；`hourly_rate_score = min(100, 时薪×1.2)`（≈¥83/h 封顶）
- recommendation 阈值：90 强烈推荐 / 75 值得考虑 / 60 一般
- 问题：完全不感知**需求增长、付费证据、供给缺口、信息时效**——这是"接单评分器"不是"赚钱评分器"。

## 8. 成本瓶颈

- LLM 无分级（fast/standard/premium 未实现；`llm_fast_model` 配置项存在但无人读）。
- 无 Stage 漏斗：所有 raw item 一律过强模型。
- 去重范围 per-radar → 跨 radar 重复分析重复计费。
- `llm_calls` 无法核算成本（无 token 数），也无预算熔断。

## 9. 稳定性瓶颈

- run 内任何非 collector 异常 → run failed + radar error，Arq 重试 3 次全量重跑（重复 LLM 消耗）。
- 无 source health、无熔断、无部分成功语义（除 collector 级）。
- 内存模式下 API 与 worker 数据不一致（各自单例）——任何"run 后立刻查"的依赖在 compose 部署下会随机出错。
- CI 无 PG/Redis service → PostgresRepository 契约测试**永远 skip**，PG 路径回归只能靠人肉。
- scheduler 60s tick 无 jitter、无锁，多副本部署会重复入队（靠 run 状态 NOT EXISTS 缓解但存在竞态窗口）。

## 10. 测试体系现状

- 后端 7 个 pytest 文件（collectors/radar_run/repository/queue/engine/feedback/delivery），Memory 契约为主；`test_repository.py` 的 PG 契约测试需 `DATABASE_URL`，CI 未提供 → 恒 skip。
- 静态 SQL 安全检查（禁 f-string/format 拼接）是好实践，保留。
- 无 collector fixture 契约测试、无时间逻辑测试（正是 P0-1 溜过去的原因）、无迁移测试。

## 11. 结论与升级方向

现系统 = "**接单雷达 V0.1**"：从公开网络找「有偿」帖，按技能/预算/风险排序。
要成为 Money Intelligence OS，缺的是四层：
1. **时间层**（first_seen/last_seen/seen_count/时间字段规范）——修复 P0-1/P0-2 后，"变化"才可度量；
2. **语义层**（embedding + simhash + 聚类）——修复 P1-1/P2-1 后，"聚合信号"才可能；
3. **情报层**（Signal → Cluster → Trend/Change → Gap → MoneyScore → Edge → Verification）；
4. **成本层**（Stage 漏斗 + 模型分级 + token 核算）。

以上即 MONEY_INTELLIGENCE_ROADMAP.md Phase 1 的全部依据。逐文件级缺陷引用见 roadmap 附录。
