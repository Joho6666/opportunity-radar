# @local/opportunity-radar

DeepSeek Harness 插件（bundle）：把本机 **Opportunity Radar Local Edition** 以「只读工具 + 技能 + 右侧栏看板入口」的形式接入 Harness。

它**不启动、不替代**雷达的 Next.js / FastAPI / PostgreSQL / Redis 服务，只读地访问已有数据，
并在服务未运行时给出可执行的离线诊断；可视化看板则借 Harness 自带的右侧栏 Browser tab 呈现。

其中 6 个工具代理仓库里的 `scripts/or` CLI；`radar_list` 直接调用后端只读的
`GET /api/agent/radars`（CLI 没有 `radars` 子命令），用于拿到 `radar_id` 的正规入口。

## 组成

| 文件 | 作用 |
|---|---|
| `index.js` | Host 插件：注册 9 个只读工具 + 1 个付费搜索工具 + 1 个技能 provider |
| `client.js` | Client 插件：在输入框停靠区放「机会雷达看板」+「新窗口」两个入口，文案走 Client locale |
| `cordis.patch.yml` | 插入一行 `opportunity-radar`，配置仓库路径、App Home 与端口 |
| `assets/opportunity-radar.md` | 技能正文（用法、安全红线、degraded/offline 排障步骤） |
| `docs/DETAIL.md`、`docs/DETAIL.zh.md`、`docs/preview.svg` | 插件详情页的功能图（中英各一份文档，共用一张无文字 SVG） |
| `locale/*.json` | 插件管理器显示用的中英文标题、描述与 `meta.detail` |
| `icon.svg` | 原创雷达图标 |

## GUI：右侧栏看板

`client.js` 通过官方 API `ctx.sidebarRight.openTab('browser', { params: { url } })`
打开 `http://localhost:3004`，由已启用的内置包
`@deepseek-ai/dsh-client-ui-sidebar-browser` 承载：Web 版是带 sandbox 的 iframe，
Desktop 版是 Electron `<webview>`。看板的页面（雷达列表、情报条目、设置等）可直接使用，
不需要重写 React 组件，也不需要额外的 Host 同源代理。

两个已知边界：(1) 主题 / 深浅色不跟随 Harness 的 `--dsw-alias-*` token，这是复用现成应用的
取舍；(2) 内置 iframe sandbox 不含 `allow-modals`，看板里依赖 `window.confirm` 的原生确认框
会被浏览器拦掉，涉及确认的写操作请在「新窗口」里完成。

入口按钮在输入框下方停靠区（`conversation.composer.dock`）；点击后看板在右侧栏展开，
可与当前会话并排查看。按钮点击失败会显示「打开失败，点此重试」并在控制台告警。
旁边还有一个「↗ 新窗口」按钮：`window.open` 走顶层导航（`Sec-Fetch-Site: none`），
不受下面的 403 限制，两种主机名下都能用；若浏览器拦截弹窗，按钮会转为失败提示。

**⚠️ 访问地址决定侧栏能否显示**：3004 的 `middleware.ts` 拒绝 `sec-fetch-site: cross-site`。
实测结果（端口随 Harness 会话变化，关键在主机名）：

| Harness 页面地址 | iframe 到 `localhost:3004` | 结果 |
|---|---|---|
| `http://localhost:<GUI 端口>` | same-site | ✅ 完整看板正常渲染 |
| `http://127.0.0.1:<GUI 端口>` | cross-site | ❌ 403 `Local Edition only accepts direct loopback requests.` |

所以**请用 `http://localhost:<GUI 端口>` 打开 Harness**（若提示重新认证，用 `dsh web` 打印的
URL）。插件已做自适应：在 `localhost` 下自动弹出侧栏；在 `127.0.0.1` 下既不自动弹，
主按钮也改为直接在新窗口打开，不让你点出一个必然 403 的侧栏。

插件激活时会**一次性自动打开**侧栏看板（`localStorage` 键 `opportunity-radar:auto-open:v3`
防止重复），之后只靠按钮，刷新页面不会再弹。

## 工具

9 个只读工具 + 1 个付费搜索工具：

`radar_status`、`radar_search`、`radar_sources`、`radar_list`、`radar_results`、`radar_runs`、
`radar_run_detail`、`radar_provider_diagnose`、`radar_identity`、`radar_token_status`。

**`radar_search` 是唯一会花钱的工具**：`{query, confirm: true}` → 建普通模式雷达 → 跑一轮 →
等到结束 → 返回结果（时间/来源/标题/链接）。单次花费受 provider 配置上限约束（默认 $0.10）。
它建的是 `required_terms` 为空的普通雷达，绕开 `scripts/or new` 写死的 `lead_hunt` + 业务必需词
（否则「单片机毕设」这类内容帖会被「视频/电商/带货」过滤光）。agent 接口没有删除入口，搜索建的
雷达会保留（去界面删）。

其余全部只读，绝不输出令牌明文，**不暴露** `key` / 预算修改 / 删雷达 / 改身份等写操作。
终端付费运行仍需人工 `scripts/or run <雷达ID> --confirm`。

`radar_list`、`radar_run_detail`、`radar_provider_diagnose` 直接走 HTTP（`/api/agent/radars`、
`/api/agent/runs/{id}`、`/api/agent/sources`，CLI 没有对应子命令），用同一份 loopback 令牌鉴权，
令牌值不进入返回值、日志或错误信息。

结果过大时不再「只留 3 条」：`radar_list` 只投影列表字段（完整配置用 `radar_id` 读单个），
`radar_sources` 只投影关键字段并保留全部平台行，两者都全量保留并标记 `reduced: true`；
`radar_results` 把 `raw_text` 截到 900 字符（`truncated: true`），只有仍超 16 KB 才按条数
裁减并提示分页。

返回值统一为：

```jsonc
{
  "ok": false,
  "state": "degraded",             // online | degraded | offline | misconfigured
  "command": "radar_status",
  "exit_code": 0,
  "http_status": 503,
  "request_id": "...",
  "api_base": "http://127.0.0.1:8015",
  "repo": "...",
  "data": {},
  "error": { "code": "", "message": "" },
  "hint": "API 进程可达但返回 HTTP 503：后台依赖 ... up -d --wait postgres redis",
  "duration_ms": 1432,
  "checks": { "script": true, "localEnv": true, "runtimeEnv": true,
              "agentToken": true, "apiReachable": true, "apiReady": false,
              "apiStatus": 503, "uiReachable": true, "uiStatus": 403 }
}
```

状态含义：`online` 正常（或服务健康、但本次请求参数被拒）；`degraded` API 进程在但
PostgreSQL/Redis 没起来；`offline` 端口不可达；`misconfigured` 配置或鉴权问题。

## 配置

`cordis.patch.yml` 的 `config` 支持：

- `repoPath` — 雷达仓库根目录（必填）
- `appHome` — 本机私有运行目录，默认 `~/Library/Application Support/Opportunity Radar`
- `apiPort` / `uiPort` — 默认 8015 / 3004（`uiPort` 只影响 Host 侧的探活；Client 按钮里的
  看板地址是 `http://localhost:3004`，改端口需同时改 `client.js` 的 `BOARD_URL`）
- `python` — 可选，默认优先 `<repo>/.venv/bin/python`，回退 `python3`
- `timeoutMs` — 单次 CLI / HTTP 调用上限，默认 12000

也可用环境变量 `OPPORTUNITY_RADAR_REPO` / `OPPORTUNITY_RADAR_HOME` /
`OPPORTUNITY_RADAR_PYTHON` / `LOCAL_API_PORT` 覆盖。

## 当前机器状态（2026-11-16 复核）

服务在线：4 个 LaunchAgent（`KeepAlive` + `RunAtLoad`）、PG16 + Redis 7（Compose 项目
`opportunity-radar-local`），`http://localhost:3004` 与 `127.0.0.1:8015/ready`
（`{"status":"ready","storage":"postgresql"}`）均健康。私有 `config/local.env` /
`local-runtime.env` / `agent-token.json` 均已就位（600 权限）。原数据保住：库
`opportunity_radar_copy`、owner `00000000-0000-0000-0000-000000000001`、
13 个雷达 / 309 条证据。7 个工具实测 `ONLINE`。

**2026-11-16 曾出现 `degraded`**：Docker Desktop 退出导致 PG/Redis 容器消失，API 返回
`503 not_ready`，而 4 个 LaunchAgent 仍显示 running。只拉起容器即可恢复，**不需要**重启
LaunchAgent 或重置令牌：

```bash
open -a Docker      # 等守护进程就绪
cd /Users/joho/Documents/Codex/2026-10-13/opportunity-radar-ai-agent-github-https/work/opportunity-radar
docker compose -p opportunity-radar-local -f docker-compose.local.yml \
  --env-file "$HOME/Library/Application Support/Opportunity Radar/config/local.env" \
  up -d --wait postgres redis
```

`radar_status` 的 `state=degraded` 就是这一情形；`state=offline` 才是 LaunchAgent 没跑
（用 `LC_ALL=C scripts/local.sh status|start`，提示「服务已注册」时先 `stop`）。

**仍未配置**：`provider-config.json`（TikHub key）缺失，各平台 `available=false`、
`paid_api_enabled=false`；若旧 key 曾以明文形式传递过，请先在 TikHub 后台轮换，再把新 key
粘贴到设置页，或放入 600 权限文件后用工作区的 `verify-tikhub-key.mjs` 走官方不计费端点测活。

排查命令需加 `LC_ALL=C`（`scripts/local.sh` 在 UTF-8 locale 下有中文变量名 bug）。
恢复已有数据时库名必须沿用 `opportunity_radar_copy`、`LOCAL_USER_ID` 沿用原值，
否则旧数据会被「藏起来」；详见仓库 `docs/LOCAL_EDITION_RUNBOOK.md`。

## 安装

由 `plugin_manager` 的 `install_bundle` 以本目录绝对路径安装到当前 profile；
不要手工编辑 profile 的 `package.json` / `cordis.patch.yml`，也不要在 profile 目录里跑 pnpm。
