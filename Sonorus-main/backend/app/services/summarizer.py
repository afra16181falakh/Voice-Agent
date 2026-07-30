"""
TextRank extractive summarizer — pure Python, no external dependencies
(no nltk/sumy/numpy, deliberately, to avoid a model/corpus download step
that would undercut the whole point of keeping the voice pipeline fast
and free of API costs).

Implements the algorithm from Mihalcea & Tarau (2004): sentences are nodes
in a graph, edge weight = word-overlap similarity between two sentences
(normalised by sentence length), and sentence importance is the PageRank
of that graph, computed via plain power iteration.
"""

import math
import re

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "at", "for", "with", "and", "or", "but", "so",
    "it", "this", "that", "i", "you", "he", "she", "we", "they", "my",
    "your", "his", "her", "our", "their", "me", "him", "us", "them",
    "do", "does", "did", "have", "has", "had", "not", "no", "yes",
    "user", "sonorus",
}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-zA-Z']+")

_DAMPING = 0.85
_MAX_ITER = 50
_CONVERGENCE_TOL = 1e-4


def _tokenize(sentence: str) -> set:
    return {w for w in _WORD_RE.findall(sentence.lower()) if w not in _STOPWORDS}


def _sentence_similarity(words_a: set, words_b: set) -> float:
    """TextRank's original similarity function: word overlap normalised by
    the log of each sentence's length, so two long sentences sharing a few
    common words don't outweigh two short, tightly-related sentences."""
    if not words_a or not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    if overlap == 0:
        return 0.0
    norm = math.log(len(words_a) + 1) + math.log(len(words_b) + 1)
    return overlap / norm if norm else 0.0


def _pagerank(similarity_matrix: list) -> list:
    """Plain power-iteration PageRank over the sentence similarity graph."""
    n = len(similarity_matrix)
    if n == 0:
        return []

    scores = [1.0 / n] * n
    row_sums = [sum(row) for row in similarity_matrix]

    for _ in range(_MAX_ITER):
        new_scores = [0.0] * n
        for i in range(n):
            rank_sum = 0.0
            for j in range(n):
                if i == j or row_sums[j] == 0:
                    continue
                rank_sum += similarity_matrix[j][i] / row_sums[j] * scores[j]
            new_scores[i] = (1 - _DAMPING) / n + _DAMPING * rank_sum

        delta = sum(abs(new_scores[i] - scores[i]) for i in range(n))
        scores = new_scores
        if delta < _CONVERGENCE_TOL:
            break

    return scores


def extractive_summarize(text: str, max_sentences: int = 3) -> str:
    """
    Condenses a block of conversation text down to its most representative
    sentences via TextRank. Returns an empty string if there's nothing
    worth summarizing.
    """
    if not text or not text.strip():
        return ""

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    tokenized = [_tokenize(s) for s in sentences]
    n = len(sentences)
    similarity_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                similarity_matrix[i][j] = _sentence_similarity(tokenized[i], tokenized[j])

    scores = _pagerank(similarity_matrix)
    if not scores or not any(scores):
        # No word overlap between any sentences — graph is disconnected,
        # fall back to the first N sentences in original order.
        return " ".join(sentences[:max_sentences])

    top_indices = sorted(range(n), key=lambda i: scores[i], reverse=True)[:max_sentences]
    return " ".join(sentences[i] for i in sorted(top_indices))
