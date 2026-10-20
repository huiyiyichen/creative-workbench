# 质量回归矩阵

缺陷与回归只在本文件登记；修复后写明回归测试和验证结果。

## 一、测试运行

后端 conftest 会对 `DATABASE_URL` 指向的库执行 `TRUNCATE ... CASCADE` 并终止其他连接，`DATABASE_URL` 必须指向独立的 `creative_workbench_test*` 库。

| 场景 | 命令 |
|---|---|
| 后端全量 | `make test-backend` |
| 后端单项 | `cd backend && uv run python -m pytest tests/<文件> -q` |
| 无数据库单测 | `cd backend && uv run python -m pytest tests/<文件> -q --noconftest -o addopts=''` |
| 前端 | `cd frontend && npx tsc --noEmit && npm test` |

## 二、关键流程基线

| # | 流程 | 回归测试（`backend/tests/`） |
|---|---|---|
| 1 | 信源创建 → 同步 → 内容落库 | `test_source_api` `test_source_seed` `test_api_source_scraper` `test_content_pipeline` `test_source_url_safety` `test_recognizer` |
| 2 | 抽取 / 富化 / 分类 | `test_enricher` `test_classifier_contract` `test_content_labeling` `test_content_summary` `test_tag_normalization` `test_content_actions` |
| 3 | 分析任务入队 → 恢复 → 完成 | `test_analysis_recovery` `test_analysis_jobs_persistence` `test_job_tracker` `test_analyses_api` |
| 4 | 当日精选 / 标记 / 反馈 | `test_today_picks` `test_feedback_signal`；`test_duckdb_service -k today_picks` 单独执行 |
| 5 | 热榜同步 / 趋势快照 | `test_trending_pipeline` `test_trends_api` `test_trend` `test_trend_traceability` |
| 6 | DuckDB 不可用 → OLTP 回退 | `test_duckdb_service` `test_latest_analysis_queries` `test_digest_fallback` `test_db_backend` |
| 7 | 启动迁移 → 调度器 → 停机 | `test_migrations` `test_lifespan_duckdb_init` `test_cache_warmup` `test_startup_warmup_policy` `test_interest_vector_lifecycle` `test_task_registry` `test_shutdown_prewarm` `test_rescan_selfheal` `test_health_endpoints` |
| 8 | 日报生成 | `test_daily_generation_task` `test_daily_report_versions` |
| 9 | 创作工作台 | 见 §五 |
| 10 | 前端 | `npx tsc --noEmit`、`npm test` |

最近结果：2026-10-20 阶段 6 提交后（bd563e0），后端全量通过（1 skipped）；前端 vitest 208 passed，`tsc`、`npx eslint src`、ruff、分层检查通过。全量 pytest 未装 xdist，不要加 `-n`。

## 三、待处理缺陷

暂无。2026-10-20 核对后，原登记的 6 条均已修复，见 §四。

## 四、已修复缺陷

| 缺陷 | 修复 | 回归测试 |
|---|---|---|
| Windows 上进程指标不可用（模块级 `import resource`） | 改用 psutil 跨平台取常驻内存与 CPU 时间 | `test_metrics_persistence::TestProcessMetrics` |
| 侧栏计数不复用已预热的精选缓存 | 精选缓存键带本地用户 id，预热与侧栏计数共用 | `test_contents_api` |
| 工作台按 `content_id` 带入来源失败 | 旧 `/studio` 只做跳转，来源改为 `/projects/new?source=content:<id>` 按 id 直接读取 | `src/lib/__tests__/studio-redirect.test.ts` |
| 模板 / 风格 / 收藏读取上限 200 | `studio_catalog` 分页读全量 | `test_studio_presets` |
| 测试顺序污染（post-sync 任务引用） | 更新同步后处理引用、隔离事件循环连接；全量顺序下通过 | `test_analysis_recovery::test_post_sync_pipeline_task_reference_clears_when_done` |
| `npm run lint` 扫描构建产物、`src` 有 `react-hooks/refs` 问题 | 忽略 `.next-local/**`，逐条修掉 | `npx eslint src`（0 错误） |
| 日报异步生成的占位记录与后台结果错位 | 后台按请求返回的记录 id 更新 | `test_daily_generation_task` |
| Windows 下 Alembic 以 GBK 读取 UTF-8 ini 失败 | `alembic.ini` 改为 ASCII | 启动迁移冒烟 |
| 提交源码的 `start.cmd` 在新目录无法启动 | 入口改为 ASCII/CRLF，首次启动准备依赖与独立数据库 | 新目录冷启动与重复启动 |
| 提交包未同步新启动入口与项目名 | `scripts/prepare-publish.ps1` 从源码重新生成 | `scripts/audit-publish.ps1` |
| 收藏测试触发真实后台向量重建 | 测试隔离，后台任务纳入追踪 | `test_content_favorite_api` 与 `test_content_pipeline` 连续执行 |
| 分析恢复 / inflight 去重 / post-sync drain | 更新同步后处理引用，隔离事件循环连接 | `test_analysis_recovery` `test_analysis_jobs_persistence` |
| DuckDB 当日精选查询契约 | fixture 补 `content_type` 列 | `test_duckdb_service -k today_picks` |
| 依赖安全公告 | 升级 cryptography、fastapi、starlette、vitest | CI `security-scan` |
| `/health/ready` 恒为 ready | 增加 OLTP 连通性探测 | `test_health_endpoints` |
| 无主后台任务 | 收编到 `app/core/task_registry.py` | `test_task_registry` |
| 停机链中断 | 预热任务异常隔离与超时 | `test_shutdown_prewarm` |
| 信源批量操作失败不可见 | 失败项逐条反馈并保留选择 | `src/app/admin/sources/_batch-utils.test.ts` |
| Webhook 日志页内计数与总数混排 | 徽章标注口径，失败数始终渲染 | `src/app/admin/webhook-logs/_scope-utils.test.ts` |
| 管理后台面包屑缺映射 | 映射由导航清单派生 | `src/lib/__tests__/admin-nav.test.ts` |
| SSRF 测试受本机代理影响 | conftest 清除代理环境变量 | `test_source_url_safety` |

## 五、创作工作台

| 功能 | 实现 | 回归测试（`backend/tests/`） |
|---|---|---|
| 工程、版本、修订与定稿 | `studio_projects` / `studio_revisions`，乐观锁；迁移 `a71c9e604b22` | — |
| 制作进度持久化 | `studio_artifacts.progress`；迁移 `b91e438ca552` | — |
| 内容模板与视觉风格分层、自定义预设 | `studio_catalog.py`，收藏夹模板 / 风格 | `test_studio_presets` `test_studio_lrc::test_style_compiler_keeps_content_structure_separate` |
| 内容形态分流（文章 / 视频 / 动画讲解 / MV） | `compile_draft`、AI 成稿按形态提示 | `test_studio_lrc::test_content_form_changes_compiled_output` `test_studio_lrc::test_animation_video_is_a_distinct_content_form` |
| 音乐 MV 时间轴 | LRC 多时间戳与 offset，分镜跟随歌词与音频时长 | `test_studio_lrc` |
| 千问配音 | 流式 PCM 封装为 WAV，逐字朗读定稿 | `test_studio_tts::test_omni_pcm_is_wrapped_as_playable_wav_and_keeps_script` |
| 旁白字幕 | 按配音时长分句，导出 SRT / ASS 与 Remotion 字幕层；动画讲解必带字幕 | `test_studio_tts::test_subtitles_follow_voice_duration_and_scene_offsets` `test_studio_tts::test_animation_subtitles_are_required_even_with_empty_emphasis_caption` |
| 动画场景 | 按定稿分镜规划场景 | `test_studio_animation` |
| DeepSeek Harness + Remotion 制作 | 独立作品目录生成源码，工作台渲染 MP4；MP4 与工程 ZIP 分开下载 | `test_studio_tts::test_remotion_preview_and_source_use_separate_files` |
| 趋势刷新 | `POST /api/v1/trends/refresh` 从已分析内容生成快照 | `test_trends_api::test_refresh_trends_builds_snapshots` |
| 创作者与榜单信源识别 | B 站主页 / 搜索 / 热门，抖音热榜 | `test_recognizer` |
| 灵感库、随笔、Obsidian 双向同步 | 阶段 3 | `test_stage3_library` `test_stage3_obsidian` |
| 评论采集与折叠区 | 阶段 3 | `test_stage3_comments` |
| 流程引擎、角色、运行记录 | 阶段 3–4 | `test_stage3_flows` `test_stage4_flows` |
| 项目、来源、定稿分层、修改建议 | 阶段 4 | `test_stage4_projects` `test_stage4_suggestions` |
| 成稿 / 成片、产出物、溯源 | 阶段 4 | `test_stage4_outputs` |
| 生图服务与生成任务 | 阶段 4 | `test_stage4_generation` |
| 抖音 / 小红书采集 | 阶段 4 | `test_stage4_platforms` |
| 平台改写流程、一键全流程、重跑对比 | 阶段 5 | `test_stage5_platform_flow` `test_stage5_pipeline` |
| 任务中心（运行 / 生成 / 同步 / 分析 / 飞书） | 阶段 5–6 | `test_stage5_tasks` |
| 作品库 | 阶段 5 | `test_stage5_works` |
| 提示词包与外部 agent 回传 | 阶段 5 | `test_stage5_delivery` |
| 视频生成接口（异步厂商任务、预算） | 阶段 5 | `test_stage5_video_generation` |
| 飞书多维表格（记入、状态列更新、自动写入、失败重试） | 阶段 6，迁移 `c3e5a7b9d104` | `test_stage6_feishu`（模拟飞书接口；真实联调待凭证） |
