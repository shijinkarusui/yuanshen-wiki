"""共享的请求参数校验工具。"""
from __future__ import annotations

import uuid

from app.core.errors import ApiError


def parse_uuid(value: str | None, field_name: str, *, optional: bool = False) -> uuid.UUID | None:
    """解析 UUID 字符串；非法时抛 404（资源定位语义），缺失且 optional 时返回 None。"""
    if value is None:
        if optional:
            return None
        raise ApiError("not_found", 404, f"{field_name} 缺失")
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ApiError("not_found", 404, f"{field_name} 不是合法的 UUID")
