from abc import ABC, abstractmethod
from typing import Optional
import logging
import io
import asyncio
from PIL import Image
from models.asset_request import SpriteStyle

logger = logging.getLogger(__name__)

class ImageProvider(ABC):
    """Abstract base class for image generation providers."""

    @abstractmethod
    async def generate_image(self, prompt: str, width: int, height: int, style: SpriteStyle, negative_prompt: str = "") -> Optional[Image.Image]:
        """
        Generates an image from a text prompt.
        
        Args:
            prompt: Text description of the image to generate
            width: Width in pixels
            height: Height in pixels
            style: The requested art style
            
        Returns:
            A PIL Image if successful, None otherwise.
        """
        pass

class GeminiImageProvider(ImageProvider):
    """Generates images using Google's Gemini/Imagen API."""
    def __init__(self, api_key: str, model: str = "imagen-4.0-fast-generate-001"):
        self.api_key = api_key
        self.model = model
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except ImportError:
            logger.error("google-genai package not installed.")
            self.client = None
            
    async def generate_image(self, prompt: str, width: int, height: int, style: SpriteStyle, negative_prompt: str = "") -> Optional[Image.Image]:
        if not self.client:
            logger.error("Gemini client not initialized.")
            return None
            
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_images,
                model=self.model,
                prompt=prompt,
                config={
                    "number_of_images": 1,
                    # Imagen primarily supports strict aspect ratios rather than exact 
                    # arbitrary pixel dimensions. Request 1:1 or 16:9 as a base, then we
                    # resize perfectly inside the asset generator.
                    "aspect_ratio": "16:9" if width > height * 1.5 else "1:1",
                },
            )
            
            if response and response.generated_images:
                img_data = response.generated_images[0].image.image_bytes
                return Image.open(io.BytesIO(img_data)).convert("RGBA")
            return None
        except Exception as e:
            logger.error(f"Gemini image generation failed: {e}")
            return None

class HuggingFaceAPIProvider(ImageProvider):
    """Generates images using Hugging Face Inference API."""
    def __init__(self, api_key: str, model: str = "stabilityai/stable-diffusion-xl-base-1.0"):
        self.api_key = api_key
        self.model = model
        self.url = f"https://api-inference.huggingface.co/models/{self.model}"
        
    async def generate_image(self, prompt: str, width: int, height: int, style: SpriteStyle, negative_prompt: str = "") -> Optional[Image.Image]:
        if not self.api_key:
            logger.error("HF API Key missing.")
            return None
            
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {"inputs": prompt}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        image_bytes = await resp.read()
                        return Image.open(io.BytesIO(image_bytes)).convert("RGBA")
                    else:
                        error_msg = await resp.text()
                        logger.error(f"HF API returned {resp.status}: {error_msg}")
                        return None
        except ImportError:
            logger.error("aiohttp package not installed.")
            return None
        except Exception as e:
            logger.error(f"HF API image generation failed: {e}")
            return None

class LocalDiffusersProvider(ImageProvider):
    """Generates images locally using PyTorch and Hugging Face Diffusers (e.g., SD1.5)."""
    def __init__(self, model_id: str = "runwayml/stable-diffusion-v1-5"):
        self.model_id = model_id
        self.pipeline = None
        self._is_loading = False
        
    def _load_pipeline(self):
        """Lazy load the pipeline to avoid taking VRAM if we aren't using image gen."""
        if self.pipeline is not None:
            return
            
        import torch
        from diffusers import StableDiffusionPipeline
        
        logger.info(f"Loading local diffusers model: {self.model_id} onto GPU...")
        
        # Determine device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load pipeline (FP16 is highly recommended for 6GB VRAM on RTX 4060)
        dtype = torch.float16 if device == "cuda" else torch.float32
        
        self.pipeline = StableDiffusionPipeline.from_pretrained(
            self.model_id, 
            torch_dtype=dtype,
            use_safetensors=True
        )
        self.pipeline = self.pipeline.to(device)
        
        # Disable the NSFW safety checker entirely.
        # This checker is meant for consumer-facing products and incorrectly flags
        # innocent game assets (e.g. "bright light", "glowing", "explosion") as black images.
        # For a local game dev tool there is no need for this filter.
        self.pipeline.safety_checker = None
        self.pipeline.requires_safety_checker = False
        
        # Enable memory efficient attention if available (PyTorch 2 SDP or xformers)
        try:
            self.pipeline.enable_xformers_memory_efficient_attention()
            logger.info("xformers attention enabled for SD.")
        except Exception:
            logger.info("xformers not available, using PyTorch SDP core attention.")
            
        logger.info(f"Model {self.model_id} loaded successfully.")

    @staticmethod
    def _truncate_prompt_to_clip(prompt: str, max_tokens: int = 75) -> str:
        """
        Naively truncates a prompt to fit within CLIP's 77-token limit.
        CLIP uses a BPE tokenizer; a rough safe estimate is 4 chars / token.
        We truncate by words to avoid breaking mid-word.
        """
        words = prompt.split()
        # SD1.5 CLIP supports 77 tokens including BOS/EOS — so 75 body tokens max.
        # Each word is roughly 1-2 tokens; keep well under the limit.
        MAX_WORDS = 55  # ~55 words ≈ ≤75 tokens for almost any English text
        if len(words) > MAX_WORDS:
            truncated = " ".join(words[:MAX_WORDS])
            logger.warning(
                f"Prompt too long ({len(words)} words). Truncated to {MAX_WORDS} words "
                f"to stay within CLIP's 77-token limit."
            )
            return truncated
        return prompt

    async def generate_image(self, prompt: str, width: int, height: int, style: SpriteStyle, negative_prompt: str = "") -> Optional[Image.Image]:
        try:
            if not self.pipeline:
                self._load_pipeline()
                
            # Local Diffusers strictly expect width and height to be multiples of 8.
            target_width = (width // 8) * 8
            target_height = (height // 8) * 8
            
            # Avoid too small images (SD struggles under 384x384 or 512x512)
            # Typically for best SD1.5 output, generate at 512x512 and we resize it down later inside AssetGenerator
            sd_width = max(target_width, 512)
            sd_height = max(target_height, 512)
            
            import torch
            import gc
            
            # Combine provided negative prompt with defaults
            default_neg = "blurry, watermark, low quality, signature, nsfw, text, background details, scenery, floor, wall"
            combined_neg = f"{negative_prompt}, {default_neg}" if negative_prompt else default_neg
            
            # We run diffusers inference in a thread because torch is blocking
            def run_inference():
                # Truncate prompt to CLIP's 77-token hard limit before inference
                safe_prompt = LocalDiffusersProvider._truncate_prompt_to_clip(prompt)
                safe_neg_prompt = LocalDiffusersProvider._truncate_prompt_to_clip(combined_neg)
                generator = torch.Generator(device=self.pipeline.device).manual_seed(
                    torch.randint(0, 1000000, (1,)).item()
                )

                result = self.pipeline(
                    prompt=safe_prompt,
                    negative_prompt=safe_neg_prompt,
                    width=sd_width,
                    height=sd_height,
                    num_inference_steps=25,
                    guidance_scale=12.0,
                    generator=generator
                ).images[0]
                
                # Cleanup to free up prompt caches etc
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                gc.collect()
                
                return result

            img = await asyncio.to_thread(run_inference)
            return img.convert("RGBA")
            
        except ImportError as e:
            logger.error(f"Missing required packages for local diffusers: {e}. You may need 'diffusers', 'transformers', 'accelerate', and 'torch'.")
            return None
        except Exception as e:
            logger.error(f"Local diffusers generation failed: {e}")
            return None

def get_image_provider(provider_type: str, config: any) -> Optional[ImageProvider]:
    """Factory to return the configured ImageProvider."""
    provider_type = provider_type.lower()
    
    if provider_type == "gemini":
        if config.GEMINI_API_KEY:
            return GeminiImageProvider(api_key=config.GEMINI_API_KEY, model=config.IMAGEN_MODEL)
        logger.warning("GEMINI_API_KEY missing for GeminiImageProvider.")
        
    elif provider_type == "hf":
        if getattr(config, 'HF_ACCESS_TOKEN', None):
            return HuggingFaceAPIProvider(api_key=config.HF_ACCESS_TOKEN)
        logger.warning("HF_ACCESS_TOKEN missing for HuggingFaceAPIProvider.")
        
    elif provider_type == "local":
        model = getattr(config, 'LOCAL_DIFFUSION_MODEL', "runwayml/stable-diffusion-v1-5")
        return LocalDiffusersProvider(model_id=model)
        
    return None
