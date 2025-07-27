import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from main import app


class TestMCPServer:
    """Test suite for MCP server tools using HTTP API"""

    def setup_method(self):
        """Set up test client"""
        self.client = TestClient(app)

    def test_mcp_root_endpoint(self):
        """Test MCP root endpoint"""
        response = self.client.get("/mcp")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "tools" in data

    def test_list_mcp_tools(self):
        """Test MCP tools listing"""
        response = self.client.get("/mcp/tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        tools = data["tools"]
        assert len(tools) > 0
        tool_names = [tool["name"] for tool in tools]
        assert "run_container" in tool_names
        assert "create_volume" in tool_names



    @pytest.mark.skip(reason="Docker container tests disabled for CI")
    def test_run_docker_container_simple_disabled(self):
        """Test running a simple Docker container - DISABLED FOR CI"""
        # This test is disabled to avoid Docker dependency in CI
        pass

    # NOTE: The following tests are disabled because they use the old MCP Client API
    # which doesn't work with the current FastAPI-based architecture.
    # These can be re-enabled once proper MCP transport is implemented.
    
    @pytest.mark.skip(reason="MCP Client tests disabled - use HTTP tests instead")
    def test_run_docker_container_simple_disabled(self):
        """Test running a simple Docker container - DISABLED"""
        pass

    @pytest.mark.skip(reason="MCP Client tests disabled - use HTTP tests instead")
    def test_run_docker_container_with_env_vars_disabled(self):
        """Test running Docker container with environment variables - DISABLED"""
        pass

    @pytest.mark.skip(reason="MCP Client tests disabled - use HTTP tests instead")
    def test_run_docker_container_with_file_volume_disabled(self):
        """Test running Docker container with file volume - DISABLED"""
        pass

    @pytest.mark.skip(reason="MCP Client tests disabled - use HTTP tests instead")
    def test_create_docker_volume_disabled(self):
        """Test creating a Docker volume - DISABLED"""
        pass

    @pytest.mark.skip(reason="MCP Client tests disabled - use HTTP tests instead")
    def test_list_tools_disabled(self):
        """Test listing available tools - DISABLED"""
        pass

    @pytest.mark.skip(reason="MCP Client tests disabled - use HTTP tests instead")
    def test_tool_schemas_disabled(self):
        """Test that tools have proper schemas - DISABLED"""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
