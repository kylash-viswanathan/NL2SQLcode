"""Embeds schema metadata, few-shot exemplars, and glossary terms into ChromaDB.
Run after ingestion/schema_crawler.py has produced schema_metadata.json.

Usage:
    python -m knowledge.build_index
"""
import json
from pathlib import Path

import yaml

from knowledge.chroma_client import get_chroma_client, get_embedding_function

KNOWLEDGE_DIR = Path(__file__).resolve().parent
SCHEMA_METADATA_PATH = KNOWLEDGE_DIR.parent / "ingestion" / "schema_metadata.json"
EXEMPLARS_PATH = KNOWLEDGE_DIR / "exemplars.yaml"
GLOSSARY_PATH = KNOWLEDGE_DIR / "glossary.yaml"


def _column_doc(table: str, col: dict) -> str:
    flag = f" [{col['sensitivity']}]" if col["sensitivity"] != "public" else ""
    return f"{table}.{col['name']} ({col['type']}){flag}"


def build_schema_collection(client, embed_fn) -> None:
    metadata = json.loads(SCHEMA_METADATA_PATH.read_text(encoding="utf-8"))
    collection = client.get_or_create_collection("schema", embedding_function=embed_fn)

    ids, docs, metadatas = [], [], []
    for table in metadata["tables"]:
        table_name = table["name"]
        col_summaries = ", ".join(_column_doc(table_name, c) for c in table["columns"])
        doc = f"Table {table_name}: columns are {col_summaries}"
        ids.append(f"table::{table_name}")
        docs.append(doc)
        metadatas.append({"table": table_name, "kind": "table"})

        for col in table["columns"]:
            doc = f"Column {table_name}.{col['name']} ({col['type']}), sensitivity={col['sensitivity']}"
            ids.append(f"column::{table_name}.{col['name']}")
            docs.append(doc)
            metadatas.append(
                {
                    "table": table_name,
                    "column": col["name"],
                    "sensitivity": col["sensitivity"],
                    "kind": "column",
                }
            )

    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    print(f"Indexed {len(ids)} schema entries.")


def build_exemplars_collection(client, embed_fn) -> None:
    exemplars = yaml.safe_load(EXEMPLARS_PATH.read_text(encoding="utf-8"))
    collection = client.get_or_create_collection("exemplars", embedding_function=embed_fn)

    ids = [f"exemplar::{i}" for i in range(len(exemplars))]
    docs = [ex["question"] for ex in exemplars]
    metadatas = [{"sql": ex["sql"]} for ex in exemplars]

    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    print(f"Indexed {len(ids)} exemplars.")


def build_glossary_collection(client, embed_fn) -> None:
    glossary = yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8"))
    collection = client.get_or_create_collection("glossary", embedding_function=embed_fn)

    ids = [f"glossary::{i}" for i in range(len(glossary))]
    docs = [f"{g['term']}: {g['expansion']}" for g in glossary]
    metadatas = [{"term": g["term"], "maps_to": g["maps_to"]} for g in glossary]

    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    print(f"Indexed {len(ids)} glossary terms.")


def main() -> None:
    if not SCHEMA_METADATA_PATH.exists():
        raise FileNotFoundError(
            f"{SCHEMA_METADATA_PATH} not found — run `python -m ingestion.schema_crawler` first."
        )
    client = get_chroma_client()
    embed_fn = get_embedding_function()
    build_schema_collection(client, embed_fn)
    build_exemplars_collection(client, embed_fn)
    build_glossary_collection(client, embed_fn)


if __name__ == "__main__":
    main()
