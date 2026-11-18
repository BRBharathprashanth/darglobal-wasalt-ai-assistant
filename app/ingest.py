
import json
import sqlite3
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import DATA_DIR, SQLITE_PATH


def load_documents(path: Path) -> list[dict[str, Any]]:
    documents = []

    if not path.exists():
        return documents

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSONL line: {line_number}")
                continue

            text = str(item.get("text", "")).strip()

            if text:
                documents.append({
                    "source": item.get("source", "Unknown"),
                    "title": item.get("title", "Untitled"),
                    "url": item.get("url", ""),
                    "text": text
                })

    return documents


def main():
    data_dir = Path(DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = data_dir / "captured_content.jsonl"
    documents = load_documents(dataset_path)

    if not documents:
        raise SystemExit(
            "Dataset not found. Add captured_content.jsonl to the data folder."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=850,
        chunk_overlap=120
    )

    chunks = []

    for doc_index, document in enumerate(documents):
        text_chunks = splitter.split_text(document["text"])

        for chunk_index, chunk in enumerate(text_chunks):
            if chunk.strip():
                chunks.append((
                    f"doc-{doc_index}-chunk-{chunk_index}",
                    document["source"],
                    document["title"],
                    document["url"],
                    chunk.strip()
                ))

    db_path = Path(SQLITE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                content TEXT NOT NULL
            )
        """)

        conn.execute("DELETE FROM chunks")

        conn.executemany("""
            INSERT INTO chunks
            (id, source, title, url, content)
            VALUES (?, ?, ?, ?, ?)
        """, chunks)

        conn.commit()

    print(f"Documents loaded: {len(documents)}")
    print(f"Text chunks indexed: {len(chunks)}")
    print(f"Database location: {db_path.resolve()}")


if __name__ == "__main__":
    main()
