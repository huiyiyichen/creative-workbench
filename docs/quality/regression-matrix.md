# 质量回归矩阵与缺陷清单（#5）

> 建立日期：2026-09-27（基于 main @ 7203847 的证据核查）；同日独立复核修正了 §一 OAuth 命令、§三 第 1/5 行命令与证据口径、依赖漏洞条目的公告计数口径。
> （历史说明：早期条目使用过 D-1~D-10 编号，已退役；已关闭 issue/PR 评论中的旧编号即指本节对应条目。）
> 本文件是 [Issue #5](https://github.com/fxbin/TopicEye/issues/5) 要求的「单一缺陷/复现矩阵」，后续缺陷与回归条目**只在此追加**，避免散落在聊天记录和 issue 评论里。

## 一、运行安全守则（先读再跑）

后端测试的 conftest 有 autouse `clean_tables` fixture，会对 `DATABASE_URL` 指向的库执行
`TRUNCATE ... CASCADE` 并终止其它连接。**直接对开发库跑 `pytest tests/` 会清空数据。**

| 场景 | 命令 | 说明 |
|---|---|---|
| 后端全量（推荐） | `make test-backend` | 自动起一次性 PG 容器（127.0.0.1:5433，`topiceye_test` 库），跑完即删；可用 `TEST_PG_PORT` 换端口并行 |
| 针对性 PG 测试 | 见下表各条目 | 自建一次性库（`CREATE DATABASE ..._tmp`）后以 `DATABASE_URL` 指向运行，用完 `DROP DATABASE` |
| OAuth 修复隔离测试 | `DATABASE_URL='postgresql+asyncpg://dummy:dummy@localhost:5432/never_connect' uv run --no-sync python -m pytest tests_oauth_patch/` | 全 mock，不连任何数据库；必须 `python -m`（`tests_oauth_patch/` 无 `__init__.py`，裸 `pytest` 解析不到 `app` 包，`tests/` 因是包不受影响） |
| 前端 | `cd frontend && npx tsc --noEmit && npm run test:coverage` | 类型门禁 + 单测/覆盖率 |

## 二、缺陷清单（confirmed defects）

每条按 #5 要求的十个维度登记；复现与修复细节以 issue 正文为准，此处只留索引和当前状态。

### 旧提交 ZIP 未同步新启动入口和项目名称
- **症状**：源码目录已更新，但旧 ZIP 仍包含旧启动脚本；配置样例和 Docker 默认名称仍使用上游项目名。
- **边界**：提交产物、启动配置、项目目录名；已存在的数据库与本地配置保留。
- **修复**：新提交包使用 `creative-workbench` 项目目录，重新从已审查源码生成；启动变量、Docker 名称和配置样例统一为新名称。
- **验证**：新 ZIP 的目录、启动文件、ASCII/CRLF、隐私文件和 500 MB 上限检查。
- **状态**：2026-10-08 已生成新的提交包，682 个文件、298003267 字节，低于 500 MB。包内项目目录 `creative-workbench`，启动入口 ASCII/CRLF，启动文件和目录无旧项目名；隐私文件扫描与视频哈希校验通过。实际启动后页面返回 200，仓库已同步命名修正。

### 提交源码的 Windows 启动入口无法在新目录使用
- **症状**：CMD 误解析 `DisableDelayedExpansion`，并报告缺少 `backend/.venv/Scripts/python.exe`。
- **环境/前提**：脱敏源码目录，运行环境与数据库未打包；批处理使用 UTF-8 中文和 LF 换行。
- **复现**：双击提交目录中的 `start.cmd`。
- **期望 vs 实际**：准备本地环境后启动；旧入口依赖开发机既有运行文件。
- **边界**：Windows 批处理、依赖安装、独立 PostgreSQL 初始化；已有 `.env` 和数据保留。
- **严重度**：P1；**复现性**：新源码目录可复现。
- **回归验证**：PowerShell 语法解析；CMD ASCII/CRLF 检查；脱敏源码目录首次启动、重复启动、页面及健康接口冒烟。
- **owner**：当前本地开发分支。
- **状态**：修复并验证通过。2026-10-08 在脱敏源码目录完成 Python/npm 安装、官方 PostgreSQL 下载、独立库初始化、迁移与前端构建；`/studio` 返回 200、`/health/ready` 返回 ready。随后以 CMD 运行 `start.cmd` 再次成功，配置哈希保持不变。前端类型检查及评分/LRC 23 项测试通过，实际界面截图已查看。

### 日报异步生成的占位记录与后台结果错位
- **症状**：点击生成后持续显示 GENERATING；同日另有一条 ERROR 结果，前端读取不到。
- **环境/前提**：当前本地 PostgreSQL、新库无分析数据，异步 `/generate-version` 路径。
- **复现**：生成端点返回 id=2；后台产生 id=3，id=2 保持 GENERATING。
- **期望 vs 实际**：后台更新请求返回的记录，页面读取该记录；实际按日期/截止时间创建了另一条记录，页面读取“最新日报”。
- **边界**：日报任务记录、时间窗口与客户端轮询。
- **严重度**：P1；**复现性**：当前异步路径可重复。
- **回归测试**：`tests/test_daily_generation_task.py` 验证绑定记录 ID、UTC 窗口、完成/失败状态、未配置模型、归属、非法参数和超时中断；与 `test_source_seed.py` 共 11 项通过，测试使用独立 `topiceye_test_daily`，未清理运行库。
- **owner**：当前本地开发分支。
- **状态**：修复通过。运行库从 HN RSS 采集 20 条真实内容，首页可见；浏览器点击日报生成后结束等待并显示未配置 AI 模型，实际请求和结果使用同一 id。前端类型、构建、相关文件 ESLint（无错误）、后端相关 Ruff 与分层检查通过。桌面和移动视口已查看，运行服务保持开启。尚未配置真实模型，未声称 AI 日报已生成成功。

### Windows 本地启动读取 Alembic 配置失败
- **症状**：后端 lifespan 中断，8102 端口未监听，前端接口代理返回连接失败。
- **环境/前提**：Windows 的 locale 编码为 GBK，Alembic 1.14 以 locale 编码读取 UTF-8 ini。
- **复现**：启动当前后端，读取 `backend/alembic.ini` 第三行的非 ASCII 标点。
- **期望 vs 实际**：配置在本机可读取；实际抛出 UnicodeDecodeError。
- **边界**：配置文件注释与启动迁移，不改变数据库迁移行为。
- **严重度**：P1；**复现性**：GBK locale 下 always。
- **回归验证**：ini 用 ASCII/GBK 均可解码；独立 PostgreSQL 上完成 baseline 至 head 迁移；`/health/live` 与 `/health/ready` 返回 200；前端首页、`/studio` 及 contents/favorites/sources/categories 代理请求均为 200。
- **owner**：当前本地开发分支。
- **状态**：本地运行修复与验证通过。完整创作与冗余模块清理仍在开发中，不能由启动成功推导为整个项目完成。

### 管理员权限测试泄漏真实 DuckDB attach — #22 ✅ 已修复关闭（2026-09-27）
- **症状**：权限测试通过后，下一个测试在 fixture setup 阶段挂起（exit 124）
- **环境/前提**：PG 套件，`clean_tables` autouse
- **复现**：连续跑 `tests/test_admin_api_permissions.py` 与后续任意 PG 测试（修复前）
- **期望 vs 实际**：权限测试应 hermetic；实际曾打开真实 DuckDB→PG attach
- **边界**：测试 / duckdb_service 单例 / PG 连接
- **严重度**：P0；**复现性**：always
- **回归测试**：`pytest tests/test_admin_api_permissions.py`（7 passed @ 2026-09-27）
- **owner**：#22（修复 PR #29，`FakeAnalytics` 注入）

### 收藏测试触发真实后台向量重建 — #27 ✅ 已修复关闭（2026-09-27）
- **症状**：收藏测试后、content pipeline 测试前 fixture 挂起 180s+
- **复现**：连续跑 `test_content_favorite_api.py` → `test_content_pipeline.py`（修复前）
- **期望 vs 实际**：API 测试不启动生产后台任务；实际 `trigger_vector_rebuild` 泄漏跨库事务
- **边界**：测试 / interest_vector_service / PG 事务
- **严重度**：P0；**复现性**：always
- **回归测试**：连续执行 `pytest tests/test_content_favorite_api.py tests/test_content_pipeline.py`（15 passed @ 2026-09-27）
- **owner**：#27（修复 PR #33 测试隔离 + PR #56 生产侧任务追踪/优雅关闭）

### 分析恢复 / inflight 去重 / post-sync drain 回归簇 — #35 ✅ 已修复关闭（2026-09-27）
- **症状**：六项测试失败（权限契约过时 / 旧同步后处理函数引用 / DB 连接跨事件循环复用）
- **复现**：`pytest tests/test_analysis_recovery.py tests/test_analysis_jobs_persistence.py tests/test_analysis_notification_permissions.py`
- **期望 vs 实际**：六项应全绿；实际三种独立根因
- **边界**：测试契约 / analysis job 持久化 / 事件循环
- **严重度**：P0；**复现性**：always（修复前）
- **回归测试**：同上复现命令（47 passed @ 2026-09-27）
- **owner**：#35（修复 PR #38 / #43 / #47；组合验证 PR #48 已关闭未合并，由新鲜运行取代）

### DuckDB Today Picks 查询契约回归 — #45 ✅ 已修复关闭（2026-09-27）
- **症状**：四项 Today Picks 查询测试失败
- **根因**：测试 fixture 临时表缺 `content_type` 列（契约重构后未跟上），非生产 SQL 回归
- **复现**：`pytest tests/test_duckdb_service.py -k today_picks`
- **边界**：测试 fixture / DuckDB 查询契约
- **严重度**：P1；**复现性**：always（修复前）
- **回归测试**：同上（4 passed @ 2026-09-27）
- **owner**：#45（修复 PR #54）

### 依赖安全漏洞 — #4 ✅ 已修复关闭（2026-09-27）
- **症状**：pip-audit / npm audit 报漏洞
- **环境**：uv.lock 锁定生产依赖 + 前端 package-lock（2026-09-27 修复后复扫）
- **期望 vs 实际**：无未处置高危漏洞；修复后前后端均 0 公告（后端 `No known vulnerabilities found`，前端 `found 0 vulnerabilities`）
- **边界**：依赖 / 部署镜像 / CI security-scan 作业
- **严重度**：P0；**复现性**：always
- **回归测试**：CI `security-scan` 作业自 PR #68 起全绿；main push 自动复验由 #65 引入
- **owner**：#4（前端 #66：`npm audit fix` + vitest 5.0.2 + @types/node 22；后端 #67：cryptography 50.0.1；#68：fastapi 0.141.1 + starlette 1.7.0）
- **日志/证据**：`uvx pip-audit -r <uv export --frozen 产物> --no-deps --disable-pip`；修复前口径（后端 12 条唯一公告 + 前端 6 条）见 #4 评论存档

### OAuth 回调经 URL fragment 传完整凭证 — #63 ✅ 已修复关闭（2026-09-27）
- 安全收窄项：fragment 不再含 access token，仅带 provider/expires_at；凭证只经 HttpOnly cookie；前端回调页不消费任何凭证参数（旧 #token= 链接落地但不消费）。
- 回归测试：`tests_oauth_patch/test_oauth_fix.py` GitHub/Google 双 mock 断言 fragment 无 token。owner：#63（修复 PR #80；真实 provider E2E 待人工回归）。

### 管理员第三方账号手动绑定流程缺失 — #64 ✅ 已修复关闭（2026-09-27）
- 已实现 step-up 绑定流程：`POST /auth/oauth/{provider}/bind/start`（重输密码→绑定意图入 session，TTL 10min）+ 回调绑定分支（会话本人校验、未验证邮箱拒绝、双冲突防护）；绑定成功不建新登录会话。
- 回归测试：`tests_oauth_patch/test_oauth_bind.py` 六场景（含会话不匹配与无意图回退）。owner：#64（修复 PR #81；设置页 UI 与解绑端点为后续）。

### /health/ready 判定门恒真 — #71 ✅ 已修复关闭（2026-09-27）
- 症状：ready 的 oltp 判定读自纯元数据 dict（`database_diagnostics` 不做连通性探测），恒为 True，`not_ready` 分支不可达；OLTP 不可达仍返回 ready。
- 边界：health 路由 / 部署路由层；复现性 always。
- 回归测试：`tests/test_health_endpoints.py` 四态路由级（正常 / 调度器禁用 / DuckDB 降级 / OLTP 不可达 503 + /health 别名）。owner：#71（Parent #6，修复 PR #75）。

### 三处无主 create_task — #72 ✅ 已修复关闭（2026-09-27）
- 症状：`scheduler.py:1204/1205` 启动 rescan/恢复任务与 `daily_reports.py:294` 日报后台——无引用、无异常收集、不受停机管理；日报 `mark_error` 失败被裸 `except: pass` 吞掉可永卡 GENERATING。
- 边界：scheduler 启动路径 / daily_reports / lifespan 停机序。
- 回归测试：`tests/test_task_registry.py`（异常记日志注销 / drain 取消清空 / 超时告警不抛出）。owner：#72（Parent #6，修复 PR #76：`app/core/task_registry.py` 收编三处 + mark_error 留痕）。

### 优雅停机链中断点 — #73 ✅ 已修复关闭（2026-09-27）
- 症状：`_cache_warmup_task` 非 CancelledError 异常会中断后续全部清理步骤；jieba 预热 await 无超时且 `to_thread` 不可取消，可挂死停机；整体停机无 deadline。
- 回归测试：`tests/test_shutdown_prewarm.py`（异常不外抛且留痕 / jieba 超时不挂死 / 正常与已取消路径）。owner：#73（Parent #6，修复 PR #77：`_shutdown_prewarm_tasks`）。

### 管理后台批量操作静默失败 — #88 🔧 修复完成待合并（2026-09-29）
- 症状：`sources/page.tsx` `handleBatchToggle` 逐条 `sourcesApi.update` 的 `catch` 只写 `console.error`，循环结束后**无条件** `setSelectedIds(new Set())` + `fetchSources()`。批量停用 30 个信源、其中 5 个失败时，UI 表现为「全部处理完」，失败的 5 个仍按原状态继续采集并污染内容池，而操作者无从察觉。
- 环境/前提：生产数据，仅管理员账号；`PATCH /api/v1/sources/{id}` 任一请求失败（网络抖动 / 404 / 5xx）即可触发。
- 复现：信源管理页多选 ≥2 个信源 → 批量停用 → 中途阻断网络或使其中之一更新失败 → 观察 UI 与浏览器控制台对照。
- 期望 vs 实际：期望逐条失败上抛 UI、成功项与失败项分别反馈；实际只有 console 记录，UI 无任何差异。
- 边界：仅前端 `sources/page.tsx`；**不改写入语义**，只改失败可见性与选择态保留。
- 严重度：P0（数据污染且不可察觉）；**复现性**：conditional（依赖批量中至少一条更新失败）。
- 回归测试：`npx vitest run src/app/admin/sources/_batch-utils.test.ts`（11 条）。选择态重算与结果文案已抽为纯函数 `_batch-utils.ts`，`.tsx` 只做调用；已用变异测试验证——把实现改回旧行为（失败进 console + 无条件清空）后 3 条转红，其中包含「中途新勾选项被静默丢弃」这条。
- owner：#88。

### Webhook 日志页读数口径撒谎 — #88 🔧 修复完成待合并（2026-09-29）
- 症状：`webhook-logs/page.tsx` 的 `successCount` / `failCount` 只统计**当前页** 30 行，却与全局 `total` 并排渲染成同款 Badge。读者会把「本页 2 失败」除以「共 1240 条」读成 0.16% 失败率，真相是第 5 页可能还躺着 40 条。更严重的是失败徽章以 `failCount > 0` 为条件渲染——翻到失败为 0 的分页时「失败」整枚徽章消失，**徽章的缺席本身制造错误信念**。
- 环境/前提：任何有 ≥1 页推送日志的生产数据。
- 复现：`/admin/webhook-logs` 翻页，观察任意分页顶部的 Badge 组。
- 期望 vs 实际：期望页内计数带明确口径标注、失败数显式渲染；实际两者视觉同层且口径未标注，失败为 0 时徽章缺席。
- 边界：仅前端展示层；**不改数值来源**，不改 API。
- 严重度：P1（对交付健康度给出错误读数，不直接损坏数据）；**复现性**：always。
- 回归测试：`npx vitest run src/app/admin/webhook-logs/_scope-utils.test.ts`（15 条）。徽章**构造**（口径标注 + 无条件渲染）已抽为 `buildSummaryBadges` 纯函数并被锁住。
  - **覆盖边界（独立复核 M3 实证，勿夸大）**：修复前 `summarizeLogPage` 的 6 个公式与修复后逐字相同，只测它**证明不了**本缺陷；真正的修复是把「渲染成什么」下沉成 `buildSummaryBadges`，其断言（失败徽章 0 时仍存在且为中性色、全部徽章带「本页」/「全部」口径词、空页只留 1 枚）才真正对应缺陷本身。JSX 渲染层仍无组件测试（见下方遗留项）。
- owner：#88。

### 管理后台面包屑缺 4 项映射 — #88 🔧 修复完成待合并（2026-09-29）
- 症状：`AdminTopBar.tsx` 的 `ADMIN_PAGE_LABELS` 只有 10 条，侧边栏 `ADMIN_NAV_ITEMS` 有 15 项。`prompts` / `scoring-dashboard` / `evidence` / `webhook-logs` 四页无映射，`findPageLabel` 回退显示兜底文案「管理」，与侧边栏自相矛盾。（另经核实：概览卡片 13 张、面包屑 10 条、侧边栏 15 项三份目录互相矛盾，说明分类从未被写下来过。）
- 环境/前提：always。
- 复现：访问上述四页之一，观察顶栏面包屑第二段。
- 期望 vs 实际：期望显示真实页面名；**实际显示「概览」**（独立复核更正：实现者原记为「管理」有误——旧实现里 `/admin` 本身是前缀匹配键，`/admin/prompts` 先命中 `/admin/` 落成「概览」，压根走不到兜底文案。真实症状比原记录更严重：不是泛化文案，而是谎称在概览页）。
- 边界：前端。实际改动含 `AdminTopBar.tsx` + `AdminSidebar.tsx` 重构 + 新增 `src/lib/admin-nav.ts` 单一事实源（实现者原记为「仅 AdminTopBar.tsx」，有误）。
- 严重度：P2（说错话的廉价困惑，不改变任何决定的对错）；**复现性**：always。
- 回归测试：`npx vitest run src/lib/__tests__/admin-nav.test.ts`（13 条）。导航清单与面包屑映射合并到 `src/lib/admin-nav.ts` 单一事实源，映射由清单派生；`nav-checklist` 等价断言（壳内每项都有映射、label 与清单逐项一致）已在其中，漏项即红。顺带修掉一个被测试抓出的旧行为：`/admin/任何未知路径` 曾因壳根前缀匹配被判成「概览」，现已回退兜底。
- owner：#88。

## 三、关键流程基线（9 项）

状态标记：✅ = 2026-09-27 在 main @ 7203847 新鲜复跑通过；📋 = 现有套件覆盖、未逐项复跑（跑全量即覆盖）；🔧 = 修复完成待合并（PR 已开、CI 绿、独立复核非 pass 尚未全部处置）。

| # | 关键流程 | 验证命令（backend/ 下，遵守§一） | 状态 |
|---|---|---|---|
| 1 | 登录 / 会话 / OAuth | `pytest tests/test_auth.py tests/test_oauth_service.py`；隔离版 `python -m pytest tests_oauth_patch/`（须 `python -m`，见 §一） | ✅（隔离套件 27/27（oauth_fix 8 + account_link_security 19）；auth + oauth_service 19 passed） |
| 2 | 信源创建 → 同步 → 内容落库 | `pytest tests/test_source_api.py tests/test_source_seed.py tests/test_api_source_scraper.py tests/test_content_pipeline.py` | ✅（2026-09-27 全量 exit 0，#68 后） |
| 3 | 抽取 / 富化 / 分类 | `pytest tests/test_enricher.py tests/test_classifier_contract.py tests/test_content_labeling.py tests/test_content_summary.py tests/test_recognizer.py tests/test_tag_normalization.py` | ✅（同上） |
| 4 | 分析任务入队 → 恢复 → 完成/失败 | `pytest tests/test_analysis_recovery.py tests/test_analysis_jobs_persistence.py tests/test_job_tracker.py tests/test_analyses_api.py` | ✅（47 passed） |
| 5 | Today Picks 查询 / 标记 / 反馈 | `pytest tests/test_duckdb_service.py -k today_picks` + `pytest tests/test_today_picks.py tests/test_feedback_signal.py`（`-k` 是全局过滤器，不能与其它文件混在同一条命令，否则 feedback 用例被静默过滤） | ✅（today_picks 4/4；today_picks + feedback 25 passed） |
| 6 | 热榜同步 / 快照 | `pytest tests/test_trending_pipeline.py tests/test_trends_api.py tests/test_trend.py` | ✅（2026-09-27 全量 exit 0，#68 后） |
| 7 | DuckDB 不可用 → OLTP 回退 | `pytest tests/test_duckdb_service.py tests/test_latest_analysis_queries.py tests/test_digest_fallback.py tests/test_db_backend.py` | ✅（同上） |
| 8 | 启动迁移 → 调度器 → 优雅停机 | `pytest tests/test_migrations.py tests/test_lifespan_duckdb_init.py tests/test_cache_warmup.py tests/test_startup_warmup_policy.py tests/test_interest_vector_lifecycle.py tests/test_task_registry.py tests/test_shutdown_prewarm.py tests/test_rescan_selfheal.py tests/test_health_endpoints.py` | ✅（2026-09-27 全量 exit 0 ×2；#6 生命周期补充已并入，PR #74~#78） |
| 9 | 前端主界面状态 | `cd frontend && npx tsc --noEmit && npm run test:coverage` | ✅（2026-09-27 tsc 通过 + 147/147 + coverage 通过，#66 vitest 5） |

**全量基线**：`make test-backend`（一次性 PG 容器）+ 前端命令。2026-09-27 全量转绿：#67（cryptography 50.0.1）与 #68（fastapi 0.141.1 / starlette 1.7.0）各跑一次全量均 exit 0；main push CI（#65 引入）@ `9da010e` 起全绿，#2 的全量转绿 DoD 达成。同日 #6 生命周期加固波（PR #74~#78）最终状态全量 exit 0（含新增 5 个生命周期测试文件；#77 所引的中间态全量日志被截断无结论行，以本最终状态运行覆盖实证）。

## 四、维护规则

1. 新确认缺陷：先在此登记（十个维度），再开 issue；关闭 issue 时同步本表状态。
2. 关键流程新增/重构：同步更新§三的命令列。
3. 每次稳定化迭代（如 #2）收尾时，把「📋 未复跑」条目刷成当次结果。

## 五、创作工作台交付（2026-10-04）

- **范围**：选题 → 成稿 → 成片 → 作品库；内容模板、视觉风格、表现方案、输出媒介分层；视频制作提示词；音频 + LRC MV；Codex 工程制片。
- **后端**：`studio_projects`、`studio_revisions`、`studio_assets`、`studio_artifacts` 采用增量迁移 `a71c9e604b22`；项目版本乐观锁、确认版本、素材权利确认和可播放产物校验由服务端校验。
- **风格与模板**：`backend/app/services/studio_catalog.py` 提供 7 个模板和 7 个风格包；`production_prompt()` 输出分镜、镜头、声音、字幕、负向约束和制作交付要求。
- **MV**：`studio_lrc.py` 解析多时间戳、offset、UTF-8 LRC；`studio_media.py` 使用固定 FFmpeg filter graph、Noto Sans SC 字体槽和确认过的音频素材，不执行模型代码。
- **实际证据**：本地 PostgreSQL 工程 id=2 完成音频上传、LRC 解析、权利确认、版本确认和 FFmpeg 渲染；artifact id=2 状态 `done`，960×540、8 秒、含音轨 MP4 已生成并可下载。未确认素材权利时，`POST /api/v1/studio/projects/2/render` 返回 422。
- **删除入口**：登录/注册/OAuth/邮件/套餐/用户管理/微信读书/网文雷达旧路由与导航已移除；`/api/v1/creation/platforms`、`/login`、`/novel` 在本地运行时返回 404。历史迁移和旧表保留，未执行破坏性删表。
- **门禁**：`frontend npx tsc --noEmit`、`frontend npm run build`、`backend uv run --no-sync ruff check app tests` 通过；Studio/LRC/配置/缓存回归共 24 项通过。缓存预热测试仍有 BeautifulSoup 的既有 warning，不影响通过结果。

## 六、一键启动（2026-10-04）

- **入口**：根目录 `start.cmd`，从任意当前目录调用 `start-local.ps1 -OpenBrowser`；启动失败返回非零并保留窗口。子服务隐藏运行，不使用 Docker，不初始化或清理数据库。
- **运行检查**：PowerShell 语法检查通过；用 Windows PowerShell 5 从父目录完成冷启动，数据库、后端 ready、工作台页面和前端代理目录接口均可访问。
- **重复启动**：实际运行 `start.cmd` 后，15432、8102、3000 的监听 PID 保持不变；识别虚拟环境及 Next.js 子进程，不再重复创建服务。
- **边界检查**：独立 TCP 监听测试验证跳过占用端口；非法参数 `-BackendPort 0` 返回 1，显示错误并暂停窗口。运行环境文件缺失会明确报错，不自动安装依赖。

## 七、启动后工作台加载与点击无响应（2026-10-04）

- **复现**：后端和前端代理的目录、选题、历史接口均返回 200；浏览器卡在开发版 `main-app.js` 请求，脚本体积约 13 MB，只有服务端页面外壳，按钮未能及时绑定。
- **修复**：一键启动默认运行优化构建，构建目录 `.next-local` 与开发目录隔离；源码指纹变化自动重建，复用时检查运行模式。打开浏览器前，额外完整读取 bootstrap JavaScript，构建和连接等待均设截止时间。
- **加载逻辑**：目录、选题和历史分开加载，历史慢请求不再阻塞整个工作台；请求和响应正文使用 10 秒截止时间，离开页面主动取消，请求失败可重试。
- **验证**：本地优化构建成功，6 个 bootstrap 脚本均完整返回 200；实际浏览器验证工作台、风格下拉框、输入、收藏夹及首页往返。注入历史延迟后，工作台仍可操作，10 秒后显示超时，点击重试恢复；浏览器无 JavaScript 错误。
- **测试**：超时、响应正文、取消及现有 API 契约 3 个测试文件共 10 项通过；TypeScript 与相关 ESLint 无错误。已有 `_core.ts` 的两个 no-op 参数仍有 unused warning。重复启动复用优化构建，三个服务监听 PID 保持不变。

## 八、自由模板与音乐 MV 时间轴（2026-10-05）

- **症状**：模板和视觉风格留空时，界面没有明确表达“可不选”；歌曲 MV 在未上传音频前使用默认 180 秒分镜，音频/LRC 上传后不会同步重排，规则草稿与 AI 成稿的差异也不清楚。
- **修复**：模板/风格显示“不指定 · 自由发挥”；自由模板生成使用独立的中性结构；含 MV/歌曲主题创建时默认进入“音频 + LRC MV”；音频上传后写入真实工程时长并重排分镜；LRC 时间码优先作为歌词落点和可用分镜边界；生成前先保存右侧创作设定。
- **验证**：`backend/tests/test_studio_lrc.py` 5 passed；`frontend npx tsc --noEmit` 通过；`frontend npm run build` 通过；Ruff、分层检查和浏览器生产冒烟通过。工作台 3000 端口已重启，主题“制作深海少女的mv”实测显示 MV 模式、可选模板/风格和 MV 时间轴素材入口。

## 九、成稿提示框与 MV 素材入口收敛（2026-10-06）

- **症状**：成稿页出现蓝色规则说明框、右侧绿色 MV 说明框和重复的小字提示；歌曲与 LRC 上传入口同时出现在右侧设定和成片页，歌词页反而只是空状态。
- **修复**：移除解释性提示框和重复说明；歌曲、LRC、音频时长、权利确认与歌词列表统一收进“歌词”页；成片页不再重复上传入口。
- **验证**：`frontend npx tsc --noEmit`、`frontend npm run build`、`git diff --check` 和后端 Studio 语法检查通过；待浏览器重启后确认页面只保留歌词页上传控件。

## 十、创作库、收藏带入与视频信源识别（2026-10-05）

- **症状**：收藏夹没有可浏览的模板/风格参考；收藏内容进入工作台后主题未带入；选题页混合展示收藏与今日内容；B 站主页、搜索页和热门榜没有对应抓取路由；MV 渲染还要求额外的权利确认。
- **修复**：收藏夹新增内容模板/视觉风格图文库与详情带入；工作台分开展示收藏内容和今日内容，收藏进入创作自动选中并同步主题，底部操作栏固定可见；B 站识别为 `user/video-all`、`vsearch`、`ranking/all`，抖音热榜识别为 `DouyinHot`；移除 Studio 权利确认 API 与渲染门槛；制作提示词改为制作导向文本。
- **验证**：`npx tsc --noEmit`；`uv run --no-sync pytest tests/test_recognizer.py tests/test_studio_lrc.py -q -o addopts='' --noconftest`（35 passed）；Ruff、`py_compile`、`git diff --check` 通过；真实浏览器验证收藏夹模板/风格详情、带入链接、工作台收藏选中、固定“开始成稿”、MV 歌词页音频/LRC入口；四个信源识别接口返回预期路由。

## 十一、创意工作台品牌与导航收敛（2026-10-05）

- **症状**：主导航仍使用旧产品名，品牌色在橙色、青绿色和局部硬编码之间分散；创作区保留“我的母题”，工作区保留“更新记录”。
- **修复**：主品牌统一为“创意工作台 / CREATIVE WORKBENCH”，全局主色收敛为蓝色 token，并同步侧栏、雷达签名、选题卡、统计与创作页主色；从公共导航移除“我的母题”和“更新记录”。
- **验证**：前端 `npx tsc --noEmit`、`npm run build` 通过；启动本地优化构建后浏览器确认标题、品牌和导航入口。

## 十二、趋势追踪空数据链路（2026-10-06）

- **症状**：趋势雷达实时榜单有数据，但趋势追踪的历史快照、话题曲线和关键词面板为空；本地工作区关闭定时调度时，页面只有读取和空状态。
- **修复**：新增 `POST /api/v1/trends/refresh`，从已分析内容生成话题归类并按实际内容日期写入趋势快照；趋势追踪页的“更新趋势”与空状态按钮调用该链路后重新读取数据。
- **实际结果**：当前本地数据生成 `2026-10-03` 至 `2026-10-05` 三个日期的快照，9 个话题组、162 条话题趋势记录、每个日期 50 个关键词快照；实时趋势接口恢复返回榜单数据。
- **验证**：`npx tsc --noEmit`；`uv run --no-sync pytest tests/test_trends_api.py tests/test_trend_traceability.py -q -o addopts='' --noconftest`（7 passed）；后端 `py_compile`；真实 API `POST /api/v1/trends/refresh?days=7` 返回成功。

## 十三、创作修订、制作状态与提示词（2026-10-06）

- **创作修订**：成稿页加入“我的创作思路”“改稿要求”、重新生成和版本对比；AI 请求携带创作方向与本次修改要求，修订保留独立版本。
- **制作状态**：制作阶段、时间记录与 FFmpeg 实际渲染进度写入 `studio_artifacts.progress`；全局制作任务入口与工作台持续读取同一任务记录，页面切换后可重新打开工程。
- **成片**：提供浏览器 MP4 预览、下载与实际存放路径；新完成的作品同步存入收藏夹作品分类。
- **提示词**：移除版权、授权、待核查、缺失材料声明与中英文负向限制；规则草稿和制作指令使用正向创作描述。新 AI 输出、旧 AI 稿件显示、历史版本与提示词导出共用清理；歌词原文及“不完美的声音”“手持不稳定”等创意表达保留。
- **验证**：Studio/LRC 与自定义模板风格测试共 7 passed；相关 Ruff、前端 `npx tsc --noEmit`、本地生产构建通过；增量迁移 `b91e438ca552` 已在本地 PostgreSQL 应用。实际 API 与浏览器复查工程 33，12 个分镜保留，截图中的声明与负向限制已清理；`/studio/jobs` 返回持久化任务；既有 MP4 预览实际加载为 960×540、8 秒，视频状态 `readyState=4` 且无媒体错误。
- **验证范围**：本次未重新请求付费 AI 成稿或执行完整 Codex 制片。

## 十四、形态分流与可播放动画制作（2026-10-06）

- **内容形态**：文章成稿只生成完整正文；普通视频生成旁白/脚本与镜头；动画讲解生成完整中文旁白、图形动画分镜和动画制作提示词；音乐 MV 使用歌曲与 LRC 时间轴。
- **制作链**：动画讲解走本地 Pillow/FFmpeg 渲染，AI 场景规划、Windows 中文旁白、逐场景动画、MP4、时间轴 JSON、源工程 ZIP 和作品收藏一起完成。Codex 工程作为扩展入口，不再是动画成片的唯一出口。
- **状态反馈**：任务持久化阶段、百分比、耗时、后台心跳、工作区文件数和最近日志；超过 10 分钟的 Codex 任务结束为明确失败，界面显示错误原因。
- **实际结果**：工程 36 的 artifact 10 完成，10 个动画场景、中文旁白、960×540 H.264/AAC MP4，时长 98.916667 秒，制作耗时 67 秒；浏览器预览 `readyState=4`，实际播放时间从 3 秒推进至 4.46 秒，媒体错误为空。工程 ZIP 的 Range 请求返回 206，作品收藏 id=18。原 artifact 9 已标记为失败并停止。
- **验证**：动画与 Studio/LRC/模板测试共 11 passed；Ruff、`py_compile`、前端 `npx tsc --noEmit` 和生产构建通过；浏览器复查阶段日志、预览、下载和作品库入口。

## 十五、DeepSeek Harness 动画工程与千问配音（2026-10-06）

- **改动**：动画制作改为 DeepSeek Harness 读取冻结分镜并生成 Remotion 前端工程；保留可复用的 Stage、Reveal、AnimatedNumber、Connector、Label、Caption 组件，由 Remotion 在 1920×1080 / 1080×1920 / 1080×1080 输出 MP4。Harness 默认模型读取本机 `deepseek-flash`，工作台覆盖为中等思考对应的 `high`。
- **配音**：接入 Qwen-Audio-3.1-TTS-Flash 配置、加密存储、试听接口和制作前检查；音色默认 `longanhuan_v3.1`。API Key 不进入前端、日志或工程包。
- **验证**：Harness headless 实际返回 `READY`；Harness 覆盖配置通过 `--dump-config` 验证；前端 `npx tsc --noEmit`、后端 `py_compile`、相关 Ruff 通过；动画/LRC 测试 10 passed。当前本机 TTS WebSocket 连接超时，尚未生成新的 Remotion 成片，旧 Pillow 成片不作为本次效果证据。

## 十六、完整制作与旁白字幕（2026-10-07）

- **故障**：作品 12 的第一段配音是裸 PCM，被直接写成 WAV，FFprobe 读取失败；Harness 的旧覆盖参数受本机 `max` 设置影响，输出源码后还继续进行渲染检查，作品 14 最终超时。
- **修复**：Omni 流式音频封装为 24kHz 单声道 PCM16 WAV，并逐字朗读定稿；任务级覆盖使用中等思考对应的 `high`。源码交付与工作台渲染分开，重试可复用已生成且编译过的源码；MP4 与工程 ZIP 分开下载，重试清除旧错误横幅。
- **完整结果**：工程 36、版本 8、作品 15 完成，9 段旁白文本与定稿一致；1920×1080、30fps、96.171 秒、H.264/AAC MP4。此次复用了作品 14 的 DeepSeek 源码，配音与渲染约 5 分钟完成，作品收藏 id=20。
- **真实验证**：浏览器播放从 3 秒推进到 4.461 秒，`readyState=4`、媒体错误为空；预览、MP4 下载和工程 ZIP 的 Range 请求均返回 206。独立短工程完成新的 Harness 源码交接和 Remotion 渲染。
- **字幕**：作品 15 已烧录中文旁白字幕，按每段实测配音时长分句；导出 `narration.srt`、`narration.ass`，工程时间轴和 ZIP 同步更新。新工程的 Remotion 字幕层也已实际渲染验证。
- **检查**：相关测试 12 passed；Ruff、`py_compile`、TypeScript 和本地优化构建通过。

## 十七、动画讲解强制旁白字幕（2026-10-07）

- **规则**：动画讲解的完整旁白字幕是制作层，不依赖分镜 `caption` 字段，也不依赖中英双语开关；画面强调文字与旁白字幕分开。
- **流程**：配音完成后生成 `timeline.captions`、SRT、ASS 和 Remotion 字幕层；字幕覆盖校验在渲染前执行，缺失时任务失败，不会生成无字幕动画。
- **验证**：关闭双语、清空分镜字幕字段的短工程仍生成 3 条完整字幕并成功渲染；相关测试 13 passed，Ruff、`py_compile` 和 `git diff --check` 通过。
