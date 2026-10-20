"""灵感库图谱（改造方案 6.7）。

节点：灵感库条目、随笔、专题、风格、模板、项目。边：
* 显式关联（``library_links``）：提炼、生成、提取、双链、手动、用于项目；
* 推导关联：同一事件、同作者、同标签（按组串成链，避免大团完全图）。

前端（sigma.js + graphology）按类型着色、按关联数定大小；``center`` 给出一度 / 二度的局部图谱。
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dossier import TopicDossier
from app.models.library import LibraryItem, LibraryLink, Note
from app.models.styles import ContentTemplate, VisualStyle
from app.services.event_members import event_members_subquery

_em = event_members_subquery("graph_em")

NODE_TYPES = ("item", "note", "dossier", "style", "template", "project")
MAX_ITEMS = 2000
CHAIN = 3  # 同标签 / 同作者 / 同一事件：每个节点最多连组里后面的 3 个


def _key(kind: str, rid: int) -> str:
    return f"{kind}:{rid}"


def parse_key(key: str) -> tuple[str, int]:
    kind, _, rid = key.partition(":")
    if kind not in NODE_TYPES or not rid.isdigit():
        raise ValueError(f"无效节点：{key}")
    return kind, int(rid)


async def build_graph(
    db: AsyncSession,
    *,
    types: list[str] | None = None,
    days: int | None = None,
    center: str | None = None,
    depth: int = 2,
) -> dict[str, Any]:
    wanted = set(types or NODE_TYPES) & set(NODE_TYPES)
    if center:
        parse_key(center)
        wanted |= {center.split(":", 1)[0]}
    nodes: dict[str, dict[str, Any]] = {}

    stmt = select(LibraryItem).where(LibraryItem.archived_at.is_(None))
    if days:
        stmt = stmt.where(LibraryItem.created_at >= datetime.now(UTC) - timedelta(days=days))
    items = (await db.execute(stmt.order_by(LibraryItem.id.desc()).limit(MAX_ITEMS))).scalars().all()
    if "item" in wanted:
        for it in items:
            nodes[_key("item", it.id)] = {
                "key": _key("item", it.id),
                "type": "item",
                "kind": it.asset_kind or it.kind,
                "label": (it.title or "")[:60],
                "thumb": bool(it.thumb_small),
                "color": it.dominant_color,
            }
    by_content = {it.content_id: it.id for it in items if it.content_id}

    links = (await db.execute(select(LibraryLink))).scalars().all()
    ref_ids: dict[str, set[int]] = defaultdict(set)
    for link in links:
        for kind, rid in ((link.from_type, link.from_id), (link.to_type, link.to_id)):
            ref_ids[kind].add(rid)

    if "note" in wanted:
        nstmt = select(Note).where(Note.deleted_at.is_(None))
        if days:
            nstmt = nstmt.where(Note.created_at >= datetime.now(UTC) - timedelta(days=days))
        for n in (await db.execute(nstmt.order_by(Note.id.desc()).limit(MAX_ITEMS))).scalars():
            first = (n.body or "").strip().splitlines()[0] if (n.body or "").strip() else "（图片 / 语音）"
            nodes[_key("note", n.id)] = {"key": _key("note", n.id), "type": "note", "kind": "note", "label": first[:40]}
    if "dossier" in wanted and ref_ids["dossier"]:
        for d in (await db.execute(select(TopicDossier).where(TopicDossier.id.in_(ref_ids["dossier"])))).scalars():
            nodes[_key("dossier", d.id)] = {
                "key": _key("dossier", d.id),
                "type": "dossier",
                "kind": "dossier",
                "label": d.title[:60],
            }
    for kind, model in (("style", VisualStyle), ("template", ContentTemplate)):
        if kind in wanted and ref_ids[kind]:
            for s in (await db.execute(select(model).where(model.id.in_(ref_ids[kind])))).scalars():
                nodes[_key(kind, s.id)] = {
                    "key": _key(kind, s.id),
                    "type": kind,
                    "kind": kind,
                    "label": s.name,
                    "ref": s.key,
                }
    if "project" in wanted and ref_ids["project"]:
        from app.models.studio import StudioProject

        for p in (await db.execute(select(StudioProject).where(StudioProject.id.in_(ref_ids["project"])))).scalars():
            nodes[_key("project", p.id)] = {
                "key": _key("project", p.id),
                "type": "project",
                "kind": "project",
                "label": (p.title or "")[:60],
            }

    edges: dict[tuple[str, str], str] = {}

    def add(a: str, b: str, relation: str) -> None:
        if a == b or a not in nodes or b not in nodes:
            return
        pair = (a, b) if a < b else (b, a)
        edges.setdefault(pair, relation)  # 显式关联先加，优先保留

    for link in links:
        a_kind, a_id = link.from_type, link.from_id
        if a_kind == "content":  # 原内容 → 提取：画在收藏了这条内容的条目上
            if a_id not in by_content:
                continue
            a_kind, a_id = "item", by_content[a_id]
        add(_key(a_kind, a_id), _key(link.to_type, link.to_id), link.relation)

    if "item" in wanted:

        def chain(groups: dict[Any, list[int]], relation: str) -> None:
            for ids in groups.values():
                ids = sorted(set(ids))
                for i, a in enumerate(ids):
                    for b in ids[i + 1 : i + 1 + CHAIN]:
                        add(_key("item", a), _key("item", b), relation)

        authors: dict[str, list[int]] = defaultdict(list)
        tags: dict[str, list[int]] = defaultdict(list)
        for it in items:
            if it.author:
                authors[it.author].append(it.id)
            for t in it.tags or []:
                tags[t].append(it.id)
        if by_content:
            rows = (
                await db.execute(
                    select(_em.c.event_group_id, _em.c.content_id).where(_em.c.content_id.in_(list(by_content)))
                )
            ).all()
            events: dict[int, list[int]] = defaultdict(list)
            for gid, cid in rows:
                events[gid].append(by_content[cid])
            chain(events, "same_event")
        chain(authors, "same_author")
        chain(tags, "same_tag")
        if by_content:
            for a, b in await _similar_pairs(db, by_content):
                add(_key("item", a), _key("item", b), "similar")

    edge_list = [{"source": a, "target": b, "relation": r} for (a, b), r in edges.items()]

    if center:
        if center not in nodes:
            return {"nodes": [], "edges": [], "center": center}
        adj: dict[str, set[str]] = defaultdict(set)
        for e in edge_list:
            adj[e["source"]].add(e["target"])
            adj[e["target"]].add(e["source"])
        dist = {center: 0}
        q = deque([center])
        while q:
            cur = q.popleft()
            if dist[cur] >= max(1, min(depth, 2)):
                continue
            for nb in adj[cur]:
                if nb not in dist:
                    dist[nb] = dist[cur] + 1
                    q.append(nb)
        nodes = {k: {**v, "depth": dist[k]} for k, v in nodes.items() if k in dist}
        edge_list = [e for e in edge_list if e["source"] in nodes and e["target"] in nodes]
    else:
        # 全局图谱默认不画孤立的随笔，避免几百个散点
        connected = {e["source"] for e in edge_list} | {e["target"] for e in edge_list}
        nodes = {k: v for k, v in nodes.items() if v["type"] == "item" or k in connected}

    degree: dict[str, int] = defaultdict(int)
    for e in edge_list:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
    out_nodes = [{**v, "degree": degree[k]} for k, v in nodes.items()]
    return {"nodes": out_nodes, "edges": edge_list, "center": center}


SIMILAR_MIN = 0.78
SIMILAR_TOP = 3


async def _similar_pairs(db: AsyncSession, by_content: dict[int, int]) -> list[tuple[int, int]]:
    """语义相似（6.7）：收藏条目对应内容的本地向量，余弦 ≥ 阈值的每条取最相近的前 3 条。"""
    import numpy as np

    from app.models.content_observation import ContentEmbedding
    from app.services import embeddings

    rows = (
        await db.execute(
            select(ContentEmbedding.content_id, ContentEmbedding.vector).where(
                ContentEmbedding.content_id.in_(list(by_content)), ContentEmbedding.model == embeddings.MODEL_NAME
            )
        )
    ).all()
    seen: set[int] = set()
    ids: list[int] = []
    vecs = []
    for cid, raw in rows:
        if cid in seen:
            continue
        seen.add(cid)
        ids.append(by_content[cid])
        vecs.append(embeddings.from_bytes(raw))
    if len(ids) < 2:
        return []
    mat = np.vstack(vecs).astype(np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = mat / np.where(norms == 0, 1, norms)
    sims = mat @ mat.T
    np.fill_diagonal(sims, -1)
    pairs: list[tuple[int, int]] = []
    for i in range(len(ids)):
        for j in np.argsort(-sims[i])[:SIMILAR_TOP]:
            if sims[i, j] >= SIMILAR_MIN:
                pairs.append((ids[i], ids[int(j)]))
    return pairs
