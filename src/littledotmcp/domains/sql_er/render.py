"""ER 图渲染（M2-03）。

将 Schema 渲染为 Mermaid erDiagram 文本。约定：
- 表名作为 ENTITY；列以 `类型 PK|FK|...` 标注；
- PK 在列后标 PK，FK 用 relationship 行描述 `||--o{`；
- 列注释作为 Mermaid 行尾 `//` 注释（Mermaid erDiagram 支持行尾备注）。
"""

from __future__ import annotations

import re

from .model import Schema, Table

_INVALID = re.compile(r"\W")


def _sanitize(ident: str) -> str:
    """Mermaid 标识符仅允许字母数字下划线，其余归一为下划线。"""
    return _INVALID.sub("_", ident)


def _render_table(t: Table) -> list[str]:
    lines: list[str] = []
    entity = _sanitize(t.name)
    label = f" [{t.comment}]" if t.comment else ""
    lines.append(f"    {entity}{label} {{")
    pk_set = {c.lower() for c in t.primary_keys}
    for col in t.columns:
        flags: list[str] = []
        if col.name.lower() in pk_set:
            flags.append("PK")
        if any(fk.column.lower() == col.name.lower() for fk in t.foreign_keys):
            flags.append("FK")
        if not col.nullable:
            flags.append("not null")
        flag_str = " ".join(flags)
        col_label = f" // {col.comment}" if col.comment else ""
        lines.append(f"        {col.dtype} {col.name} {flag_str}{col_label}")
    lines.append("    }")
    return lines


def render_er(schema: Schema) -> str:
    """渲染 Schema 为完整 Mermaid erDiagram。"""
    out: list[str] = ["erDiagram"]
    rels: list[str] = []
    for t in schema.tables:
        out.extend(_render_table(t))
        for fk in t.foreign_keys:
            child = _sanitize(t.name)
            parent = _sanitize(fk.ref_table)
            ccol = _sanitize(fk.column)
            pcol = _sanitize(fk.ref_column)
            rels.append(f'    {parent} ||--o{{ {child} : "{ccol} -> {pcol}"')
    out.extend(rels)
    return "\n".join(out)
