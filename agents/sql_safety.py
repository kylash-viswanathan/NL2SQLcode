"""SQL safety helpers shared by the SQL Generation, HITL Gate, and Execution agents."""
import re

import sqlparse

KNOWN_TABLES = {"clients", "portfolios", "holdings", "trades", "assets"}


def strip_sql_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(sql)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def is_select_only(sql: str) -> bool:
    statements = sqlparse.parse(sql)
    if not statements:
        return False
    for stmt in statements:
        stmt_type = stmt.get_type()
        if stmt_type != "SELECT":
            return False
    return True


def extract_tables(sql: str) -> list[str]:
    """Best-effort extraction of referenced table names, matched against KNOWN_TABLES."""
    lowered = sql.lower()
    return sorted(table for table in KNOWN_TABLES if re.search(rf"\b{table}\b", lowered))


def hitl_check(sql: str, tables: list[str], trigger_columns: set[tuple[str, str]]) -> tuple[bool, list[str]]:
    """Returns (should_trigger, matched_columns) — checks referenced tables for any
    column tagged PII/confidential that also appears (by name) in the SQL text, or a
    `SELECT *` that would pull sensitive columns implicitly."""
    lowered = sql.lower()
    is_star_select = bool(re.search(r"select\s+(\w+\.)?\*", lowered))
    matches = []
    for table, column in trigger_columns:
        if table not in tables:
            continue
        if is_star_select or re.search(rf"\b{column.lower()}\b", lowered):
            matches.append(f"{table}.{column}")
    return (len(matches) > 0, matches)
