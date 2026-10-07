# Money Intelligence Engine — Phase 1 说明

Phase 1 把后端从「接单雷达」升级为 Money Intelligence OS 的数据与情报基础。设计依据见仓库根目录的 `MONEY_INTELLIGENCE_ROADMAP.md` 与 `CURRENT_ARCHITECTURE.md`；本文件说明新增模块的职责、数据流与配置。

## P1 护栏 + Phase 2（2026-10-06 追加）

### P1 护栏（8 项全部落地）

1. **Per-user LLM token 预算**（`services/budget_service.py`）：`LLM_DAILY_TOKEN_BUDGET`（0=不限）按日计数（Redis INCR+TTL，无 Redis 降级进程内计数）。LLM 可用时每次调用前预检（估算 len/3），超限走熔断——原始记录照存，只是跳过 LLM，`stage_stats.llm_budget_skipped` 计数，run 不失败。
2. **数据保留 TTL**（`services/retention_service.py`）：`RETENTION_RAW_ITEMS_DAYS=90`（按 last_seen_at）、`RETENTION_LLM_CALLS_DAYS=30`（按 created_at），scheduler 每日执行，0=永久保留。trend_snapshots 是趋势历史本体，永久保留。
3. **Scheduler 单实例护栏**：PG 模式 `pg_try_advisory_lock(727272)`，拿不到锁的副本跳过本轮；每轮 0-10s jitter。
4. **生产排除 Mock**：compose 三个服务显式 `INCLUDE_MOCK_COLLECTOR=false`（覆盖 .env 的 true）。
5. **Payment 按 cluster 聚合**：run 内累计同簇付款信号数（`cluster_payment`），MoneyScore 的 payment_evidence 不再被单条上限 55 卡死。
6. **structlog 接入**（`core/logging.py`）：JSON 日志管线，main/scheduler/worker 入口 `configure_logging()`；新模块用 structlog，存量 `extra=` 调用点保留 stdlib logging（同一后端输出）。
7. **Brief 历史真读**：`GET /api/daily-brief/{date}` 现在经 `repo.get_brief()` 读 `daily_briefs` 真实历史行（含 V2 列），无历史返回 404 `BRIEF_NOT_FOUND`；今天的 brief 行为不变。
8. **RLS 陷阱文档化**：见下。

> **RLS 注意**：backend 以 postgres superuser 连接（superuser 绕过 RLS），行级所有权实际由 repository 层的 `user_id` 关联强制。compose 的 `auth.uid()` 桩读 `request.jwt.claim.sub`（服务连接时为 NULL）——若改用受限角色直连而不带 JWT 上下文，所有 RLS 策略会静默拒绝（空结果）。

### Phase 2 四模块

1. **自然语言 Listener**（`services/listener_service.py`，openmagpie 模式）：RadarCreate/Read 新增 `listener_description`（如「寻找正在抱怨短视频制作太慢、希望批量生产视频的商家」）。保存/更新时编译为 `RadarListenerConfig{positive_signals, negative_signals, search_queries, exclusion_rules}`（LLM 编译，失败规则兜底——CJK bigram 分词），缓存在 `radars.listener_config`。运行时语义：**必须命中正向且不碰负向**（openmagpie 语义过滤），未配置 listener 的雷达走原 Stage 0.5 关键词门；命中正向的条目在 MoneyScore personal_fit 上获得 +5/命中（封顶 +10）。
2. **Signal LLM 抽取**（`ai_service.extract_signals_llm`）：对 `document_count>=2` 的簇取 representative 文本，用 `LLM_FAST_MODEL`（快模型分级路由，缺省回落 llm_model）抽取 0-4 条多类型信号，落 `signals`（`extraction_method='llm'` + `cluster_id`）。无效类型剔除，失败静默回落规则层。受 token 预算闸门约束。
3. **PainPoint Engine**（`services/pain_point_service.py` + `pain_points` 表）：run 末尾聚合 pain_point/complaint/feature_request 信号按 theme（cluster title 优先）→ mention_count / growth_rate（对比上次）/ unique_user_count / severity（urgency+payment+量加权）/ payment_intent。可选 LLM 补写 current_solutions/solution_satisfaction（预算内）。`GET /api/intelligence/pain-points`；后续 Brief V2 与 Gap Engine 直接吃这张表。
4. **Cluster merge 维护**（`services/cluster_maintenance.py`）：每日 job 把质心余弦 >0.90 的簇合并（大吞小：members 重挂、document_count 累加、`merged_into` 链可回溯；list_clusters 只返回存活簇）。**split/漂移分裂明确延后**——centroid 已在持续记录，Phase 3 需要时再实现临时 vs 持续漂移的判别。

新迁移：`202610060003_phase2.sql`（radars listener 列、signals.cluster_id、pain_points 表 + RLS）。

## P0 根基修复（2026-10-06 追加）

代码复查发现 Phase 1 的三个"承诺"不成立，已修复（迁移 `202610060002_p0_fixes.sql` + 代码）：

1. **跨 run 记忆**
   - `mark_raw(..., embedding=...)` 现在把向量写入 `raw_items.embedding`（HNSW 索引已建）；
   - `repository.find_similar_raw(radar_id, vector)` 用 pgvector `<=>` 查历史近邻（阈值 0.92），run 内命中即跳过 LLM——**跨 run 语义去重生效**；
   - `ClusterState.seed_from(repository.list_clusters(...))` 把上一批簇（含 centroid）载入为归并目标，`save_cluster` 持久化 centroid——**同一事件跨 run 长在同一个簇里**，velocity/breakout 从此有真基线。
2. **真成本漏斗（闸门，不只是计数器）**
   - Stage 0.5：无 signal 且与 radar keywords/goal 无关键词交集 → 跳过 LLM（`stage_stats.gated_off_topic`）；
   - Stage 1：item 向量与 radar 主题向量（goal+keywords，每 run 一次）余弦 < `RELEVANCE_SIMILARITY_THRESHOLD`（默认 0.30）→ 跳过 LLM（`gated_low_relevance`）；无 embedding 时自动旁路；
   - 兜底误报修复：`analyze_raw_item(..., has_commercial_signal=signal is not None)`——无商业信号时确定性兜底返回 `is_opportunity=False`（此前"天气不错"也会变成机会）；
   - token/cost 计量：provider 捕获 `usage`，`llm_calls.prompt_tokens/completion_tokens/cost_usd` 开始有真数据（单价配置见下，0=不记成本）。
3. **Breakout 幂等**：`change_events.dedup_key`（radar:kind:subject:metric:日期）唯一索引 + `ON CONFLICT DO NOTHING`——run 内与 scheduler 每小时检测重复触发无害，每天每主题每指标最多一行。

新增配置：`ENABLE_RELEVANCE_GATE` / `RELEVANCE_SIMILARITY_THRESHOLD` / `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK`。

## 数据流（一次 run）

```
collectors.search()
  → Stage 0  dedup_service.deduplicate()      L1 url_hash / L2 content_hash / L3 simhash(CJK bigram)
  → 新鲜度过滤  activity_time = max(published_at, updated_at_source)   ← 修复 GitHub created_at 误杀
  → 跨 run    repository.has_raw() (url_hash)
  → Stage 1  embedding_service.embed_texts()  批量 embedding（无 key 时优雅降级）
  → Stage 4  is_semantic_duplicate()          L4 cosine ≥ 0.92
  → signal_service.extract_signal()           规则抽取 Signal（15 类，零 LLM）
  → clustering_service.assign_to_cluster()    EventCluster 增量聚类（centroid 余弦 / Jaccard 兜底）
  → mark_raw()                                ON CONFLICT (radar_id,url_hash) DO UPDATE
                                              last_seen_at / seen_count / content_changed_at
  → analyze_raw_item()                        LLM（不变）
  → information_edge + money_score            挂到 Opportunity
  → trend_topics upsert + breakout 检测
  → run.stage_stats                           每级漏斗计数
```

## 新增模块

| 模块 | 职责 |
|---|---|
| `services/simhash.py` | 纯 Python simhash64；中文按字符 bigram 切分（整句 token 会让指纹失效）。近重复阈值 12（实测近重复对距离 ~8、无关对 ~30） |
| `services/embedding_service.py` | OpenAI 兼容 `/embeddings`，L2 归一化；失败返回 None，绝不抛异常 |
| `services/dedup_service.py` | 四级去重：L1 url_hash → L2 content_hash → L3 simhash → L4 embedding（`SemanticDedupState` 承载 run 内状态） |
| `services/signal_service.py` | 规则词典抽取：purchase_intent / pain_point / hiring / tender / complaint 等 15 类 + payment_evidence + commercial_intent。LLM 抽取留 Phase 2 |
| `services/clustering_service.py` | 增量聚类：余弦 ≥ `cluster_similarity_threshold`(0.82) 归并并更新质心；无 embedding 时 Jaccard 兜底；`breakout_score` 体积+速度+跨平台启发式 |
| `services/trend_service.py` | trend topic upsert；**快照存累计值**，周期增量由差分推导（`cumulative_deltas`）；滚动窗口 `rolling_mentions` |
| `services/change_detection.py` | 7 期基线 z-score → velocity/acceleration/momentum/breakout；`breakout_from_snapshots()` 是 run 与 scheduler 共用的入口。验收样例：7 天基线 18 条/天、今日 97 → breakout |
| `services/money_score.py` | 11 维加权（权重和归一）；competition / execution_difficulty 反向计分。默认权重：payment_evidence(0.16) > demand_velocity(0.12) = supply_gap(0.12) |
| `services/information_edge.py` | 9 维 + `information_half_life_hours`（信息差窗口估计，封顶两周） |
| `services/source_health_service.py` | 每次 collector 调用 → success_rate / latency / 429 计数 / health_score(0-100)，状态机 healthy→degraded→unhealthy |
| `services/daily_intelligence.py` | Brief V2 组装器：Top Opportunities（含 why_now）/ Rising Trends / Pain Points / Payment Signals / Job Market / Tender / Content Opportunities / **Today Actions ≤3**；旧字段由同一数据推导，前端契约不破 |
| `api/intelligence.py` | 只读路由 `/api/intelligence/{signals,clusters,trends,changes,source-health}` |

## 修复的两个 P0

1. **GitHub 时间逻辑**（`collectors/github.py`）：`metadata` 现在记录 created_at/updated_at/pushed_at 三者；`published_at`=created_at（真实发布时间），`updated_at_source`=pushed_at（平台侧最后活跃）。新鲜度过滤改用 `activity_time()`，**几年前创建、今天因 push 爆发的仓库不再被丢弃**。
2. **Web Search 日期**（`collectors/web_search.py`）：从 Firecrawl 结果递归提取 `publishedAt/published/date/...` 字段；无法解析时保持 None（按不可判定处理，仍可入库）。

## Collector 契约扩展（`collectors/base.py`）

```python
@dataclass(frozen=True)
class CollectorCapabilities:
    search / timeline / comments / profile / detail / historical / realtime / change_detection

class SourceAdapter:
    def capabilities(self) -> CollectorCapabilities   # 新 adapter 必须如实声明
    async def healthcheck(self) -> bool               # 默认 True，测试不碰网络
```

Registry 在每次 `search()` 后通过 health recorder 记录成功/失败/延迟/429；单 collector 失败依旧不影响 run（原有契约）。`INCLUDE_MOCK_COLLECTOR=false` 可在生产部署排除 MockCollector。

## Schema（`supabase/migrations/202610060001_money_intelligence.sql`）

- `raw_items` +`platform/language/engagement/updated_at_source/first_seen_at/last_seen_at/crawled_at/content_changed_at/seen_count/simhash/embedding vector(1536)/embedding_model`；`unique(radar_id, content_hash)` 约束降级为普通索引（旧的静默吞行是 P1-1 漏洞）
- 新表：`signals` / `event_clusters` (+`event_cluster_members`) / `trend_topics` (+`trend_snapshots`) / `change_events` / `source_health`
- `opportunities` +`money_score/money_breakdown/information_edge/information_edge_breakdown/verification_status/verification_evidence/cluster_id`
- `daily_briefs` +8 个 V2 jsonb 列（旧列保留）
- `llm_calls` +`stage/input_count/output_count/prompt_tokens/completion_tokens/cost_usd`；`radar_runs` +`stage_stats`

## 配置（`backend/.env`）

```bash
EMBEDDING_MODEL=text-embedding-3-small   # 需 LLM_BASE_URL/LLM_API_KEY 同时配置
CLUSTER_SIMILARITY_THRESHOLD=0.82
BREAKOUT_Z_THRESHOLD=3.0
BREAKOUT_MIN_BASELINE=2.0                # 基线均值下限，防止冷启动话题误报
MONEY_SCORE_WEIGHTS_JSON={"payment_evidence":0.2}   # 可选，按维覆盖
INFORMATION_EDGE_WEIGHTS_JSON=            # 可选
INCLUDE_MOCK_COLLECTOR=false              # 生产排除 Mock
```

## 本地验证

```bash
cd backend
uv venv --python 3.12 .venv && uv pip install -r requirements.txt
.venv/bin/python -m pytest -q          # 105 passed（无 DATABASE_URL 时 PG 契约测试 skip）
```

带真实 PG（pgvector）跑迁移 + 契约测试：`docker compose up migrate` 后设 `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/opportunity_radar` 再跑 pytest；或直接看 CI（GitHub Actions 会起 pgvector/pg16 service 执行同一套）。

## 明确不在 Phase 1

20 个平台爬虫、SourcePack UI、自然语言 Listener、Verification Agent、ActionPlan、Dashboard 改版——见 ROADMAP Phase 2-8。
