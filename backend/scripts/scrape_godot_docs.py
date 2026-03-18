"""
Godot 4 Documentation Scraper
Fetches targeted API documentation from the official Godot 4.3 docs and converts it to Markdown
for use in the RAG system. Focuses on high-value classes to avoid bloat.
"""
import requests
from bs4 import BeautifulSoup
import re
from pathlib import Path
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Base URL for Godot 4.3 Documentation
BASE_URL = "https://docs.godotengine.org/en/stable/classes/"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "godot_docs"

# Targeted High-Value Classes (Case-insensitive for URL construction)
TARGET_CLASSES = [
    # Core & Math
    "@GlobalScope", "Object", "Node", "Resource", "Ref", "Vector2", "Vector3", "Color", "Rect2",
    "Math", "RandomNumberGenerator", "Time", "FileAccess", "DirAccess", "Input", "InputEvent",

    # 2D Engine
    "Node2D", "CanvasItem", "Sprite2D", "AnimatedSprite2D", "Camera2D", "Marker2D", "Path2D", "PathFollow2D",
    "Line2D", "Polygon2D", "RemoteTransform2D", "VisibleOnScreenNotifier2D",

    # Physics 2D
    "CollisionObject2D", "Area2D", "PhysicsBody2D", "StaticBody2D", "AnimatableBody2D", 
    "RigidBody2D", "CharacterBody2D", "CollisionShape2D", "CollisionPolygon2D", "RayCast2D", "ShapeCast2D",

    # UI Controls
    "Control", "CanvasLayer", "Container", "BoxContainer", "HBoxContainer", "VBoxContainer", 
    "GridContainer", "CenterContainer", "MarginContainer", "PanelContainer", "ScrollContainer", "AspectRatioContainer",
    "Label", "Button", "TextureButton", "LinkButton", "CheckButton", "CheckBox", "OptionButton", "MenuButton",
    "TextureRect", "ColorRect", "NinePatchRect", "ReferenceRect",
    "ProgressBar", "TextureProgressBar", "Range", "SpinBox", "HSlider", "VSlider",
    "TextEdit", "LineEdit", "RichTextLabel", "Tree", "ItemList",
    "Popup", "Window", "AcceptDialog", "ConfirmationDialog", "FileDialog",

    # Animation & Audio
    "AnimationPlayer", "AnimationTree", "Tween", "AudioStreamPlayer", "AudioStreamPlayer2D",

    # Scene Management
    "SceneTree", "PackedScene", "tscn",  # General concepts rather than just classes
    
    # TileMaps
    "TileMap", "TileMapLayer", "TileSet",
]

def get_class_url(class_name):
    """Constructs the URL for a given class name."""
    # Special handling for @GlobalScope
    if class_name.startswith("@"):
        slug = f"class_{class_name.lower().replace('@', '')}"
    else:
        slug = f"class_{class_name.lower()}"
    return f"{BASE_URL}{slug}.html"

def html_to_markdown(soup):
    """Converts the parsed HTML soup into clean Markdown."""
    markdown = []

    # Title / Class Name
    title = soup.find('h1')
    if title:
        class_name = title.text.strip()
        markdown.append(f"# {class_name}\n")
    
    # Description (The text immediately following the title but before properties/methods)
    # This usually resides in the first few paragraphs or a <p> tag right after the header block.
    # In Godot docs, it's often under the "Description" header, or implicitly at the top.
    
    # We will look for the "Description" section specifically.
    desc_header = soup.find('section', id='description')
    if desc_header:
        markdown.append("## Description\n")
        for p in desc_header.find_all('p', recursive=False):
            markdown.append(p.get_text().strip() + "\n")
        markdown.append("") # Newline

    # Properties Summary
    props_table = soup.find('section', id='properties')
    if props_table:
        markdown.append("## Properties\n")
        # Extract rows from table
        rows = props_table.find_all('tr')
        if rows:
            markdown.append("| Type | Name | Default |")
            markdown.append("| --- | --- | --- |")
            for row in rows[1:]: # Skip header
                cols = row.find_all('td')
                if len(cols) >= 3:
                    type_text = cols[0].get_text(strip=True)
                    name_text = cols[1].get_text(strip=True)
                    default_text = cols[2].get_text(strip=True)
                    markdown.append(f"| {type_text} | `{name_text}` | {default_text} |")
        markdown.append("\n")

    # Methods Summary (Only public methods)
    methods_table = soup.find('section', id='methods')
    if methods_table:
        markdown.append("## Methods\n")
        rows = methods_table.find_all('tr')
        if rows:
             markdown.append("| Return | Name |")
             markdown.append("| --- | --- |")
             for row in rows[1:]:
                 cols = row.find_all('td')
                 if len(cols) >= 2:
                     return_type = cols[0].get_text(strip=True)
                     # The method signature is usually in the second column
                     method_sig = cols[1].get_text(strip=True)
                     # Clean up signature (remove newlines/excess spaces)
                     method_sig = re.sub(r'\s+', ' ', method_sig).strip()
                     markdown.append(f"| {return_type} | `{method_sig}` |")
        markdown.append("\n")

    # Signals
    signals_section = soup.find('section', id='signals')
    if signals_section:
        markdown.append("## Signals\n")
        # Signals are usually listed as dl/dt/dd definitions or similar list items
        # In Godot docs HTML structure, they are often <dl class="classref-signal"> or similar.
        # Let's target the individual signal entries.
        # They often appear as id="signal-signalname"
        
        # We'll just grab the list of signal definitions if possible.
        # Iterate over all elements with id starting with 'signal-'
        signals = signals_section.find_all(id=re.compile(r'^signal-'))
        for sig in signals:
            # The signal name is usually in a <dt> or <p> nearby or the element itself
            # We want the text representation e.g. "body_entered ( Node body )"
            sig_text = sig.get_text(strip=True)
            # Remove "¶" symbol which is common in docs anchors
            sig_text = sig_text.replace('¶', '')
            markdown.append(f"- `{sig_text}`")
            
            # Try to find description (usually following dd/p)
            # This is tricky with inconsistent HTML, keeping it simple: just list names/sigs
            markdown.append("")
        markdown.append("\n")

    # Detailed Descriptions (Properties & Methods) - OPTIONAL
    # For RAG, summaries are often better than full verbose text. 
    # But let's add Property Descriptions if they exist, as they explain WHAT the property does.
    
    # We will skip valid detailed property/method descriptions to keep token count low for now, 
    # unless the summaries are insufficient. The summary tables above capture 80% of value.
    
    return "\n".join(markdown)

def scrape_class(class_name):
    url = get_class_url(class_name)
    logger.info(f"Fetching {class_name} from {url}...")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            md_content = html_to_markdown(soup)
            
            # Save to file
            filename = f"godot_api_{class_name.lower().replace('@', '')}.md"
            filepath = OUTPUT_DIR / filename
            filepath.write_text(md_content, encoding="utf-8")
            logger.info(f"Saved {filepath}")
        else:
            logger.warning(f"Failed to fetch {class_name}: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Error scraping {class_name}: {e}")

def main():
    logger.info("Starting Godot 4 Docs Scraper...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    for cls in TARGET_CLASSES:
        scrape_class(cls)
        # Be polite to the server
        time.sleep(0.5)
        
    logger.info("Scraping complete.")

if __name__ == "__main__":
    main()
