import asyncio
import sys
from pathlib import Path
from PIL import Image

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.asset_generator import AssetGenerator
from models.asset_request import SpriteStyle

async def debug_gen():
    gen = AssetGenerator()
    
    description = "a shiny metal sword with a gold hilt"
    style = SpriteStyle.PIXEL_ART
    width = 512
    height = 512
    
    # 1. Manually build prompt to see what's sent
    prompt = gen._build_sprite_prompt(description, style, width, height, False)
    prompt += " pure white background, isolated."
    print(f"DEBUG Prompt: {prompt}")
    
    # 2. Generate raw image
    neg_prompt = "background scenery, room, floor, landscape, clouds, blurry, noisy"
    img = await gen.image_provider.generate_image(prompt, width, height, style, negative_prompt=neg_prompt)
    if not img:
        print("Generation failed")
        return
        
    img.save("/tmp/debug_raw.png")
    print("Saved raw image to /tmp/debug_raw.png")
    
    # 3. Process it
    # Need to access private method or mock the flow
    processed_chroma = gen._remove_chroma_key_background(img)
    processed_chroma.save("/tmp/debug_chroma.png")
    print("Saved chroma-removed image to /tmp/debug_chroma.png")
    
    # 4. Resize check
    # Simulate the resize logic
    final = processed_chroma.resize((width, height), Image.Resampling.LANCZOS)
    final.save("/tmp/debug_final.png")
    print("Saved final image to /tmp/debug_final.png")

if __name__ == "__main__":
    asyncio.run(debug_gen())
