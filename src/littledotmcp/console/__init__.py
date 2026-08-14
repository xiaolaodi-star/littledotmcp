"""M11 管理端（Web Console，方案 A：同进程内嵌 Web）。

包结构：
- auth.py   ：管理端会话签发/校验、空库初始化管理员
- deps.py   ：路由级依赖（require_role / require_owner）
- routes.py ：管理 API + 页面路由（custom_route 挂载）
- errors.py ：MCP 工具调用异常采集 middleware
- static/   ：离线静态单页（index.html / app.js / style.css）
"""

from __future__ import annotations
