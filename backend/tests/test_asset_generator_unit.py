import pytest
from pathlib import Path
from services.asset_generator import AssetGenerator
from models.asset_request import SpriteStyle
from PIL import Image

@pytest.fixture
def generator():
    # Force image_provider to None to test the fallback/placeholder generation
    # without hitting the API and spending credits during tests.
    from core.config import config
    config.IMAGE_PROVIDER = "none"
    gen = AssetGenerator()
    gen.image_provider = None
    return gen

@pytest.fixture
def tmp_dir(tmp_path):
    return str(tmp_path)

@pytest.mark.asyncio
async def test_generate_placeholder_sprite(generator, tmp_dir):
    result = await generator.generate_sprite(
        name="test_sprite",
        description="A little red cube",
        style=SpriteStyle.PIXEL_ART,
        width=32,
        height=32,
        output_dir=tmp_dir
    )
    assert result is not None
    assert Path(result).exists()
    
    img = Image.open(result)
    assert img.width == 32
    assert img.height == 32

@pytest.mark.asyncio
async def test_generate_spritesheet_fallback_stitching(generator, tmp_dir):
    # Test that the offline fallback correctly stitches placeholder frames 
    # instead of crashing when asked for a sprite sheet.
    result = await generator.generate_spritesheet(
        name="test_sheet",
        description="A little red cube",
        style=SpriteStyle.PIXEL_ART,
        frame_width=32,
        frame_height=32,
        poses=["idle", "walk", "jump"],
        output_dir=tmp_dir
    )
    
    assert result is not None
    path, count = result
    assert Path(path).exists()
    assert count == 3
    
    img = Image.open(path)
    assert img.width == 32 * 3
    assert img.height == 32

@pytest.mark.asyncio
async def test_generate_placeholder_background(generator, tmp_dir):
    result = await generator.generate_background(
        name="test_bg",
        description="A beautiful sunset",
        width=1280,
        height=720,
        output_dir=tmp_dir
    )
    # Background generation doesn't have a placeholder natively; it just returns None
    # if the client is missing. This test verifies it doesn't crash.
    assert result is None

def test_chroma_key_removal(generator):
    # Create an image with a magenta background and some non-magenta pixels
    img = Image.new("RGBA", (10, 10), (255, 0, 255, 255))
    
    # Put a green pixel in the middle
    img.putpixel((5, 5), (0, 255, 0, 255))
    
    # Put a pixel that's almost magenta but should be softly blended (distance ~60)
    img.putpixel((6, 6), (235, 20, 235, 255))
    
    processed = generator._remove_chroma_key_background(img, tolerance=40)
    
    # Check the pure magenta pixel is removed (transparent)
    r, g, b, a = processed.getpixel((0, 0))
    assert a == 0
    
    # Check the green pixel is perfectly preserved
    r, g, b, a = processed.getpixel((5, 5))
    assert (r, g, b, a) == (0, 255, 0, 255)
    
    # Check the edge pixel was soft-blended (alpha > 0 but < 255)
    r, g, b, a = processed.getpixel((6, 6))
    assert a > 0 and a < 255
