"""
Asset Service — Main orchestrator for asset acquisition.

This is the single entry point that agents call. It:
  1. Checks the local cache
  2. Searches online databases
  3. Falls back to AI generation
  4. Saves the result into the Godot project's assets/ folder
  5. Returns a Godot-friendly res:// path
"""
import asyncio
import logging
import shutil
import tempfile
import zipfile
import datetime
import subprocess
from filelock import FileLock
from pathlib import Path
from typing import Optional, List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

from models.asset_request import (
    SpriteRequest, TilesetRequest, AudioRequest, BackgroundRequest, AssetResult,
    AssetType, SpriteStyle,
)
from services.asset_cache import AssetCache
from services.asset_search import AssetSearcher
from services.asset_generator import AssetGenerator

logger = logging.getLogger(__name__)


class AssetService:
    """
    Unified asset acquisition service.
    
    Usage from an agent tool:
        service = AssetService(project_path)
        result = await service.get_sprite(SpriteRequest(...))
        # result.godot_path → "res://assets/sprites/player.png"
    """

    # Subdirectories inside the Godot project's assets folder
    SPRITE_DIR = "assets/sprites"
    AUDIO_DIR = "assets/audio"
    TILESET_DIR = "assets/tilesets"
    BACKGROUND_DIR = "assets/backgrounds"
    
    TRUSTED_CC0_SOURCES = {"cache", "generated", "synthesized", "kenney"}
    
    # Only accept online results with relevance score above this
    MIN_RELEVANCE_THRESHOLD = 0.3

    def __init__(self, project_path: str, log_callback=None):
        self.project_path = Path(project_path)
        self.cache = AssetCache(project_path)
        self.searcher = AssetSearcher()
        self.generator = AssetGenerator()
        
        # Callback for UI live logging (func(str) -> None)
        self.log_callback = log_callback

        # Ensure asset directories exist in the project
        (self.project_path / self.SPRITE_DIR).mkdir(parents=True, exist_ok=True)
        (self.project_path / self.AUDIO_DIR).mkdir(parents=True, exist_ok=True)
        (self.project_path / self.TILESET_DIR).mkdir(parents=True, exist_ok=True)
        (self.project_path / self.BACKGROUND_DIR).mkdir(parents=True, exist_ok=True)
        
    def _log(self, msg: str):
        """Helper to log both to Python logger and the UI callback."""
        logger.info(msg)
        if self.log_callback:
            try:
                self.log_callback(msg)
            except Exception as e:
                logger.error(f"UI log callback failed: {e}")

    async def get_sprite(self, request: SpriteRequest) -> AssetResult:
        """
        Acquire a sprite asset. Tries: project dir → cache → online search → AI generation.

        For multi-pose requests, this produces a sprite sheet.
        """
        is_sheet = len(request.poses) > 1
        asset_type = AssetType.SPRITESHEET if is_sheet else AssetType.SPRITE

        # 0. Already in project?
        existing = self._find_existing_project_asset(request.name, self.SPRITE_DIR)
        if existing:
            return existing

        # 1. Check cache
        cached = self.cache.get(
            request.name, asset_type.value,
            style=request.style.value, w=request.width, h=request.height,
            poses=",".join(request.poses),
        )
        if cached:
            godot_path = self._copy_to_project(cached, self.SPRITE_DIR, request.name)
            return AssetResult(
                success=True,
                asset_path=str(self.project_path / godot_path),
                godot_path=f"res://{godot_path}",
                source="cache",
                message=f"Loaded '{request.name}' from cache.",
                frame_count=len(request.poses),
                frame_width=request.width,
                frame_height=request.height,
            )

        # 2. Search online
        self._log(f"Searching online for sprite: {request.name} ({request.description})")
        search_results = await self.searcher.search_sprites(
            query=request.description,
            tags=request.tags + [request.style.value],
            style=request.style.value,
            max_results=10,
        )

        for result in search_results:
            if result.relevance_score < self.MIN_RELEVANCE_THRESHOLD:
                self._log(f"Skipping match from {result.source} (low relevance: {result.relevance_score:.2f})")
                continue

            self._log(f"Downloading match from {result.source} (relevance: {result.relevance_score:.2f})...")
            # Try to download the asset
            with tempfile.TemporaryDirectory() as tmp_dir:
                downloaded = await self.searcher.download_asset(
                    result.download_url, tmp_dir
                )
                if downloaded:
                    # Check if it's a usable image file
                    dl_path = Path(downloaded)
                    if dl_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                        # Process: resize if needed
                        processed = await self._process_downloaded_sprite(
                            downloaded, request
                        )
                        if processed:
                            # Cache it
                            self.cache.put(
                                request.name, asset_type.value, processed,
                                source=result.source,
                                style=request.style.value, w=request.width, h=request.height,
                                poses=",".join(request.poses),
                            )
                            godot_path = self._copy_to_project(processed, self.SPRITE_DIR, request.name)
                            self._track_license(request.name, result.source, godot_path)
                            self._log(f"Acquired: {godot_path}")
                            return AssetResult(
                                success=True,
                                asset_path=str(self.project_path / godot_path),
                                godot_path=f"res://{godot_path}",
                                source=result.source,
                                message=f"Downloaded '{request.name}' from {result.source}.",
                                frame_count=len(request.poses),
                                frame_width=request.width,
                                frame_height=request.height,
                            )
                    elif dl_path.suffix.lower() == ".zip":
                        # Try to extract usable sprites from zip
                        extracted = self._extract_sprites_from_zip(downloaded, tmp_dir, request.name, request.tags)
                        if extracted:
                            processed = await self._process_downloaded_sprite(
                                extracted[0], request
                            )
                            if processed:
                                self.cache.put(
                                    request.name, asset_type.value, processed,
                                    source=result.source,
                                    style=request.style.value, w=request.width, h=request.height,
                                    poses=",".join(request.poses),
                                )
                                godot_path = self._copy_to_project(processed, self.SPRITE_DIR, request.name)
                                self._track_license(request.name, result.source, godot_path)
                                self._log(f"Acquired: {godot_path}")
                                return AssetResult(
                                    success=True,
                                    asset_path=str(self.project_path / godot_path),
                                    godot_path=f"res://{godot_path}",
                                    source=result.source,
                                    message=f"Extracted '{request.name}' from {result.source} pack.",
                                    frame_count=len(request.poses),
                                    frame_width=request.width,
                                    frame_height=request.height,
                                )

        # 3. Generate with AI
        self._log(f"Online search failed, generating '{request.name}' with AI...")

        with tempfile.TemporaryDirectory() as tmp_dir:
            if is_sheet:
                gen_result = await self.generator.generate_spritesheet(
                    name=request.name,
                    description=request.description,
                    style=request.style,
                    frame_width=request.width,
                    frame_height=request.height,
                    poses=request.poses,
                    transparent_bg=request.transparent_background,
                    color_palette=request.color_palette,
                    output_dir=tmp_dir,
                )
                if gen_result:
                    gen_path, frame_count = gen_result
                    processed_gen = await self._process_downloaded_sprite(gen_path, request)
                    if not processed_gen:
                        self._log(f"Generated sheet post-processing failed for '{request.name}'.")
                        return AssetResult(
                            success=False,
                            message=f"Generated sprite sheet '{request.name}', but post-processing failed."
                        )
                    self.cache.put(
                        request.name, asset_type.value, processed_gen,
                        source="generated",
                        style=request.style.value, w=request.width, h=request.height,
                        poses=",".join(request.poses),
                    )
                    godot_path = self._copy_to_project(processed_gen, self.SPRITE_DIR, request.name)
                    self._track_license(request.name, "generated", godot_path)
                    self._log(f"Generated: {godot_path}")
                    return AssetResult(
                        success=True,
                        asset_path=str(self.project_path / godot_path),
                        godot_path=f"res://{godot_path}",
                        source="generated",
                        message=f"Generated sprite sheet '{request.name}' ({frame_count} frames).",
                        frame_count=frame_count,
                        frame_width=request.width,
                        frame_height=request.height,
                    )
            else:
                gen_path = await self.generator.generate_sprite(
                    name=request.name,
                    description=request.description,
                    style=request.style,
                    width=request.width,
                    height=request.height,
                    transparent_bg=request.transparent_background,
                    color_palette=request.color_palette,
                    output_dir=tmp_dir,
                )
                if gen_path:
                    processed_gen = await self._process_downloaded_sprite(gen_path, request)
                    if not processed_gen:
                        self._log(f"Generated sprite post-processing failed for '{request.name}'.")
                        return AssetResult(
                            success=False,
                            message=f"Generated sprite '{request.name}', but post-processing failed."
                        )
                    self.cache.put(
                        request.name, asset_type.value, processed_gen,
                        source="generated",
                        style=request.style.value, w=request.width, h=request.height,
                        poses=",".join(request.poses),
                    )
                    godot_path = self._copy_to_project(processed_gen, self.SPRITE_DIR, request.name)
                    self._track_license(request.name, "generated", godot_path)
                    self._log(f"Generated: {godot_path}")
                    return AssetResult(
                        success=True,
                        asset_path=str(self.project_path / godot_path),
                        godot_path=f"res://{godot_path}",
                        source="generated",
                        message=f"Generated sprite '{request.name}'.",
                        frame_count=1,
                        frame_width=request.width,
                        frame_height=request.height,
                    )

        return AssetResult(
            success=False,
            message=f"Failed to acquire sprite '{request.name}' from any source."
        )

    async def get_sprite_options(self, request: SpriteRequest, max_options: int = 3) -> list:
        """
        Collect up to *max_options* candidate sprites/spritesheets.

        Each candidate is saved in the project with a numbered suffix:
            assets/sprites/{name}_opt0.png, _opt1.png, …

        The caller is responsible for:
          - Renaming the selected option to the canonical ``{name}.png``.
          - Deleting the rejected options.

        Returns a list of AssetResult (may be fewer than max_options if sources
        are exhausted).
        """
        is_sheet = len(request.poses) > 1

        candidates: list = []

        # 0. Already in project? Include it as option 0 but still collect more
        #    options so the user sees 3 choices and can pick the best one.
        existing = self._find_existing_project_asset(request.name, self.SPRITE_DIR)
        if existing:
            candidates.append(existing)
            # Fall through — don't return early; fill remaining slots below.

        # Clean up stale option files from any previous run for this asset name
        sprite_dir = self.project_path / self.SPRITE_DIR
        for stale in sprite_dir.glob(f"{request.name}_opt*"):
            try:
                stale.unlink()
            except OSError:
                pass

        def _save_candidate(src_path: str, source: str) -> AssetResult | None:
            idx = len(candidates)
            opt_name = f"{request.name}_opt{idx}"
            src = Path(src_path)
            dest_dir = self.project_path / self.SPRITE_DIR
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / f"{opt_name}{src.suffix}"
            shutil.copy2(str(src), str(dest_path))  # overwrite any existing option file
            godot_path = str(dest_path.relative_to(self.project_path))
            if source not in self.TRUSTED_CC0_SOURCES:
                self._track_license(opt_name, source, godot_path)
            return AssetResult(
                success=True,
                asset_path=str(dest_path),
                godot_path=f"res://{godot_path}",
                source=source,
                message=f"Option {idx} from {source}.",
                frame_count=len(request.poses),
                frame_width=request.width,
                frame_height=request.height,
            )

        # 1. Online search — collect up to max_options good matches
        self._log(f"Searching for up to {max_options} options for '{request.name}'…")
        search_results = await self.searcher.search_sprites(
            query=request.description,
            tags=request.tags + [request.style.value],
            style=request.style.value,
            max_results=max_options * 3,  # ask for more so we have filtering room
        )

        for result in search_results:
            if len(candidates) >= max_options:
                break
            if result.relevance_score < self.MIN_RELEVANCE_THRESHOLD:
                continue
            self._log(f"Downloading option candidate from {result.source} (score: {result.relevance_score:.2f})…")
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    downloaded = await self.searcher.download_asset(result.download_url, tmp_dir)
                    if not downloaded:
                        continue
                    dl_path = Path(downloaded)
                    if dl_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                        processed = await self._process_downloaded_sprite(downloaded, request)
                        if processed:
                            res = _save_candidate(processed, result.source)
                            if res:
                                candidates.append(res)
                    elif dl_path.suffix.lower() == ".zip":
                        extracted = self._extract_sprites_from_zip(downloaded, tmp_dir, request.name, request.tags)
                        for extracted_img in extracted:
                            if len(candidates) >= max_options:
                                break
                            # Extract all blobs from each zip image so packed sheets
                            # yield multiple candidates rather than just one.
                            processed_list = await self._process_downloaded_sprite_all(extracted_img, request)
                            for processed in processed_list:
                                if len(candidates) >= max_options:
                                    break
                                res = _save_candidate(processed, result.source)
                                if res:
                                    candidates.append(res)
            except Exception as e:
                logger.error(f"Error processing candidate from {result.source}: {e}")

        # 2. AI generation to fill remaining slots
        # Each option uses a variation hint so the generator produces visually
        # distinct results rather than three identical images.
        VARIATION_HINTS = [
            "",  # slot 0: original description unchanged
            " Alternative design with a different pose or color arrangement.",
            " Another variation: distinct silhouette or contrasting color scheme.",
        ]
        fail_count = 0
        while len(candidates) < max_options and fail_count < max_options:
            slot = len(candidates)
            variation_hint = VARIATION_HINTS[slot] if slot < len(VARIATION_HINTS) else VARIATION_HINTS[-1]
            varied_description = request.description + variation_hint
            self._log(f"Generating AI option {slot} for '{request.name}'…")
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    if is_sheet:
                        gen_result = await self.generator.generate_spritesheet(
                            name=request.name,
                            description=varied_description,
                            style=request.style,
                            frame_width=request.width,
                            frame_height=request.height,
                            poses=request.poses,
                            transparent_bg=request.transparent_background,
                            color_palette=request.color_palette,
                            output_dir=tmp_dir,
                        )
                        gen_path = gen_result[0] if gen_result else None
                    else:
                        gen_path = await self.generator.generate_sprite(
                            name=request.name,
                            description=varied_description,
                            style=request.style,
                            width=request.width,
                            height=request.height,
                            transparent_bg=request.transparent_background,
                            color_palette=request.color_palette,
                            output_dir=tmp_dir,
                        )
                    if gen_path:
                        processed_gen = await self._process_downloaded_sprite(gen_path, request)
                        if not processed_gen:
                            fail_count += 1
                            continue
                        res = _save_candidate(processed_gen, "generated")
                        if res:
                            candidates.append(res)
                            fail_count = 0  # reset on success
                    else:
                        fail_count += 1  # try again; don't hard-stop on one failure
            except Exception as e:
                logger.error(f"AI generation failed for option {slot}: {e}")
                fail_count += 1  # retry instead of aborting the loop

        return candidates

    async def get_tileset(self, request: TilesetRequest) -> AssetResult:
        """Acquire a tileset asset. Tries: project dir → cache → online → generate."""
        asset_type = AssetType.TILESET

        # 0. Already in project?
        existing = self._find_existing_project_asset(request.name, self.TILESET_DIR)
        if existing:
            return existing

        # 1. Check cache
        cached = self.cache.get(
            request.name, asset_type.value,
            style=request.style.value, tile_size=request.tile_size,
            cols=request.columns, rows=request.rows,
        )
        if cached:
            godot_path = self._copy_to_project(cached, self.TILESET_DIR, request.name)
            return AssetResult(
                success=True,
                asset_path=str(self.project_path / godot_path),
                godot_path=f"res://{godot_path}",
                source="cache",
                message=f"Loaded tileset '{request.name}' from cache.",
            )

        # 2. Search online (tilesets specifically)
        self._log(f"Searching online for tileset: {request.name}")
        search_results = await self.searcher.search_sprites(
            query=f"{request.description} tileset",
            tags=request.tags + ["tileset", request.style.value],
            style=request.style.value,
            max_results=10,
        )

        for result in search_results:
            if result.relevance_score < self.MIN_RELEVANCE_THRESHOLD:
                self._log(f"Skipping match from {result.source} (low relevance: {result.relevance_score:.2f})")
                continue

            self._log(f"Downloading match from {result.source} (relevance: {result.relevance_score:.2f})...")
            with tempfile.TemporaryDirectory() as tmp_dir:
                downloaded = await self.searcher.download_asset(result.download_url, tmp_dir)
                if downloaded and Path(downloaded).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    self.cache.put(
                        request.name, asset_type.value, downloaded,
                        source=result.source,
                        style=request.style.value, tile_size=request.tile_size,
                        cols=request.columns, rows=request.rows,
                    )
                    godot_path = self._copy_to_project(downloaded, self.TILESET_DIR, request.name)
                    self._track_license(request.name, result.source, godot_path)
                    self._log(f"Acquired: {godot_path}")
                    return AssetResult(
                        success=True,
                        asset_path=str(self.project_path / godot_path),
                        godot_path=f"res://{godot_path}",
                        source=result.source,
                        message=f"Downloaded tileset '{request.name}' from {result.source}.",
                    )

        # 3. Generate tileset
        self._log(f"Online search failed, generating tileset '{request.name}' with AI...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            gen_path = await self.generator.generate_tileset(
                name=request.name,
                description=request.description,
                style=request.style,
                tile_size=request.tile_size,
                columns=request.columns,
                rows=request.rows,
                tile_types=request.tile_types,
                output_dir=tmp_dir,
            )
            if gen_path:
                self.cache.put(
                    request.name, asset_type.value, gen_path,
                    source="generated",
                    style=request.style.value, tile_size=request.tile_size,
                    cols=request.columns, rows=request.rows,
                )
                godot_path = self._copy_to_project(gen_path, self.TILESET_DIR, request.name)
                self._log(f"Generated: {godot_path}")
                return AssetResult(
                    success=True,
                    asset_path=str(self.project_path / godot_path),
                    godot_path=f"res://{godot_path}",
                    source="generated",
                    message=f"Generated tileset '{request.name}'.",
                )

        return AssetResult(
            success=False,
            message=f"Failed to acquire tileset '{request.name}' from any source."
        )

    async def get_background(self, request: BackgroundRequest) -> AssetResult:
        """Acquire a background asset. Tries: project dir → cache → online → generate."""
        asset_type = AssetType.BACKGROUND

        # 0. Already in project?
        existing = self._find_existing_project_asset(request.name, self.BACKGROUND_DIR)
        if existing:
            return existing

        # 1. Check cache
        cached = self.cache.get(
            request.name, asset_type.value,
            style=request.style.value, w=request.width, h=request.height,
        )
        if cached:
            godot_path = self._copy_to_project(cached, self.BACKGROUND_DIR, request.name)
            return AssetResult(
                success=True,
                asset_path=str(self.project_path / godot_path),
                godot_path=f"res://{godot_path}",
                source="cache",
                message=f"Loaded background '{request.name}' from cache.",
            )

        # 2. Search online
        self._log(f"Searching online for background: {request.name}")
        search_results = await self.searcher.search_sprites(
            query=f"{request.description} background",
            tags=request.tags + ["background", request.style.value],
            style=request.style.value,
            max_results=10,
        )

        for result in search_results:
            if result.relevance_score < self.MIN_RELEVANCE_THRESHOLD:
                self._log(f"Skipping background match from {result.source} (low relevance: {result.relevance_score:.2f})")
                continue

            self._log(f"Downloading background match from {result.source} (relevance: {result.relevance_score:.2f})...")
            with tempfile.TemporaryDirectory() as tmp_dir:
                downloaded = await self.searcher.download_asset(result.download_url, tmp_dir)
                if downloaded and Path(downloaded).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    self.cache.put(
                        request.name, asset_type.value, downloaded,
                        source=result.source,
                        style=request.style.value, w=request.width, h=request.height,
                    )
                    godot_path = self._copy_to_project(downloaded, self.BACKGROUND_DIR, request.name)
                    self._track_license(request.name, result.source, godot_path)
                    self._log(f"Acquired: {godot_path}")
                    return AssetResult(
                        success=True,
                        asset_path=str(self.project_path / godot_path),
                        godot_path=f"res://{godot_path}",
                        source=result.source,
                        message=f"Downloaded background '{request.name}' from {result.source}.",
                    )

        # 3. Generate background
        self._log(f"Online search failed, generating background '{request.name}' with AI...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            gen_path = await self.generator.generate_background(
                name=request.name,
                description=request.description,
                style=request.style,
                width=request.width,
                height=request.height,
                output_dir=tmp_dir,
            )
            if gen_path:
                self.cache.put(
                    request.name, asset_type.value, gen_path,
                    source="generated",
                    style=request.style.value, w=request.width, h=request.height,
                )
                godot_path = self._copy_to_project(gen_path, self.BACKGROUND_DIR, request.name)
                self._track_license(request.name, "generated", godot_path)
                self._log(f"Generated: {godot_path}")
                return AssetResult(
                    success=True,
                    asset_path=str(self.project_path / godot_path),
                    godot_path=f"res://{godot_path}",
                    source="generated",
                    message=f"Generated background '{request.name}'.",
                )

        return AssetResult(
            success=False,
            message=f"Failed to acquire background '{request.name}' from any source."
        )

    async def get_audio(self, request: AudioRequest) -> AssetResult:
        """Acquire an audio asset. Tries: project dir → cache → online → synthesize."""
        asset_type = AssetType.AUDIO_SFX if request.audio_type == "sfx" else AssetType.AUDIO_MUSIC

        # 0. Already in project?
        existing = self._find_existing_project_asset(request.name, self.AUDIO_DIR)
        if existing:
            return existing

        # 1. Check cache
        cached = self.cache.get(
            request.name, asset_type.value,
            audio_type=request.audio_type,
        )
        if cached:
            godot_path = self._copy_to_project(cached, self.AUDIO_DIR, request.name)
            return AssetResult(
                success=True,
                asset_path=str(self.project_path / godot_path),
                godot_path=f"res://{godot_path}",
                source="cache",
                message=f"Loaded audio '{request.name}' from cache.",
            )

        # 2. Search online
        self._log(f"Searching online for audio: {request.name}")
        search_results = await self.searcher.search_audio(
            query=request.description,
            tags=request.tags,
            audio_type=request.audio_type,
            max_results=10,
        )

        for result in search_results:
            if result.relevance_score < self.MIN_RELEVANCE_THRESHOLD:
                self._log(f"Skipping audio match from {result.source} (low relevance: {result.relevance_score:.2f})")
                continue

            self._log(f"Downloading audio match from {result.source} (relevance: {result.relevance_score:.2f})...")
            with tempfile.TemporaryDirectory() as tmp_dir:
                downloaded = await self.searcher.download_asset(result.download_url, tmp_dir)
                if downloaded and Path(downloaded).suffix.lower() in (".wav", ".ogg", ".mp3"):
                    self.cache.put(
                        request.name, asset_type.value, downloaded,
                        source=result.source,
                        audio_type=request.audio_type,
                    )
                    godot_path = self._copy_to_project(downloaded, self.AUDIO_DIR, request.name)
                    self._track_license(request.name, result.source, godot_path)
                    self._log(f"Acquired: {godot_path}")
                    return AssetResult(
                        success=True,
                        asset_path=str(self.project_path / godot_path),
                        godot_path=f"res://{godot_path}",
                        source=result.source,
                        message=f"Downloaded audio '{request.name}' from {result.source}.",
                    )

        # 3. Synthesize (SFX only — music generation is beyond scope)
        if request.audio_type == "sfx":
            self._log(f"Online search failed, synthesizing SFX '{request.name}'...")
            duration = request.duration_seconds or 0.5
            with tempfile.TemporaryDirectory() as tmp_dir:
                gen_path = await self.generator.generate_audio_sfx(
                    name=request.name,
                    description=request.description,
                    duration_seconds=duration,
                    output_dir=tmp_dir,
                )
                if gen_path:
                    self.cache.put(
                        request.name, asset_type.value, gen_path,
                        source="synthesized",
                        audio_type=request.audio_type,
                    )
                    godot_path = self._copy_to_project(gen_path, self.AUDIO_DIR, request.name)
                    self._log(f"Synthesized: {godot_path}")
                    return AssetResult(
                        success=True,
                        asset_path=str(self.project_path / godot_path),
                        godot_path=f"res://{godot_path}",
                        source="synthesized",
                        message=f"Synthesized SFX '{request.name}'.",
                    )

        self._log(f"Failed to acquire audio '{request.name}'.")
        return AssetResult(
            success=False,
            message=f"Failed to acquire audio '{request.name}' from any source."
        )

    # -----------------------------------------------------------------------
    # Private Helpers
    # -----------------------------------------------------------------------

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    _AUDIO_EXTS = {".wav", ".ogg", ".mp3"}

    def _find_existing_project_asset(self, name: str, asset_subdir: str) -> Optional[AssetResult]:
        """
        Return an AssetResult if the canonical asset file already exists in the
        project directory.  This is checked before any network/AI calls so that
        retries and task re-runs never re-download an asset that is already present.
        """
        asset_dir = self.project_path / asset_subdir
        for ext in self._IMAGE_EXTS | self._AUDIO_EXTS:
            candidate = asset_dir / f"{name}{ext}"
            if candidate.exists():
                godot_path = str(candidate.relative_to(self.project_path))
                self._log(f"Found existing project asset, skipping download: {godot_path}")
                return AssetResult(
                    success=True,
                    asset_path=str(candidate),
                    godot_path=f"res://{godot_path}",
                    source="project",
                    message=f"Using existing project asset '{name}'.",
                )
        return None

    def _track_license(self, asset_name: str, source: str, file_path: str):
        """Appends downloaded asset details to a tracking file for license review."""
        if source in self.TRUSTED_CC0_SOURCES:
            return 
            
        tracker_path = self.project_path / "assets" / "LICENSES_TODO.md"
        tracker_path.parent.mkdir(parents=True, exist_ok=True)
        
        lock_path = self.project_path / "assets" / "LICENSES_TODO.md.lock"
        with FileLock(lock_path):
            # Create header if new
            if not tracker_path.exists():
                with open(tracker_path, "w") as f:
                    f.write("# Asset License Tracker\n\n")
                    f.write("The following assets were acquired automatically from the web via scraping.\n")
                    f.write("Their licenses are unbound/mixed. **Review or replace before commercial release:**\n\n")
                    
            date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(tracker_path, "a") as f:
                f.write(f"- [ ] **{asset_name}** | Source: `{source}` | Path: `{file_path}` | Acquired: {date_str}\n")

    def _copy_to_project(self, source_path: str, asset_subdir: str, name: str) -> str:
        """
        Copy a file into the project's asset directory.
        
        Returns:
            Relative path from project root (suitable for res://)
        """
        src = Path(source_path)
        ext = src.suffix
        dest_dir = self.project_path / asset_subdir
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Use the asset name + original extension
        dest_filename = f"{name}{ext}"
        dest_path = dest_dir / dest_filename

        # Handle conflicts
        counter = 1
        while dest_path.exists():
            dest_filename = f"{name}_{counter}{ext}"
            dest_path = dest_dir / dest_filename
            counter += 1

        shutil.copy2(str(src), str(dest_path))
        logger.info(f"Asset saved: {dest_path}")

        # Force import so the asset is usable immediately
        self._force_godot_import()

        # Return path relative to project root
        return str(dest_path.relative_to(self.project_path))

    def _force_godot_import(self):
        """Forces Godot to import new assets by running the editor headless for a brief moment."""
        try:
            # Run godot in headless mode, which triggers the import process and then quits
            # Using timeout to prevent hanging if Godot gets stuck
            cmd = ["godot", "--headless", "--path", str(self.project_path), "--editor", "--quit"]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            logger.info("Forced Godot import successfully.")
        except Exception as e:
            # Non-critical failure, log and continue
            logger.warning(f"Failed to force Godot import (assets might not load immediately): {e}")

    async def _process_downloaded_sprite(
        self, file_path: str, request: SpriteRequest
    ) -> Optional[str]:
        """Post-process a downloaded sprite image (runs in a thread pool to avoid blocking the event loop)."""
        return await asyncio.to_thread(self._process_downloaded_sprite_sync, file_path, request)

    async def _process_downloaded_sprite_all(
        self, file_path: str, request: SpriteRequest
    ) -> List[str]:
        """Like _process_downloaded_sprite but extracts ALL blobs from a packed sheet.
        Returns a list of processed image paths (may be a single item if no sheet detected)."""
        return await asyncio.to_thread(self._process_downloaded_sprite_all_sync, file_path, request)

    def _process_downloaded_sprite_all_sync(
        self, file_path: str, request: SpriteRequest
    ) -> List[str]:
        """Synchronous version of _process_downloaded_sprite_all."""
        try:
            from PIL import Image

            img = Image.open(file_path).convert("RGBA")

            is_sheet_request = len(request.poses) > 1
            results: List[str] = []

            if not is_sheet_request:
                blobs = self._extract_sprite_from_sheet(img, request, return_all=True)
                if blobs and isinstance(blobs, list):
                    for i, blob_img in enumerate(blobs):
                        if request.transparent_background:
                            extrema = blob_img.getextrema()
                            already_transparent = len(extrema) >= 4 and extrema[3][0] < 200
                            if not already_transparent:
                                blob_img = self._remove_white_background(blob_img)
                        processed_path = str(Path(file_path).with_suffix("")) + f"_blob{i}.png"
                        blob_img.save(processed_path, "PNG")
                        results.append(processed_path)
                    return results

            # Fallback: single-image processing
            single = self._process_downloaded_sprite_sync(file_path, request)
            return [single] if single else []
        except Exception as e:
            logger.error(f"Sprite multi-blob processing failed: {e}")
            return []

    def _process_downloaded_sprite_sync(
        self, file_path: str, request: SpriteRequest
    ) -> Optional[str]:
        """
        Post-process a downloaded sprite image.

        Strategy:
          1. Attempt smart extraction: detect individual sprite blobs on a white
             or transparent background and crop the best one.
          2. Preserve the natural image resolution — do NOT blindly resize to
             request.width × request.height; that destroys downloaded asset quality.
          3. Only upscale if the sprite is smaller than required AND art style
             is pixel_art (NEAREST so pixels stay crisp).
        """
        try:
            from PIL import Image

            img = Image.open(file_path).convert("RGBA")

            # Step 1: For single-sprite requests, try to extract one sprite from a
            # packed sheet. For spritesheet requests (poses > 1) we preserve the full
            # image — the downloaded file may already be a valid animation strip.
            is_sheet_request = len(request.poses) > 1
            if not is_sheet_request:
                extracted = self._extract_sprite_from_sheet(img, request)
                if extracted is not None:
                    img = extracted

            # Step 2: Strip white (or near-white) background when transparency requested.
            # Skip if the image already carries meaningful transparency — applying the
            # white-removal heuristic on top would corrupt light-coloured sprite parts.
            if request.transparent_background:
                extrema = img.getextrema()  # ((r_min,r_max), (g_min,g_max), (b_min,b_max), (a_min,a_max))
                already_transparent = len(extrema) >= 4 and extrema[3][0] < 200
                if not already_transparent:
                    img = self._remove_white_background(img)

            # Step 3: Smart resize — only upscale pixel art, never downscale downloaded quality
            nat_w, nat_h = img.size
            req_w = request.width
            req_h = request.height

            if (nat_w < req_w or nat_h < req_h) and request.style == SpriteStyle.PIXEL_ART:
                # Upscale small pixel art with NEAREST to preserve crisp pixels
                scale = max(req_w // max(nat_w, 1), req_h // max(nat_h, 1), 1)
                new_w = nat_w * scale
                new_h = nat_h * scale
                img = img.resize((new_w, new_h), Image.Resampling.NEAREST)
            # else: keep the natural resolution — it's already good quality

            processed_path = str(Path(file_path).with_suffix("")) + "_processed.png"
            img.save(processed_path, "PNG")
            return processed_path
        except Exception as e:
            logger.error(f"Sprite processing failed: {e}")
            return None

    @staticmethod
    def _remove_white_background(
        img: "Image.Image",
        threshold: int = 220,
        softness: int = 35,
    ) -> "Image.Image":
        """
        Removes a white or near-white background, replacing it with transparency.

        threshold:  pixels dimmer than this are kept fully opaque.
        softness:   transition band width above threshold (threshold+softness == 255
                    ensures pure-white pixels become fully transparent).
        Alpha fades OUT as brightness rises — bright pixels → more transparent.
        """
        img = img.convert("RGBA")
        data = img.getdata()
        new_data = []
        top = threshold + softness  # == 255 with the defaults above
        for r, g, b, a in data:
            brightness = (r + g + b) // 3
            if brightness >= top:
                new_data.append((r, g, b, 0))          # fully transparent
            elif brightness > threshold:
                ratio = (brightness - threshold) / softness   # 0 → 1
                new_a = int(a * (1.0 - ratio))          # fades to 0 as brightness rises
                new_data.append((r, g, b, new_a))
            else:
                new_data.append((r, g, b, a))           # unchanged
        img.putdata(new_data)
        return img

    @staticmethod
    def _extract_sprite_from_sheet(
        img: "Image.Image",
        request: "SpriteRequest",
        return_all: bool = False,
    ) -> "Optional[Union[Image.Image, List[Image.Image]]]":
        """
        Given a downloaded image that might be a packed sprite sheet, detect
        individual sprite blobs on a white/plain background.

        return_all=False (default): return the single best-matching blob crop,
            or None if the image is already a single sprite.
        return_all=True: return a list of all significant blob crops found,
            or None if no multi-blob sheet is detected.
        """
        import numpy as np

        img_rgba = img.convert("RGBA")
        arr = np.array(img_rgba)
        w, h = img_rgba.size

        # Nothing to do for very small images
        if w <= 128 and h <= 128:
            return None

        # Build a binary mask: True where pixels are NON-background
        # Background is white (r,g,b > 240) or already transparent (a < 10)
        r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
        is_white = (r > 240) & (g > 240) & (b > 240)
        is_transparent = a < 10
        background_mask = is_white | is_transparent
        content_mask = ~background_mask

        # If more than 70% of the image is content, it's probably a single sprite already
        content_ratio = content_mask.sum() / (w * h)
        if content_ratio > 0.70:
            return None

        # Connected-component labeling to find distinct blobs
        try:
            from scipy.ndimage import label as scipy_label
            labeled, num_features = scipy_label(content_mask)
        except ImportError:
            # Fallback: simple row/column scan to find the largest bounding box
            rows = np.any(content_mask, axis=1)
            cols = np.any(content_mask, axis=0)
            if not rows.any():
                return None
            r_min, r_max = np.where(rows)[0][[0, -1]]
            c_min, c_max = np.where(cols)[0][[0, -1]]
            pad = 4
            box = (
                max(0, c_min - pad), max(0, r_min - pad),
                min(w, c_max + pad + 1), min(h, r_max + pad + 1)
            )
            cropped = img_rgba.crop(box)
            return cropped

        if num_features < 2:
            # Single blob — use the full image
            return None

        # Score each blob: prefer largest area, penalise tiny noise
        center_x, center_y = w / 2, h / 2
        best_score = -1
        best_box = None

        for blob_id in range(1, num_features + 1):
            blob_mask = labeled == blob_id
            area = int(blob_mask.sum())
            if area < 64:  # skip tiny noise blobs
                continue

            rows_idx = np.where(np.any(blob_mask, axis=1))[0]
            cols_idx = np.where(np.any(blob_mask, axis=0))[0]
            if rows_idx.size == 0 or cols_idx.size == 0:
                continue
            r0, r1 = int(rows_idx[0]), int(rows_idx[-1])
            c0, c1 = int(cols_idx[0]), int(cols_idx[-1])

            bw = c1 - c0 + 1
            bh = r1 - r0 + 1

            # Aspect ratio score: closer to square → higher score
            aspect = min(bw, bh) / max(bw, bh, 1)

            # Centrality score: blobs closer to center win
            blob_cx = (c0 + c1) / 2
            blob_cy = (r0 + r1) / 2
            dist = ((blob_cx - center_x) ** 2 + (blob_cy - center_y) ** 2) ** 0.5
            max_dist = ((w / 2) ** 2 + (h / 2) ** 2) ** 0.5
            centrality = 1 - dist / max(max_dist, 1)

            score = area * 0.5 + aspect * 1000 + centrality * 500
            if score > best_score:
                best_score = score
                best_box = (c0, r0, c1 + 1, r1 + 1)

        if best_box is None:
            return None

        pad = max(4, int(min(w, h) * 0.02))

        # return_all: extract every significant blob as a separate crop
        if return_all:
            all_crops = []
            for blob_id in range(1, num_features + 1):
                blob_mask = labeled == blob_id
                area = int(blob_mask.sum())
                if area < 64:
                    continue
                rows_idx = np.where(np.any(blob_mask, axis=1))[0]
                cols_idx = np.where(np.any(blob_mask, axis=0))[0]
                if rows_idx.size == 0 or cols_idx.size == 0:
                    continue
                r0, r1 = int(rows_idx[0]), int(rows_idx[-1])
                c0, c1 = int(cols_idx[0]), int(cols_idx[-1])
                x0 = max(0, c0 - pad)
                y0 = max(0, r0 - pad)
                x1 = min(w, c1 + pad + 1)
                y1 = min(h, r1 + pad + 1)
                all_crops.append(img_rgba.crop((x0, y0, x1, y1)))
            logger.info(f"Extracted {len(all_crops)} sprite blob(s) from sheet ({w}×{h}).")
            return all_crops if all_crops else None

        # Default: return only the single best-scoring blob
        x0 = max(0, best_box[0] - pad)
        y0 = max(0, best_box[1] - pad)
        x1 = min(w, best_box[2] + pad)
        y1 = min(h, best_box[3] + pad)

        cropped = img_rgba.crop((x0, y0, x1, y1))
        logger.info(f"Extracted sprite blob ({x1-x0}×{y1-y0}) from sheet ({w}×{h}).")
        return cropped

    def _extract_sprites_from_zip(self, zip_path: str, output_dir: str, target_name: str = "", target_tags: List[str] = None) -> List[str]:

        """
        Extract image files from a ZIP archive.
        Returns list of extracted image paths, ranked by relevance to target_name.
        """
        extracted = []
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    lower = member.lower()
                    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                        # Skip macOS resource forks and hidden files
                        if "__MACOSX" in member or member.startswith("."):
                            continue
                        extracted_path = zf.extract(member, output_dir)
                        extracted.append(extracted_path)
        except Exception as e:
            logger.error(f"ZIP extraction failed: {e}")
            
        if not extracted or not target_name:
            return extracted
            
        # Rank extracted files by relevance to target_name and tags
        def rank_file(path_str):
            score = 0
            filename_lower = Path(path_str).name.lower()
            
            # Exact or partial name match
            if target_name.lower() in filename_lower:
                score += 10
            
            # Match tags
            if target_tags:
                for tag in target_tags:
                    if tag.lower() in filename_lower:
                        score += 5
            
            # Penalize generic UI/bullet/particle names if we're looking for a character/tile
            if "bullet" in filename_lower or "particle" in filename_lower or "ui" in filename_lower:
                score -= 5
                
            return score
            
        extracted.sort(key=rank_file, reverse=True)
        return extracted
