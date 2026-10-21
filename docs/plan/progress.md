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

### 阶段 4 · 第 ③ 步：成稿流程与成片流程（2026-10-20）
- 引擎：模板支持 `reads`（读取非上游节点的最新产物，例如修改稿读原稿、制作读质检报告）与 `loop_to` + `max_loops`（产物 `passed=False` 时退回，节点轮次记入 `agent_steps.round`）；关卡类型 `choose_direction` / `accept`（接受 / 不接受），关卡不产出产物时把上游产物传给下游；按节点覆盖执行者（运行输入 `_executors`、从这里重跑可换执行者）；流程结束回调（按流程 key 懒加载）；退回次数用完仍不通过时运行标为失败并说明。节点图里退回边为黄色虚线，连线按上游角色标注产物，节点显示实际执行者。
- 成稿流程 `draft_writing`：写手（初稿，段落引用 → 产物来源带段落锚点）→ 审校（只提意见，指向段落 / 分镜，过滤不存在的段落）→ 写手修改（读原稿 + 意见；没有意见时直接沿用、不调模型）→〔接受〕→ 写入文稿（新版本，原因 ai；不接受则不变；已定稿拒绝）。`POST /projects/{id}/draft/generate {mode: ai}` 返回运行 id（关卡默认关闭，旧版本都在「版本」里）；运行中重复点击复用同一运行。
- 成片流程 `video_production`：分镜（定稿分镜完整时直接沿用；否则模型细化，每镜标依据段落）→ 美术（项目素材里指定的关键帧优先，生图服务可用时生图，否则给提示词）→ 制作（`production_service.produce`：读定稿版本 + 产出物 settings，建挂产出物的 StudioArtifact 并写 settings 快照，阶段写进 progress 并推运行事件；上一版已交付设计源码时复用，质检退回时把问题写进 `qa_feedback.json` 在原源码上改）→ 质检（时长 ±10%/2 秒、黑帧 ≥1 秒、讲解视频静音 ≥3 秒、字幕覆盖旁白且不超出成片、与分镜逐镜一致；问题定位到镜头），不通过退回制作最多 2 次。`POST /outputs/{id}/render` 先检查定稿、在制、前置条件（MV 音频、千问 TTS、执行者 CLI），结束后同步产出物状态，完成时照旧写入作品收藏。
- 外部执行者（`agent_adapters`，第 ⑤ 步的一部分）：DeepSeek Harness 沿用 dsh；Claude Code（`claude -p --output-format stream-json`）与 Codex（`codex exec --json`）逐行解析事件，统一成 message / tool_call / tool_result / command / file_change / usage / error，写入调用树（via = dsh / claude / codex），原始事件存工作目录 `*.events.jsonl`；`GET /production/executors` 返回安装情况。
- 溯源：文稿版本登记为产物（成稿流程写入的版本沿用写手的段落引用；手写版本按正文「[n]」登记到段落，没有标注时引用主来源），分镜每镜 → 文稿段落，成片 → 分镜 / 关键帧 / 质检报告，可以从成片一路追到采集内容。
- 顺带修正：`creative_text` 清洗会把段落之间的空行吃掉，导致 AI 成稿合成一段、段落 id 失效；现在保留空行。
- 前端：「AI 写初稿」接通（跳到文稿页，横幅显示写手 / 审校 / 写手修改阶段条，完成后自动载入新版本）；讲解视频 / MV「开始制作」接通（阶段条、制作阶段与百分比、耗时、质检报告、成片预览、停止 / 从失败处继续 / 重新制作；执行者未安装时提示）；运行视图重跑弹窗在制作节点可换执行者。纯逻辑 `flowStages` / `qaMark`。
- 验证：tests/test_stage4_flows.py 11 项（成稿写入版本与段落溯源、关卡拒绝、无意见跳过修改、定稿拒绝、质检退回一次后通过、两次退回后停下并可换执行者分叉重跑、启动前检查、质检规则、两种 CLI 事件转换、假 CLI 端到端）；后端全量 pytest；ruff、分层检查；前端 tsc、vitest 193 项、eslint 0 错误。
- 未验证：真实模型下的写手 / 审校 / 分镜质量；真实 dsh / Claude Code / Codex 在 Windows 工作目录里的设计交付与 Remotion 渲染（沙箱没有这些 CLI 和字体）。

### 阶段 4 · 第 ④ 步：生成服务与用灵感生图（2026-10-20）
- 表（迁移 b8d2f4a6c913）：`generation_services`（名称、类型、接口格式、地址、加密 Key、模型、能力 {refs, max_n, sizes}、单价、每日上限、启用、默认）、`generation_jobs`（服务、模型、提示词、参考条目、参数、目标、项目 / 产出物 / 运行、状态、候选结果、花费、错误）。
- `generation_service`：OpenAI 兼容图像接口适配器（文生图 `/images/generations`；服务支持参考图时带图走 `/images/edits`；不支持时把参考条目的 AI 描述 / 提示词写进提示词）；目标决定默认画幅与素材角色（情绪板 1:1、小红书 3:4、封面 / 插图 / 关键帧 16:9）；按服务单独的每日上限（单价 × 张数，超出返回 429 并说明已用 / 预计 / 上限）；候选逐张落盘 `data/generations/<job>/` 并逐张可见；「存入并使用」写进灵感库（生成图、授权 AI 生成、meta 记提示词 / 模型 / 参数 / 参考条目 / 目标，并与参考条目建 generated 关联）同时加入项目素材放到目标位置（target 带 output_id / index / shot）；「以此为参考再生成 / 出变体」把选中的图作为第一张参考；提示词起草读目标处的文稿段落或分镜、风格当前版本规则、参考条目描述；没选中的候选 7 天后由每日 4:20 的维护任务清理；Key 只回显末 4 位。
- 成片流程的美术节点接上：项目里给镜头指定的关键帧优先；生成服务可用时每镜生一张并挂成关键帧素材。
- 接口：`/generation/services`（增删改、测试）、`POST /generations/images`、`GET /generations/{id}`、`GET /generations/{id}/files/{i}`、`POST /generations/{id}/keep`、`POST /projects/{id}/image-prompt`。
- 前端：设置 · 生成服务（列表、今日花费 / 上限、测试、编辑弹窗）；生图面板（参考条、AI 起草、服务 / 尺寸 / 张数、预计花费与今日已用、候选网格、出变体、以此为参考再生成、存入并使用；未配置时「配置生成服务」）；入口：情绪板「+ 生图」（默认取情绪板里的图作参考）、小红书版配图格（第 1–9 张）、公众号封面、讲解视频「分镜关键帧」卡（每镜生图，带产出物的视觉风格）。
- 验证：tests/test_stage4_generation.py 8 项（Key 加密与掩码、情绪板参考生成 → 存入灵感库带提示词与参考关联 → 项目素材目标、以此为参考再生成、服务不收参考图时写进提示词、每日上限与未配置、适配器失败、关键帧挂到镜头、候选清理、目标上下文）；迁移在 dev 库升降级往返；vitest 新增 3 项；tsc、eslint。
- 未验证：真实 image2.5 / gpt-image 接口（沙箱无 Key）。

### 阶段 4 · 第 ⑤ 步：溯源图与引用（2026-10-20）
- 外部执行者（Claude Code / Codex / DeepSeek Harness）已在第 ③ 步随成片流程接入，见上。
- 溯源查询 `trace_service.lineage(anchor=)`：只看产物里某一处（文稿段落 id、`shot_N`、方向卡 / 结论 / 意见编号）的来源，沿关系的 target_anchor 逐层往上；整体溯源时同一上游产物的逐处关系只展开一次；采集内容 / 灵感库节点带标题、平台、链接；生成图继续展开它的参考条目（灵感库 generated 关联）。
- 溯源入口 `GET /lineage?target=paragraph|version|shot|video|platform`（`project_lineage.resolve`）：段落 / 版本（没登记过的版本按正文「[n]」登记段落引用，没有标注时引用主来源）、分镜某一镜（只取属于这个产出物的运行）、成片（按 StudioArtifact）、平台稿；`/artifacts/{id}/lineage` 支持 anchor。
- 平台稿登记为产物（原来调用了不存在的 `register_artifact`，一直没登记）：平台稿 ← 文稿版本 ← 来源。
- 前端：溯源抽屉（来源树：关系、类型、版本、锚点、可跳转到条目 / 灵感库 / 运行 / 网页；采集内容可展开「经历」；被哪些产物使用；追到的采集内容 / 灵感库 / 网页数量）；入口：版本预览「溯源」与点任一段落溯源这一段、历史成片「溯源」、平台稿「溯源」。
- 验证：test_stage4_flows.py 新增 2 项（分镜第 2 镜 → 段落 2 → 主来源、成片入口；正文「[n]」段落引用、无引用段落为空、平台稿 ← 文稿版本）；stage3 溯源用例不变；vitest 新增 2 项。

### 阶段 4 · 第 ⑥ 步：抖音、小红书采集与评论（2026-10-20）
- 浏览器采集统一管理 `platforms/browser.py`：每个平台独立的 Edge 配置目录 `data/browser/<平台>`（各自的登录态）、全局并发 1、按平台限频（抖音 15 秒、小红书 45 秒）、只读页面自身的接口响应；登录页 / 验证码识别后报「登录失效」「验证码」，同步记录据此归类并走自动处理（3.9）；有界面的登录窗口（关窗即保存）；每个平台记录最近成功 / 失败。
- 适配器：抖音（订阅主页、搜索、详情、热门评论）、小红书（订阅主页、搜索、详情——接口没有时读 `__INITIAL_STATE__`、评论；链接与 media 里保留 `xsec_token`，「1.2万」类计数转整数）。粘贴抖音 / 小红书主页或搜索页链接会识别成平台订阅 / 追踪词；追踪词默认平台不变，抖音、小红书需要手动勾选（低频、有封号风险）。
- 评论：抖音、小红书加入评论来源；被项目用作来源（新建项目带来源、添加来源）时后台采一次评论（3.5 触发条件 2，原来只接了收藏）；项目来源的评论算「保留」，不在 30 天清理里删除。
- 前端：信源 · 平台接入里抖音、小红书显示浏览器登录状态（未登录 / 正常 / 登录失效 / 需要验证）与「打开登录窗口」。
- 验证：tests/test_stage4_platforms.py 8 项（两平台条目 / 评论解析、经浏览器捕获的订阅 / 搜索 / 评论、登录墙与验证码识别及归类、限频与并发 1、链接识别、项目来源触发评论采集、登录失效时评论标记失败、随笔用于新项目）；stage1 追踪词平台过滤用例改为用未接入的微博。
- 未验证：真实抖音 / 小红书页面（沙箱没有 Edge 和登录态）；接口路径按当前网页版，平台改版时只需改匹配串。

### 阶段 4 · 第 ⑦ 步：/studio 并入 /projects（2026-10-20）
- `/studio` 变成跳转：`project_id`（按 stage 进选题 / 文稿 / 产出）、`content_id` / `library` / `notes`（「用于新项目」）→ `/projects/new?source=…`，其余回项目列表；新页 `/projects/new` 新建后进入选题与创意。
- 「用于新项目」入口（灵感库图谱、随笔、分析面板、选题生成、制作状态）改为直接指向新地址；随笔作为 `note:<id>` 写进创作思路（正文第一行作主题），不算来源。
- 旧的 `/studio/*` 后端接口暂不删除：配音设置（`/studio/tts`）和旧作品仍在使用，等阶段 5 作品库 / 任务中心接管后一并清理。
- 补充（实测）：沙箱装了 Playwright Chromium 实测真实页面。浏览器不会自动走 HTTPS_PROXY，现在显式传代理（`CW_BROWSER_PROXY` 优先）；没有 Edge 的环境设 `CW_BROWSER_CHANNEL=chromium`。海外 IP、未登录时：抖音搜索页弹滑块验证码，原来只看页面地址认不出来，现在从验证码组件的接口响应识别并报「验证码」；小红书返回 not found，现在报「内容不可见或地区被拒绝」；抖音不存在的作品会跳回精选，报「作品不存在」。真实数据仍需在本机（国内网络 + 登录态）验证。

### 阶段 4 · 截图验收（2026-10-20）
- 沙箱起本机后端（8102）+ next dev（3100），Chromium 在 1280 / 1024 两档截了项目列表、选题与创意、文稿、产出、设置 · 生成服务、信源、/studio 跳转；页面无运行时错误，/studio?project_id=1&stage=2 正确落到 /projects/1/draft。
- 发现并修正：① 本机限流 200 次 / 分钟太低——单页首屏二三十个请求，快速切几页就 429 整页报错，调到 1200；② 文稿底栏「定稿」被右下角「记一笔」浮钮压住，底栏右侧留位；③ 产出空状态按钮贴着说明文字，加间距。

### 暗色 / 亮色主题切换（2026-10-20，用户反馈「暗色外壳 + 白纸面对比过大，看着累」）
- tokens 拆成 darkColor / lightColor 两套（tokens.css 的 `:root` 与 `:root[data-theme='light']`，tokens.test 校验两边同值同键）；`color.*` 改为 CSS 变量引用，页面内联颜色随主题变；antd 主题改为 `cwAntdThemeFor(mode)`。
- 文稿纸面改用 `--cw-paper-bg / ink / sub / line / ph`：暗色下是深灰纸，亮色下是米白纸，修订样式也跟着走。cw.css 里写死的暗色值（hover 底、首卡渐变、主按钮字色、状态胶囊等）换成变量；手机预览、知乎预览等模拟外观保持白底。
- 导航栏底部加切换按钮；存 localStorage `cw-theme`，`<head>` 内联脚本在渲染前设 `data-theme`，不闪。默认仍为暗色。
- 1280 下两种主题截图验收了项目、选题、文稿、信源页。

## 阶段 5（refactor/stage-5，从 stage-4 切出）

### 阶段 5 · 第 ① 步：平台改写流程（2026-10-20）
- 模板 `platform_rewrite.yaml`：平台编辑（按 `platforms` 并行，每个平台一个分支）→ 规则校验。输入支持 `dict` 类型（`output_ids`：指定写进哪个产出物）。
- 角色 `roles_platform.py`：平台编辑沿用直接改写的提示词（`output_service.platform_messages`），超限时带问题重写一次，模型调用记入调用树；规则校验逐个平台规整（截断并提示、公众号 HTML 清洗、知乎补来源），写入平台版本产出物（指定的 → 最新一个未发布的同平台版本 → 新建），登记平台稿产物，产出校验报告（每个平台是否通过 / 截断 / 提示）。
- `output_service` 拆出 `platform_messages / platform_issues / retry_messages / finalize_platform / save_platform`，单个产出物的「AI 从定稿改写」与流程共用。
- `POST /projects/{id}/platforms/rewrite {kinds, output_ids}` → 运行 id；运行中重复点击复用；结束回调写回 `project.platform_rewrite`。
- 前端：产出页左栏「AI 生成平台版本」（选平台弹窗 → 阶段条 → 结束后刷新列表），「查看过程」打开运行视图。
- 验证：tests/test_stage5_platform_flow.py 3 项（并行分支、超限重写、写进指定产出物与新建、清洗与补来源、报告、复用运行、空稿 / 非法平台拒绝）。

### 阶段 5 · 第 ② 步：一键全流程（2026-10-20）
- `pipeline_service.py`：选题研究 →〔选方向〕→ 成稿 →〔接受〕→〔定稿〕→ 讲解视频 + 平台改写。各段是独立流程运行，用项目 `spec.pipeline`（stage / runs / outputs / gates / direction / problems）串起来；引擎结束回调在专属回调之后统一调用 `pipeline_service.on_run_finished` 推进；选方向结果（或关卡关闭时第一张方向卡、或自定义方向）写进设定的主题与创作思路；成稿完成后停在「等你定稿」并发通知；`finalize` 后自动建讲解视频并开始制作、启动平台改写；某一路启动失败记为问题、其他照常，全部结束后标记完成（部分完成写明原因）。可停止（停掉在跑的运行）；运行中重复启动返回当前状态；已定稿不能从头跑。
- 接口：`POST /projects/{id}/pipeline {outputs, choose_gate, accept_gate}`、`POST /projects/{id}/pipeline/stop`；项目视图带 `pipeline`。`start_directions` 支持保留选方向关卡。
- 前端：项目栏「一键全流程」（产出勾选、两个关卡开关）与状态胶囊（阶段、去定稿、选方向 / 过程、停止；运行中每 4 秒刷新）。
- 验证：tests/test_stage5_pipeline.py 2 项（关卡选第二个方向 → 成稿 → 等定稿 → 定稿后视频启动失败记问题、平台改写完成 → 部分完成；关卡关闭取第一张、停止后定稿不再触发）；阶段 3 / 4 / 5 流程与项目测试 40 项通过。

### 阶段 5 · 第 ③ 步：重跑对比（2026-10-20）
- `GET /runs/{id}/compare?node=&other=`（`trace_service.compare_node`）：同一节点在两次运行里的输出，每个分支取最后一轮，带步骤（执行者、模型、花费、状态）、分叉时改了什么（追加提示词 / 模型组 / 执行者）和产物内容；默认和父运行比，没有父运行就和最新的分叉比；可选对象是父运行、分叉、同一父运行的其他分叉；左边放较早的运行。复用的上游两边是同一份产物。
- 前端：节点详情在有分叉关系时出现「对比」，打开 `/runs/[id]/compare`：顶部两边的运行与改动，字段逐个并排——长文字按段落对齐 + 段内字符差异（与文稿版本对比同一套），对象列表（方向卡、发现、意见、分镜）按项逐字段标出改动，图片并排，其他按值；可切换对比对象。纯逻辑在 `lib/compare.ts`。
- 验证：tests/test_stage3_flows.py 的分叉用例补对比断言（父子方向、改动、复用产物同一份、多分支）；vitest 新增 3 项，共 206 项通过；tsc、eslint 通过。

### 阶段 5 · 第 ④ 步：任务中心（2026-10-20）
- `task_service.py`：流程运行、生成任务、信源采集、内容分析合成一张任务表，统一成 TaskView（类型、标题、项目 / 产出物、状态 running / waiting / failed / done / stopped、当前阶段、耗时、花费、失败原因 + 处理建议、跳转链接、能否停止 / 重试）；进行中在前、其余按时间倒序；按类型、状态、项目、天数筛选；暂停的运行显示「已暂停：原因」。
- 接口：`GET /tasks`、`GET /tasks/summary`、`POST /tasks/{key}/retry|stop`（流程运行；重试即从失败处继续，已完成步骤复用）、`GET /tasks/stream`（SSE，3 秒检查一次，有变化推送进行中列表与刚结束的任务）。
- 前端：导航「任务」改为按钮，显示进行中数量（SSE + 30 秒兜底），点开全局抽屉（进行中 / 失败 / 完成分组，「全部任务」进入 `/tasks`）；任务结束 / 等你处理时右下角弹通知；`/tasks` 页按状态、类型、项目、时间筛选。任务行：类型图标、项目、产出物、阶段、耗时、花费、状态、失败原因与建议、重试 / 停止。
- 验证：tests/test_stage5_tasks.py（合并、时间范围、排序、阶段、建议、筛选、摘要、不能停止的类型）；vitest 208 项；两种主题截图验收 `/tasks` 与抽屉（修正暗色下标题用错变量、抽屉 `width` 弃用警告）。

### 阶段 5 · 第 ⑤ 步：作品库（2026-10-20）
- `works_service.py`：按项目归档产出物。完成 / 已导出 / 已发布自动收录；草稿可手动「加入作品库」（`settings.in_works = true`），`false` 表示移出；旧工作台做的、没挂在产出物上的完成成片列为「旧成片」。每件带摘要、字数、可复制文本（平台版标题 + 正文 + 话题，公众号去掉 HTML；提示词包为 Markdown）、最新成片的预览 / 下载地址、发布链接；按类型、关键词（项目名或作品标题 / 摘要）、项目筛选。
- 接口：`GET /works`、`POST|DELETE /outputs/{id}/works`。
- 前端：导航「作品」上线（`/works`）：类型分段、搜索，按项目分组的卡片（视频直接播放、文字显示摘要），复制 / 下载 / 已发布链接 / 移出；产出物工作区头部加「加入作品库 / 移出作品库」。
- 验证：tests/test_stage5_works.py（收录规则、移出、旧成片只列完成的、复制文本、筛选与搜索）；vitest 208 项；两种主题截图验收 `/works`。

### 阶段 5 · 第 ⑥ 步：提示词包与外部 agent 回传（2026-10-20）
- `delivery_service.py`：回传的成片存成该产出物的制作物（`data/studio/deliveries/{项目}/{id}.mp4`，`settings.delivered`），产出物标为完成，`content.deliveries` 记来源（上传 / 外部 agent）、文件名、大小、时长（有 ffprobe 时）、说明；只收视频扩展名，上限 4 GB，空文件拒绝。本机路径是复制，下载地址会流式下载。
- 工作台工具新增 `read_bundle`（读取提示词包 Markdown 与回传说明）和 `upload_output`（`path` 本机绝对路径或 `url`）；令牌可限定项目（`project_ids`），越权调用返回拒绝；MCP 说明更新。
- 接口：`POST /outputs/{id}/deliveries`（multipart 上传，先写暂存再挂上，失败不留临时文件）；`POST /workbench/tokens` 支持 `project_ids`。
- 前端：提示词包工作区加「外部 agent 接入」（一键生成限本项目、24 小时的令牌和 MCP 配置片段，附 read_bundle / upload_output 用法）与「回传成片」（说明 + 选择视频上传，历史回传带预览、大小、时长、来源、下载）；回传后的成片自动进作品库。
- 验证：tests/test_stage5_delivery.py 2 项（MCP 工具清单、读取提示词包、跨项目拒绝、相对路径 / 非视频拒绝、回传后产出物状态与记录、预览下载、作品库可见；上传接口与非视频 422、暂存目录清空）；截图验收提示词包工作区。

### 阶段 5 · 第 ⑦ 步：视频生成接口（2026-10-20）
- `video_generation.py`：`generate_video(prompt, first_frame, duration, aspect) → 任务`。适配器按 `api_format` 扩展，每个实现 `submit` / `poll`；先接 OpenAI 兼容视频接口（`POST /videos`，首帧走 `input_reference`；`GET /videos/{id}` 查状态和进度；`/videos/{id}/content` 下载）。任务记在 `generation_jobs`（kind=video），厂商任务 id、提交时间、进度写进 `params`；轮询到完成 / 失败 / 30 分钟超时，结果存 `data/generations/<job>/0.mp4`。单价按元 / 秒，每日上限与生图同一套；时长只能选服务声明的（`capabilities.durations`），可关首帧。
- 服务重启：已提交到厂商的视频任务接着轮询（不重复提交），没提交的标失败提示重新生成。测试连接对视频服务只查一次任务列表，不产生费用。存入并使用支持视频（灵感库里是 mp4，挂到分镜）；图片接口拒绝用视频服务生图。
- 接口：`POST /generations/videos`；服务的 `api_format` 增加 `openai_videos`；文件接口按扩展名返回 `video/mp4`；任务中心显示「生成视频」与厂商进度。
- 前端：设置 · 生成服务可加视频服务（类型、可选时长、首帧开关、元 / 秒），开关排版修正；讲解视频产出的「分镜关键帧」下加「视频片段」：按镜头生成（提示词取分镜提示词 / 画面，可用该镜关键帧作首帧，时长取最接近分镜时长的可选值，显示预计花费），任务进度、预览、存入并使用。
- 验证：tests/test_stage5_video_generation.py 3 项（提交 → 轮询进度 → 下载、花费、任务中心、存入并使用；超每日上限、厂商失败、重启续跑与未提交标失败；OpenAI 视频适配器的请求 / 轮询 / 下载）；阶段 4 生图回归；截图验收设置页。

### 阶段 5 · 第 ⑧ 步：清理旧 /studio/*（2026-10-20）
- 删除旧工作台接口 `app/api/v1/studio.py`（目录、项目增改、版本、AI 稿、制作提示、音频、LRC、定稿、渲染、Harness 制作、制作任务列表）。还在用的两块迁到 `app/api/v1/renders.py`：成片信息 / 预览 / 下载 / 动画工程 `/renders/{id}…`（`artifact_dict` 的路径同步改，回传的 mov / webm 按扩展名给类型），配音设置 `/voice/tts`（GET / PUT / 试听）。
- `studio_service.py` 去掉只被旧接口用的函数（约 400 行：保存项目、版本视图、音频 / LRC、定稿、排队渲染、Harness 制作、制作任务、心跳等）；新流程用到的（成片信息、进度、工程文件、草稿整理、启动恢复）保留。
- 前端：删 `studioApi` 与 Studio* 类型、旧顶栏「制作任务」(`ProductionStatus`，已被任务中心替代)、没人用的 `CreativePresetCard` / `DraftComparison`；配音设置（`StudioVoice`，改用 `/voice/tts`）放进「设置 · 生成服务」。`/studio` 页面仍只做跳转。
- 验证：后端全量 pytest 通过（1 项跳过）；vitest 208 项；tsc、ESLint、ruff、分层检查通过。

## 阶段 6：飞书多维表格（2026-10-20）

- 后端：`feishu_records` 表（迁移 c3e5a7b9d104）；`feishu_service`：自建应用 tenant_access_token、表格链接解析（/base/ 与知识库 /wiki/ 换 obj_token）、字段映射按列类型写入（链接 / 日期 / 数字 / 单选 / 多选 / 文本）、新建或更新记录、保存 record_id。
- 写入时机：「记入飞书」（条目详情、项目栏）；可选自动写入（结论变「值得做」、新建项目）；项目定稿、产出物完成 / 发布、外部回传成片时后台只更新状态列（未开始 / 创作中 / 已产出）。
- 失败记 failed，进任务中心（类型「飞书」），可重试；权限、列名错误给出处理建议。
- API：GET/PUT /feishu/settings、POST /feishu/test、POST/GET /feishu/records、POST /feishu/records/{id}/retry。
- 前端：设置 · 飞书（凭证、表格链接、测试连接、字段映射带列名补全、自动写入开关）；FeishuButton。
- 测试：tests/test_stage6_feishu.py（模拟飞书接口）；全量 pytest、vitest 208、tsc、eslint、ruff、分层检查通过；设置页深浅色截图。
- 待验收：需要真实飞书应用 App ID / Secret 与多维表格。
- 补充：支持 Lark 国际版（larksuite.com 链接走 open.larksuite.com）；`CW_FEISHU_API_BASE` 可指向本地模拟服务 `scripts/dev/fake_feishu.py` 联调。
- 本地联调（模拟飞书服务 + 浏览器）：设置页保存与测试连接 → 条目「记入飞书」→ 项目「记入飞书」→ 定稿后状态列变「创作中」→ 公众号版填发布链接后变「已产出」，任务中心显示对应记录。注意：本机有 HTTP 代理时，联调要设 NO_PROXY=127.0.0.1,localhost。

## 收尾：能在沙箱里做完的部分（2026-10-20）

- 回归矩阵核对：原「待处理缺陷」6 条均已修复，移入已修复并写明回归测试。
- 旧页面跟随主题：管理页（信源列表、内容、AI 模型、Prompt、系统）和日报 / 周刊 / 月刊包在 `.cw-legacy`，Tailwind 调色板换成 --cw-* 变量，antd 跟随主题；补删阶段 5 漏提交的旧工作台前端（制作任务条、studioApi、旧类型），配音设置改用 /voice/tts。
- 分镜表拖动排序（@dnd-kit）：拖动柄，键盘空格拿起 / 方向键移动；替换上移 / 下移按钮。
- 正文 TipTap 富文本：存储仍是纯文本正文（`lib/md-lite.ts` 互转，每个顶层块一段，段落 id 不变），工具栏与 Markdown 快捷输入，选区换算 AI 修改范围。
- 音乐 MV（阶段 5 清理旧接口时音频 / LRC 上传随 studio.py 删掉，这里在项目接口重做）：`mv_service`，`GET/POST /projects/{id}/audio`、`/audio/file`、`PUT /projects/{id}/lrc`；歌词时间轴 LyricTimeline（wavesurfer.js 波形、歌词点、分镜边界拖动吸附歌词、点歌词跳转）。
- 浏览器实测：分镜拖动、富文本输入与自动保存、MV 上传音频 → 粘贴 LRC → 拖动边界，均通过；测试 tests/test_stage6_mv.py、lib/__tests__/md-lite.test.ts、mv.test.ts。

## 2026-10-20 · review 改进（stage-6）

- 文稿状态：自动保存后显示「未存版本」（空心点），只有还在写入时才显示「未保存」；底栏同步改为「已保存 · 还没存成版本」。
- 分镜行菜单「…」：改写这一镜（选中该镜、切到 AI 助手并预填指令）、拆成两镜（时长对半、旁白 / 字幕在最靠近中间的句末断开）、合并到下一镜（时长相加、文字相接、转场取后一镜）、复制、删除。纯函数在 `lib/projects.ts`（splitShot / mergeShotWithNext / splitTextNearMiddle）。
- 分镜表操作列固定在右侧、文字列最小宽度 96px，窄屏不再把操作按钮挤没。
- 大纲拖动整节：`OutlineTree`（dnd-kit），同级标题之间换位置，连同子标题和正文一起移动；Alt+↑/↓ 键盘等价。`lib/projects.ts` moveSection / sectionRange。
- 全局跳转 Ctrl+K（`design/command.tsx`、`lib/command.ts`）：页面、项目、常用操作，支持拼音首字母和英文别名；「?」打开快捷键面板；导航底部加「跳转」入口。
- MV 时间轴：选中分镜时波形跳到该镜开头；播放时高亮并滚动到当前歌词（`lib/mv.ts` cueAt）；波形放大 / 缩小。
- 首页「开始使用」三步引导（配模型 → 加信源 → 建项目），全部完成或点「不再显示」后隐藏（`design/onboarding.tsx`）。
- 后端：旧 `Studio*` ORM 类改名为 `Project` / `ProjectRevision` / `ProjectUpload` / `ProjectArtifact` / `ProjectOutput`（表名不变，无迁移）；`models/studio.py` → `models/project.py`，`studio_repo` → `project_repo`。告警规则、慢查询计数、迁移锁释放、B 站 cookie 预热处的 `except: pass` 改为记日志。
- 前端卫生：ESLint 警告 105 → 22（补 hooks 依赖、删未用导入）。
- 未做（判断后放弃或留待以后）：旁白全文不改富文本（它直接喂给配音，保持纯文本更稳）；`/stats/jobs` 保留，作为任务中心里调度任务的明细页；十几处轮询合并为全局事件流、旧管理页布局重做、类型改为 OpenAPI 生成，改动面大，留作下一阶段。
- E2E 脚本：work/scripts/e2e_p1.py、e2e_cmd.py、e2e_mv.py（扩展）。

## 视觉对齐样张（2026-10-20）
- 9c285c6：旧页面调色板按「方向 A 调色台」样张：主按钮白底黑字、色块底中性、去渐变 / 投影、字体统一；今日页收藏 / 开始创作、虚线无指标框、顶栏搜索；跨平台共振不撑出侧栏。
- 74a6802 / fdcaccf：时间轴 今天 / 48 小时 / 7 天（`/today/signals?range=`）；导航底部工具图标并行；旧页面下拉框样式；整页空状态虚线框；信号排序时区修正。

## 全局搜索与通知中心（2026-10-21）
- 搜索页 /search：库内检索（采集内容、灵感库、随笔、项目、产出、报告，命中高亮）+「去平台抓」：选平台按关键词现抓，复用追踪词信源整条采集链路（同一个词只建一个信源），默认只抓一次（新建的信源抓完停用），勾「以后自动追踪」则保留为追踪词。后端 search_service、/search、/search/crawl、/search/platforms、/search/tracking；测试 test_search_service.py。
- Ctrl+K：输入即显示库内命中（每类 3 条），第一项「搜索『词』」进搜索页；`/` 打开面板。
- 通知中心：导航底部铃铛（未读红点，60 秒 + 窗口聚焦刷新）、抽屉（只看未读、全部已读、删除，按类别 / 正文路径跳转，lib/notify.ts）。
- 仍为 ilike，全文索引（pg_trgm）留待数据量上来再加。

## 兜底页、统一提示、CI（2026-10-21）
- app/error.tsx（检测后端是否可达：连不上给启动提示，连得上给错误信息与编号，重试 / 回今日）、global-error.tsx、not-found.tsx（去搜索 / 回今日）、loading.tsx（骨架，尊重 prefers-reduced-motion）；design/fallback.tsx。
- design/feedback.tsx：静态 message / Modal / notification 统一套调色台主题（ConfigProvider.config holderRender，AppShell 调用）；confirmAction 替换全部 window.confirm（6 处），toast 替换 alert（3 处）；toastUndo 供删除类操作「先做后撤」。
- 翻译（google_provider）分块共用一个 httpx 客户端并显式超时；其余 AsyncClient 复查后均已有 timeout。
- CI：新增 frontend-lint（eslint --quiet，error 阻断）与 backend-tests（postgres:17 服务容器跑全量 pytest），push 触发加上 refactor/** 分支。

## 2026-10-21 清单改进（stage-6）

- fb98deb 今日时间线：刻度 / 播放头 / 日期统一按北京时间（lib/time-cn.ts）；清早自动缩放到 [00:00, max(现在+3h, 09:00)]、未来区斜纹、密集片段合并成带数字的密度柱、扫描点亮、悬停提示与信息流联动；无封面时按形态生成信号图（lib/signal-art.ts）。
- f1e3bd0 花费总览 /costs（cost_service：LLM 调用按用途 / 场景 / 模型 / 项目，生成任务按种类 / 服务；北京时间分天；今日分析预算）；CI：日报测试按北京时间、导航覆盖测试、aiohttp / multidict 升级、npm audit 只审运行时依赖。
- 1ad6085 全局事件流 /events/stream（event_hub：tasks 3 秒、notifications 15 秒、sources 60 秒，单循环多订阅，无变化不推）；前端 lib/events.ts 整页一条连接，任务中心 / 抽屉 / 运行列表 / 视频生成改为事件触发刷新。
- 102ec1b 发布排期与数据回收（publishing_service + work_metric_observations 表）：排期与到点提醒、发布日历、发布链接按时回抓平台指标（2 天内每 3 小时 → 14 天内每 12 小时 → 90 天内每 3 天）、按形态 / 平台的效果中位数。
- 8086886 公众号草稿箱直推（wechat_mp_service，设置 · 公众号）。
- 7bc6d1b 一键备份（backup_service，设置 · 备份，每周日自动；scripts/restore_backup.py 还原）。
- 9ce3f0c 健壮性：静默吞错改记日志、日志轮转（data/logs/backend.log，10MB×5）、重启恢复生图 / 飞书任务、搜索 pg_trgm 索引。
- c208b6e 项目复制与批量操作。
- N+1 抽查：任务列表 5、作品 3、项目 3、搜索 9、今日信息流 19 条查询，热路径没有循环查库，不再改。
- 下一步：前端全站重做，规范见 work/design-review-1.md。

## 投票拉票功能（2026-10-21，stage-6）

单用户、无登录；四项都融进已有流程，没有单开孤立页面。

- **平台腔调**（7b9d343）：平台版本新增 `douyin`（前三秒钩子 hook、一行一镜【画面：…】口播、3–5 话题）和 `bilibili`（开头 15 秒看点、【弹幕】互动点、简介 ≤250、3–10 标签）。规则在 output_rules.py（SCRIPT_KINDS），平台改写流程 / 全流程 / 作品库 / 发布都认。前端 design/platform-preview.tsx 三种原生样式预览（小红书笔记、抖音竖屏自动轮播分镜、B站播放器飞弹幕，reduced-motion 下静止），lib/script.ts 解析口播稿。产出总览顶部「同一份稿，N 种腔调」三栏并排。
- **爆款拆解**（0bf3d19）：breakdown_service.py，POST /library/breakdown（url / content_id / library_item_id）。拆过的一律收进灵感库（import_method=breakdown），结果存 meta.breakdown；评论用评论服务缓存或按平台直接抓；hot_phrases 本地粗算 2–4 字高频片段再交模型。入口：条目详情、灵感库条目、搜索框 / Ctrl+K 贴链接。「照这个结构写」= 新建项目（来源 library:id，ProjectCreate.intent 写进创作思路）。
- **今日梗雷达**（fb39370）：meme_service.py，GET /trending/memes，24h 热榜标题 + 72h 热门评论，按北京时间每天一次存 app_settings.meme_radar。今日页侧栏卡片（拿它开稿 → /projects/new?theme&intent），写稿底栏「今日梗」插入示范用法。
- **创作人格**（5eee81e）：persona_service.py，GET /monthly-digests/persona?month=，规则判定 9 种人格（不调模型）。月刊顶部 PersonaPanel，lib/persona-card.ts 生成 1080×1920 SVG → canvas 导出 PNG，可印投票口令（localStorage cw.persona.vote），复制配图文案。看「最新」时按当月，点了历史期按那一期。
- 演示数据：backend/seed_vote.py（dev 库直写）。截图 work/shots/r/vote2-*。
