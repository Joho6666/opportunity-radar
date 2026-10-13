# Production acquisition upgrade — audit baseline

2026-10-13: remote main `7f6e7c4`; evidence branch `1d34837`, ahead 17 / behind 0. Clean clone; implementation branch `feat/production-acquisition-loop`. No open PR at audit time.

Baseline: backend 195 passed / 3 PostgreSQL tests skipped without DATABASE_URL. Frontend lint, TypeScript, 27 Vitest tests and production build passed. Latest main CI: https://github.com/Joho6666/opportunity-radar/actions/runs/37616700342 . Evidence branch has no CI run; this is not validation of its changes.

## Priority and causes

- P0 billing: confirmation exists only on evidence HTTP route; Radar, scheduler, LLM and embeddings can call providers directly. Redis token budget fails open to process-local counters. Add one persistent fail-closed gateway, explicit policy, atomic request/cost reservation, bounded retries and usage ledger.
- P0 persistence: compose replays all historical migrations on each startup; CREATE TYPE/TABLE/POLICY are not replay-safe. Add checksummed migration ledger without editing applied history. PG tests currently skip schema errors; configured DB must fail tests on schema failure.
- P0 security: production memory/mock configuration accepted; proxy headers can spoof loopback with uvicorn forwarding enabled; auth.users synthesized in every environment. Enforce production startup, reject forwarding, disable uvicorn proxy trust, guard development user creation. SSRF DNS validation has a rebind gap; use transport-level resolution validation.
- P0 correctness: fallback analysis assigns fictional budgets/hours/conversion probability. Won revenue falls back to budget. Review payload can set conversion link. Remove invented amounts, preserve manual state and recorded income.
- P0 deletion: scheduler retention runs without explicit deletion authorization. Default disabled.
- P1 classification: hiring falls into buyer, seller collapsed into market; three categories cannot express job/seller. Add five classes, semantic cascade behind billing, anchored extraction and fixed bilingual evaluation.
- P1 acquisition: source dropdown omits four domestic sources; one-page paid parsers are synthetic fixture tested, not provider validated. Preserve honest provenance and date/content types; never label fixtures as live contracts.
- P1 workflow: seven legacy Pipeline states, missing follow-up/quote/cost/lost reason. Extend existing opportunities and action history; no parallel CRM.
- P2 product: current architecture doc describes older compose/defaults; actual funnel not surfaced. Replace current-state architecture and add acquisition metrics with null rates when denominators absent.

## Gates

Small commits by stage. No real paid calls, customer messages or destructive operations. Additive migrations only. main remains unchanged; PR remains draft if material acceptance gaps remain. Saved synthetic fixtures and offline scenario results are explicitly labeled.

## 本轮交付状态

P0 已实现并本机验证：统一付费拒绝/授权/预算网关、PG 并发原子预留、无内存放行、付费重试为零；历史迁移账本；默认关闭 Mock/删除；API/worker/scheduler 共用生产配置检查；直接本机身份边界与 JWT；连接时 DNS 防 SSRF；非超级用户 RLS；Pipeline 状态与金额持久化、审核同步和重复保存；单 active run、单次 claim、人工失效恢复；开发分支 CI 和 Compose smoke。

P1 已实现：五类规则，收费关闭的可选语义级联与证据原文 substring 校验，预算/日期与币种不补造；64 条中英文合成 Golden Dataset，旧 HEAD/当前同样本可重复评测；国内平台配置 PG 回读修复，分页契约、独立评论归属、来源熔断和可见 schema 错误；统一证据修订/纠正历史；统一获客 Pipeline、下次跟进、三档报价与沟通草案、手工实收/成本/工时和流失原因。获客优先级提供逐项原因，未知因素明确使用中性分，不是成交概率。

P2 已实现：真实漏斗/费用 UI、五类筛选、国内来源选项、手动下一页、空状态与错误恢复；六个页面保持现有设计语言；更新部署/架构文档。当前分类回归评测各类 Precision/Recall/F1 为 1.0；旧分类器 buyer 为 P=.6957/R=1/F1=.8205。样本用于开发且类目发生扩展，这只是合成回归表现，不是留出集或线上准确率提升证明。强模型尚未付费评测。

### 本轮真实免费验证

HN 评论与 GitHub Issue 各两个查询，总计四个免费公开请求，真实响应顶层 keys 与 items/hits 列表匹配。采集 40 条，30 天时效过滤和规范化后有效证据 17，买方预测 0、人工核实 0、联系/回复/报价/成交均 0，实收未知。没有替换为合成客户。初次运行因 6 万字符 Issue 超过 2 万字符上限失败；修复为单条 10 万字符、批次 200 万字符上限并保留原文，使用保存响应重放成功，无追加请求。

Compose 已验证完整镜像构建、迁移退出 0、API/PG/Redis 健康、worker/scheduler 启动，重启 PG/Redis 后专用测试记录仍存在，再次迁移 no-op。审计端口使用 8012，未停止或改动占用原 8011 的另一套服务。测试数据使用独立本机审计 DB / 身份；业务数据未删除。

### 明确未完成的验收

- TikHub/Firecrawl 正式付费响应与实际账单、真实语义模型分类：需要明确付费授权，当前只有离线契约/网关拒绝证据。
- 正式 Supabase 登录、TLS/反向代理与部署环境端到端：未部署到生产，也未使用用户真实凭据；本机测试不代表生产 ready。
- 来源长期 watermark、自动续抓与共享限速/熔断：当前手动分页、跨运行身份去重与原文更新，熔断/限速仍为进程内。
- 真实买方核实、联系、回复、报价、成交：本轮真实探针未找到买方；两个全流程的成交反馈仅固定合成测试，未写成真实业绩。
- 报价工时/毛收益仍需人工判断，尚无真实项目成本校准；公开联系渠道人工填写，无自动营销。
- 模糊转载、没有稳定 ID/链接的同义内容仍需人工去重；纯规则对隐含需求和讽刺表达可能误判。
- 历史无账本数据库不能自动安全接管，需要管理员先在备份副本审计。生产备份、SLO/报警、专用角色、真实性能压测仍待配置。

基线与完成版 pytest/Vitest/构建、UI 和本轮 CI 的确切结果见交付报告，不能用基线 main CI 替代本轮验证。合并保持人工审查，PR 以 draft 提供；不合并 main。

审计过程中曾因国内 adapter 未接网关，以无效测试 key 触发一次 401 请求。已修复底层收费入口并加 pytest 网络护栏与全部 adapter 拒绝测试。该请求未获取有效数据，实际费用不可确认；没有执行获授权的付费采集或客户联系。
