#!/usr/bin/env python3
"""
Integration test for instance_scene  –  no LLM required.

WHAT IT CHECKS
==============
Mirrors the exact workflow the AI uses:
  create_scene(main) → create_scene(sub) → add_node×2 → save_scene(sub)
  → open_scene(main) → instance_scene(sub) → save_scene(main)

The saved main .tscn must contain only a single
[node … instance=ExtResource(…)] line for the sub-scene root.

ROOT CAUSE OF THE BUG
=====================
_cmd_instance_scene calls _set_owner_recursive(instance, edited_scene),
which sets owner=main_scene_root on every child of the instance.
PackedScene.pack() then serialises those children as local nodes:

    [node name="Visuals" type="Sprite2D" parent="CharacterBody2D"]  ← BUG

That produces "Load Error: name clashes" the next time Godot opens the file.

WHY THE SAVE BEFORE open_scene MATTERS
=======================================
_cmd_create_scene does NOT auto-save the currently open scene before
switching.  If save_scene is omitted after building the sub-scene, the
sub-scene has no children on disk when instance_scene calls load().
The instance is empty → nothing to duplicate → test trivially passes
without ever exercising the bug.

HOW TO RUN
==========
  1. Stop the main backend (main.py) — it also listens on port 8000.
  2. Open Godot with the genesis_bridge plugin active.
     The bridge auto-reconnects; it will find this test server.
  3.  cd backend && python tests/test_instance_scene_integration.py

Exit code 0 = PASS, exit code 1 = FAIL or error.
"""

import asyncio
import json
import re
import sys
import uuid
from pathlib import Path

import websockets

# Allow imports from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.studio.tools import GodotInterface

# ── Config ────────────────────────────────────────────────────────────────────

HOST = "127.0.0.1"
PORT = 8000
CONNECT_TIMEOUT = 60  # seconds to wait for Godot to connect
TEST_TIMEOUT = 180    # seconds to wait for the test run after connect

TEMP_SUB  = "res://test_instance_scene_sub.tscn"
TEMP_MAIN = "res://test_instance_scene_main.tscn"


# ── Minimal ConnectionManager replacement ────────────────────────────────────

class DirectBridge:
    """
    Drop-in for ConnectionManager using a raw websockets connection.
    Sequential: sends a command then reads until the matching reply arrives.
    """

    def __init__(self, ws):
        self._ws = ws

    def stop(self):
        pass

    async def send_command(self, _project_path: str, payload: dict, timeout: float = 60.0) -> dict:
        cmd_id = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", **payload, "id": cmd_id}
        await self._ws.send(json.dumps(payload))
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return {"success": False, "message": f"Command timed out after {timeout}s"}
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                return {"success": False, "message": f"Command timed out after {timeout}s"}
            msg = json.loads(raw)
            if msg.get("id") != cmd_id:
                continue  # stray message, keep waiting
            if "result" in msg:
                return msg["result"]
            if "error" in msg:
                return {"success": False, "message": msg["error"].get("message", "Unknown error")}
            return {"success": False, "message": "Malformed response"}


# ── .tscn assertion ───────────────────────────────────────────────────────────

def find_duplicate_child_entries(tscn_content: str, sub_scene_res_path: str):
    """
    Parse a saved .tscn and return any [node …] entries whose parent matches
    the instance root and that are NOT themselves instance declarations.

    A non-empty list means bridge_client._clear_children_owner failed and
    the sub-scene's children were serialised as local overrides (the bug).

    Returns (duplicates: list[str], instance_name: str).
    """
    # 1. Find the ext_resource id that refers to sub_scene_res_path
    m = re.search(
        r'\[ext_resource[^\]]*path="' + re.escape(sub_scene_res_path) + r'"[^\]]*id="([^"]+)"',
        tscn_content,
    )
    if not m:
        raise ValueError(
            f"ext_resource for '{sub_scene_res_path}' not found in .tscn.\n"
            "instance_scene may have failed silently."
        )
    ext_id = m.group(1)

    # 2. Find the [node …] line that is the instance root
    m = re.search(
        r'\[node name="([^"]+)"[^\]]*instance=ExtResource\("' + re.escape(ext_id) + r'"\)',
        tscn_content,
    )
    if not m:
        raise ValueError(
            f"No [node … instance=ExtResource(\"{ext_id}\")] found in .tscn."
        )
    instance_name = m.group(1)

    # 3. Any [node …] entry with parent="<instance_name>" or "instance_name/…"
    #    that does NOT have instance= is a local-override duplicate.
    all_nodes = re.findall(r'\[node [^\]]+\]', tscn_content)
    duplicates = [
        n for n in all_nodes
        if (
            f'parent="{instance_name}"' in n or
            f'parent="{instance_name}/' in n
        ) and "instance=" not in n
    ]
    return duplicates, instance_name


# ── Test sequence ─────────────────────────────────────────────────────────────

async def run_test(bridge: DirectBridge, project_path: str) -> bool:
    iface = GodotInterface(bridge)
    passed = True

    def step(n, msg):
        print(f"    [{n}/6] {msg}")

    try:
        # ── 1. Create the main scene (empty, just establishes the file) ────
        step(1, f"create_scene {TEMP_MAIN}  (root=Node2D, empty)")
        r = await iface.create_scene(project_path, TEMP_MAIN, "Node2D")
        if "Failed" in r or "Error" in r:
            raise RuntimeError(f"create_scene(main) → {r}")

        # ── 2. Build the sub-scene with children ───────────────────────────
        step(2, f"create_scene {TEMP_SUB}  (root=CharacterBody2D, children=Visuals+Collision)")
        r = await iface.create_scene(project_path, TEMP_SUB, "CharacterBody2D")
        if "Failed" in r or "Error" in r:
            raise RuntimeError(f"create_scene(sub) → {r}")

        r = await iface.add_node(project_path, ".", "Sprite2D", "Visuals")
        if "Failed" in r or "Error" in r:
            raise RuntimeError(f"add_node(Visuals) → {r}")

        r = await iface.add_node(project_path, ".", "CollisionShape2D", "Collision")
        if "Failed" in r or "Error" in r:
            raise RuntimeError(f"add_node(Collision) → {r}")

        # ── 3. Save sub-scene explicitly ───────────────────────────────────
        # Critical: the AI always saves before switching scenes.
        # Without this, the sub-scene has no children on disk and
        # instance_scene loads an empty scene — the bug never triggers.
        step(3, f"save_scene  ({TEMP_SUB} with its children)")
        r = await iface.save_scene(project_path)
        if "Failed" in r or "Error" in r:
            raise RuntimeError(f"save_scene(sub) → {r}")

        # ── 4. Switch to the main scene (open_scene, like the AI does) ─────
        step(4, f"open_scene {TEMP_MAIN}")
        r = await iface.open_scene(project_path, TEMP_MAIN)
        if "Failed" in r or "Error" in r:
            raise RuntimeError(f"open_scene(main) → {r}")

        # ── 5. Instance the sub-scene ──────────────────────────────────────
        step(5, f"instance_scene {TEMP_SUB}  parent='.'")
        r = await iface.instance_scene(project_path, TEMP_SUB, ".")
        if "Failed" in r or "Error" in r:
            raise RuntimeError(f"instance_scene → {r}")

        # ── 6. Save and inspect ────────────────────────────────────────────
        step(6, "save_scene")
        r = await iface.save_scene(project_path)
        if "Failed" in r or "Error" in r:
            raise RuntimeError(f"save_scene(main) → {r}")

        step(6, f"parsing {TEMP_MAIN} for duplicate [node] entries …")
        disk_path = Path(project_path) / TEMP_MAIN.replace("res://", "")
        if not disk_path.exists():
            raise FileNotFoundError(f"Expected file not found: {disk_path}")

        content = disk_path.read_text()
        dupes, instance_name = find_duplicate_child_entries(content, TEMP_SUB)

        if dupes:
            passed = False
            print(f"\n  ✗  FAIL  — instance root: '{instance_name}'")
            print(f"     {len(dupes)} child node(s) were incorrectly serialised as local overrides:\n")
            for d in dupes:
                print(f"       {d}")
            print()
            print("     These entries belong inside the sub-scene's own .tscn file.")
            print("     Their presence here causes 'Load Error: name clashes' on next open.")
            print("     Root cause: _clear_children_owner / _prepare_scene_for_saving")
            print("     in bridge_client.gd did not clear the ownership chain before pack().")
        else:
            print(f"\n  ✓  PASS  — no duplicate child nodes under '{instance_name}' in {TEMP_MAIN}\n")

    except Exception as exc:
        print(f"\n  ✗  ERROR  — {exc}\n")
        passed = False

    finally:
        try:
            print("    Final save_scene …")
            r = await iface.save_scene(project_path)
            if "Failed" in r or "Error" in r:
                print(f"    Warning: final save_scene reported: {r}")
        except Exception as exc:
            print(f"    Warning: final save_scene failed: {exc}")

    return passed


# ── WebSocket server ──────────────────────────────────────────────────────────

async def main():
    result_future: asyncio.Future = asyncio.get_event_loop().create_future()
    connected_future: asyncio.Future = asyncio.get_event_loop().create_future()

    async def handle_godot(ws):
        # Registration handshake
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
        except asyncio.TimeoutError:
            print("  No registration message received within 10 s.")
            if not result_future.done():
                result_future.set_result(False)
            return

        msg = json.loads(raw)
        if msg.get("type") != "register" or not msg.get("project_path"):
            print(f"  Unexpected message (expected register): {msg}")
            if not result_future.done():
                result_future.set_result(False)
            return

        project_path = msg["project_path"]
        print(f"  Godot connected  →  project: {project_path}\n")
        if not connected_future.done():
            connected_future.set_result(True)

        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "result": {"status": "connected", "path": project_path},
        }))

        bridge = DirectBridge(ws)
        try:
            passed = await run_test(bridge, project_path)
        finally:
            bridge.stop()

        if not result_future.done():
            result_future.set_result(passed)

    print("─" * 60)
    print("  instance_scene  integration test")
    print("─" * 60)
    print(f"  Server: ws://{HOST}:{PORT}")
    print(f"  Waiting up to {CONNECT_TIMEOUT}s for Godot to connect …")
    print("  (The main backend must be stopped; Godot will auto-reconnect here.)\n")

    async with websockets.serve(handle_godot, HOST, PORT):
        try:
            await asyncio.wait_for(connected_future, timeout=CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            print(f"\n  TIMEOUT: Godot did not connect within {CONNECT_TIMEOUT}s.")
            print("  Ensure the main backend is stopped and Godot is open.\n")
            sys.exit(1)

        try:
            passed = await asyncio.wait_for(result_future, timeout=TEST_TIMEOUT)
        except asyncio.TimeoutError:
            print(f"\n  TIMEOUT: Test did not finish within {TEST_TIMEOUT}s after Godot connected.")
            print("  Check Godot/plugin logs for a stuck command or increase TEST_TIMEOUT.\n")
            sys.exit(1)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
