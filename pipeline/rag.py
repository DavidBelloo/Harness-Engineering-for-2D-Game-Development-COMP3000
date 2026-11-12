"""RAG over a small knowledge base of game-making patterns (docs/*.md).

Ranking is hybrid: 60% embedding similarity (local nomic-embed-text via Ollama, cosine in numpy)
+ 40% keyword score (BM25 with a light stemmer and a boost for each doc's curated "Keywords:" line).
If the embedding model is unavailable the keyword score alone is used, so retrieval never blocks the pipeline.

Each doc is tagged "Kind: mechanic" (a genre pattern such as shooter/platformer) or "Kind: common"
(lives, restart, juice...). Generic docs match almost every idea, so selection reserves slots for mechanics.

The corpus is ~15 short documents, so a plain numpy store is plenty - and it avoids native
dependencies (chromadb/hnswlib) that need a C++ compiler on Windows.
"""
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

from . import config, llm
from .util import read_text, write_text

STOP = set("a an the and or of to in on for with is are be it its this that as at by from your you can use make "
           "game games player when then if each every into over per out up down run lose lives".split())


@dataclass
class Doc:
    id: str
    title: str
    text: str
    kind: str = "common"      # 'mechanic' (genre pattern) or 'common' (applies to many games)
    keywords: str = ""


def load_docs():
    docs = []
    for p in sorted(config.DOCS_DIR.glob("*.md")):
        text = read_text(p)
        m = re.search(r"^#\s+(.+)$", text, re.M)
        km = re.search(r"^Kind:\s*(\w+)", text, re.M)
        kw = re.search(r"^Keywords:\s*(.+)$", text, re.M)
        docs.append(Doc(p.stem, m.group(1).strip() if m else p.stem, text,
                        km.group(1).lower() if km else "common", kw.group(1) if kw else ""))
    return docs


def _stem(t):
    for suf in ("ing", "ies", "es", "ed", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)] + ("y" if suf == "ies" else "")
    return t


def _tokens(text):
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1]


class Retriever:
    K1, B = 1.5, 0.5
    MECH_FLOOR = 0.45      # a 2nd mechanic doc must reach 45% of the best relevance to be included

    def __init__(self, use_embeddings=True):
        self.docs = load_docs()
        self.method = "keyword"
        self.fallback_reason = ""
        self._vecs = None
        if use_embeddings and self.docs:
            try:
                self._vecs = self._load_or_embed()
                self.method = "hybrid"
            except Exception as e:  # noqa: BLE001
                self._vecs = None
                self.fallback_reason = str(e)[:160]
        # BM25 index (always built; it is the fallback and half of the hybrid score)
        self._tf, self._df = [], Counter()
        for d in self.docs:
            toks = _tokens(d.text) + 2 * _tokens(d.keywords)       # curated keywords count triple
            self._tf.append(Counter(toks))
            self._df.update(set(toks))
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(self._len)) if self._len else 1.0

    # ---- embeddings -----------------------------------------------------
    def _load_or_embed(self):
        cache_path = config.CACHE_DIR / "embeddings.json"
        cache = {}
        if cache_path.exists():
            try:
                cache = json.loads(read_text(cache_path))
            except Exception:  # noqa: BLE001
                cache = {}
        model_cache = cache.setdefault(config.EMBED_MODEL, {})
        todo = []
        for d in self.docs:
            h = hashlib.sha1(d.text.encode("utf-8")).hexdigest()
            if model_cache.get(d.id, {}).get("hash") != h:
                todo.append((d, h))
        if todo:
            vecs = llm.embed(["search_document: " + d.text for d, _ in todo])
            for (d, h), v in zip(todo, vecs):
                model_cache[d.id] = {"hash": h, "vec": v}
            write_text(cache_path, json.dumps(cache))
        m = np.array([model_cache[d.id]["vec"] for d in self.docs], dtype=np.float32)
        return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)

    # ---- search ---------------------------------------------------------
    def _keyword_scores(self, query):
        n = len(self.docs)
        qt = set(_tokens(query))
        out = []
        for i in range(n):
            tf, s = self._tf[i], 0.0
            for t in qt:
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                s += idf * f * (self.K1 + 1) / (f + self.K1 * (1 - self.B + self.B * self._len[i] / self._avg))
            out.append(s)
        return np.array(out, dtype=np.float32)

    @staticmethod
    def _norm(a):
        lo, hi = float(a.min()), float(a.max())
        return (a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)

    def search(self, query, k=3):
        if not self.docs:
            return []
        kw = self._keyword_scores(query)
        scores = kw
        if self._vecs is not None:
            try:
                q = np.array(llm.embed(["search_query: " + query])[0], dtype=np.float32)
                q /= (np.linalg.norm(q) + 1e-9)
                scores = 0.6 * self._norm(self._vecs @ q) + 0.4 * self._norm(kw)
                self.method = "hybrid"
            except Exception:  # noqa: BLE001
                self.method = "keyword"
        order = list(np.argsort(-scores))
        rel = self._norm(scores)                      # 0..1 relevance across the corpus
        # Quota: generic docs (lives, restart...) match every idea, so reserve slots for genre/mechanic patterns -
        # but only for mechanics that are actually relevant (a weak match could mislead a small model).
        mech = [i for i in order if self.docs[i].kind == "mechanic"]
        chosen = [i for n, i in enumerate(mech[:max(1, k - 1)]) if n == 0 or rel[i] >= self.MECH_FLOOR]
        chosen += [i for i in order if i not in chosen and self.docs[i].kind != "mechanic"][:k - len(chosen)]
        chosen += [i for i in order if i not in chosen][:k - len(chosen)]
        chosen.sort(key=lambda i: -scores[i])
        return [(self.docs[i], float(scores[i])) for i in chosen]


def format_patterns(hits, max_chars_each=1800):
    parts = []
    for doc, _ in hits:
        body = doc.text.strip()
        if len(body) > max_chars_each:
            body = body[:max_chars_each] + "\n..."
        parts.append(body)
    return "\n\n---\n\n".join(parts)
