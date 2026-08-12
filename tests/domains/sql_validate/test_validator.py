"""M2-04 golden 测试：L1 静态校验规则。"""

from __future__ import annotations

from littledotmcp.domains.sql_er.parser import parse_ddl
from littledotmcp.domains.sql_validate.validator import validate

DUP_COLUMN = """
CREATE TABLE t (
  id INT,
  id STRING
);
"""

FK_MISSING = """
CREATE TABLE child (
  pid INT,
  CONSTRAINT fk FOREIGN KEY (pid) REFERENCES ghost(id)
);
"""

RESERVED_COLUMN = """
CREATE TABLE t (
  id INT,
  "select" STRING
);
"""

OK_DDL = """
CREATE TABLE user_profile (
  id BIGINT PRIMARY KEY,
  nickname STRING
);
CREATE TABLE order_log (
  id BIGINT PRIMARY KEY,
  uid BIGINT,
  CONSTRAINT fk_uid FOREIGN KEY (uid) REFERENCES user_profile(id)
);
"""


def test_dup_column_error():
    s = parse_ddl(DUP_COLUMN, dialect="mysql")
    r = validate(s)
    assert any(i.code == "DUP_COLUMN" for i in r.errors)
    assert not r.passed


def test_fk_missing_table_error():
    s = parse_ddl(FK_MISSING, dialect="mysql")
    r = validate(s)
    assert any(i.code == "FK_TABLE_MISSING" for i in r.errors)


def test_reserved_column_warning():
    s = parse_ddl(RESERVED_COLUMN, dialect="mysql")
    r = validate(s)
    assert any(i.code == "RESERVED_COLUMN" for i in r.warnings)


def test_ok_ddl_passes():
    s = parse_ddl(OK_DDL, dialect="mysql")
    r = validate(s)
    assert r.passed
    assert not r.errors
