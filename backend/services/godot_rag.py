"""
Godot 4 Documentation RAG Service
Embeds curated Godot 4 docs using Gemini embeddings and persists them as JSON.
Retrieval uses pure-Python cosine similarity — no compiled dependencies required.
The coder_node queries this to inject relevant documentation into its prompt.
"""
import json
import math
import logging
import re
from pathlib import Path
from typing import List, Dict

from google import genai
from google.genai import types

from core.config import config

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "godot_docs"
INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "godot_rag_index.json"
EMBEDDING_MODEL = "gemini-embedding-2-preview"

# Chunk size in characters for splitting large doc sections
CHUNK_SIZE = 2500
CHUNK_OVERLAP = 300


def _cosine_sim(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0


class GodotRAG:
    """
    Singleton RAG service for Godot 4 documentation.

    Usage:
        from services.godot_rag import godot_rag
        results = godot_rag.query("how to move CharacterBody2D", top_k=3)
        # returns a list of relevant doc snippet strings
    """

    _instance: "GodotRAG | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._ready = False
            cls._instance._chunks: List[Dict] = []
        return cls._instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_api_key(self) -> str:
        keys = config.get_gemini_keys()
        if not keys:
            raise RuntimeError("No Gemini API keys configured.")
        return keys[0]

    def _make_client(self) -> genai.Client:
        return genai.Client(api_key=self._get_api_key())

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        client = self._make_client()
        results = []
        for text in texts:
            r = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type="retrieval_document"),
            )
            if not r.embeddings:
                raise RuntimeError(f"Empty embeddings response for text: {text[:80]!r}")
            results.append(r.embeddings[0].values)
        return results

    def _embed_query(self, text: str) -> List[float]:
        client = self._make_client()
        r = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="retrieval_query"),
        )
        if not r.embeddings:
            raise RuntimeError(f"Empty embeddings response for query: {text[:80]!r}")
        return r.embeddings[0].values

    def _docs_checksum(self) -> str:
        parts = []
        for f in sorted(DOCS_DIR.glob("*.md")):
            parts.append(f"{f.name}:{f.stat().st_size}")
        return "|".join(parts)

    def _load_raw_docs(self) -> List[Dict]:
        chunks = []
        for md_file in sorted(DOCS_DIR.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            for chunk in self._split_sections(text, md_file.stem):
                chunks.append(chunk)
        logger.info("Loaded %d raw doc chunks from %s", len(chunks), DOCS_DIR)
        return chunks

    def _split_sections(self, text: str, source: str) -> List[Dict]:
        sections = re.split(r"\n(?=## )", text)
        result = []
        for section in sections:
            section = section.strip()
            if not section:
                continue
            if len(section) <= CHUNK_SIZE:
                result.append({"text": section, "source": source})
            else:
                for i in range(0, len(section), CHUNK_SIZE - CHUNK_OVERLAP):
                    chunk = section[i: i + CHUNK_SIZE].strip()
                    if chunk:
                        result.append({"text": chunk, "source": source})
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_index(self, force: bool = False) -> None:
        """
        Build (or load) the embedding index.
        Embeddings are cached in godot_rag_index.json; only rebuilt when docs change.
        """
        current_checksum = self._docs_checksum()

        # Try loading existing index
        if not force and INDEX_PATH.exists():
            try:
                data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
                if data.get("checksum") == current_checksum and data.get("chunks"):
                    self._chunks = data["chunks"]
                    self._ready = True
                    logger.info(
                        "Godot RAG index loaded from cache (%d chunks).", len(self._chunks)
                    )
                    return
            except Exception as e:
                logger.warning("Failed to load RAG cache: %s — will rebuild.", e)

        raw_chunks = self._load_raw_docs()
        logger.info("Building Godot RAG index (embedding %d chunks)...", len(raw_chunks))
        texts = [c["text"] for c in raw_chunks]

        # Embed in small batches to respect API limits
        batch_size = 10
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            logger.info(
                "Embedding batch %d/%d (%d chunks)...",
                i // batch_size + 1,
                math.ceil(len(texts) / batch_size),
                len(batch),
            )
            all_embeddings.extend(self._embed_batch(batch))

        self._chunks = [
            {"text": c["text"], "source": c["source"], "embedding": emb}
            for c, emb in zip(raw_chunks, all_embeddings)
        ]

        INDEX_PATH.write_text(
            json.dumps({"checksum": current_checksum, "chunks": self._chunks}, indent=None),
            encoding="utf-8",
        )
        logger.info("Godot RAG index built and saved: %d chunks.", len(self._chunks))
        self._ready = True

    def _ensure_ready(self) -> None:
        if not self._ready:
            self.build_index()

    def query(self, question: str, top_k: int = 4) -> List[str]:
        """
        Retrieve the top_k most relevant doc snippets for a question.
        Returns a list of formatted strings (source label + text).
        """
        print(f"\n[RAG QUERY] \"{question}\"")
        self._ensure_ready()
        if not self._chunks:
            print("[RAG] No chunks available.")
            return []
        
        try:
            q_emb = self._embed_query(question)
        except Exception as e:
            logger.error(f"RAG embedding failed: {e}")
            print(f"[RAG ERROR] Embedding failed: {e}")
            return []

        scored = []
        for c in self._chunks:
            # Check if embedding exists
            if "embedding" not in c or not c["embedding"]:
                continue
            score = _cosine_sim(q_emb, c["embedding"])
            scored.append((score, c))
            
        scored.sort(key=lambda x: x[0], reverse=True)
        
        results = []
        for i, (score, chunk) in enumerate(scored[:top_k]):
            source = chunk.get('source', 'unknown')
            text = chunk.get('text', '')
            preview = text[:60].replace("\n", " ") + "..."
            print(f"[RAG HIT {i+1}] (Score: {score:.2f}) [{source}] {preview}")
            results.append(f"[{source}]\n{text}")
            
        return results

    def format_for_prompt(self, question: str, top_k: int = 4) -> str:
        """
        Query and format results as a prompt block.
        Returns empty string on failure so coder still runs without RAG.
        """
        try:
            snippets = self.query(question, top_k=top_k)
            if not snippets:
                return ""
            joined = "\n\n---\n\n".join(snippets)
            return (
                "\n\n## Relevant Godot 4 Documentation\n"
                "Use the following GDScript reference to write correct Godot 4 code:\n\n"
                + joined
            )
        except Exception as e:
            logger.warning("Godot RAG query failed (non-fatal): %s", e)
            return ""


# Module-level singleton
godot_rag = GodotRAG()
