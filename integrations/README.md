# integrations

## dsh-plugin — DeepSeek Harness 接入

`dsh-plugin/` 是一个 DeepSeek Harness bundle，把本机 **Local Edition** 以「只读工具 + 技能 +
右侧栏看板入口」的形式接进 Harness。

### 安装

由 Harness 的 `plugin_manager` 以本目录**绝对路径**安装（`install_bundle`），安装后：

- 7 个只读工具：`radar_status`、`radar_sources`、`radar_list`、`radar_results`、
  `radar_runs`、`radar_identity`、`radar_token_status`
- 技能 `opportunity-radar`（`assets/opportunity-radar.md`）
- 输入框停靠区的「机会雷达看板 / 新窗口」两个按钮

### 换机器要改的地方

`dsh-plugin/cordis.patch.yml` 里的 `config` 是**本机专用**路径，换环境需按实际位置修改：

| 键 | 含义 |
|---|---|
| `repoPath` | 本项目仓库根目录 |
| `appHome` | 私有运行目录（默认 `~/Library/Application Support/Opportunity Radar`） |
| `apiPort` / `uiPort` | 默认 8015 / 3004 |

`dsh-plugin/client.js` 中的看板地址固定为 `http://localhost:3004`；若改 `uiPort`，需同时改
`BOARD_URL`。

### 已知限制

- 侧栏 iframe 要求用 `http://localhost:<GUI 端口>` 打开 Harness；用 `127.0.0.1` 会被
  `middleware.ts` 的 `sec-fetch-site` 校验返回 403（此时插件会自动改用「新窗口」）。
- 看板是嵌入的独立网页，主题不跟随 Harness；iframe sandbox 无 `allow-modals`。
- 插件只读：不暴露 `new` / `run` / `key`，不触发付费采集，不输出令牌明文。

更多细节见 [dsh-plugin/README.md](dsh-plugin/README.md)。
