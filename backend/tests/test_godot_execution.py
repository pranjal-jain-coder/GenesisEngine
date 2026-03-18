import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from agents.studio.tools import GodotInterface

@pytest.mark.asyncio
async def test_execute_godot_script_routing():
    """
    Verifies that calling execute_godot_script on the GodotInterface
    correctly formats and sends the 'execute_script' command via the ConnectionManager.
    """
    # Mock ConnectionManager
    mock_manager = MagicMock()
    mock_manager.send_command = AsyncMock(return_value={"success": True, "result": "Script run successfully"})
    
    # Initialize GodotInterface with mock manager
    interface = GodotInterface(mock_manager)
    
    project_path = "/path/to/project"
    test_code = "print('Hello World')\nreturn 42"
    
    # Execute the tool
    result = await interface.execute_godot_script(project_path, test_code)
    
    # Verify manager.send_command was called with correct payload
    mock_manager.send_command.assert_called_once()
    args, _ = mock_manager.send_command.call_args
    
    sent_project_path = args[0]
    sent_payload = args[1]
    
    assert sent_project_path == project_path
    assert sent_payload["method"] == "execute_script"
    assert sent_payload["params"]["code"] == test_code
    assert "Script executed successfully" in result
    assert "Script run successfully" in result

if __name__ == "__main__":
    asyncio.run(test_execute_godot_script_routing())
