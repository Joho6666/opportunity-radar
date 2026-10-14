# TikHub 关键词获客：受限实采与离线回放

2026-10-13。本轮接入已有 Evidence Inbox、Opportunities 和 Pipeline；没有建立第二套客户库。

## 本轮状态

密钥已写入本机 Git 忽略的 `backend/.env`，权限 `600`；没有进入源码、前端或响应样本。`backend/.dockerignore` 排除环境文件，避免密钥进入构建上下文。密钥配置成功不等于鉴权已验证。

**真实 TikHub 请求 0，费用预留 US$0，保存响应 0，买方/人工核实/联系/回复/报价/成交均 0，实收暂无数据。** 服务商实际费用未知。官方计费页按接口分别定价，公开页未确认本轮三个端点的具体单价；Marketplace 需要登录。因此真实开关保持关闭，不使用未知价格的鉴权或价格查询请求试探。

| 次序 | 来源 | 操作 | 当前状态 |
|---|---|---|---|
| 1 | 小红书 | 找人做PPT | 等待官方 USD/request |
| 2 | 微博 | 求助 Word排版 | 等待官方 USD/request |
| 3 | 抖音 | 找人剪视频 | 等待官方 USD/request |
| 4 | 小红书 | 找人开发小程序 | 同第 1 个端点 |
| 5 | 小红书 | 第 1 页的有效续页 | 仅有完整会话时执行 |

知乎继续只有离线契约验证。真实响应、买方产出和线上准确率均未验收。

## P0 安全边界和根因修复

- PostgreSQL `billing_batches` 在账户事务锁和批次行锁下累计扣减：最多 5 次、US$0.50、单次 US$0.10。跨日、换 run 或重启不会恢复。它附加于已有全局、范围、每日和单次授权。
- 调试批次只允许 `evidence` 人工范围和指定来源；既有 Radar 授权也不能使用它。Firecrawl、LLM、embedding、Scheduler 不在本轮范围内。
- 每次网络尝试先预留。错误/超时照计，付费传输无自动重试。没有官方端点价格则拒绝；显式空价格表不会退回统一价格。保守报价仍不能保证服务商绝不超收，若报告高于预留则后续额度使用较大实际值。
- 原 HTTP 错误会再次完成账单并抹掉费用。现在只完成一次；重复完成保留已有费用/token，异常 usage 结构按未知处理。
- 采集层曾把配额拒绝的 429 改成 502；现在保留计费状态码，并使用安全提示，不暴露上游凭据。
- 付费手动采集必须提供 `request_id`。同账户、同 ID 和同来源/关键词/分页/时效/批次重复提交返回保存结果；改变参数为 409。并发或崩溃遗留 running 返回 409，不自动重发；失败结果也保存。不同 ID 是新的尝试，仍消耗批次额度。
- 新表启用 RLS，响应/批次/收据只允许用户读自己的记录；客户端不能写入，分页会话后台专用。服务端仍须使用 tenant 查询和安全数据库角色。

## P1 响应、会话和回放

`HttpFetcher` 在解析前保存 `provider_responses`：关联 `billing_calls` 的来源和端点、关键词、服务商 request ID、HTTP 状态与采集时间。响应递归清除密钥字段、cookie、授权、cache URL 及已配置密钥值；不保存请求 Authorization。解析失败保留样本。没有 HTTP 响应的超时只有账单预留，无法保存不存在的响应。

小红书保存 `search_id`、`search_session_id`；抖音保存 `cursor`、`search_id`、`backtrace`。前端只得到 opaque 字符串 `next_cursor`，服务端按账户、来源、关键词和 24 小时有效期解析。会话字段缺失时不猜测下一页。空页和全部过期页仍返回有效续页。

新鲜度以发布/更新中较新时间判断；缺失时间明确未知。视频和评论具有独立 ID、原文和作者；重复运行复用既有证据身份。真实误判应基于保存响应修复，不用额外付费请求替代回放。

## P2 使用流程

打开 Evidence Inbox 的“采集”，选择个人文档或企业视频与开发预设，编辑关键词。采集前展示接口价格及累计余额；价格未知或未启用则阻止开始。下一页需再次确认。

默认查看买方待复核结果；阅读公开原文、预算未知项、发布时间、分类理由与风险后人工纠正/核实。然后转入已有 Opportunities / Pipeline，编辑三档报价和沟通草案，手动记录联系、回复、报价、跟进和真实成交。没有自动发送消息或自动成交。

失败重试保留同一请求 ID；“准备新的采集请求”明确开始另一尝试。页面重新加载不会自动采集。来源漏斗按采集收据、唯一证据、买方预测和人工核实统计；离线回放不写入漏斗。

## 本机操作

已有环境不要覆盖 `.env`、重置数据库或删除卷。本机 API 使用 8013，前端 3002，已有 PostgreSQL 54329。生产继续参照 [README](../README.md) 的 JWT 配置。

在 `backend/.env` 合并以下非敏感项，官方价取得之前保持空表和关闭：

```dotenv
PAID_BATCH_ID=tikhub-debug-20261013
TIKHUB_ENDPOINT_PRICES_JSON={}
PAID_API_ENABLED=false
PAID_DAILY_REQUEST_LIMIT=5
PAID_DAILY_COST_LIMIT=0.5
ENABLE_AI_CLASSIFICATION=false
```

取得 Marketplace 的当前单价后，仅把已核实端点的 USD/request 写入价格 JSON，并保存报价出处和时间。三个路径：

```text
/api/v1/xiaohongshu/app_v2/search_notes
/api/v1/weibo/web_v2/fetch_realtime_search
/api/v1/douyin/search/fetch_general_search_v1
```

批次初始化只执行已明确授权的本轮计划，重复运行不能补充旧批次额度。在 `backend` 执行：

```bash
../.venv/bin/python ../scripts/authorize_tikhub_batch.py
AUTH_DISABLED=true APP_ENV=development USE_IN_MEMORY_STORE=false \
CORS_ORIGINS=http://127.0.0.1:3002,http://localhost:3002 \
PAID_API_ENABLED=false REDIS_URL='' INCLUDE_MOCK_COLLECTOR=false \
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --no-proxy-headers
```

另一终端在根目录执行：

```bash
NEXT_PUBLIC_AUTH_DISABLED=true NEXT_PUBLIC_DEMO_MODE=false \
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8013 \
npm run dev -- --hostname 127.0.0.1 --port 3002
```

在 `backend` 做无付费预检和只读回放：

```bash
../.venv/bin/python ../scripts/tikhub_keyword_probe.py /absolute/probe.json
../.venv/bin/python ../scripts/replay_tikhub_batch.py /absolute/replay.json
```

`--execute` 只在当前单价已核实且管理员按已有授权启用后使用；运行后关闭真实开关。脚本遇错误立即停止，不要求用完额度。没有续页则少于 5 次。价格查询/鉴权请求同样不得脱离网关和本轮次数上限。

可用 `replay_tikhub_batch.py ... --labels /absolute/labels.json` 读取人工标注：`[{"id":"evidence_id","category":"buyer","split":"development"}]`。开发集/holdout 按 ID 分开，输出每类 Precision/Recall/F1 和混淆矩阵；重复 ID 或未知记录拒绝。回放是预测复现，不代表人工验证。

## 验证证据与剩余项

- 完整 pytest **288 通过，0 跳过**，使用真实 PostgreSQL/pgvector、Redis 和迁移；HTTP 测试禁止真实网络。覆盖并发额度、跨日/重启等价检查、重复提交、错误费用保留、RLS、空页/过期页会话及两类业务的合成闭环。仍有一条上游 Starlette 弃用警告。
- lint、TypeScript、**33 项 Vitest**、生产构建及隔离 Compose 健康/PG 与 Redis 重启持久化均通过。本轮开发和构建使用 `.next-dev` / `.next`，解决生产构建覆盖运行中 dev chunks 导致空页的问题；ESLint 同时排除生成目录。
- Ego Browser 检查预设、未知价阻止收费、桌面/390px 无文档横向溢出、断网显示错误和重试恢复。截图接口超时，未完成截图视觉验收。
- 既有 64 条中英文合成开发回归集五类 P/R/F1 均 1.0，混淆矩阵仅对角线为 16/12/12/12/12。它在开发中使用过；新增真实标注 0、holdout 未测，不能宣称准确率提高。
- 下轮优先取得官方单价 → 有限实采 → 保存响应 → 人工标注开发/留出集 → 无网络修复 → 本人核实真实需求并跟进。真实 Supabase 登录、线上部署、共享来源限流/watermark 仍需独立验收。

仅提交独立开发分支并更新 draft PR #2，不合并 main。代码回退可 revert 小步提交；数据库使用新增表，回退代码时保留证据和账单记录，不删除业务历史。

参考：[官方计费](https://tikhub.io/pricing)、[小红书接口](https://docs.tikhub.io/420136398e0)、[抖音接口](https://docs.tikhub.io/370212773e0)。
