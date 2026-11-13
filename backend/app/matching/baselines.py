"""Baselines for comparison and the ablation study.

Each baseline maps (resume, jobs) -> one score per job; higher is better.
  keyword_jaccard  - Jaccard overlap of extracted skill ids
  tfidf            - TF-IDF cosine (fit on the job pool + resume)
  bm25             - Okapi BM25 with the resume as query
  sbert_whole      - raw cosine of whole-resume vs whole-JD embeddings
  sbert_section    - section-level semantic score only (our Sem term)
  ours             - full skill-weighted model
  ours_finetuned   - ours with the fine-tuned encoder (selected at eval time)
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

METHODS = ("keyword_jaccard", "tfidf", "bm25", "sbert_whole", "sbert_section", "ours")
_TOKEN = re.compile(r"[a-z0-9+#.]+")


def tokenize(text: str) -> list[str]:
    return [t.strip(".") for t in _TOKEN.findall(text.lower()) if len(t.strip(".")) > 1]


def keyword_jaccard(resume_skills: set[str], job_skills: Sequence[set[str]]) -> np.ndarray:
    out = np.zeros(len(job_skills), dtype=np.float32)
    for i, js in enumerate(job_skills):
        union = resume_skills | js
        out[i] = len(resume_skills & js) / len(union) if union else 0.0
    return out


def tfidf_scores(resume_text: str, job_texts: Sequence[str]) -> np.ndarray:
    if not job_texts:
        return np.zeros(0, dtype=np.float32)
    vec = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False, sublinear_tf=True, min_df=1)
    mat = vec.fit_transform([*job_texts, resume_text])
    return cosine_similarity(mat[-1], mat[:-1]).ravel().astype(np.float32)


def bm25_scores(resume_text: str, job_texts: Sequence[str]) -> np.ndarray:
    if not job_texts:
        return np.zeros(0, dtype=np.float32)
    bm = BM25Okapi([tokenize(t) or ["_"] for t in job_texts])
    q = list(dict.fromkeys(tokenize(resume_text)))  # unique query terms
    s = np.asarray(bm.get_scores(q), dtype=np.float32)
    return s / s.max() if s.max() > 0 else s


def sbert_whole(resume_vec: np.ndarray, job_doc_vecs: np.ndarray) -> np.ndarray:
    return (job_doc_vecs @ resume_vec).astype(np.float32)
