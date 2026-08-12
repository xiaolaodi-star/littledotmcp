"""M2-06 / M2-07 工具层测试：sql_er_from_ddl / sql_validate_script 返回统一信封。"""

from __future__ import annotations

from littledotmcp.domains.sql_er.tools import sql_er_from_ddl
from littledotmcp.domains.sql_validate.tools import sql_validate_script

DDL = """
CREATE TABLE t (
  id BIGINT PRIMARY KEY,
  name STRING
);
"""


def test_sql_er_envelope():
    res = sql_er_from_ddl(DDL, dialect="hive")
    assert res["success"] is True
    assert "mermaid" in res["data"]
    assert res["data"]["tables"] == ["t"]


def test_sql_validate_envelope():
    res = sql_validate_script(DDL, dialect="hive")
    assert res["success"] is True
    assert res["data"]["passed"] is True


def test_sql_er_bad_ddl_returns_fail():
    res = sql_er_from_ddl("not a ddl at all ???")
    assert res["success"] is False
    assert res["message"]
