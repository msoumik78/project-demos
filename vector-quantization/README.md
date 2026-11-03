# Vector quantization demo

Same 50,000 embeddings, three ways of storing them. Int8 keeps the float32 neighbors and uses a quarter of the bytes. Binary is the control: much smaller, and recall drops.

This was run twice on this machine. Both runs printed `PASS` and exited 0. The second run reused `data/embeddings.npy`.

Accuracy means recall@10 against an exact float32 cosine search. A hit is a neighbor that appears in both top-10 lists. The query vector stays float32. Only the stored document vectors are quantized. Each query is a document row, and that row is left out of its own result list.

| Store | What is kept | Pass bar |
| --- | --- | --- |
| float32 | full matrix | baseline |
| int8 | one int8 code per dimension, plus one float32 scale per vector | recall@10 ≥ 0.99 and bytes ≤ 30% of float32 |
| binary | one sign bit per dimension, packed | no bar; expected to miss neighbors |

## What you need

- Python 3.10 or newer. On this Mac, `python3` is 3.9, so use `python3.10`.
- `pip`
- Network the first time, to download AG News (`fancyzhx/ag_news`) and `sentence-transformers/all-MiniLM-L6-v2`

`data/` and `.venv/` are gitignored. A fresh checkout does not include the embeddings or the virtualenv.

## 1. Create the environment

From `vector-quantization`:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Run the comparison

```bash
python quantize_demo.py
```

That command is the whole test. It uses 50,000 documents, 500 queries, top-10, and seed 42.

The first run embeds the articles (about four minutes on this Mac) and writes:

- `data/embeddings.npy`
- `data/meta.json`

A later run prints `Using cached embeddings at data/embeddings.npy` and finishes in a few seconds. Delete `data/` to force a fresh embed.

## 3. Check the result

Success is exit code 0 and a final line that says `PASS`.

```bash
python quantize_demo.py
echo "exit code: $?"
```

The measured output, both times:

```text
docs=50000 dim=384 queries=500 k=10
store            MB  vs fp32  recall@10  mean |dcos|
float32        73.2   100.0%      1.000       0.0000
int8           18.5    25.3%      0.997       0.0002
binary          2.3     3.1%      0.754       0.1324
pass bar: int8 recall@10 >= 0.99 and int8 bytes <= 30% of float32 -> PASS
```

| Store | Size | vs float32 | recall@10 | mean absolute cosine gap |
| --- | --- | --- | --- | --- |
| float32 | 73.2 MB | 100% | 1.000 | 0.0000 |
| int8 | 18.5 MB | 25.3% | 0.997 | 0.0002 |
| binary | 2.3 MB | 3.1% | 0.754 | 0.1324 |

`mean |dcos|` is the average absolute difference between the float32 cosine and the quantized cosine, scored on the float32 top-10. Int8 moves those scores by about 0.0002. Binary moves them by about 0.13 and keeps only 75.4% of the same neighbors.

If int8 misses the bar, the process exits 1 and the last line says `FAIL`.

## Same test with the knobs written out

```bash
python quantize_demo.py --docs 50000 --queries 500 --k 10 --seed 42
```

Changing `--docs` builds a new cache entry only when the count differs from `data/meta.json`. Changing `--queries` or `--seed` resamples queries from the cached matrix and does not re-embed.
