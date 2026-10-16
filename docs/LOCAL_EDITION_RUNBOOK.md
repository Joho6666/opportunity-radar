# Opportunity Radar Local Edition 使用手册

Local Edition 是 macOS 本机单用户工作台。Next.js、FastAPI、Worker 和 Scheduler 通过用户级 LaunchAgent 运行；PostgreSQL/pgvector 与 Redis 使用独立 Docker Compose Project。`scripts/local.sh start` 会将仓库代码及已安装依赖同步到 `~/Library/Application Support/Opportunity Radar/app`，再从该目录构建和运行，以兼容 macOS 对 `~/Documents` 中代码的后台访问限制。私有配置、日志、配对票据和备份保存在同一 Application Support 目录下。界面与 API 仅绑定 `127.0.0.1`；浏览器的规范地址为 `http://localhost:3004`。默认关闭付费 API、自动 AI、Mock 采集、本地模型和自动数据删除。

## 首次准备

需要 macOS、Node.js 20+、Python 3.12+ 与 Docker Desktop。先使用开发分支，安装依赖并准备私有配置：

```bash
git switch feat/local-edition
npm ci
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

私有配置位于 `~/Library/Application Support/Opportunity Radar/config/local.env`，目录权限应为 `700`，配置文件权限为 `600`。它不进入 Git。当前机器已存在权限合规的 Local Edition 配置；新安装时需要创建该文件，至少提供这些字段：

```text
LOCAL_DB_PASSWORD=<strong random password>
LOCAL_PROXY_TOKEN=<64 or more random characters>
LOCAL_SESSION_SECRET=<64 or more random characters>
LOCAL_USER_ID=<the UUID belonging to the isolated local database owner>
LOCAL_PG_PORT=54330
LOCAL_REDIS_PORT=6380
LOCAL_API_PORT=8015
LOCAL_UI_PORT=3004
LOCAL_DATABASE_URL=postgresql+psycopg://postgres:<url-encoded-password>@127.0.0.1:54330/opportunity_radar
LOCAL_REDIS_URL=redis://127.0.0.1:6380/0
```

`LOCAL_DB_PASSWORD` 必须与 `LOCAL_DATABASE_URL` 中 URL 编码后的密码一致。恢复已有备份时，沿用同一备份配套的 `LOCAL_USER_ID`，避免把另一用户的数据暴露到工作台。不要复用审计/开发数据库；Local Edition 应连接已从备份恢复的独立本地库。启动脚本会拒绝远程数据库地址、弱凭据、内存存储、`AUTH_DISABLED=true`、付费/自动 AI/Mock/自动删除配置。

## 启动、停止和查看状态

在仓库根目录执行：

```bash
scripts/local.sh start
scripts/local.sh status
```

打开 `http://localhost:3004`。首次登录前另开终端运行 `scripts/local.sh pair`，把一次性配对码输入本机页面。配对码十分钟有效且使用一次后作废。不要通过端口转发、共享链接或反向代理暴露该页面。停止后重新启动会再次从当前仓库同步代码与依赖；`app/` 是专用运行副本，不要在其中存放数据库、备份或手工文件。

```bash
scripts/local.sh logs
scripts/local.sh logs api
scripts/local.sh stop
```

`stop` 会卸载 Local Edition 的用户级服务并停止 Local Edition Compose 数据库/Redis；不删除容器卷或业务数据。它不会停止审计、开发或其他 Compose Project。主要端口为 UI 3004、API 8015、PostgreSQL 54330、Redis 6380；端口冲突时脚本会失败，先用 `status`/`lsof` 检查，不要盲目改连其他数据库。

## 备份与恢复

备份保存在 `~/Library/Application Support/Opportunity Radar/backups/`，目录权限为 `700`，备份、清单及配套私有配置权限为 `600`。备份命令先用 `pg_dump` 生成 PostgreSQL 一致性快照，再验证归档可读性：

```bash
scripts/local.sh backup
```

先在 Local Edition 数据库中进行隔离恢复验证。该命令会创建一个新的恢复测试数据库，不覆盖当前数据库：

```bash
scripts/local.sh restore-test "/absolute/path/to/local-<timestamp>.dump"
```

若要从备份切换到恢复出的数据库，先执行 `scripts/local.sh stop`，再用配套的 `local-<timestamp>.env` 恢复对应数据库名和 `LOCAL_USER_ID`。实际恢复到一个**全新数据库名**的示例：

```bash
COMPOSE_PROJECT=opportunity-radar-local
RESTORE_DB=opportunity_radar_restore_20261016
BACKUP="/absolute/path/to/local-<timestamp>.dump"
docker compose -p "$COMPOSE_PROJECT" -f docker-compose.local.yml \
  --env-file "$HOME/Library/Application Support/Opportunity Radar/config/local.env" \
  exec -T postgres createdb -U postgres "$RESTORE_DB"
docker compose -p "$COMPOSE_PROJECT" -f docker-compose.local.yml \
  --env-file "$HOME/Library/Application Support/Opportunity Radar/config/local.env" \
  exec -T postgres pg_restore --exit-on-error --no-owner -U postgres \
  -d "$RESTORE_DB" < "$BACKUP"
```

验证迁移记录、关键表和用户归属后，再将私有 `LOCAL_DATABASE_URL` 的数据库路径切换到新库并重启。保留旧库及原卷直到确认恢复结果；不要对现有数据库执行 `DROP DATABASE`、`docker compose down -v` 或覆盖式恢复。备份含有业务数据与私有配置，应仅保存在本机加密磁盘或受控备份介质。

## 使用范围与验收边界

- 首页、雷达、情报 Inbox 和设置是 Local Edition 主入口；云端 CRM、报价与技能路由保留，但不在本地导航中展示。
- 新建雷达默认通用情报、手动运行、零预算。定时任务需显式开启；Local Scheduler 只处理本地用户明确开启的计划。
- 自动采集不加载模型。设置为“按需”后，用户可对单条内容发起分析；付费接口仍需原有授权、精确价格和配额，否则回退规则结果并说明原因。
- 已验证的免费来源流程使用 Hacker News RSS；它证明当前 RSS 适配器与公开源可端到端工作，不代表所有来源都已验证。真实付费调用次数为 0。
- 当前代码通过隔离 QA 完成迁移、API/CSRF/Host、队列、UI 和 Compose 持久化检查。真实 Local 实例的 `start`/`stop`、配对前访问控制、备份与新数据库隔离恢复已通过；macOS 重启后的 LaunchAgent 恢复尚未验证。当前页面仍需用户在本机运行 `scripts/local.sh pair` 后才能查看数据。Ego Browser 截图超时，视觉截图复核缺口保留；性能前后对比和 7 天连续运行也尚未完成。

更完整的风险与测试记录见 [Local Edition 审计](LOCAL_EDITION_AUDIT.md)。
