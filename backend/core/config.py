import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# We look for .env in the backend directory or the project root
backend_env = Path(__file__).resolve().parent.parent / '.env'
root_env = Path(__file__).resolve().parent.parent.parent / '.env'

if backend_env.exists():
    load_dotenv(dotenv_path=backend_env)
elif root_env.exists():
    load_dotenv(dotenv_path=root_env)
else:
    print(f"Warning: .env file not found in {backend_env} or {root_env}")

class Config:
    """Configuration class for the Genesis Engine Brain."""
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # Support for multiple keys (comma-separated or list)
    _gemini_keys_str = os.getenv("GEMINI_API_KEYS", "")
    GEMINI_API_KEYS: list[str] = [
        k.strip() for k in _gemini_keys_str.split(",") if k.strip()
    ] if _gemini_keys_str else ([
        # Fallback: if GEMINI_API_KEY itself is a comma-separated list,
        # split it into individual keys for rotation.
        k.strip() for k in GEMINI_API_KEY.split(",") if k.strip()
    ] if GEMINI_API_KEY else [])
    
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    HF_ACCESS_TOKEN: str = os.getenv("HF_ACCESS_TOKEN", "")
    
    # LLM Settings
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

    # Image Generation Settings
    IMAGE_PROVIDER: str = os.getenv("IMAGE_PROVIDER", "local")
    IMAGEN_MODEL: str = os.getenv("IMAGEN_MODEL", "imagen-4.0-fast-generate-001")
    LOCAL_DIFFUSION_MODEL: str = os.getenv("LOCAL_DIFFUSION_MODEL", "runwayml/stable-diffusion-v1-5")
    
    # Usage Tracking
    GEMINI_USAGE_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "gemini_usage.json"
    GEMINI_DAILY_LIMIT: int = int(os.getenv("GEMINI_DAILY_LIMIT", "20"))
    GEMINI_RATE_LIMIT: int = int(os.getenv("GEMINI_RATE_LIMIT", "5"))  # requests per minute per key


    @classmethod
    def validate(cls):
        """Validates that necessary configuration is present."""
        if not cls.GEMINI_API_KEY and cls.LLM_PROVIDER == "gemini":
            print("Warning: GEMINI_API_KEY not found and LLM_PROVIDER is 'gemini'.")
        if not cls.OPENAI_API_KEY and cls.LLM_PROVIDER == "openai":
            print("Warning: OPENAI_API_KEY not found and LLM_PROVIDER is 'openai'.")

    def get_gemini_keys(self) -> list[str]:
        """Reloads .env and returns the latest Gemini API keys."""
        load_dotenv(dotenv_path=backend_env, override=True)
        keys_str = os.getenv("GEMINI_API_KEYS", "")
        if keys_str:
            # Primary source: explicit GEMINI_API_KEYS env var
            return [k.strip() for k in keys_str.split(",") if k.strip()]

        single_or_multi = os.getenv("GEMINI_API_KEY", "")
        if not single_or_multi:
            return []

        # Support comma-separated GEMINI_API_KEY as a list of keys
        if "," in single_or_multi:
            return [k.strip() for k in single_or_multi.split(",") if k.strip()]

        # Fallback: single key
        return [single_or_multi]

config = Config()
