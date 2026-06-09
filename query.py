from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_DIR = PROJECT_DIR / "data" / "rag_index"


def load_chunks(path: Path) -> list[dict]:
    chunks = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            chunks.append(json.loads(line))

    return chunks


def score_with_tfidf(index_dir: Path, query: str) -> np.ndarray:
    vectorizer = joblib.load(index_dir / "vectorizer.joblib")
    vectors = joblib.load(index_dir / "vectors.joblib")

    query_vector = vectorizer.transform([query])
    scores = vectors @ query_vector.T

    return np.asarray(scores.toarray()).reshape(-1)


def score_with_sentence_transformers(index_dir: Path, query: str, model_name: str) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    embeddings = np.load(index_dir / "embeddings.npy")
    model = SentenceTransformer(model_name)

    query_embedding = model.encode(
        [query],
        normalize_embeddings=True,
    )[0].astype(np.float32)

    scores = embeddings @ query_embedding

    return scores


def main() -> None:
    parser = argparse.ArgumentParser(description="Query local deploy agent RAG index.")
    parser.add_argument("query", help="Question to search in the RAG index.")
    parser.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    parser.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()

    index_dir = Path(args.index_dir)
    manifest_path = index_dir / "manifest.json"
    chunks_path = index_dir / "chunks.jsonl"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    if not chunks_path.exists():
        raise FileNotFoundError(f"Chunks not found: {chunks_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = load_chunks(chunks_path)

    provider = manifest.get("embedding_provider", "sentence_transformers")

    if provider == "tfidf":
        scores = score_with_tfidf(index_dir, args.query)
    elif provider == "sentence_transformers":
        model_name = manifest["embedding_model"]
        scores = score_with_sentence_transformers(index_dir, args.query, model_name)
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")

    top_indices = np.argsort(scores)[::-1][: args.top_k]

    for rank, idx in enumerate(top_indices, start=1):
        chunk = chunks[int(idx)]
        metadata = chunk["metadata"]

        print("=" * 100)
        print(f"Rank: {rank}")
        print(f"Score: {scores[int(idx)]:.4f}")
        print(f"Repo: {metadata['repo']}")
        print(f"Path: {metadata['path']}")
        print(f"Commit: {metadata['commit']}")
        print(f"Source: {metadata['source_url']}")
        print("-" * 100)
        print(chunk["text"][:1200])


if __name__ == "__main__":
    main()