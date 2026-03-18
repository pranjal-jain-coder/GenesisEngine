"""
Project RAG Service
Indexes the user's current project code (.gd files) to help the AI maintain consistency.
"""
import logging
from pathlib import Path
from typing import List, Dict

from google import genai
from google.genai import types

from core.config import config
from services.godot_rag import _cosine_sim

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-2-preview"

class ProjectRAG:
    """
    RAG service for the *User's Project Code*.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._chunks = []
        return cls._instance

    def _get_api_key(self) -> str:
        keys = config.get_gemini_keys()
        if not keys:
            raise RuntimeError("No Gemini API keys configured.")
        return keys[0]

    def _make_client(self) -> genai.Client:
        return genai.Client(api_key=self._get_api_key())

    def index_project(self, project_path: str):
        """
        Scans all .gd files in the project and embeds them.
        Call this periodically or before a major task.
        """
        path = Path(project_path)
        gd_files = list(path.rglob("*.gd"))
        
        chunks = []
        for gd in gd_files:
            # Skip addons content
            if "addons" in gd.parts:
                continue
                
            try:
                text = gd.read_text(encoding="utf-8")
                # Simple chunking by file for now (small scripts)
                # For larger scripts, we might want to split by func
                if text.strip():
                    chunks.append({
                        "text": text,
                        "source": str(gd.relative_to(path)),
                        "type": "script"
                    })
            except Exception as e:
                logger.warning(f"Failed to read {gd}: {e}")

        if not chunks:
            logger.info("Project RAG: No scripts to index.")
            self._chunks = []
            return

        logger.info(f"Project RAG: Indexing {len(chunks)} scripts...")
        
        client = self._make_client()
        texts = [c["text"] for c in chunks]
        
        # Batch embed
        batch_size = 10
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            try:
                resp = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type="retrieval_document"),
                )
                for e in resp.embeddings:
                    all_embeddings.append(e.values)
            except Exception as e:
                logger.error(f"Project RAG embedding failed: {e}")
                # Pad with empty embeddings to keep alignment? Or abort?
                # Abort batch
                continue

        # Reconstruct valid chunks
        self._chunks = []
        if len(all_embeddings) == len(chunks):
             for c, emb in zip(chunks, all_embeddings):
                 c["embedding"] = emb
                 self._chunks.append(c)
        
        logger.info(f"Project RAG: Indexed {len(self._chunks)} scripts.")

    def query(self, question: str, top_k: int = 3) -> List[str]:
        if not self._chunks:
            return []
            
        client = self._make_client()
        try:
            resp = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=question,
                config=types.EmbedContentConfig(task_type="retrieval_query"),
            )
            q_emb = resp.embeddings[0].values
        except Exception as e:
            logger.error(f"Project RAG query failed: {e}")
            return []

        scored = [
            (_cosine_sim(q_emb, c["embedding"]), c)
            for c in self._chunks
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        
        results = []
        print(f"\n[PROJECT RAG QUERY] \"{question}\"")
        for i, (score, chunk) in enumerate(scored[:top_k]):
            print(f"[PROJECT RAG HIT {i+1}] (Score: {score:.2f}) {chunk['source']}")
            results.append(f"filename: {chunk['source']}\ncode:\n{chunk['text']}")
            
        return results

project_rag = ProjectRAG()
