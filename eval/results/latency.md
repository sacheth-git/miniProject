# Latency (CPU, warm)

Resume parse + skill extraction (embedding cache warm for these resumes; a first-time resume adds about one encoding per section): median 50 ms (p95 50 ms) over 10 resumes.
Encoding one unseen resume text (bge-small, 512 tokens): median 57 ms.

| Jobs indexed | Query p50 (ms) | Query p95 (ms) | FAISS search (ms) | Re-score top 300 (ms) |
|---:|---:|---:|---:|---:|
| 1,000 | 165 | 178 | 0.2 | 164 |
| 10,000 | 165 | 169 | 0.9 | 163 |
| 50,000 | 169 | 175 | 4.0 | 164 |

Query = profile from cached embeddings + exact inner-product search (IndexFlatIP) + full re-scoring; 20 runs each.
The live API adds the database load of the 300 candidates (about 20 ms; see backend/scripts/bench_match.py).
