"""阶段 4：AI 修改建议的校验、部分应用与冲突处理。"""

from __future__ import annotations

import pytest

from app.schemas.projects import DraftSave, ProjectCreate
from app.schemas.studio import StudioDraft
from app.services import project_service as ps, suggestion_service as ss

BODY = "第一段讲背景。\n\n第二段讲数据。\n\n第三段收尾。"


def _ids(body=BODY):
    return [p["id"] for p in ps.paragraphs_with_ids(body)]


def test_validate_ops_filters_bad_and_scope():
    draft = {"body": BODY, "shots": [{"seconds": 3, "visual": "a"}]}
    a, b, c = _ids()
    raw = [
        {"op": "replace_paragraph", "id": a, "text": "新开头"},
        {"op": "replace_paragraph", "id": "p_nope", "text": "x"},
        {"op": "replace_paragraph", "id": b, "text": ""},
        {"op": "update_shot", "index": 0, "field": "visual", "value": "b"},
        {"op": "update_shot", "index": 5, "field": "visual", "value": "b"},
        {"op": "update_shot", "index": 0, "field": "hack", "value": "b"},
        {"op": "drop_table"},
    ]
    ops = ss.validate_ops(raw, draft, {"type": "all"})
    assert [o["op"] for o in ops] == ["replace_paragraph", "update_shot"]
    assert [o["op_id"] for o in ops] == ["o1", "o2"]
    scoped = ss.validate_ops(raw, draft, {"type": "paragraphs", "ids": [c]})
    assert scoped == []
    assert len(ss.validate_ops([{"op": "delete_paragraph", "id": a}] * 80, draft, {})) == ss.MAX_OPS


def test_apply_ops_partial_and_shots():
    a, b, c = _ids()
    draft = {"body": BODY, "shots": [{"seconds": 3, "visual": "一"}, {"seconds": 4, "visual": "二"}]}
    ops = [
        {"op_id": "o1", "op": "replace_paragraph", "id": a, "text": "新开头。"},
        {"op_id": "o2", "op": "insert_after", "id": b, "text": "补一个例子。"},
        {"op_id": "o3", "op": "delete_paragraph", "id": c},
        {"op_id": "o4", "op": "move_shot", "from": 1, "to": 0},
        {"op_id": "o5", "op": "insert_shot", "after": -1, "shot": {"seconds": 2, "visual": "零"}},
    ]
    out, applied, conflicts = ss.apply_ops(draft, [ops[0], ops[2]])
    assert out["body"] == "新开头。\n\n第二段讲数据。" and applied == ["o1", "o3"] and not conflicts
    out, applied, _ = ss.apply_ops(draft, ops)
    assert out["body"] == "新开头。\n\n第二段讲数据。\n\n补一个例子。"
    assert [s["visual"] for s in out["shots"]] == ["零", "二", "一"]


def test_apply_ops_conflict_when_target_changed():
    a, b, _ = _ids()
    base = {"body": BODY, "shots": [{"seconds": 3, "visual": "一"}]}
    # 别处改了第一段与第一镜
    current = {"body": BODY.replace("第一段讲背景。", "第一段被人改过。"), "shots": [{"seconds": 3, "visual": "改"}]}
    ops = [
        {"op_id": "o1", "op": "replace_paragraph", "id": a, "text": "AI 开头"},
        {"op_id": "o2", "op": "replace_paragraph", "id": b, "text": "AI 数据"},
        {"op_id": "o3", "op": "update_shot", "index": 0, "field": "visual", "value": "AI"},
    ]
    out, applied, conflicts = ss.apply_ops(current, ops, base)
    assert applied == ["o2"] and conflicts == ["o1", "o3"]
    assert "第一段被人改过。" in out["body"] and "AI 数据" in out["body"]


@pytest.mark.asyncio
async def test_suggestion_flow_accept_one(db, monkeypatch):
    p = await ps.create_project(db, 1, ProjectCreate(theme="主题"))
    await ps.save_draft(db, p["id"], DraftSave(draft=StudioDraft(body=BODY)))
    a, b, _ = _ids()

    async def fake(messages):
        return {
            "ops": [
                {"op": "replace_paragraph", "id": a, "text": "口语开头"},
                {"op": "replace_paragraph", "id": b, "text": "口语数据"},
            ]
        }, {"model": "fake"}

    monkeypatch.setattr(ss, "_call_model", fake)
    sug = await ss.create_suggestion(db, p["id"], scope={"type": "all"}, quick="colloquial")
    assert sug["status"] == "pending" and len(sug["ops"]) == 2 and "base_draft" not in sug["scope"]
    assert (await ps.list_versions(db, p["id"]))["items"] == []  # 生成建议不改文稿
    r = await ss.apply_suggestion(db, sug["id"], ["o1"])
    assert r["status"] == "partial" and r["version"] == 1
    assert r["draft"]["draft"]["body"].startswith("口语开头")
    assert (await ps.list_versions(db, p["id"]))["items"][0]["reason"] == "ai_suggestion"
    # 之后用户又自动保存了一次（token 变了，但第二段没动）→ 剩下的一处仍能接受
    d = await ps.draft_view(db, p["id"])
    await ps.save_draft(
        db,
        p["id"],
        DraftSave(draft=StudioDraft(body=d["draft"]["body"] + "\n\n新加一段"), draft_token=d["draft_token"]),
    )
    r2 = await ss.apply_suggestion(db, sug["id"])
    assert r2["status"] == "applied" and r2["conflicts"] == []
    assert "口语数据" in r2["draft"]["draft"]["body"] and "新加一段" in r2["draft"]["draft"]["body"]
