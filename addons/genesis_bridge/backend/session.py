"""
Session Management for Genesis Engine Orchestrator.
"""
from typing import Dict
from fastapi import WebSocket
import logging
import json
import asyncio
import uuid

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}

    async def register(self, project_path: str, websocket: WebSocket):
        """Registers a verified connection."""
        if project_path in self.active_connections:
            logger.warning(f"Project {project_path} re-connecting. Closing old connection.")
            await self.disconnect(project_path)
        
        self.active_connections[project_path] = websocket
        logger.info(f"Registered project: {project_path}. Active count: {len(self.active_connections)}")

    async def disconnect(self, project_path: str):
        """Removes the connection."""
        if project_path in self.active_connections:
            del self.active_connections[project_path]
            logger.info(f"Project disconnected: {project_path}")

    async def send_command(self, project_path: str, command_dict: dict, timeout: float = 30.0) -> dict:
        """Sends a JSON-RPC command, waits for response via future."""
        if project_path not in self.active_connections:
            return {"success": False, "message": "Project not connected"}
        
        cmd_id = command_dict.get("id", str(uuid.uuid4()))
        command_dict["id"] = cmd_id
        
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_requests[cmd_id] = future
        
        websocket = self.active_connections[project_path]
        try:
            await websocket.send_text(json.dumps(command_dict))
            
            try:
                response = await asyncio.wait_for(future, timeout=timeout)
                return response
            except asyncio.TimeoutError:
                if cmd_id in self.pending_requests:
                    del self.pending_requests[cmd_id]
                return {"success": False, "message": "Command timed out"}
        except Exception as e:
            logger.error(f"Send failed: {e}")
            if cmd_id in self.pending_requests:
                del self.pending_requests[cmd_id]
            await self.disconnect(project_path)
            return {"success": False, "message": str(e)}

    async def incoming_response(self, response_dict: dict):
        """Resolves a pending request future if the ID matches."""
        cmd_id = response_dict.get("id")
        if cmd_id and cmd_id in self.pending_requests:
            future = self.pending_requests[cmd_id]
            if not future.done():
                if "result" in response_dict:
                    future.set_result(response_dict["result"])
                elif "error" in response_dict:
                    # Coerce error into a failed result object to match signature expected by GodotInterface
                    future.set_result({"success": False, "message": response_dict["error"].get("message", "Unknown error")})
                else:
                    future.set_result(response_dict)
            del self.pending_requests[cmd_id]

    def get_connected_projects(self) -> list[str]:
        return list(self.active_connections.keys())

    def is_connected(self, project_path: str) -> bool:
        return project_path in self.active_connections