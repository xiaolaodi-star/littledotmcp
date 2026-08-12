"""M2-02 / M2-03 golden 测试：三方言 DDL 解析与 ER 渲染。"""

from __future__ import annotations

import pytest

from littledotmcp.domains.sql_er.parser import ParseError, parse_ddl
from littledotmcp.domains.sql_er.render import render_er

HIVE_DDL = """
CREATE TABLE ods_user (
  id BIGINT COMMENT '主键',
  name STRING,
  age INT
) COMMENT '用户表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;
"""

ORACLE_DDL = """
CREATE TABLE emp (
  id NUMBER(10) PRIMARY KEY,
  dept_id NUMBER(10),
  name VARCHAR2(50) NOT NULL,
  CONSTRAINT fk_dept FOREIGN KEY (dept_id) REFERENCES dept(id)
);
CREATE TABLE dept (
  id NUMBER(10) PRIMARY KEY,
  dname VARCHAR2(50)
);
"""

DORIS_DDL = """
CREATE TABLE user_log (
  user_id BIGINT,
  event VARCHAR(64),
  ts DATETIME
) ENGINE=OLAP
UNIQUE KEY(user_id)
DISTRIBUTED BY HASH(user_id) BUCKETS 10
PROPERTIES ("replication_num" = "3");
"""


def test_hive_parse():
    s = parse_ddl(HIVE_DDL, dialect="hive")
    assert s.dialect == "hive"
    assert s.table_names() == ["ods_user"]
    t = s.tables[0]
    assert t.comment == "用户表"
    assert t.partitioned_by == ["dt"]
    assert {c.name for c in t.columns if c.is_partition} == {"dt"}


def test_oracle_parse_and_fk():
    s = parse_ddl(ORACLE_DDL, dialect="oracle")
    assert s.dialect == "oracle"
    assert set(s.table_names()) == {"emp", "dept"}
    emp = s.find_table("emp")
    assert "id" in emp.primary_keys
    assert emp.foreign_keys[0].ref_table == "dept"
    assert emp.foreign_keys[0].ref_column == "id"


def test_doris_parse_and_model():
    s = parse_ddl(DORIS_DDL, dialect="doris")
    assert s.dialect == "doris"
    assert s.tables[0].extra.get("doris_model") == "Unique Key"


def test_render_contains_entities_and_relationship():
    s = parse_ddl(ORACLE_DDL, dialect="oracle")
    m = render_er(s)
    assert m.startswith("erDiagram")
    assert "emp" in m and "dept" in m
    assert "||--o{" in m  # FK 关系行


def test_auto_detect_hive():
    s = parse_ddl(HIVE_DDL)
    assert s.dialect == "hive"


def test_empty_ddl_raises():
    with pytest.raises(ParseError):
        parse_ddl("")


def test_unknown_dialect_raises_readable():
    with pytest.raises(ParseError) as exc:
        parse_ddl("CREATE TABLE t (a INT);")
    assert "方言" in str(exc.value)
