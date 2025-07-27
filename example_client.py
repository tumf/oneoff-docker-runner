#!/usr/bin/env python3
"""
Example Client for Integrated Docker Runner

This script demonstrates how to use both the REST API and MCP functionality
of the integrated Docker Runner server.

Usage:
    python example_client.py
"""

import asyncio
import json
import base64
import requests
from fastmcp import Client


def test_rest_api():
    """Test the traditional REST API endpoints"""
    print("🌐 Testing REST API")
    print("=" * 50)
    
    try:
        # Test health endpoint
        print("📊 Testing health endpoint...")
        response = requests.get("http://localhost:8001/health")
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.json()}")
        
        # Test run endpoint
        print("\n🐳 Testing run endpoint...")
        payload = {
            "image": "alpine:latest",
            "command": ["echo", "Hello from REST API!"],
            "pull_policy": "always"
        }
        response = requests.post("http://localhost:8001/run", json=payload)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"  Container status: {result.get('status')}")
            print(f"  Output: {result.get('stdout', '').strip()}")
            print(f"  Execution time: {result.get('execution_time', 0):.2f}s")
        else:
            print(f"  Error: {response.text}")
            
    except Exception as e:
        print(f"❌ REST API test failed: {e}")


async def test_mcp_api():
    """Test the MCP functionality"""
    print("\n🔧 Testing MCP API")
    print("=" * 50)
    
    try:
        # Connect to the MCP endpoint
        server_url = "http://localhost:8001/mcp"
        
        async with Client(server_url) as client:
            print("✅ Connected to MCP server!")
            
            # List available tools
            print("\n🛠️ Available tools:")
            tools = await client.list_tools()
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description}")
            
                    # Test simple container run
        print("\n🐳 Running container via MCP...")
        result = await client.call_tool("run_container", {
            "image": "alpine:latest",
            "command": ["echo", "Hello from MCP!"],
            "pull_policy": "always"
        })

        print(f"  Result: {result.text}")

        # Test with environment variables
        print("\n🌍 Running container with environment variables...")
        result = await client.call_tool("run_container", {
            "image": "alpine:latest",
            "command": ["sh", "-c", "echo 'Env var: '$TEST_VAR"],
            "env_vars": {"TEST_VAR": "MCP_VALUE"},
            "pull_policy": "always"
        })

        print(f"  Result: {result.text}")

        # Test volume creation
        print("\n🗃️ Creating volume via MCP...")
        result = await client.call_tool("create_volume", {
            "name": "mcp-test-volume",
            "driver": "local"
        })

        print(f"  Result: {result.text}")

        # Test Docker health check
        print("\n💊 Checking Docker health via MCP...")
        result = await client.call_tool("docker_health", {})

        print(f"  Result: {result.text}")
            
    except Exception as e:
        print(f"❌ MCP test failed: {e}")
        print("Make sure the server is running with: python main.py")


async def main():
    """Run all tests"""
    print("🎭 Docker Runner Integrated Server Client Example")
    print("=" * 60)
    
    # Check if server is running
    try:
        response = requests.get("http://localhost:8001/health", timeout=5)
        if response.status_code != 200:
            print("❌ Server not responding correctly")
            return
    except:
        print("❌ Server not running. Please start with: python main.py")
        return
    
    print("✅ Server is running\n")
    
    # Test REST API
    test_rest_api()
    
    # Test MCP API  
    await test_mcp_api()
    
    print("\n" + "=" * 60)
    print("✨ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main()) 