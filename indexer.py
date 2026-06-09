from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_DIR / "configs" / "rag_sources.yml"
DEFAULT_TMP_DIR = Path(tempfile.gettempdir()) / "deploy_agent_rag_tmp" / "sources"


def resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value)

    if path.is_absolute():
        return path

    return PROJECT_DIR / path


def run_command(command: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {command}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    return result.stdout.strip()


def handle_remove_readonly(func, path, exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=handle_remove_readonly)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha1_text(payload: str) -> str:
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def clean_repo_url(repo_url: str) -> str:
    return repo_url.removesuffix(".git")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def should_index_file(relative_path: str, include: list[str], exclude: list[str]) -> bool:
    if include and not matches_any(relative_path, include):
        return False

    if exclude and matches_any(relative_path, exclude):
        return False

    return True


def clone_repository(repo: dict[str, Any], destination: Path) -> str:
    safe_rmtree(destination)

    repo_url = repo["url"]
    branch = repo.get("branch")

    command = ["git", "clone", "--depth", "1"]

    if branch:
        command.extend(["--branch", branch])

    command.extend([repo_url, str(destination)])

    print(f"Cloning {repo['name']}...")
    run_command(command)

    commit = run_command(["git", "rev-parse", "HEAD"], cwd=destination)
    print(f"Cloned {repo['name']} at commit {commit}")

    return commit


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if not text:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            paragraph_boundary = text.rfind("\n\n", start, end)
            line_boundary = text.rfind("\n", start, end)

            if paragraph_boundary > start + int(chunk_size * 0.5):
                end = paragraph_boundary
            elif line_boundary > start + int(chunk_size * 0.5):
                end = line_boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = max(0, end - chunk_overlap)

    return chunks


def read_source_files(
    config: dict[str, Any],
    tmp_sources_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global_exclude = config.get("exclude", [])
    all_documents: list[dict[str, Any]] = []
    source_state: dict[str, Any] = {}

    for repo in config["repositories"]:
        repo_name = repo["name"]
        repo_dir = tmp_sources_dir / repo_name
        commit = clone_repository(repo, repo_dir)

        include = repo.get("include", [])
        repo_exclude = global_exclude + repo.get("exclude", [])

        repo_state: dict[str, Any] = {
            "url": repo["url"],
            "branch": repo.get("branch"),
            "commit": commit,
            "files": {},
        }

        for file_path in repo_dir.rglob("*"):
            if not file_path.is_file():
                continue

            relative_path = file_path.relative_to(repo_dir).as_posix()

            if not should_index_file(relative_path, include, repo_exclude):
                continue

            payload = file_path.read_bytes()
            content_hash = sha256_bytes(payload)

            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                text = payload.decode("utf-8", errors="ignore")

            if not text.strip():
                continue

            repo_state["files"][relative_path] = content_hash

            source_url = f"{clean_repo_url(repo['url'])}/blob/{commit}/{relative_path}"

            all_documents.append(
                {
                    "repo": repo_name,
                    "repo_url": repo["url"],
                    "branch": repo.get("branch"),
                    "commit": commit,
                    "path": relative_path,
                    "source_url": source_url,
                    "content_hash": content_hash,
                    "text": text,
                }
            )

        source_state[repo_name] = repo_state

    return all_documents, source_state


def build_chunks(
    documents: list[dict[str, Any]],
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    for document in documents:
        text_chunks = split_text(document["text"], chunk_size, chunk_overlap)

        for index, chunk_text in enumerate(text_chunks):
            chunk_id_raw = (
                f"{document['repo']}:{document['commit']}:"
                f"{document['path']}:{document['content_hash']}:{index}"
            )
            chunk_id = sha1_text(chunk_id_raw)

            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "metadata": {
                        "repo": document["repo"],
                        "branch": document["branch"],
                        "commit": document["commit"],
                        "path": document["path"],
                        "source_url": document["source_url"],
                        "content_hash": document["content_hash"],
                        "chunk_index": index,
                    },
                }
            )

    return chunks


def required_index_files(output_dir: Path, provider: str) -> list[Path]:
    base_files = [
        output_dir / "manifest.json",
        output_dir / "chunks.jsonl",
    ]

    if provider == "tfidf":
        return base_files + [
            output_dir / "vectors.joblib",
            output_dir / "vectorizer.joblib",
        ]

    if provider == "sentence_transformers":
        return base_files + [
            output_dir / "embeddings.npy",
        ]

    raise ValueError(f"Unsupported embedding provider: {provider}")


def should_rebuild(
    output_dir: Path,
    source_state: dict[str, Any],
    provider: str,
    force: bool,
) -> bool:
    if force:
        return True

    for required_file in required_index_files(output_dir, provider):
        if not required_file.exists():
            return True

    previous_manifest = load_json(output_dir / "manifest.json")
    previous_state = previous_manifest.get("source_state", {})
    previous_provider = previous_manifest.get("embedding_provider")

    if previous_provider != provider:
        return True

    return previous_state != source_state


def remove_stale_vector_files(output_dir: Path) -> None:
    for filename in [
        "embeddings.npy",
        "vectors.joblib",
        "vectorizer.joblib",
    ]:
        path = output_dir / filename

        if path.exists():
            path.unlink()


def build_tfidf_index(
    texts: list[str],
    output_dir: Path,
    embedding_config: dict[str, Any],
) -> list[int]:
    tfidf_config = embedding_config.get("tfidf", {})
    max_features = int(tfidf_config.get("max_features", 50000))
    ngram_range_config = tfidf_config.get("ngram_range", [1, 2])
    ngram_range = (int(ngram_range_config[0]), int(ngram_range_config[1]))

    print("Building local TF-IDF vectors...")
    print(f"max_features={max_features}")
    print(f"ngram_range={ngram_range}")

    vectorizer = TfidfVectorizer(
        max_features=max_features,
        ngram_range=ngram_range,
        lowercase=True,
        strip_accents="unicode",
    )

    vectors = vectorizer.fit_transform(texts)

    joblib.dump(vectorizer, output_dir / "vectorizer.joblib")
    joblib.dump(vectors, output_dir / "vectors.joblib")

    return [int(vectors.shape[0]), int(vectors.shape[1])]


def build_sentence_transformers_index(
    texts: list[str],
    output_dir: Path,
    embedding_config: dict[str, Any],
) -> list[int]:
    from sentence_transformers import SentenceTransformer

    model_name = embedding_config.get(
        "model_name",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    batch_size = int(embedding_config.get("batch_size", 32))

    print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    print(f"Generating embeddings for {len(texts)} chunks...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    embeddings = np.asarray(embeddings, dtype=np.float32)
    np.save(output_dir / "embeddings.npy", embeddings)

    return list(embeddings.shape)


def build_index(config_path: Path, force: bool = False) -> None:
    config_path = config_path.resolve()
    config = load_yaml(config_path)

    embedding_config = config.get("embedding", {})
    provider = embedding_config.get("provider", "sentence_transformers")

    output_config = config.get("output", {})
    output_dir = resolve_project_path(output_config.get("index_dir", "data/rag_index"))

    tmp_sources_dir = DEFAULT_TMP_DIR

    safe_rmtree(tmp_sources_dir)
    tmp_sources_dir.mkdir(parents=True, exist_ok=True)

    documents, source_state = read_source_files(config, tmp_sources_dir)

    if not documents:
        raise RuntimeError("No documents were found. Check repositories, branches and include patterns.")

    if not should_rebuild(output_dir, source_state, provider, force):
        print("No source changes detected. Keeping current RAG index.")
        return

    chunking_config = config.get("chunking", {})
    chunk_size = int(chunking_config.get("chunk_size", 1200))
    chunk_overlap = int(chunking_config.get("chunk_overlap", 200))

    chunks = build_chunks(documents, chunk_size, chunk_overlap)

    if not chunks:
        raise RuntimeError("No chunks were generated. Check document contents and chunking configuration.")

    texts = [chunk["text"] for chunk in chunks]

    output_dir.mkdir(parents=True, exist_ok=True)

    remove_stale_vector_files(output_dir)

    if provider == "tfidf":
        vector_shape = build_tfidf_index(texts, output_dir, embedding_config)
    elif provider == "sentence_transformers":
        vector_shape = build_sentence_transformers_index(texts, output_dir, embedding_config)
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")

    write_jsonl(output_dir / "chunks.jsonl", chunks)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "embedding_provider": provider,
        "embedding_model": embedding_config.get("model_name"),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "vector_shape": vector_shape,
        "source_state": source_state,
    }

    write_json(output_dir / "manifest.json", manifest)

    print("RAG index generated successfully.")
    print(f"Provider: {provider}")
    print(f"Documents: {len(documents)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Vector shape: {vector_shape}")
    print(f"Output directory: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deploy agent RAG index.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to RAG sources YAML config.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild even if source commits and file hashes did not change.",
    )

    args = parser.parse_args()
    build_index(config_path=Path(args.config), force=args.force)


if __name__ == "__main__":
    main()