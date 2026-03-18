"""
Unit tests for services.godot_rag
All Gemini API calls and filesystem I/O are mocked.
"""
import json
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure backend/ is on the path when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.godot_rag import GodotRAG, _cosine_sim, CHUNK_SIZE


def _fake_embedding(seed: int, dim: int = 8) -> list:
    """Deterministic unit vector for testing."""
    v = [float((seed + i) % 7) for i in range(dim)]
    mag = math.sqrt(sum(x * x for x in v))
    return [x / mag for x in v] if mag else v


def _make_embed_response(values: list):
    """Build a minimal mock EmbedContentResponse."""
    emb = MagicMock()
    emb.values = values
    resp = MagicMock()
    resp.embeddings = [emb]
    return resp


class TestCosineSimHelper(unittest.TestCase):
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(_cosine_sim(v, v), 1.0)

    def test_orthogonal_vectors(self):
        self.assertAlmostEqual(_cosine_sim([1, 0], [0, 1]), 0.0)

    def test_opposite_vectors(self):
        self.assertAlmostEqual(_cosine_sim([1, 0], [-1, 0]), -1.0)

    def test_zero_vector_returns_zero(self):
        self.assertEqual(_cosine_sim([0, 0], [1, 0]), 0.0)


class TestGodotRAGUnit(unittest.TestCase):
    """Tests that mock the Gemini API and filesystem."""

    def setUp(self):
        # Reset singleton state before every test
        GodotRAG._instance = None

        # Patch config so no real API key is needed
        self.p_config = patch("services.godot_rag.config")
        self.mock_config = self.p_config.start()
        self.mock_config.get_gemini_keys.return_value = ["test-api-key"]

        # Patch the genai Client
        self.p_genai = patch("services.godot_rag.genai")
        self.mock_genai = self.p_genai.start()
        self.mock_client = MagicMock()
        self.mock_genai.Client.return_value = self.mock_client

    def tearDown(self):
        self.p_config.stop()
        self.p_genai.stop()
        GodotRAG._instance = None

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    def test_singleton_returns_same_instance(self):
        a = GodotRAG()
        b = GodotRAG()
        self.assertIs(a, b)

    # ------------------------------------------------------------------
    # _split_sections
    # ------------------------------------------------------------------

    def test_split_sections_small_section_kept_whole(self):
        rag = GodotRAG()
        text = "## Move\nUse `move_and_slide()` to move a CharacterBody2D."
        chunks = rag._split_sections(text, "movement")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["source"], "movement")
        self.assertIn("move_and_slide", chunks[0]["text"])

    def test_split_sections_large_section_is_chunked(self):
        rag = GodotRAG()
        # Build a section larger than CHUNK_SIZE
        long_body = "x" * (CHUNK_SIZE * 3)
        text = f"## BigSection\n{long_body}"
        chunks = rag._split_sections(text, "big")
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c["text"]), CHUNK_SIZE)

    def test_split_sections_empty_text_returns_empty(self):
        rag = GodotRAG()
        self.assertEqual(rag._split_sections("", "empty"), [])

    def test_split_sections_multiple_h2_headers(self):
        rag = GodotRAG()
        text = "## A\nfoo\n## B\nbar\n## C\nbaz"
        chunks = rag._split_sections(text, "multi")
        self.assertEqual(len(chunks), 3)

    # ------------------------------------------------------------------
    # _embed_batch / _embed_query
    # ------------------------------------------------------------------

    def test_embed_query_returns_values(self):
        rag = GodotRAG()
        expected = _fake_embedding(1)
        self.mock_client.models.embed_content.return_value = _make_embed_response(expected)

        result = rag._embed_query("how to move player")
        self.assertEqual(result, expected)

    def test_embed_batch_returns_list_of_vectors(self):
        rag = GodotRAG()
        vecs = [_fake_embedding(i) for i in range(3)]
        self.mock_client.models.embed_content.side_effect = [
            _make_embed_response(v) for v in vecs
        ]
        results = rag._embed_batch(["a", "b", "c"])
        self.assertEqual(results, vecs)
        self.assertEqual(self.mock_client.models.embed_content.call_count, 3)

    def test_embed_query_raises_on_empty_embeddings(self):
        rag = GodotRAG()
        bad_resp = MagicMock()
        bad_resp.embeddings = []
        self.mock_client.models.embed_content.return_value = bad_resp

        with self.assertRaises(RuntimeError):
            rag._embed_query("test")

    def test_embed_batch_raises_on_empty_embeddings(self):
        rag = GodotRAG()
        bad_resp = MagicMock()
        bad_resp.embeddings = []
        self.mock_client.models.embed_content.return_value = bad_resp

        with self.assertRaises(RuntimeError):
            rag._embed_batch(["text"])

    # ------------------------------------------------------------------
    # build_index — cache hit / miss / force
    # ------------------------------------------------------------------

    def _make_cached_index(self, checksum: str, chunks: list) -> str:
        return json.dumps({"checksum": checksum, "chunks": chunks})

    def test_build_index_loads_from_valid_cache(self):
        rag = GodotRAG()
        cached_chunks = [
            {"text": "foo", "source": "s1", "embedding": _fake_embedding(0)},
            {"text": "bar", "source": "s2", "embedding": _fake_embedding(1)},
        ]
        checksum = "doc.md:100"

        with patch.object(rag, "_docs_checksum", return_value=checksum), \
             patch("services.godot_rag.INDEX_PATH") as mock_path:
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = self._make_cached_index(checksum, cached_chunks)

            rag.build_index()

        self.assertTrue(rag._ready)
        self.assertEqual(len(rag._chunks), 2)
        # No API call should have been made
        self.mock_client.models.embed_content.assert_not_called()

    def test_build_index_rebuilds_on_checksum_mismatch(self):
        rag = GodotRAG()
        old_checksum = "doc.md:50"
        new_checksum = "doc.md:200"
        cached_chunks = [{"text": "old", "source": "s", "embedding": _fake_embedding(0)}]
        new_raw = [{"text": "new content", "source": "doc"}]

        with patch.object(rag, "_docs_checksum", return_value=new_checksum), \
             patch.object(rag, "_load_raw_docs", return_value=new_raw), \
             patch.object(rag, "_embed_batch", return_value=[_fake_embedding(5)]), \
             patch("services.godot_rag.INDEX_PATH") as mock_path:
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = self._make_cached_index(old_checksum, cached_chunks)
            mock_path.write_text = MagicMock()

            rag.build_index()

        self.assertTrue(rag._ready)
        self.assertEqual(rag._chunks[0]["text"], "new content")

    def test_build_index_force_rebuilds_even_with_valid_cache(self):
        rag = GodotRAG()
        checksum = "doc.md:100"
        cached_chunks = [{"text": "cached", "source": "s", "embedding": _fake_embedding(0)}]
        new_raw = [{"text": "fresh", "source": "doc"}]

        with patch.object(rag, "_docs_checksum", return_value=checksum), \
             patch.object(rag, "_load_raw_docs", return_value=new_raw), \
             patch.object(rag, "_embed_batch", return_value=[_fake_embedding(3)]), \
             patch("services.godot_rag.INDEX_PATH") as mock_path:
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = self._make_cached_index(checksum, cached_chunks)
            mock_path.write_text = MagicMock()

            rag.build_index(force=True)

        self.assertEqual(rag._chunks[0]["text"], "fresh")

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------

    def _load_rag_with_chunks(self, chunks_with_embeddings: list) -> GodotRAG:
        rag = GodotRAG()
        rag._chunks = chunks_with_embeddings
        rag._ready = True
        return rag

    def test_query_returns_top_k_sorted_by_score(self):
        dim = 8
        # chunk 2 is most similar to query (same vector)
        query_vec = _fake_embedding(2, dim)
        chunks = [
            {"text": "chunk0", "source": "s0", "embedding": _fake_embedding(0, dim)},
            {"text": "chunk1", "source": "s1", "embedding": _fake_embedding(1, dim)},
            {"text": "chunk2", "source": "s2", "embedding": _fake_embedding(2, dim)},
            {"text": "chunk3", "source": "s3", "embedding": _fake_embedding(3, dim)},
        ]
        rag = self._load_rag_with_chunks(chunks)
        self.mock_client.models.embed_content.return_value = _make_embed_response(query_vec)

        results = rag.query("find chunk2", top_k=2)

        self.assertEqual(len(results), 2)
        self.assertIn("chunk2", results[0])  # best match first

    def test_query_returns_empty_when_no_chunks(self):
        rag = self._load_rag_with_chunks([])
        results = rag.query("anything")
        self.assertEqual(results, [])
        self.mock_client.models.embed_content.assert_not_called()

    def test_query_result_format_includes_source_label(self):
        dim = 8
        vec = _fake_embedding(0, dim)
        chunks = [{"text": "move_and_slide", "source": "movement", "embedding": vec}]
        rag = self._load_rag_with_chunks(chunks)
        self.mock_client.models.embed_content.return_value = _make_embed_response(vec)

        results = rag.query("player movement", top_k=1)
        self.assertTrue(results[0].startswith("[movement]"))

    # ------------------------------------------------------------------
    # format_for_prompt
    # ------------------------------------------------------------------

    def test_format_for_prompt_returns_string_with_header(self):
        dim = 8
        vec = _fake_embedding(0, dim)
        chunks = [{"text": "use move_and_slide", "source": "movement", "embedding": vec}]
        rag = self._load_rag_with_chunks(chunks)
        self.mock_client.models.embed_content.return_value = _make_embed_response(vec)

        result = rag.format_for_prompt("how to move", top_k=1)
        self.assertIn("## Relevant Godot 4 Documentation", result)
        self.assertIn("move_and_slide", result)

    def test_format_for_prompt_returns_empty_string_on_exception(self):
        rag = GodotRAG()
        rag._ready = True
        rag._chunks = [{"text": "x", "source": "s", "embedding": [1.0]}]
        self.mock_client.models.embed_content.side_effect = Exception("API down")

        result = rag.format_for_prompt("anything")
        self.assertEqual(result, "")

    def test_format_for_prompt_returns_empty_string_when_no_chunks(self):
        rag = self._load_rag_with_chunks([])
        result = rag.format_for_prompt("anything")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
