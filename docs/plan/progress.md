# 重构进度

方案见同目录《创意工作台改造方案》《创作工作台设计与实现》《现状与问题清单》，样张 `docs/design/direction-a-grading.html`。

交付方式：每个阶段一个分支（`refactor/stage-0`、`refactor/stage-1`…，后一阶段从前一阶段切出），推送到远端，由用户确认后合并到 `main`。回退点：本地 tag `pre-refactor-2026-10-18`（= 原 `main` 的 `7fc51b3`）。

## 阶段 0（分支 `refactor/stage-0`）

### 已完成

- 同步记录：新表 `source_sync_runs`，调度、手动同步都经 `services/source_sync_service.run_source_sync`，每次一行（状态、错误类型、HTTP 状态、抓到 / 新增 / 重复、预筛跳过按原因计数、耗时、触发方式）。
- 自动处理（3.9）：新表 `auto_actions`；连续失败 3 次暂停信源并每 6 小时重试、成功自动恢复；登录失效 / 验证码暂停同平台全部信源；限流间隔翻倍、恢复后逐次减半；超过平常间隔 3 倍无新内容标记「可能失效」。每条事后发站内通知，可撤销。
- 全局「暂停采集」开关（托盘与采集页共用），只影响定时同步。
- 采集页 API：`/api/v1/collection/overview | health | funnel | auto-actions | pause | sources/{id}`。
- 抖音账号被识别成榜单类型：识别器支持已存储的 `douyin/user/…` 路由，迁移把误标的信源和内容改回 RSSHub。
- 第 13 节缺陷：#1 psutil 取进程指标（指标列改可空）；#2 精选缓存带本地用户 id，预热与侧栏计数共用；#3 模板 / 风格分页读全量；#4 本地用户固定为管理员、并发创建重查；#8 删除登录 / 注册 schema、密码校验、`_feature_guard.py`、`user_repo.py`，Agent 技能文档改为免 Token；#9 删除 Docker 主机名改写与相关提示、webpack 轮询、orb.local；#11 启动 2 分钟后补跑最近 7 天日报 / 4 周周刊 / 2 月月刊中没有记录的周期；#12 停止删除 90 天前的待分析内容；#14 去掉 `owner_user_id IS NULL` 过滤，所有信源一视同仁；#15 同步记录；#16 精选率分母只算已分析。

- 后台运行：`start-local.ps1 -RegisterAutostart / -UnregisterAutostart` 注册登录自启计划任务；启动后拉起托盘（`app/desktop/tray.py`，pystray + windows-toasts）：运行 / 暂停 / 有异常 / 未运行四种状态，菜单打开工作台、记一笔、暂停采集、退出，站内通知转成 Windows 系统通知。启动 30 秒后先同步一次热榜。
- 前端骨架：`src/design/`（tokens.ts / tokens.css 同值并有测试、cw.css 照样张的自建组件样式、components.tsx、antd 暗色主题只在新页面的弹层 / 下拉等处生效）、11.1 主导航（`design/nav.ts`，作品入口阶段 5 前不可用）、`/sources` 采集页（关键数字、健康表、流程漏斗、处理记录与撤销、全局暂停）。旧页面包在浅色容器里，阶段 2 逐页替换。字体：Noto Sans SC + Barlow Semi Condensed（next/font 自托管），Windows 数字优先 Bahnschrift。
- ESLint `src` 0 error（Provider 改用 useState 惰性建 store，useFetch 不在渲染期写 ref）。

### 本地验证结果（Linux 沙箱）

- 后端全量 pytest、ruff、分层检查通过；前端 tsc、vitest、ESLint（0 error）通过。
- 真实启动：调度器在启动后同步了 24 个系统信源（22 成功、2 失败），采集页正确显示；对失败信源连续手动同步 3 次后自动暂停、写入处理记录并产生通知。桌面 1280 / 1024 两档截图检查过布局。

### 未验证（需在 Windows 本机实测）

- 托盘、计划任务自启、Windows 通知、Edge 采集。

### 留到后续阶段

- #10 趋势刷新只扫观测窗口（5.3，阶段 2）；#13 事件归并默认开启（依赖本地向量，阶段 1）；#17 日报按归属日期（依赖内容模型，阶段 1/2）；#18 模型调用记录扩展（阶段 1）；空档补采按发布时间翻页（阶段 1）。

## 阶段 1（分支 `refactor/stage-1`）

### 已完成

- 内容模型字段（形态、平台条目 id、作者、媒体信息、封面资产、评论状态、初筛分与信号、分析级别、快速判断、归属日期）；指标观测表 `content_metric_observations`；内容经历 `content_journey`；模型调用记录增加内容 / 运行 / 步骤与载荷引用。
- 分析漏斗与每日预算（默认 5 元，快速判断模型可单独选）：规则预筛 → 免费初筛 → 事件归并 → 快速判断 → 完整分析。
- 本地向量事件归并（onnxruntime + bge-small-zh-v1.5），每个事件一个分析代表。
- 平台适配器：B站、YouTube（Data API Key / RSS）、GitHub、HN、Reddit；追踪词与榜单信源；统一「添加信源」识别；平台 Key 管理。
- 封面本地缓存（主色、缩略图、淘汰）、生成封面兜底；空档补采按发布时间翻页；日报按归属日期；趋势刷新只扫窗口。
- 前端 `/sources`：添加信源弹窗、漏斗与预算设置、平台卡与 Key、最近采到抽屉（封面、媒体信息、分析状态、观测曲线）。

### 本地验证结果

- 后端 pytest、ruff、分层检查；前端 tsc、vitest、ESLint 0 error；1280 / 1024 截图。
- 真实采集（沙箱）：B站关键词 10 条、GitHub 10 条、B站热门 30 条、GitHub Trending 13 条、YouTube RSS 15 条；封面 78 张缓存 72 张；向量归并 65 条合并出 5 个事件。

### 未验证

- B站在家用网络下的稳定性；YouTube 搜索 / 详情 / 评论（需 Data API Key）；Reddit 公开接口可达性；快速判断 / 完整分析的真实模型调用与花费。

## 阶段 2（分支 `refactor/stage-2`）

### 已完成

- 选题结论（4.3）：`services/verdict.py` 纯规则（热度、时机、同题、和你相关、风险、内容质量）→ 值得做 / 观察 / 跳过 + 事实拼成的理由、缺失项、计算明细；`verdict_service` 每 15 分钟刷新近 7 天并写入经历；「不对」存 `verdict_marks`，近 30 天一致率。
- 趋势计算 v2（5.3）：`services/topic_signals.py`，话题单位为事件和追踪词；逐小时信号（发布、指标增量、上榜），没有同步的小时为「观测不足」；新出现 / 升温 / 持续 / 见顶 / 降温；扩展 `topic_trends`（`signal-v2`），每小时计算，只扫最近 7 天。
- 专题（5.5）：`topic_dossiers`，持续 3 天的事件与每个追踪词自动建专题、关注、30 天无新内容归档；专题页时间线、热度曲线、各平台首次出现、提到它的报告、相关收藏。
- 报告（5.4）：没有采集数据的日期不补日报、日历标「未采集」；连续 2 天以上没有采集时开机补采后自动生成空档回看（`period_reports`，不调模型）；任意时间段报告与版本；报告完整度；归档日历（每天头条）、全文搜索、前后连贯（上期话题的后续 / 新出现 / 降温）。
- 今日（5.1）：统一信息流（按形态筛选，全部 / 精选 7 天）、今天的信号时间线（平台轨道、形态色、热度亮度、当前时间）、追踪词点阵、跨平台共振、采集状态、「你离开了 N 天」。
- 条目详情（5.6）：抽屉与 `/items/[id]` 共用；结论与依据、「不对」、指标与观测曲线、角度与「分析并给角度」（按需补分析）、同一事件其他来源与「移出此事件」、所属专题、原文、经历；有用 / 不感兴趣；收藏后按需补分析；事件成员继承代表的分析结果（阶段 1 遗留）。
- 热点（5.2）：热榜、共振（可调最低平台数）、升温榜（迷你曲线 + 状态 + 平台分布 + 代表内容 + 结论、关注）、追踪词（曲线 / 按平台拆开、间隔、开关、预设来自原系统母题模板库）。
- 采集页其余部分（3.8）：建议（点一下执行）、覆盖漏采、完整度、信源价值与收藏趋势、结构；关键数字「漏采」接入。
- 设置分页：AI 模型与配音、生成服务 / Obsidian / 飞书（后续阶段）、通知（最近 20 次推送）、Prompt、评分说明（初筛权重、结论规则、状态阈值可调 + 一致率）、系统。信源分页：信源列表、采集、内容。管理后台侧栏与概览取消。
- 11.2 页面去向：`/today-picks`、`/trending`、`/trends`、`/my-topics/config`、`/admin/mother-topics`、`/topics/:id`、`/contents/:id/reader`、`/stats`、`/admin`、`/algorithm`、`/sources/me` 跳到新位置；删除 `/my-topics`、`/admin/content-events`、`/admin/scoring-dashboard`、`/admin/evidence`、`/admin/webhook-logs`、`/admin/feedback`、`/admin/updates`、`/changelog`、`/dashboard`（返回 404），以及只服务这些页面的接口（事件审核队列、评分看板、可信线索、排序评测、产品反馈、监控大盘 HTML）。

### 本地验证结果

- 后端全量 pytest（0 失败）、ruff、分层检查；前端 tsc、vitest 177 项、ESLint 0 error。
- 示例数据在开发库上跑通趋势、结论、专题、空档回看；1280 / 1024 截图检查今日、条目抽屉 / 独立页、热点四个页签、报告日历 / 空档回看、专题、设置、信源页；删除的页面返回 404，搬走的页面跳到新位置。

### 未验证

- 真实采集数据下的结论分布与升温阈值是否合适（跑一周后在「评分说明」调）；「停止采集 3 天再恢复」的空档回看用单测和示例数据验证，未在 Windows 本机实测。

### 留到后续阶段

- 评论采集（阶段 3）；随笔、项目关联、Obsidian 主题页（阶段 3/4）；旧页面（日报 / 周刊 / 月刊正文、信源列表、内容管理、AI 模型、Prompt、系统设置）仍在浅色容器里，后续逐页换新界面。

## 阶段 3（分支 `refactor/stage-3`，进行中）

### 已完成

- 灵感库（6.1–6.3、6.5）：新表 `library_items` / `library_boards` / `library_links`；一键收藏（旧收藏入口同步写入）、粘贴链接（B站 / 抖音 / 小红书 / YouTube / GitHub / HN / Reddit / 任意网页）、文字与提示词、上传 / 拖入 / 剪贴板截图、文章配图与视频截帧；正文里的提示词与 GitHub 仓库自动提取并关联。文件存 `data/library/`，sha256 去重，图片缩略图 / 主色 / 色板，视频时长与封面，音频波形，字体字样，SD WebUI / ComfyUI 生成参数。搜索、形态 / 素材类型 / 授权 / 标签 / 颜色筛选、画板、多选改授权。
- 随笔（6.4）：Markdown、`#标签`、`[[双链]]`（含 `^cw-id` 块引用）、时间线、相关收藏 / 热点、粘贴图片、录音存档 + 千问转写；任意页面 `Alt+N` / 右下角按钮随手记。
- 风格与模板（6.6）：内置种子幂等写入；版本不可改，编辑即新版本，编辑内置的复制为自定义；复制、归档、从素材 AI 提炼；`/studio/catalog` 读新表、形状不变；页面 `/library/styles`。
- 旧收藏夹迁移（6.9，幂等）与素材收件箱（每 2 分钟）；设置 · 灵感库页。
- 浏览器扩展（6.3）：仓库 `extension/`，MV3，右键存整页 / 链接 / 图片 / 选中文字，选项页可改服务地址并测试连接。
- Obsidian 双向同步（6.8）：`services/obsidian_sync.py`，每分钟一轮（先读回、再写出）。写入 `创意工作台/` 下 收藏 / 素材 / 提示词 / 仓库 / 随笔 / 主题 / 报告（项目目录留给阶段 4）；条目笔记含 frontmatter、`## 摘要`、`## 我的笔记`、`## 关联`，素材嵌入 `_附件/` 缩略图；随笔每天一个文件、每条 `## HH:MM ^cw-id`；关注的 / 被关联的专题生成主题页（条目、随笔、报告）。读回：frontmatter 标签、「我的笔记」及其中双链、随笔小节修改与新增、根目录新建的笔记（成为随笔）。只读你改过的文件（与上次写出的内容哈希比对），字段归属互不覆盖。设置 · Obsidian 页；条目详情「在 Obsidian 打开」。
- 图谱（6.7）：`/library/graph`，sigma.js + graphology + ForceAtlas2；节点为收藏 / 随笔 / 专题 / 风格 / 模板 / 项目，边为显式关联 + 同一事件 / 同作者 / 同标签；按类型、时间筛选；点节点看关联、打开、用于新项目；条目详情里有一度 / 二度局部图谱。

### 本地验证结果

- 后端：阶段 3 测试（灵感库 9 项、Obsidian 往返 + 图谱 6 项）、全量 pytest、ruff、分层检查。Obsidian 按演示流程在测试里走通：收藏 → vault 出现笔记 → 在 Obsidian 写「我的笔记」/ 改标签 / 改随笔 / 加随笔 / 新建笔记 → 回到工作台 → 再次写出时「我的笔记」不丢。开发库上对 `/tmp` 下的 vault 实跑两轮，第二轮 0 写出。
- 前端：tsc、vitest、ESLint；1280 / 1024 截图检查灵感库（画廊、详情抽屉、局部图谱）、随笔、风格与模板、设置 · 灵感库 / Obsidian、图谱、Alt+N 随手记。

### 未验证

- 真实 Obsidian 客户端打开 vault、`obsidian://open` 跳转、Windows 路径；Edge 实际加载扩展；千问转写（无 Key）；图谱「语义相似」边（等条目向量接入后补）。

### 待做（阶段 3 剩余）

- 条目评论（B站、YouTube、HN）；流程引擎（LangGraph）与运行记录、节点图、时间线、调用树；研究员与选题研究流程；工作台工具第一批。


### 阶段 3 · 条目评论（2026-10-20）
- `content_comments` 表 + `content_items.comment_digest`（迁移 e5a7c2d4f601）；`services/comments.py`：B站、YouTube、HN、Reddit 热门前 20 条（不取回复），按平台评论 id 去重，重复采集只更新点赞 / 回复数；状态 未采集 / 已采集 / 无评论来源 / 采集失败（带原因）。
- 触发：收藏（`on_favorited`）、收进灵感库（`/library/items/from-content` 后台调用）、详情「加载评论」；每小时 :35 维护任务：收藏内容首次采集 24 小时后刷新一次，未收藏内容的评论 30 天后删除。「被项目用作来源」的触发在阶段 4 项目接入时补。
- 「总结评论」：模型给 3–5 条要点，每条只保留真实存在的评论 id，标注基于多少条。
- API：`GET /items/{id}/comments`、`POST /items/{id}/comments/load?refresh=`、`POST /items/{id}/comments/digest`。
- 前端：条目详情底部「评论」折叠区（默认收起、按点赞排序、点要点高亮依据评论）。
- 验证：tests/test_stage3_comments.py 5 项通过；alembic 升降级往返；ruff、分层检查、tsc、eslint 通过。
- 未验证：真实平台评论接口（沙箱 B站易风控、无 YouTube Key）。

### 阶段 3 · 流程引擎、运行记录、选题研究、工作台工具（2026-10-20）
- 依赖：`langgraph==1.2.16`、`langgraph-checkpoint-postgres==3.2.0`（锁定）。
- 表（迁移 f6b8d3e5a712）：`agent_runs`、`agent_steps`、`trace_spans`、`artifacts`、`artifact_links`、`agent_decisions`、`workbench_tokens`。模型调用沿用 `llm_call_logs`（run_id / step_id），调用树查询时并入。
- `services/flows/`：YAML 模板（`templates/topic_research.yaml`）→ `spec.py` 校验 → `engine.py` 编译为 LangGraph（并行分支用 Send，关卡用 interrupt / Command(resume)，PostgreSQL checkpointer 同库；测试用内存）。预算（花费 / 步数 / 时间）超限暂停，可追加后继续；失败可从失败步骤继续（上游不重跑）；停止；「从这里重跑」建分叉运行，上游复用原产物；服务重启时运行中的流程改为暂停。checkpointer 建表在启动时、DuckDB ATTACH 之前完成（CREATE INDEX CONCURRENTLY 会等其他事务）。
- 角色（`roles.py`）：研究员（按平台分工，只读工具循环，最多 N 次调用；结论必须带真实出处，否则丢弃）→ 汇总（引用条目编号，来源链到分支简报条目）→ 策划（3 个方向卡，引用简报条目）→〔选方向〕关卡（可关闭）。
- `trace_service.py`：步骤、调用（载荷脱敏压缩存 data/traces）、产物与来源、人工决定、运行详情、调用树、节点详情（含渲染后的提示词）、溯源（向上到采集内容 / 灵感库 / 网页，向下被谁使用）。`run_events.py` 进程内事件总线；`/runs/{id}/stream` SSE 先发快照再推事件。导出 JSON / Markdown。
- 工作台工具第一批（`workbench_tools.py`）：search_library、search_content、read_content（原文 / 字幕 / 评论）、platform_search、fetch_url、add_favorite、write_note；每次调用写调用树。MCP 端点 `POST /api/v1/mcp`（Streamable HTTP，JSON 响应；initialize / tools/list / tools/call / ping），按限定范围令牌鉴权（工具白名单、过期、吊销），调用标记 via=mcp。
- 前端：`/runs`（发起选题研究、运行列表；导航「任务」指向这里，采集任务仍在 /stats/jobs）、`/runs/[id]`（节点图 @xyflow/react、时间线、调用树、节点详情、关卡选方向、追加预算 / 继续 / 停止 / 从这里重跑、导出）、`/settings/workbench`（工具清单、MCP 令牌与配置片段）；条目详情加「选题研究」入口。顺手修了 `design/graph.tsx` 渲染期写 ref 的 lint 错误。
- 验证：tests/test_stage3_flows.py 10 项（关卡中断恢复、关卡关闭、预算暂停继续、失败继续、分叉复用、停止、调用树 / 节点详情 / 溯源、载荷脱敏与 MCP 令牌、重启恢复）；后端全量 pytest 通过；迁移升降级往返；dev 库用 PostgreSQL checkpointer 实跑（另一进程创建的运行在服务进程里从关卡恢复成功）；1280 / 1024 截图检查运行列表、节点图、节点详情、时间线、调用树、设置页；vitest 181、tsc、eslint（0 错误）通过。
- 未验证：真实模型下的研究质量与花费；外部 agent（Claude Code / Codex）实际连 MCP；Obsidian 写入运行摘要（随项目在阶段 4 做）；「被项目用作来源」触发评论采集（阶段 4）。

### 阶段 3 · 图谱语义相似边（2026-10-20）
- 条目向量其实已在阶段 1 的事件归并中写入 `content_embeddings`（bge-small-zh-v1.5）；图谱对收藏条目对应内容的向量算余弦，≥0.78 的每条取最相近 3 条画「相似」边（显式关联优先）。
- 验证：tests/test_stage3_obsidian.py 新增用例通过。未验证：真实数据下阈值是否合适。

## 阶段 4（refactor/stage-4）

实施顺序（按「创作工作台设计与实现」第 14 节）：① 后端迁移与新接口 → ② 前端新路由（/projects、idea、draft、outputs）→ ③ 成稿 / 讲解视频流程与写手、审校、分镜、美术、制作、质检角色 → ④ 生成服务与用灵感生图 → ⑤ 溯源图与引用、Claude Code / Codex 执行者 → ⑥ 抖音、小红书采集与评论 → ⑦ /studio 重定向、删旧接口。

### 阶段 4 · 工作台后端：项目 / 定稿分层、AI 建议、产出物（2026-10-20）
- 迁移 a7c9e1f3b824：`studio_projects` 加 `draft_token`、`stage`、`archived_at`；新表 `project_sources`、`studio_outputs`、`project_suggestions`、`project_assets`；`studio_artifacts` 加 `output_id`、`settings`。数据迁移：制作层字段（style_id、presentation、production、aspect_ratio、bilingual）移到新建的「讲解视频 / MV / 提示词包」产出物 settings；旧作品挂到该产出物并从当时版本补 settings；`source_snapshot` 转为主来源；token 与 stage 初始化。旧字段只读不删。
- `services/project_service.py`：项目（列表 / 新建带来源 / 改名 / 归档）、来源（1 主 + ≤9 参考，进入时冻结快照：标题、链接、平台、发布与采集时间、摘要、最新指标）、文案层设定（定稿后改文案层返回 409 finalized）、工作副本（自动保存只换 token 不生成版本；旧 token 返回 409 draft_conflict；「用我的覆盖」先把对方内容存成版本）、版本（保存 / 查看 / 恢复生成新版本）、定稿与解锁、空白 / 按模板开始、产出物（视频 / MV / 提示词包需定稿；改制作参数不撤销定稿；文稿有新定稿时标记 stale；发布链接置为已发布）、情绪板素材（≤30）。段落稳定 id：`p_` + 内容哈希前 8 位，重复追加序号。
- `services/suggestion_service.py`：AI 修改返回补丁操作（替换 / 插入 / 删除段落，改 / 插 / 删 / 移分镜），服务端校验 id、字段、长度与范围（选中段落时不动分镜），≤50 个；按处接受生成「AI 建议」版本；token 变了时只应用目标未被改过的操作，其余返回冲突。
- `services/output_rules.py` + `output_service.py`：小红书 / 知乎 / 公众号规则与计数；平台改写超限带问题重写一次、再超限截断并提示；公众号 HTML 用 nh3 白名单清洗；知乎文末补来源；导出 Markdown / HTML；视频提示词包 Jinja2 确定性生成（目标：通用 / Claude Code / Codex / DeepSeek Harness；脚本、分镜表、风格规范、素材清单含授权、交付要求），ZIP 含 README.md、script.md、storyboard.csv、style.json 与素材文件。
- 接口：`/api/v1/projects…`、`/outputs/{id}…`、`/suggestions/{id}/apply|reject`（`api/v1/projects.py`）。旧 `/studio/*` 暂时并存。
- 依赖：nh3（新增）、jinja2（显式声明）。
- 验证：tests/test_stage4_projects.py、test_stage4_suggestions.py、test_stage4_outputs.py 共 18 项通过；后端全量 pytest 通过；dev 库迁移升降级往返，并用一条旧工程数据核对数据迁移（产出物 settings、作品 output_id / settings、主来源、stage）；ruff、分层检查通过。
- 未验证：真实模型下的建议与平台改写质量；「AI 写初稿」（ai 模式）随成稿流程在第 ③ 步接入；「被项目用作来源」触发评论采集待接。

### 阶段 4 · 工作台前端：/projects 三步页面（2026-10-20）
- 路由：`/projects`（列表：步骤筛选、搜索、新建、归档）、`/projects/new?source=content:1,library:2&theme=`（带来源新建）、`/projects/[id]/idea|draft|outputs|outputs/[outputId]`；导航「项目」指向 `/projects`（旧 `/studio` 暂留）。今日条目详情加「做成项目」，灵感库详情「用于新项目」、专题角度「用于新项目」、图谱项目节点改指新路由。
- `design/studio.tsx`：项目上下文、项目栏 ProjectShell（标题直接改、草稿 / 已定稿 vN 🔒 / 有修改黄点、步骤条：无主题时文稿不可进、过程链接、进行中任务数）、灵感库选择器 AssetPicker、来源选择器 SourcePicker（灵感库 / 今日 / 手动输入，列表 + 详情，设为主来源 / 加为参考）、已选来源、情绪板 MoodBoard（≤30）、方向卡轮询。
- 第一步：来源、已选来源、情绪板、创意方向（「AI 给出方向」启动选题研究流程，关卡关闭，方向卡从运行产物读取，点卡片填入主题和创作思路；「自己写」；失败可重试；「查看过程」打开运行视图）、设定（文案层字段）、空白开始 / 按模板生成结构。
- 第二步：大纲（标题树 / 分镜列表、总字数或总时长 / 目标）、纸面编辑器（标题、梗概、正文；中文输入法组字期间不触发保存）、视频形态的分镜表（逐格编辑、上下移 / Alt↑↓、插入、复制、删除、展开提示词与衔接、时长条超出目标变黄）与旁白全文（段落数与分镜数一致时写回各镜，不一致时提示）、侧面板 AI 助手（范围随选区切换：全文 / 选中段落 / 选中分镜；快捷指令、自由指令 Ctrl⏎、历史）、设定、版本（列表、只读预览、全屏对比：段落按内容哈希对齐 + 段内字符差异 + 分镜逐字段、上一处 / 下一处、恢复为此版本）、来源（插入引用 [n]、插入摘录）；建议以修订样式显示，按处接受 / 拒绝、全部接受 / 全部拒绝；底栏字数、预计朗读、自动保存状态、保存版本 Ctrl S、定稿弹窗、已定稿横幅「继续修改」；自动保存冲突横幅「载入最新 / 用我的覆盖」。
- 第三步：产出物列表（新建菜单；未定稿时视频 / MV / 提示词包不可建；状态、基于版本、字数；「文稿已更新到 vN」）、平台版本工作区（AI 从定稿改写、字段计数与超限提示、小红书手机框 / 知乎文章页 / 公众号 sandbox iframe 预览、复制标题 / 正文 / 话题、导出 Markdown / HTML、打开发布页、发布链接）、提示词包（目标、内容勾选、风格、画幅、实时 Markdown 预览、复制、下载 .md / .zip）、讲解视频 / MV（制作参数：风格、表现方案、画幅、执行者、中英字幕卡；历史成片）。
- 后端补充：`POST /projects/{id}/directions`；`/runs` 支持 `project_id` 过滤与启动时关联项目；提示词包小节前留空行。前端错误对象带 `code` / `data`（阶段 4 接口的 409 等）。
- 纯逻辑 `lib/projects.ts`：字数 / 朗读时长、分镜总时长与超时、大纲、选区到段落、建议预览、字符差异、段落对齐、平台计数、旁白与分镜对应、自动保存队列（防抖、串行、409 冲突停存、恢复）。
- 验证：vitest 190 项通过（新增 projects-stage4 9 项）；tsc、eslint（新文件 0 问题）；后端阶段 4 + 流程测试通过；dev 环境 1280 / 1024 截图检查项目列表、第一步、文稿（含修订样式建议）、已定稿只读与版本列表、小红书工作区、提示词包工作区，无控制台错误。
- 未做 / 未验证：TipTap 富文本编辑器、@dnd-kit 拖动排序、wavesurfer 歌词时间轴（当前为纸面 textarea 与按钮排序）；「AI 写初稿」与讲解视频「开始制作」等第 ③ 步流程接入；热点 / 专题页签；任务抽屉与 SSE；真实模型下的方向卡与建议。
