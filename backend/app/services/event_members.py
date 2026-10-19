"""事件成员视图：``content_event_members`` 不含规范条目（canonical，库约束禁止它同时是成员），
发现区的查询要把它补上。返回 (event_group_id, content_id) 的子查询，已排除「移出此事件」的成员。"""

from __future__ import annotations

from sqlalchemy import literal, select, union_all

from app.models.content_event import ContentEventGroup, ContentEventMember


def event_members_subquery(name: str = "em"):
    members = select(
        ContentEventMember.event_group_id.label("event_group_id"),
        ContentEventMember.content_id.label("content_id"),
        ContentEventMember.relation_type.label("relation_type"),
        ContentEventMember.confidence.label("confidence"),
    ).where(ContentEventMember.review_status != "rejected")
    canonical = select(
        ContentEventGroup.id.label("event_group_id"),
        ContentEventGroup.canonical_content_id.label("content_id"),
        literal("canonical").label("relation_type"),
        literal(1.0).label("confidence"),
    ).where(ContentEventGroup.status != "archived")
    return union_all(members, canonical).subquery(name)
