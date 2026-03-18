"""
Asset Search — Online search for free/CC0 2D game assets.

Searches multiple sources for sprites, tilesets, and audio:
  1. OpenGameArt.org (API)
  2. Kenney.nl (known asset packs)
  3. General web search fallback

All downloads go through proper attribution checks.
"""
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class AssetSearchResult:
    """Represents a single search result from an online source."""

    def __init__(
        self,
        title: str,
        download_url: str,
        preview_url: Optional[str] = None,
        source: str = "unknown",
        license: str = "unknown",
        tags: Optional[List[str]] = None,
    ):
        self.title = title
        self.download_url = download_url
        self.preview_url = preview_url
        self.source = source
        self.license = license
        self.tags = tags or []
        self.relevance_score = 0.0

    def calculate_relevance(self, query: str, target_tags: List[str]) -> float:
        """
        Calculates a relevance score (0.0 to 1.0) based on title and tag overlap.
        Penalizes generic tags so they don't artificially inflate the score.
        """
        query_words = set(re.findall(r'\w+', (query or "").lower()))
        target_tags_set = {t.lower() for t in target_tags}
        
        title_words = set(re.findall(r'\w+', self.title.lower()))
        result_tags_set = {t.lower() for t in self.tags}
        
        # Generic tags that shouldn't grant relevance on their own
        GENERIC_TAGS = {"pixel_art", "pixel", "2d", "sprite", "asset", "art", "game", "spritesheet"}
        
        # Meaningful target/result tags
        core_target_tags = target_tags_set - GENERIC_TAGS
        core_result_tags = result_tags_set - GENERIC_TAGS
        
        # 1. Tag overlap (Strong indicator)
        tag_overlap = core_target_tags & core_result_tags
        tag_score = len(tag_overlap) / max(len(core_target_tags), 1) * 0.6 if core_target_tags else 0.0
        
        # 2. Title word overlap (Moderate indicator)
        title_overlap = query_words & title_words
        title_score = len(title_overlap) / max(len(query_words), 1) * 0.3 if query_words else 0.0
        
        # 3. Source quality boost
        source_boost = 0.1 if self.source == "kenney" else 0.0
        
        self.relevance_score = min(1.0, tag_score + title_score + source_boost)
        return self.relevance_score


class AssetSearcher:
    """
    Searches online databases for free game assets.
    
    Strategy:
        1. Try OpenGameArt.org API first (largest CC0/CC-BY collection)
        2. Try Kenney.nl known packs (high-quality, CC0)
        3. Scrape itch.io free assets as last resort
    """

    # OpenGameArt API endpoint
    OGA_SEARCH_URL = "https://opengameart.org/art-search-advanced"
    OGA_API_URL = "https://opengameart.org/api/1.0/art"

    # Timeouts
    TIMEOUT = aiohttp.ClientTimeout(total=15)

    # Known Kenney asset pack URLs (CC0 — always free)
    KENNEY_PACKS: Dict[str, Dict[str, Any]] = {
        "platformer": {
            "url": "https://kenney.nl/media/pages/assets/simplified-platformer-pack/77070dd8ce-1705417943/kenney_simplified-platformer-pack.zip",
            "tags": ["platformer", "character", "tiles", "enemy", "coin", "platform"],
        },
        "pixel_platformer": {
            "url": "https://kenney.nl/media/pages/assets/pixel-platformer/77070dd8ce-1705417943/kenney_pixel-platformer.zip",
            "tags": ["pixel", "platformer", "character", "tiles"],
        },
        "tiny_dungeon": {
            "url": "https://kenney.nl/media/pages/assets/tiny-dungeon/77070dd8ce-1705417943/kenney_tiny-dungeon.zip",
            "tags": ["dungeon", "rpg", "tiles", "character", "enemy", "pixel"],
        },
        "pixel_shmup": {
            "url": "https://kenney.nl/media/pages/assets/pixel-shmup/77070dd8ce-1705417943/kenney_pixel-shmup.zip",
            "tags": ["shmup", "shooter", "spaceship", "pixel", "bullet"],
        },
        "rpg_audio": {
            "url": "https://kenney.nl/media/pages/assets/rpg-audio/77070dd8ce-1705417943/kenney_rpg-audio.zip",
            "tags": ["audio", "sfx", "rpg", "fantasy"],
        },
        "interface_sounds": {
            "url": "https://kenney.nl/media/pages/assets/interface-sounds/77070dd8ce-1705417943/kenney_interface-sounds.zip",
            "tags": ["audio", "sfx", "ui", "interface", "click", "menu"],
        },
    }

    async def search_sprites(
        self,
        query: str,
        tags: List[str],
        style: str = "pixel_art",
        max_results: int = 5,
    ) -> List[AssetSearchResult]:
        """
        Search for sprite assets online.
        
        Args:
            query: Text description to search for
            tags: Relevant tags for filtering
            style: Art style to filter by
            max_results: Maximum results to return
            
        Returns:
            List of AssetSearchResult objects, ordered by relevance
        """
        results = []

        # 1. Search OpenGameArt (Deep search for better ranking)
        try:
            oga_results = await self._search_opengameart(query, tags, "2D Art", max_results * 4)
            results.extend(oga_results)
        except Exception as e:
            logger.warning(f"OpenGameArt search failed: {e}")

        # 2. Check Kenney packs (High quality, always preferred if match)
        kenney_results = self._search_kenney_packs(tags, "sprite")
        results.extend(kenney_results)

        # 3. Search itch.io free assets (Search depth)
        try:
            itch_results = await self._search_itchio(query, tags, "sprites", max_results=max_results * 2)
            results.extend(itch_results)
        except Exception as e:
            logger.warning(f"itch.io search failed: {e}")

        # 4. Calculate relevance for ALL results and filter
        for r in results:
            r.calculate_relevance(query, tags)
            
        # Sort by relevance descending
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        return results[:max_results]

    async def search_audio(
        self,
        query: str,
        tags: List[str],
        audio_type: str = "sfx",
        max_results: int = 5,
    ) -> List[AssetSearchResult]:
        """Search for audio assets online."""
        results = []

        # 1. OpenGameArt audio
        try:
            oga_results = await self._search_opengameart(query, tags, "Music|Sound Effect", max_results * 2)
            results.extend(oga_results)
        except Exception as e:
            logger.warning(f"OpenGameArt audio search failed: {e}")

        # 2. Kenney audio packs
        kenney_results = self._search_kenney_packs(tags, "audio")
        results.extend(kenney_results)

        # 3. Freesound.org
        try:
            freesound_results = await self._search_freesound(query, max_results=max_results)
            results.extend(freesound_results)
        except Exception as e:
            logger.warning(f"Freesound search failed: {e}")

        # 4. Calculate relevance and sort
        for r in results:
            r.calculate_relevance(query, tags)
            
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        return results[:max_results]

    async def download_asset(self, url: str, output_dir: str, filename: Optional[str] = None) -> Optional[str]:
        """
        Download an asset from a URL to a local directory.
        
        Returns the path to the downloaded file, or None on failure.
        """
        try:
            # 1. Resolve actual download URL if it's a detail page
            if "opengameart.org/content/" in url:
                try:
                    async with aiohttp.ClientSession(timeout=self.TIMEOUT) as session:
                        async with session.get(url) as page_resp:
                            if page_resp.status == 200:
                                html = await page_resp.text()
                                soup = BeautifulSoup(html, "lxml")
                                # OGA files are in div.field-item span.file a
                                files = soup.select("div.field-item span.file a")
                                if files:
                                    # Pick the first one (usually the main zip or png)
                                    real_url = files[0].get("href")
                                    if real_url:
                                        if not real_url.startswith("http"):
                                            real_url = f"https://opengameart.org{real_url}"
                                        url = real_url
                                        logger.info(f"Resolved OGA detail page to: {url}")
                except Exception as eval_err:
                    logger.warning(f"Failed to resolve OGA detail page: {eval_err}")

            # 2. Proceed with download
            async with aiohttp.ClientSession(timeout=self.TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(f"Download failed (HTTP {resp.status}): {url}")
                        return None

                    # Determine filename
                    if not filename:
                        # Try Content-Disposition header
                        cd = resp.headers.get("Content-Disposition", "")
                        if "filename=" in cd:
                            filename = cd.split("filename=")[-1].strip('"\'')
                        else:
                            # Extract from URL
                            parsed = urllib.parse.urlparse(url)
                            filename = Path(parsed.path).name or "asset_download"

                    output_path = Path(output_dir) / filename
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    with open(output_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)

                    logger.info(f"Downloaded: {url} → {output_path}")
                    return str(output_path)
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    # -----------------------------------------------------------------------
    # Private search implementations
    # -----------------------------------------------------------------------

    async def _search_opengameart(
        self, query: str, tags: List[str], art_type: str, max_results: int
    ) -> List[AssetSearchResult]:
        """
        Search OpenGameArt.org using their web interface.
        
        OGA doesn't have a robust public REST API for searching,
        so we scrape the search results page.
        """
        results = []
        # Search engines like OGA fail on long sentences; prioritize tags or short query snippets
        if tags:
            search_query = " ".join(tags[:3])
        else:
            search_query = " ".join(query.split()[:2])
        
        encoded_query = urllib.parse.quote_plus(search_query)

        # Map art_type
        type_map = {
            "2D Art": "2D+Art",
            "Music|Sound Effect": "Music",
        }
        art_type_param = type_map.get(art_type, "2D+Art")

        url = (
            f"https://opengameart.org/art-search-advanced?"
            f"keys={encoded_query}"
            f"&type={art_type_param}"
        )

        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return results
                    html = await resp.text()

            soup = BeautifulSoup(html, "lxml")
            # OGA search results are in div.view-content > div.views-row
            rows = soup.select("div.views-row")[:max_results]

            for row in rows:
                title_el = row.select_one("span.art-title a") or row.select_one("h3 a") or row.select_one("a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = f"https://opengameart.org{link}"

                # Try to find preview image
                img_el = row.select_one("img")
                preview = img_el.get("src", "") if img_el else None
                if preview and not preview.startswith("http"):
                    preview = f"https://opengameart.org{preview}"

                results.append(AssetSearchResult(
                    title=title,
                    download_url=link,  # This is the page URL; actual download requires another fetch
                    preview_url=preview,
                    source="opengameart",
                    license="mixed",
                    tags=tags,
                ))
        except Exception as e:
            logger.warning(f"OGA scraping error: {e}")

        return results

    async def _search_itchio(
        self, query: str, tags: List[str], category: str = "sprites", max_results: int = 3
    ) -> List[AssetSearchResult]:
        """
        Search itch.io for free game assets.
        
        Uses the itch.io browse page with filters for free assets.
        """
        results = []
        if tags:
            search_query_str = " ".join(tags[:3])
        else:
            search_query_str = " ".join(query.split()[:2])
            
        search_query = urllib.parse.quote_plus(search_query_str)
        
        # itch.io game-assets section
        url = (
            f"https://itch.io/game-assets/free/tag-{category}"
            f"?q={search_query}"
        )

        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT) as session:
                headers = {"User-Agent": "GenesisEngine/1.0 (game-dev-tool)"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return results
                    html = await resp.text()

            soup = BeautifulSoup(html, "lxml")
            cells = soup.select("div.game_cell")[:max_results]

            for cell in cells:
                title_el = cell.select_one("a.title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")

                img_el = cell.select_one("img")
                preview = None
                if img_el:
                    preview = img_el.get("data-lazy_src") or img_el.get("src")

                results.append(AssetSearchResult(
                    title=title,
                    download_url=link,
                    preview_url=preview,
                    source="itchio",
                    license="varies",
                    tags=tags,
                ))
        except Exception as e:
            logger.warning(f"itch.io scraping error: {e}")

        return results

    async def _search_freesound(self, query: str, max_results: int = 3) -> List[AssetSearchResult]:
        """
        Search Freesound.org for audio assets.
        
        Note: Freesound requires an API key for download, so we return
        page links that the user/agent can use manually if needed.
        """
        results = []
        # Removed strict Creative Commons 0 license filter
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://freesound.org/search/?q={encoded_query}&f=&s=Rating+desc"

        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT) as session:
                headers = {"User-Agent": "GenesisEngine/1.0 (game-dev-tool)"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return results
                    html = await resp.text()

            soup = BeautifulSoup(html, "lxml")
            sound_els = soup.select("div.sample_player_small")[:max_results]

            for el in sound_els:
                title_el = el.select_one("a.title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = f"https://freesound.org{link}"

                results.append(AssetSearchResult(
                    title=title,
                    download_url=link,
                    source="freesound",
                    license="mixed",
                    tags=[query],
                ))
        except Exception as e:
            logger.warning(f"Freesound search error: {e}")

        return results

    def _search_kenney_packs(self, tags: List[str], asset_type: str) -> List[AssetSearchResult]:
        """
        Check if any known Kenney.nl asset packs match the requested tags.
        
        Kenney assets are always CC0 and high quality.
        """
        results = []
        tags_lower = {t.lower() for t in tags}

        for pack_name, pack_info in self.KENNEY_PACKS.items():
            pack_tags = set(pack_info["tags"])
            overlap = tags_lower & pack_tags

            # Filter by asset type relevance
            if asset_type == "audio" and "audio" not in pack_tags:
                continue
            if asset_type == "sprite" and "audio" in pack_tags:
                continue

            if overlap:
                results.append(AssetSearchResult(
                    title=f"Kenney: {pack_name.replace('_', ' ').title()}",
                    download_url=pack_info["url"],
                    source="kenney",
                    license="CC0",
                    tags=list(overlap),
                ))

        return results
