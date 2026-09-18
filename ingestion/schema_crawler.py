"""Introspects the Turso DB and writes table/column metadata (joined with sensitivity
tags) to ingestion/schema_metadata.json. Layer 2's index build reads this file.

Usage:
    python -m ingestion.schema_crawler
"""
import json
from pathlib import Path

from config.settings import load_sensitivity_tags
from ingestion.db import get_client

OUTPUT_PATH = Path(__file__).resolve().parent / "schema_metadata.json"


def crawl() -> dict:
    client = get_client()
    tags = load_sensitivity_tags()
    try:
        tables_result = client.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        metadata = {"tables": []}
        for row in tables_result.rows:
            table_name = row[0]
            columns_result = client.execute(f"PRAGMA table_info({table_name})")
            columns = []
            for col_row in columns_result.rows:
                # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
                col_name = col_row[1]
                col_type = col_row[2]
                is_pk = bool(col_row[5])
                sensitivity = tags.get(table_name, {}).get(col_name, "public")
                columns.append(
                    {
                        "name": col_name,
                        "type": col_type,
                        "primary_key": is_pk,
                        "sensitivity": sensitivity,
                    }
                )
            metadata["tables"].append({"name": table_name, "columns": columns})
        return metadata
    finally:
        client.close()


def main() -> None:
    metadata = crawl()
    OUTPUT_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Wrote schema metadata for {len(metadata['tables'])} tables to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
