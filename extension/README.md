# 存到灵感库（Edge / Chrome 扩展，MV3）

右键网页：存这一页、存图片、存链接、存选中文字；点工具栏图标存当前页。全部写入本机创意工作台的灵感库（`POST /api/v1/library/extension/save`，导入方式记为「扩展」）。

安装：Edge 打开 `edge://extensions` → 开启「开发人员模式」→「加载解压缩的扩展」→ 选择本目录。
服务地址默认 `http://localhost:8000/api/v1`，可在扩展「选项」里修改并测试连接。后端已放行 `chrome-extension://` / `edge-extension://` 来源。
