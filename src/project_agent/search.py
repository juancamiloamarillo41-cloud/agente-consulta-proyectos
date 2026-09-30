"""Búsqueda léxica BM25 sobre los fragmentos de los informes.

Por qué BM25 y no embeddings: el corpus es pequeño (decenas de fragmentos), las
preguntas de consultores usan los mismos términos que los informes (OEE, SMED,
quiebre de stock, abandono) y BM25 no requiere otro proveedor ni costo por
consulta. Además es determinista y explicable: se puede mostrar por qué un
fragmento salió primero. El agente compensa la falta de sinónimos reformulando la
consulta (puede llamar la herramienta varias veces con otros términos).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from project_agent.ingestion.models import Chunk

STOPWORDS = frozenset(
    """
    a al algo algun alguna algunas alguno algunos ante antes aun bajo cada como con contra cual cuales
    cuando de del desde donde dos durante e el ella ellas ello ellos en entre era eran es esa esas ese
    eso esos esta estaba estado estan estas este esto estos fue fueron ha han hasta hay la las le les lo
    los mas me mi mismo muy nada ni no nos o otra otras otro otros para pero poco por porque que quien
    se sea ser si sido sin sobre son su sus tambien tan tanto te tiene tienen todo todos tu un una unas
    uno unos y ya cuanto cuantos cuanta cuantas hicimos hizo tuvo tuvieron
    """.split()
)

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")


def normalize(text: str) -> str:
    """Minúsculas y sin tildes: 'Línea' y 'linea' deben coincidir."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _stem(token: str) -> str:
    """Stemming mínimo de plurales ('lecciones' -> 'leccion', 'proyectos' -> 'proyecto')."""
    if len(token) > 4 and token.endswith("es") and token[-3] in "nrlsdz":
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token[-2].isdigit():
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(normalize(text))
    return [_stem(t) for t in tokens if t not in STOPWORDS]


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self._term_freqs = [Counter(tokenize(c.text)) for c in chunks]
        self._lengths = [sum(tf.values()) for tf in self._term_freqs]
        self._avg_length = sum(self._lengths) / len(chunks) if chunks else 0.0
        doc_freq: Counter[str] = Counter()
        for tf in self._term_freqs:
            doc_freq.update(tf.keys())
        n = len(chunks)
        self._idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in doc_freq.items()}

    def _score(self, query_terms: list[str], i: int) -> float:
        tf, length = self._term_freqs[i], self._lengths[i]
        score = 0.0
        for term in query_terms:
            freq = tf.get(term, 0)
            if freq:
                norm = self.k1 * (1 - self.b + self.b * length / self._avg_length)
                score += self._idf[term] * freq * (self.k1 + 1) / (freq + norm)
        return score

    def search(self, query: str, top_k: int = 5, project_code: str | None = None) -> list[SearchResult]:
        query_terms = tokenize(query)
        results = []
        for i, chunk in enumerate(self.chunks):
            if project_code and chunk.project_code != project_code:
                continue
            score = self._score(query_terms, i)
            if score > 0:
                results.append(SearchResult(chunk, score))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
