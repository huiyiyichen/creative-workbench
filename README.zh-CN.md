# 创意工作台

创意工作台是本地优先的创作者工作台：

`热点/资料 → 选题 → 内容 spec → 成稿 → 成片 → 作品库`

创作系统把内容结构模板、视觉风格、表现方案和输出媒介分开保存。

## 本地启动

双击仓库根目录的 `start.cmd`，就会启动数据库、后端、前端并打开工作台。
重复启动会复用已有服务；失败时窗口保留错误提示。不需要 Docker 或管理员权限。
默认运行编译后的本地版本。预装 Node.js 20+ 和 uv 后，首次启动会安装依赖、下载 PostgreSQL 程序、初始化独立工作库并构建前端；后续启动复用环境和构建缓存。开发热更新模式另用 `start-local.ps1 -Development`。

也可以从 PowerShell 启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-local.ps1 -OpenBrowser
```

- 应用：`http://127.0.0.1:3000`
- 工作台：`http://127.0.0.1:3000/studio`
- API：`http://127.0.0.1:8102`

原生脚本会启动本地 PostgreSQL、增量迁移、FastAPI 和 Next.js。Docker 仍可选；独立的 `dawei-tianlong-canvas` 项目不会被修改。
已有配置和数据库保留；新的源码目录会创建自己的空数据库。应用端口被其他服务占用时，会使用后续空闲端口，实际地址以启动窗口为准。
构建输出在 `frontend/.next-local`，与开发缓存隔离；启动会检查页面、接口和必要 JavaScript，确认可用后才打开浏览器。

## 创作流程

1. 选择采集内容，或填写手动主题。
2. 选择内容模板、视觉风格、表现方案和制作路径。
3. 生成规则草稿，编辑标题、梗概、分镜、提示词、镜头和声音。
4. 确认不可变版本后进入制作。
5. 动画讲解由 DeepSeek Harness 生成 Remotion 工程，千问生成配音；MV 上传音频和 UTF-8 LRC。
6. 制作完成后，在作品库预览和下载 MP4、字幕及动画源工程。

没有可用 AI 模型时，规则编稿仍可用，且不会被显示为 AI 结果。

## 风格库

首批可执行风格包包括：包豪斯、构成主义、瑞士国际主义、粗野主义、解构、写实、新表现主义。模板与风格独立复用。

## 验证

```powershell
cd frontend
npx tsc --noEmit
npm run build

cd ..\backend
uv run --no-sync ruff check app tests
uv run --no-sync python -m pytest tests/test_studio_lrc.py tests/test_config.py -q -o addopts='' --noconftest
```

历史迁移和旧数据库表保留用于兼容；已移除模块不再注册到运行时路由和导航。
