"""
Asset Generator — AI-powered sprite and audio generation using Gemini Imagen.

This is the FALLBACK when online search fails. It generates:
  - Individual sprites (single frame)
  - Sprite sheets (multiple poses arranged in a grid)
  - Tilesets (seamless tile grids)
  
Generation Strategy:
  - Uses Gemini's image generation (Imagen) for sprites
  - Crafts specialized prompts for game-asset-quality output
  - Post-processes: removes background, resizes, assembles sprite sheets
  - For audio: generates placeholder PCM .wav files (basic synthesized SFX)
"""
import logging
import struct
import math
import wave
import random
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

from core.config import config
from core.image_gen import get_image_provider
from models.asset_request import SpriteStyle

logger = logging.getLogger(__name__)


class AssetGenerator:
    """
    Generates game assets using AI (Gemini Imagen) and programmatic synthesis.
    """

    # Style-specific prompt fragments for better generation results
    STYLE_PROMPTS = {
        SpriteStyle.PIXEL_ART: "sharp pixel art, 16-bit, vibrant colors, clean lines",
        SpriteStyle.FLAT: "flat design, solid colors, minimal shading, vector",
        SpriteStyle.CARTOON: "cartoon, bold outlines, vibrant, 2D art",
        SpriteStyle.HAND_DRAWN: "hand-drawn, sketch lines, watercolor, organic",
    }

    def __init__(self):
        self.image_provider = get_image_provider(config.IMAGE_PROVIDER, config)

        if not self.image_provider:
            logger.warning(
                f"Image Provider '{config.IMAGE_PROVIDER}' failed to initialize."
            )
        else:
            logger.info(f"Initialized AssetGenerator with Image Provider: {config.IMAGE_PROVIDER}")

    async def generate_sprite(
        self,
        name: str,
        description: str,
        style: SpriteStyle = SpriteStyle.PIXEL_ART,
        width: int = 32,
        height: int = 32,
        transparent_bg: bool = True,
        color_palette: Optional[List[str]] = None,
        output_dir: str = "/tmp",
    ) -> Optional[str]:
        """
        Generate a single sprite frame using Gemini Imagen.
        
        Args:
            name: Asset identifier
            description: What the sprite should look like
            style: Visual style
            width/height: Target dimensions
            transparent_bg: Whether to attempt background removal
            color_palette: Optional color constraints
            output_dir: Where to save the result
            
        Returns:
            Path to the generated sprite PNG, or None on failure
        """
        if not self.image_provider:
            logger.warning("No image provider available, using programmatic fallback.")
            return await self._generate_placeholder_sprite(
                name, description, width, height, output_dir
            )

        prompt = self._build_sprite_prompt(
            description, style, width, height, transparent_bg, color_palette
        )
        
        # For local SD, we append stronger isolation tokens.
        # NOTE: Do NOT add a white background here — the base prompt already requests a
        # magenta (#FF00FF) chroma-key background. Conflicting background instructions
        # cause SD to generate a white background, which then defeats chroma-key removal
        # and allows the flood-fill step to destroy light-colored sprite pixels.
        if config.IMAGE_PROVIDER == "local":
            prompt += ", sticker style, centered, isolated."

        try:
            # Generate image via the configured provider
            neg_prompt = "background scenery, room, floor, landscape, clouds, blurry, noisy"
            img = await self.image_provider.generate_image(
                prompt=prompt,
                width=width,
                height=height,
                style=style,
                negative_prompt=neg_prompt
            )

            if img:
                # Apply background removal if requested
                if transparent_bg:
                    # Chroma key removal only applies to local SD which generates
                    # a magenta (#FF00FF) background. Cloud providers (Gemini, etc.)
                    # don't guarantee a magenta background, so applying chroma key
                    # removal to their output would corrupt purple/pink sprite pixels.
                    if config.IMAGE_PROVIDER == "local":
                        img = self._remove_chroma_key_background(img)
                    # Flood fill from corners to remove any solid background
                    img = self._flood_fill_remove_background(img)
                    # Isolate the main sprite to remove small artifacts
                    img = self._isolate_main_sprite(img)

                # Post-process: resize intelligently.
                # If the AI provided a higher resolution than requested, preserve it (unless it's tiny).
                # We only force-resize if dimensions are vastly different or it's a spritesheet.
                nat_w, nat_h = img.size
                if nat_w < width or nat_h < height:
                    # Upscale: NEAREST for pixel art, LANCZOS for others
                    img = img.resize((width, height), Image.Resampling.NEAREST if style == SpriteStyle.PIXEL_ART else Image.Resampling.LANCZOS)
                elif nat_w > width or nat_h > height:
                    # Downscale: NEAREST for pixel art to keep blocks sharp, LANCZOS for others
                    # We always resize to requested size for stickers/sprites
                    img = img.resize((width, height), Image.Resampling.NEAREST if style == SpriteStyle.PIXEL_ART else Image.Resampling.LANCZOS)

                output_path = Path(output_dir) / f"{name}.png"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(str(output_path), "PNG", icc_profile=None)
                logger.info(f"Generated sprite: {output_path}")
                return str(output_path)
            else:
                logger.warning(f"Image provider returned no images for '{name}', using fallback.")
                return await self._generate_placeholder_sprite(
                    name, description, width, height, output_dir
                )

        except Exception as e:
            logger.error(f"Image generation failed for '{name}': {e}")
            return await self._generate_placeholder_sprite(
                name, description, width, height, output_dir
            )

    async def generate_spritesheet(
        self,
        name: str,
        description: str,
        style: SpriteStyle = SpriteStyle.PIXEL_ART,
        frame_width: int = 32,
        frame_height: int = 32,
        poses: Optional[List[str]] = None,
        transparent_bg: bool = True,
        color_palette: Optional[List[str]] = None,
        output_dir: str = "/tmp",
    ) -> Optional[Tuple[str, int]]:
        """
        Generate a multi-frame sprite sheet.
        
        Strategy:
            1. Try generating all poses as a single tiled sprite sheet via one prompt
            2. If that fails, generate each pose individually and stitch them together
        
        Args:
            name: Asset identifier
            description: What the character/object looks like
            poses: List of pose names (e.g., ["idle", "walk_1", "walk_2", "jump"])
            
        Returns:
            Tuple of (path to sprite sheet, number of frames) or None
        """
        if not poses:
            poses = ["idle"]

        num_frames = len(poses)

        # We force individual frame generation and stitching to ensure mathematically
        # precise dimension layouts, which is critical for Godot's Sprite2D Hframes/Vframes.
        
        logger.info(f"Generating individual frames for sprite sheet: '{name}' (poses: {num_frames})")
        frames = []
        
        # Consistent instruction for all individual poses
        consistency_instruction = (
            "CRITICAL: Keep the exact same character design, proportions, colors, and clothing "
            "as if it is the same 2D asset in a new pose. Minimal background."
        )

        for i, pose in enumerate(poses):
            pose_desc = f"{description}. Character is in '{pose}' pose. {consistency_instruction}"
            frame_path = await self.generate_sprite(
                name=f"{name}_frame_{i}",
                description=pose_desc,
                style=style,
                width=frame_width,
                height=frame_height,
                transparent_bg=transparent_bg,
                color_palette=color_palette,
                output_dir=output_dir,
            )
            if frame_path:
                frames.append(frame_path)

        if not frames:
            logger.error(f"Failed to generate any frames for '{name}'")
            return None

        # Stitch frames into a horizontal sprite sheet
        sheet_path = self._stitch_spritesheet(frames, name, output_dir)
        return (sheet_path, len(frames)) if sheet_path else None

    async def generate_tileset(
        self,
        name: str,
        description: str,
        style: SpriteStyle = SpriteStyle.PIXEL_ART,
        tile_size: int = 16,
        columns: int = 4,
        rows: int = 4,
        tile_types: Optional[List[str]] = None,
        output_dir: str = "/tmp",
    ) -> Optional[str]:
        """
        Generate a tileset image.
        
        Generates a grid of tiles suitable for use in a Godot TileMap.
        """
        if not tile_types:
            tile_types = ["ground"]

        style_fragment = self.STYLE_PROMPTS.get(style, self.STYLE_PROMPTS[SpriteStyle.PIXEL_ART])

        prompt = (
            f"A seamless tileset grid for a 2D game, {columns}x{rows} tiles, "
            f"each tile {tile_size}x{tile_size} pixels. "
            f"Tile types: {', '.join(tile_types)}. "
            f"Description: {description}. "
            f"{style_fragment}. "
            f"Game asset, top-down view, seamless edges between tiles, "
            f"match background color to facilitate extraction."
        )

        if self.image_provider:
            try:
                img = await self.image_provider.generate_image(
                    prompt=prompt,
                    width=tile_size * columns,
                    height=tile_size * rows,
                    style=style
                )

                if img:
                    # Only remove chroma key background for local SD (which uses a magenta
                    # #FF00FF background). Cloud providers do not use chroma key, so applying
                    # this to their output would corrupt any pink/purple/magenta tile pixels.
                    if config.IMAGE_PROVIDER == "local":
                        img = self._remove_chroma_key_background(img)

                    # Resize to exact tileset dimensions to ensure grid alignment.
                    total_w = tile_size * columns
                    total_h = tile_size * rows
                    
                    # If high-res style, use quality resizing.
                    resize_method = Image.Resampling.NEAREST if style == SpriteStyle.PIXEL_ART else Image.Resampling.LANCZOS
                    img = img.resize((total_w, total_h), resize_method)

                    output_path = Path(output_dir) / f"{name}_tileset.png"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    img.save(str(output_path), "PNG", icc_profile=None)
                    logger.info(f"Generated tileset: {output_path}")
                    return str(output_path)
            except Exception as e:
                logger.error(f"Tileset generation failed: {e}")

        # Fallback: generate a simple colored grid placeholder
        return await self._generate_placeholder_tileset(
            name, tile_size, columns, rows, output_dir
        )

    async def generate_background(
        self,
        name: str,
        description: str,
        style: SpriteStyle = SpriteStyle.PIXEL_ART,
        width: int = 1280,
        height: int = 720,
        output_dir: str = "/tmp",
    ) -> Optional[str]:
        """
        Generate a 2D background image.
        Uses 16:9 aspect ratio and does not apply chroma key transparency.
        """
        if not self.image_provider:
            logger.warning("No image provider available for background generation.")
            return None

        style_fragment = self.STYLE_PROMPTS.get(style, self.STYLE_PROMPTS[SpriteStyle.PIXEL_ART])

        prompt = (
            f"A high quality 2D game background of {description}. "
            f"{style_fragment}. "
            f"Game asset, professional quality, immersive environment."
        )

        try:
            img = await self.image_provider.generate_image(
                prompt=prompt,
                width=width,
                height=height,
                style=style
            )

            if img:
                # Resize to expected dimensions
                resize_method = Image.Resampling.NEAREST if style == SpriteStyle.PIXEL_ART else Image.Resampling.LANCZOS
                img = img.resize((width, height), resize_method)

                output_path = Path(output_dir) / f"{name}_bg.png"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(str(output_path), "PNG", icc_profile=None)
                logger.info(f"Generated background: {output_path}")
                return str(output_path)
            else:
                logger.warning(f"Image provider returned no images for background '{name}'.")
                return None
        except Exception as e:
            logger.error(f"Background generation failed for '{name}': {e}")
            return None

    async def generate_audio_sfx(
        self,
        name: str,
        description: str,
        duration_seconds: float = 0.5,
        output_dir: str = "/tmp",
    ) -> Optional[str]:
        """
        Generate a simple sound effect programmatically.
        
        Uses basic waveform synthesis (sine, square, noise) to create
        simple game SFX like jumps, coins, hits, etc.
        
        For more complex audio, online search should be used first.
        """
        output_path = Path(output_dir) / f"{name}.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sample_rate = 22050
        num_samples = int(sample_rate * duration_seconds)

        # Determine SFX type from description
        desc_lower = description.lower()

        if any(w in desc_lower for w in ["jump", "bounce", "hop"]):
            samples = self._synth_jump(num_samples, sample_rate)
        elif any(w in desc_lower for w in ["coin", "collect", "pickup", "gem"]):
            samples = self._synth_coin(num_samples, sample_rate)
        elif any(w in desc_lower for w in ["hit", "damage", "hurt", "pain"]):
            samples = self._synth_hit(num_samples, sample_rate)
        elif any(w in desc_lower for w in ["explod", "boom", "blast"]):
            samples = self._synth_explosion(num_samples, sample_rate)
        elif any(w in desc_lower for w in ["click", "button", "select", "menu"]):
            samples = self._synth_click(num_samples, sample_rate)
        elif any(w in desc_lower for w in ["shoot", "fire", "laser", "bullet"]):
            samples = self._synth_laser(num_samples, sample_rate)
        elif any(w in desc_lower for w in ["powerup", "power up", "level up", "upgrade"]):
            samples = self._synth_powerup(num_samples, sample_rate)
        else:
            # Generic beep
            samples = self._synth_beep(num_samples, sample_rate)

        # Write WAV
        try:
            with wave.open(str(output_path), "w") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                for s in samples:
                    # Clamp to 16-bit range
                    clamped = max(-32768, min(32767, int(s * 32767)))
                    wav_file.writeframes(struct.pack("<h", clamped))

            logger.info(f"Generated SFX: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"Audio generation failed: {e}")
            return None

    # -----------------------------------------------------------------------
    # Background Removal
    # -----------------------------------------------------------------------

    def _remove_chroma_key_background(self, img: Image.Image, tolerance: int = 70) -> Image.Image:
        """
        Removes a chroma key background (assumed to be bright magenta/pink #FF00FF).
        Uses a higher tolerance and soft alpha blending for anti-aliased edge pixels.
        """
        img = img.convert("RGBA")
        data = img.getdata()
        new_data = []

        target_r, target_g, target_b = 255, 0, 255
        softness = 80

        for item in data:
            r, g, b, a = item
            diff_r = abs(r - target_r)
            diff_g = abs(g - target_g)
            diff_b = abs(b - target_b)
            
            # Simple Manhattan distance for speed
            distance = diff_r + diff_g + diff_b
            
            if distance < tolerance:
                # Strong match for magenta - make completely transparent
                new_data.append((0, 0, 0, 0))
            elif distance < tolerance + softness:
                # Edge pixel - fade alpha only; do NOT alter RGB to avoid color corruption
                ratio = (distance - tolerance) / softness
                new_a = int(a * ratio)
                new_data.append((r, g, b, new_a))
            else:
                new_data.append(item)

        img.putdata(new_data)
        return img

    # -----------------------------------------------------------------------
    # Prompt Building
    # -----------------------------------------------------------------------

    def _build_sprite_prompt(
        self,
        description: str,
        style: SpriteStyle,
        width: int,
        height: int,
        transparent_bg: bool,
        color_palette: Optional[List[str]] = None,
    ) -> str:
        """Build an optimized prompt for sprite generation."""
        style_fragment = self.STYLE_PROMPTS.get(style, self.STYLE_PROMPTS[SpriteStyle.PIXEL_ART])
        
        # Prioritize background for better isolation in local SD
        bg_part = "ON A SOLID FLAT BRIGHT MAGENTA #FF00FF BACKGROUND" if transparent_bg else ""
        
        parts = [
            f"2D {style_fragment} sprite of {description}.",
            bg_part,
            "isolated, centered, centered, game asset."
        ]

        if color_palette:
            colors_str = ", ".join(color_palette)
            parts.append(f"Colors: {colors_str}.")

        return " ".join([p for p in parts if p])



    def _stitch_spritesheet(self, frame_paths: List[str], name: str, output_dir: str) -> Optional[str]:
        """Stitch individual frame images into a horizontal sprite sheet."""
        try:
            frames = []
            for p in frame_paths:
                try:
                    frames.append(Image.open(p))
                except Exception as e:
                    logger.error(f"Failed to open frame {p}: {e}")

            if not frames:
                return None

            frame_w = frames[0].width
            frame_h = frames[0].height

            # Create sprite sheet canvas
            sheet = Image.new("RGBA", (frame_w * len(frames), frame_h), (0, 0, 0, 0))

            for i, frame in enumerate(frames):
                frame = frame.convert("RGBA")
                frame = frame.resize((frame_w, frame_h), Image.Resampling.NEAREST)
                sheet.paste(frame, (i * frame_w, 0))
                # Explicitly close the Pillow Image to prevent fd exhaustion
                if hasattr(frame, "close"):
                    frame.close()

            output_path = Path(output_dir) / f"{name}_sheet.png"
            sheet.save(str(output_path), "PNG")
            logger.info(f"Stitched sprite sheet: {output_path} ({len(frames)} frames)")

            # Clean up individual frames
            for p in frame_paths:
                try:
                    Path(p).unlink()
                except Exception:
                    pass

            return str(output_path)
        except Exception as e:
            logger.error(f"Sprite sheet stitching failed: {e}")
            return None

    # -----------------------------------------------------------------------
    # Placeholder / Fallback Generators (no AI needed)
    # -----------------------------------------------------------------------

    async def _generate_placeholder_sprite(
        self, name: str, description: str, width: int, height: int, output_dir: str
    ) -> Optional[str]:
        """
        Generate a simple colored rectangle placeholder sprite.
        Used when AI generation is completely unavailable.
        """
        try:
            # Pick a deterministic color based on the name
            hash_val = hash(name)
            r = (hash_val & 0xFF0000) >> 16
            g = (hash_val & 0x00FF00) >> 8
            b = hash_val & 0x0000FF
            # Make sure it's not too dark
            r = max(80, r)
            g = max(80, g)
            b = max(80, b)

            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

            # Draw a simple shape
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)

            # Simple character-like shape: body rectangle + head circle
            margin = max(2, width // 8)
            body_top = height // 3
            draw.rectangle(
                [margin, body_top, width - margin, height - margin],
                fill=(r, g, b, 255)
            )
            # Head
            head_radius = min(width, height) // 5
            head_center = (width // 2, body_top - head_radius // 2)
            draw.ellipse(
                [head_center[0] - head_radius, head_center[1] - head_radius,
                 head_center[0] + head_radius, head_center[1] + head_radius],
                fill=(r, g, b, 255)
            )

            output_path = Path(output_dir) / f"{name}.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(output_path), "PNG")
            logger.info(f"Generated placeholder sprite: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"Placeholder sprite generation failed: {e}")
            return None

    async def _generate_placeholder_tileset(
        self, name: str, tile_size: int, columns: int, rows: int, output_dir: str
    ) -> Optional[str]:
        """Generate a simple colored grid tileset placeholder."""
        try:
            from PIL import ImageDraw

            total_w = tile_size * columns
            total_h = tile_size * rows
            img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            colors = [
                (76, 153, 0, 255),    # Grass green
                (102, 51, 0, 255),    # Dirt brown
                (128, 128, 128, 255), # Stone gray
                (0, 102, 204, 255),   # Water blue
            ]

            for row in range(rows):
                for col in range(columns):
                    x = col * tile_size
                    y = row * tile_size
                    color = colors[(row * columns + col) % len(colors)]
                    draw.rectangle([x, y, x + tile_size - 1, y + tile_size - 1], fill=color)
                    # Add a 1px grid line
                    draw.rectangle([x, y, x + tile_size - 1, y + tile_size - 1], outline=(0, 0, 0, 128))

            output_path = Path(output_dir) / f"{name}_tileset.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(output_path), "PNG")
            logger.info(f"Generated placeholder tileset: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"Placeholder tileset generation failed: {e}")
            return None

    # -----------------------------------------------------------------------
    # Audio Synthesis Primitives
    # -----------------------------------------------------------------------

    @staticmethod
    def _synth_jump(num_samples: int, sample_rate: int) -> List[float]:
        """Rising frequency sweep — classic jump SFX."""
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            progress = i / num_samples
            freq = 200 + 600 * progress  # Rising from 200Hz to 800Hz
            envelope = 1.0 - progress  # Fade out
            val = math.sin(2 * math.pi * freq * t) * envelope * 0.7
            samples.append(val)
        return samples

    @staticmethod
    def _synth_coin(num_samples: int, sample_rate: int) -> List[float]:
        """Two-tone chime — classic coin pickup."""
        samples = []
        half = num_samples // 2
        for i in range(num_samples):
            t = i / sample_rate
            freq = 880 if i < half else 1320  # A5 then E6
            envelope = 1.0 - (i / num_samples)
            val = math.sin(2 * math.pi * freq * t) * envelope * 0.6
            samples.append(val)
        return samples

    @staticmethod
    def _synth_hit(num_samples: int, sample_rate: int) -> List[float]:
        """Short noise burst — impact/damage."""
        samples = []
        for i in range(num_samples):
            progress = i / num_samples
            envelope = max(0, 1.0 - progress * 3)  # Fast decay
            noise = (random.random() * 2 - 1) * 0.8
            tone = math.sin(2 * math.pi * 150 * (i / sample_rate)) * 0.3
            samples.append((noise + tone) * envelope)
        return samples

    @staticmethod
    def _synth_explosion(num_samples: int, sample_rate: int) -> List[float]:
        """Low rumble with noise — explosion."""
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            progress = i / num_samples
            envelope = max(0, 1.0 - progress * 1.5)
            noise = (random.random() * 2 - 1) * 0.6
            low_tone = math.sin(2 * math.pi * (80 - 40 * progress) * t) * 0.5
            samples.append((noise + low_tone) * envelope)
        return samples

    @staticmethod
    def _synth_click(num_samples: int, sample_rate: int) -> List[float]:
        """Very short click/tap sound."""
        samples = []
        click_len = min(num_samples, int(sample_rate * 0.05))
        for i in range(num_samples):
            if i < click_len:
                t = i / sample_rate
                envelope = 1.0 - (i / click_len)
                val = math.sin(2 * math.pi * 1000 * t) * envelope * 0.5
            else:
                val = 0.0
            samples.append(val)
        return samples

    @staticmethod
    def _synth_laser(num_samples: int, sample_rate: int) -> List[float]:
        """Descending frequency sweep — laser/shoot."""
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            progress = i / num_samples
            freq = 1200 - 800 * progress  # Descending from 1200Hz to 400Hz
            envelope = 1.0 - progress * 0.8
            # Square-ish wave for retro feel
            val = (1.0 if math.sin(2 * math.pi * freq * t) > 0 else -1.0) * envelope * 0.4
            samples.append(val)
        return samples

    @staticmethod
    def _synth_powerup(num_samples: int, sample_rate: int) -> List[float]:
        """Rising arpeggiated tones — power up."""
        samples = []
        notes = [523.25, 659.25, 783.99, 1046.50]  # C5, E5, G5, C6
        segment_len = num_samples // len(notes)
        for i in range(num_samples):
            t = i / sample_rate
            note_idx = min(i // segment_len, len(notes) - 1)
            freq = notes[note_idx]
            progress = i / num_samples
            envelope = min(1.0, (1.0 - progress) * 2)
            val = math.sin(2 * math.pi * freq * t) * envelope * 0.5
            samples.append(val)
        return samples

    @staticmethod
    def _synth_beep(num_samples: int, sample_rate: int) -> List[float]:
        """Simple sine beep — generic SFX."""
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            envelope = 1.0 - (i / num_samples)
            val = math.sin(2 * math.pi * 440 * t) * envelope * 0.5
            samples.append(val)
        return samples

    # -----------------------------------------------------------------------
    # Image Isolation Helpers
    # -----------------------------------------------------------------------

    def _flood_fill_remove_background(self, img: Image.Image, tolerance: int = 40) -> Image.Image:
        """
        Removes background by flood-filling from the corners.
        Highly effective for solid or near-solid backgrounds that aren't perfectly uniform.
        """
        try:
            from PIL import ImageDraw
            img = img.convert("RGBA")
            w, h = img.size
            # Seeds: four corners and mid-edges
            seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                     (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
            for x, y in seeds:
                ImageDraw.floodfill(img, (x, y), (0, 0, 0, 0), thresh=tolerance)
            return img
        except Exception as e:
            logger.warning(f"Flood fill background removal failed: {e}")
            return img

    def _isolate_main_sprite(self, img: Image.Image) -> Image.Image:
        """
        Extracts the largest connected component (the main sprite) from an image.
        Removes background noise and floater pixels.
        """
        try:
            import numpy as np
            from scipy import ndimage
            img = img.convert("RGBA")
            data = np.array(img)
            mask = data[:, :, 3] > 10
            if not np.any(mask):
                return img
            labeled_array, num_features = ndimage.label(mask)
            if num_features == 0:
                return img
            counts = np.bincount(labeled_array.ravel())
            if len(counts) <= 1:
                return img
            largest_label = np.argmax(counts[1:]) + 1
            final_mask = labeled_array == largest_label
            data[~final_mask] = [0, 0, 0, 0]
            coords = np.argwhere(final_mask)
            y0, x0 = coords.min(axis=0)
            y1, x1 = coords.max(axis=0) + 1
            return Image.fromarray(data[y0:y1, x0:x1])
        except Exception as e:
            logger.warning(f"Sprite isolation failed: {e}")
            return img
