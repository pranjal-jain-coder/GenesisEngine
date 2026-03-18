import unittest
from unittest.mock import MagicMock, patch
import json
from pathlib import Path
from core.llm import GeminiProvider

class TestGeminiRotation(unittest.TestCase):
    def setUp(self):
        self.usage_path = Path("/tmp/test_gemini_usage.json")
        if self.usage_path.exists():
            self.usage_path.unlink()
        
        # Mock config
        self.patcher_config = patch('core.llm.config')
        self.mock_config = self.patcher_config.start()
        self.mock_config.GEMINI_API_KEYS = ["key1", "key2", "key3"]
        self.mock_config.GEMINI_USAGE_PATH = self.usage_path
        self.mock_config.GEMINI_DAILY_LIMIT = 2
        self.mock_config.GEMINI_RATE_LIMIT = 1000  # Disable per-minute limiting for these tests
        self.mock_config.GEMINI_MODEL = "gemini-1.5-flash"
        self.mock_config.get_gemini_keys.return_value = ["key1", "key2", "key3"]
        
        # Mock genai
        self.patcher_genai = patch('core.llm.genai')
        self.mock_genai = self.patcher_genai.start()

        # Default: generate_content returns a mock with a .text attribute
        mock_response = MagicMock()
        mock_response.text = "mocked response"
        self.mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
        
    def tearDown(self):
        self.patcher_config.stop()
        self.patcher_genai.stop()
        if self.usage_path.exists():
            self.usage_path.unlink()

    def test_key_rotation_on_limit(self):
        provider = GeminiProvider()
        
        # 1. First 2 calls should use key1
        provider.generate("test")
        self.mock_genai.configure.assert_called_with(api_key="key1")
        
        provider.generate("test")
        
        # 3. Third call should use key2 because daily limit is 2
        provider.generate("test")
        self.mock_genai.configure.assert_called_with(api_key="key2")
        
        # Check usage file
        with open(self.usage_path, 'r') as f:
            data = json.load(f)
            today = list(data.keys())[0]
            # key IDs are masked
            key1_id = "key1" # Since it's short, it's not masked in our implementation if < 10 chars
            key2_id = "key2"
            self.assertEqual(data[today][key1_id], 2)
            self.assertEqual(data[today][key2_id], 1)

    def test_key_rotation_on_429_error(self):
        provider = GeminiProvider()
        
        # Mock model.generate_content to raise 429 on first key
        mock_model = MagicMock()
        mock_response_success = MagicMock()
        mock_response_success.text = "success"
        mock_model.generate_content.side_effect = [
            Exception("429 Resource exhausted"), # First call with key1 fails
            mock_response_success,               # Second call with key2 succeeds
        ]
        self.mock_genai.GenerativeModel.return_value = mock_model
        
        result = provider.generate("test")
        
        self.assertEqual(result, "success")
        # Ensure it marked key1 as exhausted and tried key2
        with open(self.usage_path, 'r') as f:
            data = json.load(f)
            today = list(data.keys())[0]
            self.assertEqual(data[today]["key1"], 2) # Limit is 2
            self.assertEqual(data[today]["key2"], 1)

if __name__ == "__main__":
    unittest.main()
