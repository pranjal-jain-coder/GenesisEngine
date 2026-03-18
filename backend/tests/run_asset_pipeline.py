import asyncio
import argparse
import sys
from pathlib import Path

# Add the backend directory to sys.path so we can import modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.asset_service import AssetService
from models.asset_request import (
    SpriteRequest, SpriteStyle, TilesetRequest, BackgroundRequest, AudioRequest
)

async def main():
    parser = argparse.ArgumentParser(description="End-to-End Asset Pipeline Tester")
    parser.add_argument("--type", choices=["sprite", "spritesheet", "tileset", "background", "audio"], required=True, help="Type of asset to get")
    parser.add_argument("--name", type=str, required=True, help="Name of the asset")
    parser.add_argument("--desc", type=str, required=True, help="Description of the asset")
    parser.add_argument("--tags", type=str, default="", help="Comma-separated tags")
    parser.add_argument("--style", type=str, default="pixel_art", choices=["pixel_art", "flat", "cartoon", "hand_drawn"], help="Art style")
    parser.add_argument("--width", type=int, default=None, help="Width in pixels (uses model default if missing)")
    parser.add_argument("--height", type=int, default=None, help="Height in pixels (uses model default if missing)")
    parser.add_argument("--poses", type=str, default="idle", help="Comma-separated poses (for spritesheets)")
    parser.add_argument("--project", type=str, default="/tmp/genesis_test_project", help="Path to dummy project")

    args = parser.parse_args()

    # Create dummy project dir if missing
    project_path = Path(args.project)
    project_path.mkdir(parents=True, exist_ok=True)

    print("\n--- Testing Asset Pipeline ---")
    print(f"Project Path: {project_path}")
    print(f"Asset Type:   {args.type}")
    print(f"Name:         {args.name}")
    print(f"Description:  {args.desc}")
    print(f"Tags:         {args.tags}")

    # Initialize AssetService
    def log_callback(msg):
        print(f"[AssetService Log]: {msg}")

    service = AssetService(str(project_path), log_callback=log_callback)

    tags_list = [t.strip() for t in args.tags.split(",") if t.strip()]
    poses_list = [p.strip() for p in args.poses.split(",") if p.strip()]

    style_enum = SpriteStyle(args.style)

    result = None

    if args.type == "sprite":
        # Prepare request arguments, filtering out None to use Pydantic defaults
        req_args = {
            "name": args.name,
            "description": args.desc,
            "style": style_enum,
            "tags": tags_list,
            "poses": ["idle"]
        }
        if args.width:
            req_args["width"] = args.width
        if args.height:
            req_args["height"] = args.height
        
        req = SpriteRequest(**req_args)
        result = await service.get_sprite(req)

    elif args.type == "spritesheet":
        req = SpriteRequest(
            name=args.name,
            description=args.desc,
            style=style_enum,
            width=args.width,
            height=args.height,
            tags=tags_list,
            poses=poses_list
        )
        result = await service.get_sprite(req)

    elif args.type == "tileset":
        tile_size = args.width if args.width else 128
        req = TilesetRequest(
            name=args.name,
            description=args.desc,
            style=style_enum,
            tile_size=tile_size,
            columns=4,
            rows=4,
            tile_types=["ground", "wall"],
            tags=tags_list
        )
        result = await service.get_tileset(req)

    elif args.type == "background":
        req_args = {
            "name": args.name,
            "description": args.desc,
            "style": style_enum,
            "tags": tags_list,
        }
        if args.width:
            req_args["width"] = args.width
        if args.height:
            req_args["height"] = args.height
        
        req = BackgroundRequest(**req_args)
        result = await service.get_background(req)

    elif args.type == "audio":
        req = AudioRequest(
            name=args.name,
            description=args.desc,
            audio_type="sfx",
            duration_seconds=0.5,
            tags=tags_list
        )
        result = await service.get_audio(req)

    print("\n--- Result ---")
    if result:
        print(f"Success:     {result.success}")
        print(f"Source:      {result.source}")
        print(f"Message:     {result.message}")
        print(f"Godot Path:  {result.godot_path}")
        print(f"Actual Path: {result.asset_path}")
        if result.success and result.asset_path:
            p = Path(result.asset_path)
            if p.exists():
                print(f"File Exists: Yes ({p.stat().st_size} bytes)")
            else:
                print("File Exists: No - ERROR")
    else:
        print("No result returned.")

if __name__ == "__main__":
    asyncio.run(main())
