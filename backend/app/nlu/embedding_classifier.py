"""Stage 1: cheap, fast paraphrase handling (§4.1).

Substitution note: the design doc specifies "a MiniLM-class sentence-
transformer... or a small fine-tuned classifier (DistilBERT-class) trained
on historical transcripts" (§4.1). Both require downloading pretrained
weights from a model hub (e.g. Hugging Face), and this sandboxed build
environment's network allowlist does not include huggingface.co or any
model-hub domain -- only pypi/npm/github. Rather than silently pretend to
use MiniLM, this implements the *same interface*
(`top_k(text) -> ranked intent candidates`) with a TF-IDF + cosine-
similarity classifier fit on the example utterances in intents.yaml: fully
offline, dependency-light (scikit-learn only), and deterministic.

To upgrade to the doc's originally-specified approach in an environment
with model-hub access: implement this same interface using
`sentence-transformers` (e.g. `all-MiniLM-L6-v2`) or a fine-tuned
DistilBERT classifier, and swap it in wherever `EmbeddingClassifier` is
constructed (see app/dependencies.py) -- nothing else in the pipeline
needs to change, since NLUPipeline only depends on `top_k()`'s return
shape, not on how it's computed.

Real accuracy tradeoff to know about: TF-IDF matches surface wording, not
semantic meaning -- it will not generalize to a paraphrase that shares no
vocabulary with the seed examples the way a sentence embedding would. In
this design that's an acceptable tradeoff because anything Stage 1 misses
falls through to Stage 2's LLM classifier rather than being lost, but it
does mean Stage 1's "cheap paraphrase handling" claim from §4.1 is weaker
here than a real sentence-transformer would provide, and more traffic
will route to the (slower, costlier) LLM stage than the doc's design
assumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class Candidate:
    intent: str
    score: float


class EmbeddingClassifier:
    def __init__(self, intent_examples: dict[str, list[str]]):
        self._intents = list(intent_examples.keys())
        corpus: list[str] = []
        self._corpus_intents: list[str] = []
        for intent, examples in intent_examples.items():
            for ex in examples:
                corpus.append(ex)
                self._corpus_intents.append(intent)
        if not corpus:
            raise ValueError("EmbeddingClassifier needs at least one example utterance")
        # stop_words="english" matters more than it would with a large
        # corpus: with only ~8 examples per intent, a filler word like
        # "my" that happens to appear in most fee_reversal examples isn't
        # down-weighted enough by IDF alone, and was observed (via tests)
        # inflating cosine similarity for genuinely unrelated queries like
        # "something about my account" to ~0.49 -- comfortably above a
        # naively-chosen threshold.
        self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
        self._matrix = self._vectorizer.fit_transform(corpus)

    @classmethod
    def from_intents_yaml(cls, path: str | Path) -> "EmbeddingClassifier":
        data = yaml.safe_load(Path(path).read_text())
        examples = {
            intent: cfg.get("example_utterances", []) for intent, cfg in data["intents"].items()
        }
        return cls(examples)

    def top_k(self, text: str, k: int = 3) -> list[Candidate]:
        query_vec = self._vectorizer.transform([text])
        sims = cosine_similarity(query_vec, self._matrix)[0]

        best_per_intent: dict[str, float] = {}
        for intent, score in zip(self._corpus_intents, sims):
            if score > best_per_intent.get(intent, -1.0):
                best_per_intent[intent] = float(score)

        ranked = sorted(best_per_intent.items(), key=lambda kv: kv[1], reverse=True)
        return [Candidate(intent=i, score=s) for i, s in ranked[:k]]
