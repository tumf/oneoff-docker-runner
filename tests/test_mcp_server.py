import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from mcp import create_mcp_app


class TestMCPServer:
    """Test suite for MCP server tools using HTTP API"""

    def setup_method(self):
        """Set up test client"""
        app = create_mcp_app()
        self.client = TestClient(app)

    def test_mcp_initialize(self):
        """Test MCP JSON-RPC initialize method"""
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        result = data[0]
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "result" in result
        assert result["result"]["protocolVersion"] == "2024-11-05"
        assert "capabilities" in result["result"]
        assert "serverInfo" in result["result"]

    def test_mcp_tools_list(self):
        """Test MCP JSON-RPC tools/list method"""
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        result = data[0]
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 2
        assert "result" in result
        assert "tools" in result["result"]
        tools = result["result"]["tools"]
        assert len(tools) > 0
        tool_names = [tool["name"] for tool in tools]
        assert "run_container" in tool_names
        assert "create_volume" in tool_names
        assert "docker_health" in tool_names

    def test_mcp_docker_health_tool(self):
        """Test MCP JSON-RPC docker_health tool call"""
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
        assert isinstance(data, list)
        assert len(data) == 1
        result = data[0]
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 3
        assert "result" in result
        assert "content" in result["result"]

    def test_mcp_invalid_method(self):
        """Test MCP JSON-RPC with invalid method"""
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 4, "method": "invalid_method", "params": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        result = data[0]
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 4
        assert "error" in result
        assert result["error"]["code"] == -32601
        assert "Method not found" in result["error"]["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
