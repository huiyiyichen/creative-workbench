"""Windows 桌面集成：托盘图标与系统通知（改造方案 3.7 / 10.1）。

只在 Windows 上运行（``pythonw -m app.desktop.tray``），由 ``start-local.ps1`` 拉起。
判断逻辑与平台无关、可单测；pystray / windows-toasts 延迟导入。
"""
