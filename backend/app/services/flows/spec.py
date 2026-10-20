"""流程模板（YAML）：节点、角色、执行者、模型组、并行、循环上限、关卡开关、预算。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TEMPLATE_DIR = Path(__file__).parent / "templates"
ROLES = {"researcher", "aggregator", "planner"}
EXECUTORS = {"internal", "deepseek_harness", "claude_code", "codex"}


class FlowSpecError(ValueError):
    pass


@dataclass
class NodeSpec:
    id: str
    label: str
    type: str = "role"  # role / gate
    role: str | None = None
    executor: str = "internal"
    after: list[str] = field(default_factory=list)
    parallel: str | None = None  # 按哪个输入列表并行
    routing_group: str = "default"
    params: dict[str, Any] = field(default_factory=dict)
    gate: dict[str, Any] = field(default_factory=dict)
    max_loops: int = 0


@dataclass
class FlowSpec:
    key: str
    name: str
    version: int
    description: str
    inputs: dict[str, dict[str, Any]]
    budget: dict[str, Any]
    nodes: list[NodeSpec]

    def node(self, node_id: str) -> NodeSpec:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise FlowSpecError(f"没有节点 {node_id}")

    def ancestors(self, node_id: str) -> set[str]:
        out: set[str] = set()
        stack = list(self.node(node_id).after)
        while stack:
            nid = stack.pop()
            if nid not in out:
                out.add(nid)
                stack.extend(self.node(nid).after)
        return out

    def graph_view(self, gates: dict[str, bool] | None = None) -> dict[str, Any]:
        """导出给节点图：节点 + 边（边表示产物流向）。"""
        nodes = []
        edges = []
        for n in self.nodes:
            enabled = n.gate.get("enabled", True) if n.type == "gate" else True
            if gates and n.id in gates:
                enabled = gates[n.id]
            nodes.append(
                {
                    "id": n.id,
                    "label": n.label,
                    "type": n.type,
                    "role": n.role,
                    "executor": n.executor,
                    "parallel": n.parallel,
                    "routing_group": n.routing_group,
                    "enabled": enabled,
                    "can_disable": bool(n.gate.get("can_disable")) if n.type == "gate" else False,
                }
            )
            for a in n.after:
                edges.append({"from": a, "to": n.id})
        return {"key": self.key, "name": self.name, "version": self.version, "nodes": nodes, "edges": edges}


def parse_spec(data: dict[str, Any]) -> FlowSpec:
    if not isinstance(data, dict) or not data.get("key") or not data.get("nodes"):
        raise FlowSpecError("流程模板缺少 key 或 nodes")
    nodes: list[NodeSpec] = []
    seen: set[str] = set()
    for raw in data["nodes"]:
        nid = str(raw.get("id") or "")
        if not nid or nid in seen:
            raise FlowSpecError(f"节点 id 为空或重复：{nid!r}")
        ntype = raw.get("type") or "role"
        role = raw.get("role")
        if ntype == "role" and role not in ROLES:
            raise FlowSpecError(f"节点 {nid} 的角色 {role!r} 未实现")
        executor = raw.get("executor") or "internal"
        if executor not in EXECUTORS:
            raise FlowSpecError(f"节点 {nid} 的执行者 {executor!r} 未知")
        after = [str(a) for a in raw.get("after") or []]
        for a in after:
            if a not in seen:
                raise FlowSpecError(f"节点 {nid} 依赖的 {a} 必须写在它前面")
        nodes.append(
            NodeSpec(
                id=nid,
                label=str(raw.get("label") or nid),
                type=ntype,
                role=role,
                executor=executor,
                after=after,
                parallel=raw.get("parallel"),
                routing_group=str(raw.get("routing_group") or "default"),
                params=dict(raw.get("params") or {}),
                gate=dict(raw.get("gate") or {}),
                max_loops=int(raw.get("max_loops") or 0),
            )
        )
        seen.add(nid)
    return FlowSpec(
        key=str(data["key"]),
        name=str(data.get("name") or data["key"]),
        version=int(data.get("version") or 1),
        description=str(data.get("description") or ""),
        inputs=dict(data.get("inputs") or {}),
        budget=dict(data.get("budget") or {}),
        nodes=nodes,
    )


def load_spec(key: str) -> FlowSpec:
    path = TEMPLATE_DIR / f"{key}.yaml"
    if not path.is_file() or not key.replace("_", "").isalnum():
        raise FlowSpecError(f"没有流程模板 {key}")
    return parse_spec(yaml.safe_load(path.read_text(encoding="utf-8")))


def list_specs() -> list[FlowSpec]:
    return [parse_spec(yaml.safe_load(p.read_text(encoding="utf-8"))) for p in sorted(TEMPLATE_DIR.glob("*.yaml"))]
