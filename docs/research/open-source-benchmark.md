# Open Source Benchmark — 开源项目研究与集成策略

> 用途：为 opportunity-radar → Money Intelligence OS 升级提供设计参照。
> 原则：**不机械复制**。能 pip 装的嵌入 worker，需要登录态/反爬军备竞赛/AGPL 的跑 sidecar，只取模式的不抄代码。任何集成不得破坏现有 FastAPI/PG/Redis/Arq/Next.js 架构。

## 1. hunterr198/opportunity-radar

同栈前身项目：FastAPI + PG + Redis + React，扫 20+ 开发者社区做每日简报。

- **What to learn**
  - `BaseCollector → CollectedPost` 统一契约 + 每源一个类；与我们方向一致，可对照它的字段集查漏。
  - **4 级 LLM 漏斗**：relevance filter → clustering → deep analysis → briefing，且 deep analysis 共享前级结果；这是"不能每条都调强模型"的现成参考。
  - 模型分级（fast/standard/premium）+ 自动 fallback 链；Langfuse 式 trace。
  - trend tracking：occurrence counts + score history + snapshots 表——我们 Trend/Snapshot 设计的直接印证。
- **What not to copy**：仅 4 commits / ~6 stars 的单人新项目，工程成熟度不构成依赖理由；其 briefing 仍以"发现帖子"为单位，没有付费证据/供给缺口层。
- **How to integrate**：只抄模式与字段设计（MIT），不做依赖。
- **License / risk**：MIT，无风险；维护性弱是唯一警告。

## 2. NanmiCoder/MediaCrawler

中文社媒采集（小红书/抖音/快手/B站/微博/贴吧/知乎），posts+comments。

- **What to learn**：CrawlerType（keyword/precision/指定创作者）的任务语义；store 插件化（可指到 MySQL/JSON → 指到我们 ingest API）；增量爬取配置。
- **What not to copy**：**AGPL-3.0 + 额外声明禁止商用**——代码不可进入本项目；签名 JS 逆向 + 每平台登录态维护是它自己仓库里的常驻斗争，不该拖进 Intelligence Engine。
- **How to integrate**：**独立 sidecar 容器**，自有配置/凭据，产出写入统一 RawDocument ingest 端点或直接写 PG 一张独立 raw 表；平台接口变化只动 sidecar。
- **License / risk**：许可证不可商用（仅个人使用研究）；合规红线：仅采集用户有权访问的公开数据、遵守平台条款与限额，不将规避风控作为系统能力。

## 3. obris-dev/openmagpie

自托管 social listening，LLM 给自然语言"Watch"打分。

- **What to learn**（本次研究中最重要的思想来源）：
  - **Feed / Watch / WatchAction 三层分离**：Feed=源+条目流水（轮询成本只付一次），Watch=订阅某 Feed 的自然语言监听器（正/负信号、阈值），Action=semantic_filter/webhook。N 个监听器共享一次轮询。
  - 监听器 = NL 描述 → LLM 判每条 post 是否匹配 + 阈值；7B 模型 1–3s/条即可用——**自然语言 Listener 的最低成本实现路径**。
  - at-least-once webhook + 接收端按 `source:external_id` 幂等去重；每次投递留审计（WatchActionDelivery）。
  - 单进程 single-flight ticker（poll/trigger/drain/flush 四阶段）可由 cron 驱动，"no flock or singleton infrastructure"——贴合我们 Arq cron。
- **What not to copy**：Django 技术栈；每条 post 过 LLM 的成本模型（我们用漏斗先筛）。
- **How to integrate**：sidecar，webhook 打进我们的 ingest API；其 `openmagpie-schema` Pydantic 包（独立发版）可直接 pip 复用做契约对齐。
- **License / risk**：Apache-2.0（ee/ 目录商用保留），活跃维护。

## 4. VladUZH/harken

轻量 social listening：源适配器 → 归一化 Mention → 词典范式情感 → TF 主题 → SQLite → 告警。

- **What to learn**：
  - 适配器契约极小：`fetch()` + 可选 `fetch_page(cursor)`，**cursor 持久化实现可恢复分页/回填**——collector 扩展时照此设计。
  - Mention 统一记录 + content-hash 去重；**alert episode + cooldown 持久化**（告警不抖动）。
  - 默认本地词典（零 LLM），LLM 只是可选增强——与我们"Embedding/规则/小模型优先"原则一致。
- **What not to copy**：SQLite 单文件；TF 聚类太粗（我们用 embedding 聚类）。
- **How to integrate**：MIT，适配器与 Mention 模式可直接借鉴进我们的 collector 层；或作为小 sidecar。
- **License / risk**：MIT，早期阶段（31 stars）。

## 5. DIYgod/RSSHub

"万物皆可 RSS"：数千个站点的路由插件生态。

- **What to learn**：namespaced route 注册表（path/handler/example/radar 规则）；per-route Redis 缓存与 TTL；**radar 规则自动把任意站点 URL 映射到 feed** 的发现机制。
- **What not to copy**：AGPL-3.0——不把它的路由代码并入本项目；TS/Node 不进我们 Python worker。
- **How to integrate**：**首选 sidecar**：跑一个官方镜像实例，我们的 RSSHubAdapter 把每条路由当作一个免费适配器源（`/rsshub/:route/:params`）拉 Atom/JSON。**不修改其源码**即不触发 AGPL 传染；一个实例瞬间获得数千源，覆盖公众号/微博/B站等公开路由。
- **License / risk**：AGPL（隔离使用安全）；路由质量参差，需 healthcheck 兜底。

## 6. unclecode/crawl4ai

LLM 友好爬虫：任意站点 → 干净 Markdown/JSON。

- **What to learn**：**声明式优先**——`JsonCssExtractionStrategy`/`JsonXPathExtractionStrategy`/`RegexExtractionStrategy` 零 LLM 抽取，LLMExtractionStrategy 只做兜底（这正是我们 Stage 0/1 的省钱哲学）；BrowserConfig/CrawlerRunConfig 分离；`arun_many` 内存自适应并发；resume_state 深爬恢复。
- **What not to copy**：headless 浏览器依赖不进 API 镜像。
- **How to integrate**：二选一——(a) pip 装进 Arq worker 镜像（需装 Playwright/Chromium 层）；(b) 跑其 Docker server 用 REST API（更推荐，blast radius 小）。GenericWebCollector 底层用它。
- **License / risk**：Apache-2.0 + **署名条款**（badge/文字署名要求），84.8k stars 极活跃。

## 7. dgtlmoon/changedetection.io

网站变化监控：Watch（URL 监视器）→ 过滤 → 快照 diff → 触发器 → 通知。

- **What to learn**（Change Detection Engine 的参考设计）：
  - **顺序不可颠倒：先选择/提取要关注的 token（XPath/CSS/JSONPath/jq），再 diff，再触发**——直接 diff 全页噪声爆炸。
  - Watch 是一等公民：per-watch 代理/请求头/时区调度/条件触发（文本出现/消失、价格阈值、regex）。
  - 快照历史存储 + word/line/char diff + 价格趋势图——我们的 Snapshot/MetricHistory 同构。
  - Browser Steps（登录/点击后再比对）。
- **What not to copy**：Flask 全家桶；以"单 URL"为单位不适合我们的"关键词/主题"粒度。
- **How to integrate**：sidecar + 全 REST API 驱动（程序化建 watch、收 webhook、轮询其 RSS）；针对"关键产品页价格/版本变化"类精细监控用它，粗粒度趋势我们自己算。
- **License / risk**：Apache-2.0，34.8k stars 极活跃。

## 8. TenderCrawler（digiwhist/master）

欧盟公共采购采集流水线（H2020 DIGIWHIST）。

- **What to learn**（最老但最干净的模式）：
  - **staged tables + 队列只传记录 ID**：Raw → Parsed → Clean → Matched → Master 各阶段独立 worker、独立 PG 表，每行 = 元数据 + JSON blob；每阶段可重启、可审计、幂等。
  - **Matched/Master 阶段做实体解析**——"同一个真实招标的多条记录"被显式合并成 master 记录。这正是我们 EventCluster 的祖先模式。
- **What not to copy**：Java 8 / RabbitMQ 3.6 老栈；**CC BY-NC-SA 4.0 非商用 + share-alike，代码一字不可用**。
- **How to integrate**：只取架构模式（我们用 PG 表 + Arq 队列 + ID 传递即可复刻 staged pipeline）。
- **License / risk**：非商用许可证 + 项目已死（~2017），纯模式参考。

## 9. JobSpy（speedyapply/JobSpy，`pip install python-jobspy`）

聚合 LinkedIn/Indeed/Glassdoor/ZipRecruiter 等，输出 typed `JobPost` DataFrame。

- **What to learn**：typed 输出 schema（title/company/salary interval/currency/date_posted/is_remote）；per-site 已知限速文档化（LinkedIn ~10 页/IP、Glassdoor ~30 req/IP）——**把限速当操作常态设计**；`hours_old` 参数直接对应我们的 freshness 需求；round-robin 代理。
- **What not to copy**：pandas 依赖可裁剪；Google Jobs 通道已坏——上游断了要能熔断。
- **How to integrate**：**直接 pip 嵌入 Arq job**（MIT），行数据归一化为 RawDocument（source=job_board, signal hint=hiring/salary）；配 `hours_old` 做增量。
- **License / risk**：MIT，活跃维护（days ago），~4.4k stars。

## 10. vladkens/twscrape

X/Twitter 内部 GraphQL 采集，账号池 + 端点级锁。

- **What to learn**：**SQLite 账号池 + 每账号按端点 lock-until-reset**——账号是资源，限流状态是资源状态；代理优先级链（api.proxy → env → account proxy）；`_raw` 变体便于审计原始响应。
- **What not to copy**：内部 API 随时碎；多账号 ToS 风险；默认遥测（`TWS_TELEMETRY=0` 关闭）。
- **How to integrate**：可直接 pip 嵌入（MIT, async），`accounts.db` 放共享卷；但**X 数据源建议先走 RSSHub/官方 API 通道**，twscrape 作为后期可选模块，且必须尊重平台条款——不把对抗封禁作为系统能力。
- **License / risk**：MIT；法律/ToS 风险自担，运维上是 cookie 供应链。

---

## 横切架构结论（8 条）

1. **在 collector 边界归一化，立刻 hash 去重**：所有成熟项目都用统一 typed record（CollectedPost/Mention/JobPost）+ source:external_id 唯一键 + content hash，然后才允许任何昂贵操作。→ 我们的 RawDocument 表照此设计，`mark_raw` 必须 upsert 而不是 insert-ignore。
2. **适配器契约要小，重试/限流/凭据进共享基础设施**：Harken 只要 `fetch()/fetch_page(cursor)`；反例是 MediaCrawler 的每适配器自带签名/代理逻辑。账号/代理池应是一等服务（twscrape 的 per-endpoint lock）。
3. **轮询成本付一次，监听扇出免费**：openmagpie 的 Feed/Watch 分离 = 我们 RadarRun(采集) 与 SignalListener(订阅) 的分层依据。
4. **便宜检测器级联在前，LLM 在后**：hash → 声明式抽取 → 词典/统计 → 小模型阈值判断 → 强模型只看聚类幸存者；模型分级 + fallback 链是标配。
5. **变化检测 = 不可变快照 + 先过滤后 diff + typed 触发器**：changedetection.io 的过滤→diff→触发顺序 + 冷却期 + episode 持久化。
6. **实体解析值得独立阶段和独立表**：digiwhist 的 staged tables + ID 传递，让"聚合同一事件"成为显式 master 记录而非查询时技巧。
7. **非 Python/高风险 sidecar，纯 Python 直接嵌入**：RSSHub/changedetection/crawl4ai-server/openmagpie/MediaCrawler 容器化隔离（许可证、反爬军备、Chromium 都关在笼子里）；JobSpy/twscrape/crawl4ai-lib 可 pip。
8. **反爬军备是运维问题不是架构问题**：per-source 熔断、Redis 请求配额、可恢复 cursor、优雅降级到 RSS/API 通道。合规底线：只采公开/有权数据，遵守 robots/条款/限额，不做规避验证码与访问控制的能力。

## 集成路线图映射

| Phase | 用到什么 |
|---|---|
| P1 数据基础 | harken 的 cursor 契约、digiwhist 的 staged tables、openmagpie 的 source:external_id 幂等 |
| P2 Signal+Cluster | openmagpie 的 Watch 语义、digiwhist 的 matched/master 模式 |
| P3 Trend+Change | changedetection.io 的过滤→diff→触发、hunterr 的 snapshot 表 |
| P4 Gap+MoneyScore | hunterr 的模型分级 fallback 链 |
| P6 Source 扩展 | RSSHub sidecar、crawl4ai server、JobSpy pip、MediaCrawler sidecar（合规前提下） |
| P7 Daily Intelligence | openmagpie 的 at-least-once 投递审计 |
