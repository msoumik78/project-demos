#!/usr/bin/env python3
"""Compare float32, int8, and binary storage for the same embeddings."""

import argparse
import json
from pathlib import Path

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
RECALL_BAR = 0.99
SIZE_BAR = 0.30


def l2_normalize(matrix):
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def quantize_int8(embeddings):
    """Per-vector symmetric int8. One float32 scale is stored beside each vector."""
    scale = np.max(np.abs(embeddings), axis=1).astype(np.float32)
    scale = np.maximum(scale, 1e-12)
    codes = np.clip(np.round(embeddings / scale[:, None] * 127), -127, 127).astype(np.int8)
    restored = codes.astype(np.float32) * scale[:, None] / 127.0
    return codes, scale, restored


def quantize_binary(embeddings):
    signs = embeddings >= 0
    packed = np.packbits(signs, axis=1)
    restored = np.where(signs, 1.0, -1.0).astype(np.float32)
    return packed, restored


def topk_cosine(database, queries, k, exclude):
    scores = l2_normalize(queries) @ l2_normalize(database).T
    if exclude is not None:
        scores[np.arange(len(exclude)), exclude] = -np.inf
    candidates = np.argpartition(-scores, kth=k - 1, axis=1)[:, :k]
    rows = np.arange(len(queries))[:, None]
    candidate_scores = scores[rows, candidates]
    order = np.argsort(-candidate_scores, axis=1)
    return candidates[rows, order], candidate_scores[rows, order]


def recall_at_k(truth, predicted):
    hits = 0
    for row_truth, row_pred in zip(truth, predicted):
        hits += len(set(row_truth.tolist()) & set(row_pred.tolist()))
    return hits / truth.size


def mean_abs_score_delta(reference_ids, reference_scores, database, queries):
    rows = np.arange(len(queries))[:, None]
    quantized_scores = l2_normalize(queries) @ l2_normalize(database).T
    return float(np.mean(np.abs(reference_scores - quantized_scores[rows, reference_ids])))


def load_texts(count):
    from datasets import load_dataset

    dataset = load_dataset("fancyzhx/ag_news", split="train")
    if count > len(dataset):
        raise SystemExit(f"ag_news train has {len(dataset)} rows, asked for {count}")
    return list(dataset["text"][:count])


def load_or_embed(data_dir, count):
    data_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = data_dir / "embeddings.npy"
    meta_path = data_dir / "meta.json"
    if matrix_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("model") == MODEL_NAME and meta.get("count") == count:
            print(f"Using cached embeddings at {matrix_path}")
            return np.load(matrix_path)

    print(f"Embedding {count} AG News texts with {MODEL_NAME}")
    from sentence_transformers import SentenceTransformer

    texts = load_texts(count)
    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(
        texts,
        batch_size=128,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype(np.float32)
    np.save(matrix_path, embeddings)
    meta_path.write_text(json.dumps({"model": MODEL_NAME, "count": count, "dim": int(embeddings.shape[1])}))
    return embeddings


def megabytes(num_bytes):
    return num_bytes / (1024 * 1024)


def main():
    parser = argparse.ArgumentParser(description="Show int8 vector storage with recall kept against float32.")
    parser.add_argument("--docs", type=int, default=50000)
    parser.add_argument("--queries", type=int, default=500)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    embeddings = load_or_embed(args.data_dir, args.docs)
    rng = np.random.default_rng(args.seed)
    query_ids = rng.choice(len(embeddings), size=args.queries, replace=False)
    queries = embeddings[query_ids]

    int8_codes, int8_scales, int8_vectors = quantize_int8(embeddings)
    binary_packed, binary_vectors = quantize_binary(embeddings)

    truth_ids, truth_scores = topk_cosine(embeddings, queries, args.k, query_ids)
    int8_ids, _ = topk_cosine(int8_vectors, queries, args.k, query_ids)
    binary_ids, _ = topk_cosine(binary_vectors, queries, args.k, query_ids)

    rows = [
        ("float32", embeddings.nbytes, 1.0, 0.0),
        (
            "int8",
            int8_codes.nbytes + int8_scales.nbytes,
            recall_at_k(truth_ids, int8_ids),
            mean_abs_score_delta(truth_ids, truth_scores, int8_vectors, queries),
        ),
        (
            "binary",
            binary_packed.nbytes,
            recall_at_k(truth_ids, binary_ids),
            mean_abs_score_delta(truth_ids, truth_scores, binary_vectors, queries),
        ),
    ]

    baseline = rows[0][1]
    print(f"docs={args.docs} dim={embeddings.shape[1]} queries={args.queries} k={args.k}")
    print(f"{'store':<10} {'MB':>8} {'vs fp32':>8} {'recall@10':>10} {'mean |dcos|':>12}")
    for name, size, recall, delta in rows:
        print(f"{name:<10} {megabytes(size):8.1f} {size / baseline:8.1%} {recall:10.3f} {delta:12.4f}")

    int8_size = rows[1][1]
    int8_recall = rows[1][2]
    passed = int8_recall >= RECALL_BAR and int8_size <= SIZE_BAR * baseline
    print(
        f"pass bar: int8 recall@10 >= {RECALL_BAR:.2f} and int8 bytes <= {SIZE_BAR:.0%} of float32 "
        f"-> {'PASS' if passed else 'FAIL'}"
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
