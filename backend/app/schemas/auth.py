"""本地用户的响应 schema。

单用户本地应用没有注册、登录、改密码（第 13 节 #8），只保留用户信息响应。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str | None = None
    plan: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
