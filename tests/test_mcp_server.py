"""Test cases for MCP server functionality."""

import pytest
from fastapi.testclient import TestClient

from mcp import create_mcp_app


class TestMCPServer:
    """Test MCP server endpoints and functionality."""

    def setup_method(self):
        """Set up test client before each test method."""
        app = create_mcp_app()
        self.client = TestClient(app)

    def test_mcp_initialize(self):
        """Test MCP initialization endpoint."""
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert response.status_code == 200
        data = response.json()
        # Updated: Now expecting direct JSON object, not wrapped in list
        assert isinstance(data, dict)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert "capabilities" in data["result"]
        assert "serverInfo" in data["result"]

    def test_mcp_tools_list(self):
        """Test MCP tools/list method."""
        # First initialize
        self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )

        # Then list tools
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert response.status_code == 200
        data = response.json()
        # Updated: Now expecting direct JSON object, not wrapped in list
        assert isinstance(data, dict)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 2
        assert "result" in data
        assert "tools" in data["result"]
        assert len(data["result"]["tools"]) > 0

        # Check that we have the expected tools
        tool_names = [tool["name"] for tool in data["result"]["tools"]]
        expected_tools = [
            "run_container",
            "create_volume",
            "docker_health",
            "list_containers",
            "list_images",
        ]
        for expected_tool in expected_tools:
            assert expected_tool in tool_names

    def test_mcp_docker_health_tool(self):
        """Test MCP docker health tool execution."""
        # First initialize
        self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )

        # Execute docker health tool
        response = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "docker_health", "arguments": {}},
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Updated: Now expecting direct JSON object, not wrapped in list
        assert isinstance(data, dict)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 3
        assert "result" in data
        assert "content" in data["result"]
        assert len(data["result"]["content"]) > 0
        assert data["result"]["content"][0]["type"] == "text"

    def test_mcp_invalid_method(self):
        """Test MCP with invalid method."""
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 4, "method": "invalid_method"},
        )
        assert response.status_code == 200
        data = response.json()
        # Updated: Now expecting direct JSON object, not wrapped in list
        assert isinstance(data, dict)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 4
        assert "error" in data
        assert data["error"]["code"] == -32601


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
