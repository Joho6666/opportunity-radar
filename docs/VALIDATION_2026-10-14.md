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
