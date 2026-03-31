"""
Asset Cache — Local caching layer for downloaded and generated assets.

Avoids re-downloading or re-generating assets that have already been acquired.
Uses a simple JSON manifest alongside the cached files.
"""
import json
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from filelock import FileLock

logger = logging.getLogger(__name__)


class AssetCache:
    """
    Manages a local cache of downloaded/generated assets.
    
    Cache structure:
        {project_path}/.genesis_cache/
            manifest.json          — maps asset keys to cached file info
            sprites/               — cached sprite files
            audio/                 — cached audio files
    """

    CACHE_DIR_NAME = ".genesis_cache"

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.cache_dir = self.project_path / self.CACHE_DIR_NAME
        self.manifest_path = self.cache_dir / "manifest.json"
        self.lock_path = self.cache_dir / "manifest.lock"
        self._manifest: Dict[str, Any] = {}
        self._ensure_dirs()
        self._load_manifest()

    def _ensure_dirs(self):
        """Create cache directories if they don't exist."""
        (self.cache_dir / "sprites").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "audio").mkdir(parents=True, exist_ok=True)

    def _load_manifest(self):
        """Load the cache manifest from disk."""
        if self.manifest_path.exists():
            try:
                with FileLock(str(self.lock_path), timeout=5):
                    with open(self.manifest_path, "r") as f:
                        self._manifest = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load cache manifest: {e}")
                self._manifest = {}

    def _save_manifest(self):
        """Save the cache manifest to disk."""
        try:
            with FileLock(str(self.lock_path), timeout=5):
                with open(self.manifest_path, "w") as f:
                    json.dump(self._manifest, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save cache manifest: {e}")

    @staticmethod
    def _make_key(name: str, asset_type: str, **kwargs) -> str:
        """
        Create a deterministic cache key from an asset specification.
        
        Uses name + type + sorted extra params to produce a stable hash.
        """
        parts = [name, asset_type]
        for k in sorted(kwargs.keys()):
            parts.append(f"{k}={kwargs[k]}")
        raw = "|".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, name: str, asset_type: str, **kwargs) -> Optional[str]:
        """
        Check if an asset is cached. Returns the cached file path if hit, else None.
        """
        key = self._make_key(name, asset_type, **kwargs)
        entry = self._manifest.get(key)
        if entry:
            cached_path = Path(entry["path"])
            if cached_path.exists():
                logger.info(f"Cache HIT for '{name}' ({asset_type})")
                return str(cached_path)
            else:
                # Stale entry — file was deleted
                logger.info(f"Cache STALE for '{name}' — file missing, removing entry")
                del self._manifest[key]
                self._save_manifest()
        return None

    def put(self, name: str, asset_type: str, source_path: str, source: str = "unknown", **kwargs) -> str:
        """
        Add a file to the cache. Copies the file into the cache directory.
        
        Args:
            name: Asset name
            asset_type: "sprite", "spritesheet", "tileset", "audio_sfx", "audio_music"
            source_path: Path to the file to cache
            source: Origin of the asset (e.g., "opengameart", "generated")
            
        Returns:
            Path to the cached file
        """
        key = self._make_key(name, asset_type, **kwargs)
        source_file = Path(source_path)
        
        # Determine cache subdirectory
        if asset_type in ("audio_sfx", "audio_music"):
            sub_dir = self.cache_dir / "audio"
        else:
            sub_dir = self.cache_dir / "sprites"

        # Copy into cache with a unique name
        ext = source_file.suffix
        cached_filename = f"{name}_{key}{ext}"
        cached_path = sub_dir / cached_filename

        shutil.copy2(str(source_file), str(cached_path))

        self._manifest[key] = {
            "name": name,
            "type": asset_type,
            "path": str(cached_path),
            "source": source,
            "cached_at": datetime.now().isoformat(),
        }
        self._save_manifest()
        logger.info(f"Cached '{name}' ({asset_type}) → {cached_path}")
        return str(cached_path)

    def clear(self):
        """Clear the entire cache."""
        if self.cache_dir.exists():
            # Release lock context before removing the dir
            with FileLock(str(self.lock_path), timeout=5):
                shutil.rmtree(str(self.cache_dir))
        self._manifest = {}
        self._ensure_dirs()
        logger.info("Asset cache cleared.")
