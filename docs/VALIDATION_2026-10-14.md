# 2026-10-14 本轮验证证据

实际执行起点 `3103113`；分支 `feat/production-acquisition-loop`，main保持独立。主要提交：

- `c903708`：精确端点价格核实收据、计费账本保存收据、RSS发布时间修复与来源响应状态。
- `3f49753`：独立需求判断、事实与关闭状态回归、本地SetFit影子层、人工标注导出和分组评测。
- 最后复核：普通Radar保留已关闭证据但不再创建销售候选，新增回归通过。
- `e07b3ac`：差异化套餐、报价预览/版本/并发保护、追加跟进与今日/逾期筛选。

| 验证层 | 本轮结果 | 范围和限制 |
|---|---|---|
| 完整后端pytest | **320 passed，0 skipped** | PostgreSQL/pgvector54329、Redis6379、migration/RLS/租户隔离、付费并发/幂等/错误配额、来源契约、关闭阻断、报价并发持久化；Starlette有1条上游弃用警告 |
| TypeScript | 通过 | `npm run typecheck`；忽略可选Python依赖和隔离输出目录 |
| ESLint | 通过 | `npm run lint`；排除生成物和Python虚拟环境，业务代码检查保留 |
| Vitest | **36 passed** | 10文件；Node环境Zustand存储不可用警告，无测试失败 |
| Next.js生产构建 | 通过 | 静态页面和动态路由生成完成；开发与生产构建目录分离 |
| Docker Compose | 通过 | 独立项目`opportunity-radar-impl-qa`，54330/6380/8015；启动健康、PG与Redis重启持久化、迁移重复执行no-op；不重启业务数据库 |
| 当前API重新加载 | 通过 | 8013 `/ready`返回`ready/storage=postgresql`；保留本机身份、数据库与端口，强制真实付费/付费语义禁用 |
| Ego页面交互 | 通过 | 独立用户、8014/3003；合成导入→判断纠正→核实→Pipeline→无写入预览→报价v1/v2→两条追加记录→今日/逾期筛选；datetime原生值事件作为浏览器填充回退 |
| 合成数据隔离 | 通过 | 该E2E的真实漏斗全0、实收未知、标签导出0；没有联系、回复或成交 |
| SetFit基础设施 | 通过 | 安装1.1.3、固定公开底座下载、10条合成样本训练/保存、本地加载、长文截断；部署门槛false，不是业务模型评测 |
| 免费真实RSS | 1请求/10样本 | 解析前保存官方V2EX XML和收据，6 buyer/3 seller/1 market为规则预测；原文日期均有，人工核实0，业务写入0 |
| 国内真实API | **未验证** | TikHub请求0，新增预留$0；精确官方端点价格未知，密钥有效性、真实响应及分页不能宣称通过 |
| 真实留出模型效果 | **未评测** | 真实人工标签0/250；缺少独立原文/事实标注与足够买方支持，继续影子模式 |

规则回归指标和混淆矩阵见 [rule-v3-regression-evaluation.json](rule-v3-regression-evaluation.json)：64条固定合成开发样本，各类P/R/F1=1.0；对角计数buyer16，其余各12。这不是生产准确率提升证据。两条V2EX公开漏检仅开发回归，不作独立人工标注评测。

完整本机命令（backend目录）：

```bash
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/opportunity_radar \
REDIS_URL='' TEST_REDIS_URL=redis://127.0.0.1:6379 \
../.venv/bin/python -m pytest -q
../.venv/bin/python -m app.database.migrate
```

根目录：`npm run lint`、`npm run typecheck`、`npm test`、`npm run build`。

本机原始证据在Git忽略的`outputs/`：`backend-test.log`、`frontend-test.log`、`production-build.log`、`compose-smoke.log`、`setfit-smoke-result.json`、`ego-e2e-result.json`、`v2ex-public-response.xml`和`v2ex-public-receipt.json`。外部正文和合成模型不提交Git。

CI使用[现有工作流](https://github.com/Joho6666/opportunity-radar/actions/workflows/ci.yml)，覆盖`feat/**`和PR；当前提交远程结果以[PR #2](https://github.com/Joho6666/opportunity-radar/pull/2)检查及本轮交付的精确HEAD CI链接为准。不能拿旧提交绿灯代表新提交。

没有将免登录开发检查当成生产Supabase登录验证，没有将语义页面检查当成截图视觉验收。真实客户转化、人工筛选时间和每条核实线索成本未测量。

## 追加：客户端关键词、时效、热度与帖子评分

本次起点 `c72c099`。客户端新增共享采集配置：包含/排除词、任意/全部命中、1–720小时、发布时间/来源更新时间、时间未知策略、公开作者/累计评论信号、最低互动和已取得结果热度排序；配置通过新增JSONB列持久化。手动收件箱实际传递条件，雷达编辑清除过时查询计划，策略绑定幂等请求和国内续页。详情显示实际查询，不再显示页面虚构的AI策略。

修复：刚采到的未知时间不再冒充最新帖子；正文明确“接单私信我”不能被泛化外包标题翻成买方；同帖互动数会更新但不重复产生客户，也不覆盖人工复核；手动雷达不会被Scheduler自动执行。获客分和热度分独立，卖家/排除/关闭/不适用获客分为0；缺少个性化预算门槛等输入采用中性分并说明。

| 验证 | 本次结果 |
|---|---|
| 全部后端 | 343项通过，0跳过；包括真实PG/pgvector、Redis、迁移/RLS、配额/幂等/并发、策略持久化、国内空页续页绑定、重复观察与人工复核保留；1条Starlette上游弃用警告 |
| 前端 | lint、TypeScript、41项Vitest、Next生产构建通过；Zustand测试环境存储警告仍有，无失败 |
| Ego隔离功能 | 8014/3003独立合成QA身份，5条固定原文；24小时、排除教程、包含PPT、作者与评论筛选→保留2条；旧帖1/未知时间1/教程1分别被过滤；买方与广告分开，广告热度99而获客0 |
| Ego保存与费用 | 创建雷达→编辑至48小时/排除教程和广告→刷新仍保留→运行显示真实订阅地址查询；付费按钮被价格/总开关阻断 |
| 主应用 | 8013/3002已重新加载；`/ready`为PostgreSQL，主身份没有写入测试帖子或客户；累计批次仍0次/$0预留，剩余5次/$0.50，实际账单未知 |
| 未验证 | 没有国内真实接口/热门端点调用、真人身份核验、近期评论时间、真实留出分类效果或客户成交验证；没有截图视觉验收。热度仅是已取得内容的排序，不是平台热榜 |

新增SQL为 `202610140002_collection_policy.sql`，不修改历史迁移、删除业务数据或合并main。使用说明：[KEYWORD_COLLECTION](KEYWORD_COLLECTION.md)。原始日志为Git忽略的 `outputs/keyword-backend-test.log`、`keyword-lint.log`、`keyword-typecheck.log`、`keyword-frontend-test.log`、`keyword-build.log`、`keyword-ego-result.json`、`keyword-runtime-before.json`和`keyword-runtime-after.json`。旧CI链接仅说明旧提交，本次以PR最新精确HEAD检查为准。
