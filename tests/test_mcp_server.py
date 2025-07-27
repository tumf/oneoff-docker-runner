import asyncio
import base64

import pytest
from fastmcp import Client

from main import app


class TestMCPServer:
    """Test suite for MCP server tools"""

    @pytest.mark.asyncio
    async def test_docker_health_check(self):
        """Test Docker health check tool"""
        async with Client(app) as client:
            result = await client.call_tool("health", {})
            assert result.text is not None
            # Parse the JSON response
            import json

            response = json.loads(result.text)
            assert "status" in response
            assert response["status"] in ["ok", "error"]

    @pytest.mark.asyncio
    async def test_run_docker_container_simple(self):
        """Test running a simple Docker container"""
        async with Client(app) as client:
            # Test with a simple echo command
            result = await client.call_tool(
                "run",
                {
                    "image": "alpine:latest",
                    "command": ["echo", "Hello, MCP!"],
                    "pull_policy": "always",
                },
            )
            assert result.text is not None
            import json

            response = json.loads(result.text)
            assert "status" in response
            assert "stdout" in response
            assert "stderr" in response
            assert "execution_time" in response

            # If Docker is available, should succeed
            if response["status"] == "success":
                assert "Hello, MCP!" in response["stdout"]

    @pytest.mark.asyncio
    async def test_run_docker_container_with_env_vars(self):
        """Test running Docker container with environment variables"""
        async with Client(app) as client:
            result = await client.call_tool(
                "run",
                {
                    "image": "alpine:latest",
                    "command": ["sh", "-c", "echo $TEST_VAR"],
                    "env_vars": {"TEST_VAR": "test_value"},
                    "pull_policy": "always",
                },
            )
            assert result.text is not None
            import json

            response = json.loads(result.text)

            # If Docker is available, should succeed
            if response["status"] == "success":
                assert "test_value" in response["stdout"]

    @pytest.mark.asyncio
    async def test_run_docker_container_with_file_volume(self):
        """Test running Docker container with file volume"""
        async with Client(app) as client:
            # Create a test file content
            test_content = "Hello from file volume!"
            encoded_content = base64.b64encode(test_content.encode()).decode()

            result = await client.call_tool(
                "run",
                {
                    "image": "alpine:latest",
                    "command": ["cat", "/tmp/test.txt"],
                    "volumes": {
                        "/tmp/test.txt": {"type": "file", "content": encoded_content}
                    },
                    "pull_policy": "always",
                },
            )
            assert result.text is not None
            import json

            response = json.loads(result.text)

            # If Docker is available, should succeed
            if response["status"] == "success":
                assert test_content in response["stdout"]

    @pytest.mark.asyncio
    async def test_create_docker_volume(self):
        """Test creating a Docker volume"""
        async with Client(app) as client:
            result = await client.call_tool(
                "volume", {"name": "test-volume-mcp", "driver": "local"}
            )
            assert result.text is not None
            import json

            response = json.loads(result.text)
            assert "status" in response
            assert "detail" in response

            # If Docker is available, should succeed
            if response["status"] == "success":
                assert "test-volume-mcp" in response["detail"]

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing available tools"""
        async with Client(app) as client:
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools.tools]

            expected_tools = ["run", "volume", "health"]

            for expected_tool in expected_tools:
                assert expected_tool in tool_names

    @pytest.mark.asyncio
    async def test_tool_schemas(self):
        """Test that tools have proper schemas"""
        async with Client(app) as client:
            tools = await client.list_tools()

            for tool in tools.tools:
                assert tool.name is not None
                assert tool.description is not None
                assert tool.inputSchema is not None

                # Check that main tool has required parameters
                if tool.name == "run":
                    properties = tool.inputSchema.get("properties", {})
                    assert "image" in properties
                    required = tool.inputSchema.get("required", [])
                    assert "image" in required


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
