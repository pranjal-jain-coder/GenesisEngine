"""
Interactive sprite-options pipeline runner.

This file intentionally replaces the old unit-style tests so it can be run as:

    python3 tests/test_asset_generator_unit.py --desc "..."

It goes through the same backend pipeline used by the plugin:
  AssetService.get_sprite_options(..., max_options=3)

Generated/downloaded options are persisted under:
  <project>/assets/sprites/<name>_opt0.png
  <project>/assets/sprites/<name>_opt1.png
  <project>/assets/sprites/<name>_opt2.png
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

# Make backend imports work whether this file is run from repo root or backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.asset_request import SpriteRequest, SpriteStyle
from services.asset_service import AssetService


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "sprite_option"


async def _run(args: argparse.Namespace) -> int:
    project_path = Path(args.project).resolve()
    project_path.mkdir(parents=True, exist_ok=True)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    style = SpriteStyle(args.style)
    name = args.name.strip() if args.name else _slugify(args.desc)[:40]

    print("\n=== Sprite Options Pipeline ===")
    print(f"Project:      {project_path}")
    print(f"Name:         {name}")
    print(f"Description:  {args.desc}")
    print(f"Style:        {style.value}")
    print(f"Size:         {args.width}x{args.height}")
    print(f"Tags:         {tags}")
    print(f"Transparent:  {args.transparent_background}")
    print(f"Options:      {args.max_options}")

    def log_callback(msg: str):
        print(f"[AssetService] {msg}")

    service = AssetService(str(project_path), log_callback=log_callback)
    request = SpriteRequest(
        name=name,
        description=args.desc,
        style=style,
        width=args.width,
        height=args.height,
        tags=tags,
        poses=["idle"],
        transparent_background=args.transparent_background,
    )

    results = await service.get_sprite_options(request, max_options=args.max_options)

    print("\n=== Results ===")
    if not results:
        print("No options were produced.")
        return 1

    for idx, result in enumerate(results):
        print(f"\nOption {idx}")
        print(f"  success:    {result.success}")
        print(f"  source:     {result.source}")
        print(f"  message:    {result.message}")
        print(f"  godot_path: {result.godot_path}")
        print(f"  file:       {result.asset_path}")
        if result.asset_path:
            path = Path(result.asset_path)
            print(f"  exists:     {path.exists()}")
            if path.exists():
                print(f"  bytes:      {path.stat().st_size}")

    sprite_dir = project_path / "assets" / "sprites"
    print(f"\nSaved under:  {sprite_dir}")
    print("Review files named *_opt0, *_opt1, *_opt2.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate 3 sprite options through the exact plugin asset pipeline."
    )
    parser.add_argument(
        "--desc",
        required=True,
        help="Sprite description prompt.",
    )
    parser.add_argument(
        "--name",
        default="",
        help="Base asset name. If omitted, generated from --desc.",
    )
    parser.add_argument(
        "--style",
        default="pixel_art",
        choices=["pixel_art", "flat", "cartoon", "hand_drawn"],
        help="Visual style.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=32,
        help="Sprite width in pixels.",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=32,
        help="Sprite height in pixels.",
    )
    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated tags.",
    )
    parser.add_argument(
        "--project",
        default="./test_outputs/pipeline_project",
        help="Project root where assets/ will be written.",
    )
    parser.add_argument(
        "--max-options",
        type=int,
        default=3,
        help="Number of options to generate/search for.",
    )
    parser.add_argument(
        "--transparent-background",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Request transparent background processing.",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    cli_args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(cli_args)))

