"""Writes sql/schema.sql: the MySQL CREATE TABLE / CREATE INDEX statements.

    python -m pipeline.make_schema
"""
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from .config import ROOT
from .db import metadata


def build() -> str:
    d = mysql.dialect()
    parts = ["-- Star schema for the retail sales pipeline (MySQL 8 / InnoDB).",
             "-- Generated from pipeline/db.py by `python -m pipeline.make_schema`.",
             "-- The pipeline creates these tables itself; this file is for reading / manual use.\n"]
    for table in metadata.sorted_tables:
        parts.append(str(CreateTable(table).compile(dialect=d)).strip() + ";\n")
        for ix in sorted(table.indexes, key=lambda i: i.name):
            parts.append(str(CreateIndex(ix).compile(dialect=d)).strip() + ";")
        parts.append("")
    return "\n".join(parts)


if __name__ == "__main__":
    out = ROOT / "sql" / "schema.sql"
    out.write_text(build())
    print(f"wrote {out}")
