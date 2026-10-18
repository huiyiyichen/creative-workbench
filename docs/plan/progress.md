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
