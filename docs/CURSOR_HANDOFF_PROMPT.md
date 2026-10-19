# 机会雷达（Opportunity Radar）· Cursor 交接提示词

> 把下面整段复制给 Cursor，在仓库根目录打开新会话后粘贴。建议先让它读 docs/ 再动手。

---

你在一个已经跑起来的真实项目上工作，不要重新规划架构，先读懂再改。

## 一、项目是什么

**机会雷达 Opportunity Radar**：本机单用户运行的「抓单工具」，定位是 **agent 优先、人也能操作**——agent 通过 CLI/HTTP API 驱动，人在网页上手动操作。

核心用途：围绕用户自己的业务（AI 电商视频/广告、视频复刻、小程序开发、办公文档、工作流自动化），从公开平台按关键词+时间+地区+目标人群找出**真实采购需求**，人工核实后跟进。不是舆情工具、不是资讯聚合器。

用户业务关键词示例：`找人做视频`、`电商 视频 外包`、`家居 找视频拍摄`、`圣诞 视频 制作`。

## 二、仓库与运行环境

- 仓库：`/Users/joho/Documents/Codex/2026-10-13/opportunity-radar-ai-agent-github-https/work/opportunity-radar`
- 分支：`feat/local-edition`，HEAD `8c17b8d`
- **当前有 92 个文件未提交（54 个新增）**，全部是已完成的功能改动。第一步先确认基线：`git status`、跑测试，然后提交到分支（建议拆成「本地会话/抓单流程/平台接入/身份设定/Agent API」几个 commit）。不要在未确认前回滚任何文件。
- 运行方式：macOS LaunchAgent + Docker Compose（项目名 `opportunity-radar-local`）
  - UI `http://localhost:3004`（Next.js）
  - API `127.0.0.1:8015`（FastAPI）
  - PostgreSQL/pgvector `127.0.0.1:54330`，库名 `opportunity_radar_copy`
  - Redis `127.0.0.1:6380`
- 运行副本：`~/Library/Application Support/Opportunity Radar/app`（`scripts/local.sh start` 会把仓库 rsync 过去再构建启动，改完必须重新 start 才生效）
- 私密配置：`~/Library/Application Support/Opportunity Radar/config/local.env`（600/700），含 TikHub 密钥、预算上限。**永远不要打印、提交或把密钥写进日志。**

## 三、技术栈

- 前端：Next.js App Router + TypeScript + Tailwind，测试 Vitest
- 后端：FastAPI + SQLAlchemy + PostgreSQL(pgvector) + Redis/Arq worker + APScheduler
- 数据源：TikHub（付费，21 个平台入口）+ 免费公开源（GitHub / Hacker News / RSS）
- 计费：自建 `billing_gateway`（预留 + 账本 + 价格 receipt），默认手动触发、有预算上限

## 四、已经做完的功能（别重做，也别回退）

1. **本机免配对**：打开 `localhost:3004` 直接进工作台，`/pair`、`/login` 都重定向 `/dashboard`；首次访问/清 Cookie 自动建 HttpOnly 会话。保留 loopback + Host/Origin + CSRF 校验，**不要重新引入配对码**。
2. **抓单流程**：业务预设 → 平台 → 关键词（1–3 个）→ 时间（24h/3d/7d/30d/自定义）→ 地区 → 目标角色 → 需求意图 → 本地/远程模式 → 手动运行 → 结果。默认 7 天、手动、只取首屏。
3. **21 个 TikHub 平台入口**，真实状态分级：
   - 14 个「可运行·已实测」：小红书、抖音、B站、快手、Lemon8、皮皮虾、Reddit、Threads、TikTok、X、微博、YouTube、知乎、微信搜一搜
   - 微信公众号：走微信搜一搜 `article` 垂类（已实测 35 条）
   - 微信视频号：搜一搜 `video` 垂类 + `fetch_video_detail` + `fetch_video_share_url` 生成短链（每条 +$0.02，实测拿到 `weixin.qq.com/sph/...`）
   - Telegram：指定频道内搜索（`fetch_channel_search`，$0.001/频道）
   - LinkedIn：招聘信号（`search_jobs`，$0.05/次，分类为 `hiring_signal`，**不是买方需求**）
   - 今日头条：链接导入（`get_article_info`，$0.001/条，不支持关键词搜索）
   - Instagram、西瓜视频：实测不可用（400 / 上游恒空），保留原因
4. **平台级关键词适配**：同一轮不同平台用不同词（小红书保留长短语，抖音自动截成 2–4 字核心词），查询预览按平台显示实际用词。
5. **每平台统计 + 0 条告警**：结果页显示「请求数 / 返回条数 / 入库条数」，0 条标红并提示原因，提供「换短词重跑」入口（需再次确认付费）。
6. **硬验收**：任一选中平台 0 条 → 整轮 `status=partial`，页面显示「未达标」，不得显示成功。
7. **个人身份设定**：业务能力、目标角色、服务地域（含远程标记）、默认时效、平台偏好、买方关键词、排除词、业务匹配词、报价风格。新建抓单自动预填，后端 `apply_identity_defaults` 真正参与筛选。
8. **界面内配置 API**：TikHub 密钥可保存/替换/删除（只显示掩码）、测试连接（免费端点）、预算上限可调（单轮 / 每日 / 每日请求数 / 是否需确认）。
9. **Agent 接口**：
   - `GET/PUT /api/agent/identity`、`GET/POST /api/agent/radars`、`POST /api/agent/radars/{id}/run`（必须 `confirm:true`）、`GET /api/agent/radars/{id}/results`、`GET /api/agent/sources`、`GET /api/agent/runs`、`POST /api/agent/provider/test`
   - Bearer token（`/api/local/agent/token` 生成/吊销，页面只显示掩码），仅 loopback，无 token 一律 401，不回退网页会话
   - CLI：`scripts/or`（sources / identity / new / run --confirm / results --json / runs / status / token / key test）
   - 文档 `docs/AGENT_API.md`；Hermes skill `opportunity-radar`、`opportunity-radar-local-validation`
10. **测试基线**：后端 `514 passed / 2 skipped`；前端 `129 passed / 26 files`；lint / typecheck / build 全绿。

## 五、关键文件地图

- 前端页面：`features/local-workspace.tsx`（新建抓单/雷达）、`features/local-inbox.tsx`（结果）、`features/local-dashboard.tsx`、`features/local-identity.tsx`、`features/local-provider-settings.tsx`、`features/local-agent-settings.tsx`
- 前端逻辑：`lib/lead-hunt.ts`（关键词/条件/预估）、`lib/identity.ts`、`lib/local-providers.ts`、`lib/manual-radar.ts`、`lib/local-agent.ts`
- 后端采集：`backend/app/collectors/tikhub_catalog.py`、`tikhub_catalog_adapter.py`、`tikhub_modes.py`、`tikhub_cn.py`、`tikhub.py`、`registry.py`、`tikhub-platforms.json`、`tikhub-live-verification.json`
- 后端服务：`backend/app/services/{radar_run_service,hunt_conditions,billing_gateway,price_evidence,identity_defaults,provider_verify}.py`
- 后端 API：`backend/app/api/{local,radars,agent,intelligence}.py`
- 数据模型：`backend/app/schemas/{domain,hunt,identity}.py`、`backend/app/repositories/{base,memory,postgres}.py`
- 迁移：`supabase/migrations/`（已有 202610160001_local_identity_profile、202610160002_agent_api）
- 脚本：`scripts/local.sh`（start/stop/status/logs/backup/restore-test）、`scripts/or`、`scripts/sync-tikhub-catalog.py`
- 文档：`docs/LOCAL_EDITION_RUNBOOK.md`、`docs/AGENT_API.md`

## 六、接下来要做的（按优先级）

**P0｜把四个受限平台在应用里真跑一遍**
- 微信视频号 1 条、Telegram 1 频道、今日头条 1 链接、LinkedIn 1 次，走应用内 `run --confirm`，确认入库、分类、链接可点、每平台统计正确。
- LinkedIn 上一次应用内运行是修复前，入库 0；修复后只有回放验证，需要付费重跑确认（约 $0.05）。
- 修这些运行中暴露的任何问题，并补测试。

**P1｜默认平台分组与体验**
- 平台分两组默认值：抓单组（小红书、微博、知乎、微信搜一搜）、参考组（抖音、快手、B站、YouTube、TikTok）。新建时只预选抓单组。
- 结果页「换短词重跑」做成真实闭环：只对该平台、幂等键、确认付费、跑完对比新旧结果。
- 0 条告警要能区分原因：关键词过长 / 无匹配 / 接口不可用 / 字段缺失。

**P2｜能力补齐**
- 微信「综合」垂类要么实测通过，要么从 UI 移除（现在标“未单独实测”）。
- Telegram 增加频道发现（`fetch_channel_search` 搜频道）+ 相似频道（`fetch_similar_channels`）。
- 今日头条增加评论抓取（`app/get_comments`），把「求推荐」类评论作为需求信号。
- 结果导出 CSV / 剪贴板；同一雷达多轮运行的新增与消失对比。

**P3｜可选**
- 视频号分享链生成条数可配置（1–3），并确保费用估算与上限校验一致。
- 定时调度：**默认关闭**，开启需显式授权并单独预算；不做自动私信/评论/关注。

## 七、硬性约束（违反即错）

1. 不得绕过 `billing_gateway`；价格未知的端点禁止运行；单轮 ≤ $0.10、每日 ≤ $1 / 20 请求是默认上限，可在设置页调整但必须有校验。
2. 不得自动发私信、评论、关注、加好友；不得自动定时付费采集。
3. 密钥只能掩码展示，不得出现在 API 响应、日志、前端包里。
4. 任何"可用"状态必须有真实证据（request_id + 可复现结果）；接口存在 ≠ 可用。**禁止把 0 条结果报成功。**
5. 保留本机免配对设计，不得重新引入 `/pair` 流程；不得把服务绑定到 0.0.0.0。
6. 不做数据库删除、`docker compose down -v`、覆盖式恢复；备份按 runbook 走。
7. 采集遵守平台条款：不绕验证码/风控，不收集未授权个人信息，不把公开内容用于骚扰。

## 八、工作方式

- **TDD**：先写失败测试再实现；每个新平台能力必须补参数映射 + 解析 + 时间过滤 + 费用估算测试。
- 测试命令：
  - 前端：`npm test`、`npm run lint`、`npm run typecheck`、`npm run build`
  - 后端：`cd backend && ../.venv/bin/python -m pytest -q`
- 部署：`./scripts/local.sh stop && ./scripts/local.sh start`（先读脚本；**绝不 `down -v`**），然后验证：
  - `curl -L http://localhost:3004/` → 200 且最终落在 `/dashboard`
  - `./scripts/or status`、`./scripts/or sources`
  - 运行副本与源码一致
- 查库：本机没装 psql，用 `docker exec opportunity-radar-local-postgres-1 psql -U postgres -d opportunity_radar_copy -At -c "..."`
- 浏览器验证：用 Ego Browser（一个持久 TaskSpace），不要用 Playwright/Selenium。

## 九、已知的坑（别重复踩）

- **抖音**：长短语几乎不召回。实测 `找拍摄`→8 条、`家居`→1000 条，而 `家居 找视频拍摄`→0、`圣诞 视频 制作 求推荐`→0。抖音是内容场，不是需求场，定位应是「参考内容」。
- **微信视频号**：搜索结果的 `hashDocID` 当 `object_id` 会返回 200 但 `share_url=null`（照样扣费）。必须 `exportId → 详情 → object_id → 分享链`，单条耗时约 30 秒，客户端超时设 ≥60s。
- **LinkedIn**：官方限流池，偶发 400；可以重试但必须计入请求数与预算。
- **Ego Browser**：标签页初始视口可能是 0×0，fill/click 会报「not visible in viewport」→ 先 `Emulation.setDeviceMetricsOverride`；截图常超时，用 DOM 快照。定位器只支持 `text=`/`css=`/`role=` 形式。
- **代理**：本机 FlClash `127.0.0.1:7890` 会偶发挂掉，TikHub/GitHub 直接 TLS 断；国内站点正常。抓取失败先查代理。
- **账单**：TikHub 不回传实际结算金额，账本 `actual_micros` 为 null 属正常，不要当成 0。

## 十、验收标准

- 后端测试 ≥ 514 passed，前端 ≥ 129 passed，lint/typecheck/build 全绿。
- 本地 `http://localhost:3004` 打开即用，无配对；新建抓单能保存、能运行、能看到按平台统计。
- 每个声称「可用」的平台都有 request_id 和至少一次真实入库记录；未验证的在 UI 上明确标注。
- 任一平台 0 条必须体现为「未达标」，不允许显示成功。
- 所有付费调用都有 receipt、预留金额与预算校验；密钥无明文泄漏。

## 十一、交付方式

每次改动请给出：改了什么（文件级）、测试真实输出数字、部署验证证据（HTTP 状态/API 读回/心跳）、是否产生付费调用及金额、遗留问题。不要用「应该可以」代替验证。
