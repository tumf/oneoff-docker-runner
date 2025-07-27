import asyncio
import base64
import json
import os
import time
import uuid
from typing import Any, Dict, Optional, Union

import docker
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# Docker client setup
docker_host = os.getenv("DOCKER_HOST", "unix://var/run/docker.sock")
tls_verify = os.getenv("DOCKER_TLS_VERIFY", "0")
cert_path = os.getenv("DOCKER_CERT_PATH", None)

client = None


def get_docker_client():
    """Get Docker client with lazy initialization and error handling"""
    global client
    if client is None:
        try:
            if tls_verify == "1" and cert_path:
                tls_config = docker.tls.TLSConfig(
                    client_cert=(
                        os.path.join(cert_path, "cert.pem"),
                        os.path.join(cert_path, "key.pem"),
                    ),
                    ca_cert=os.path.join(cert_path, "ca.pem"),
                    verify=True,
                )
                client = docker.DockerClient(base_url=docker_host, tls=tls_config)
            else:
                client = docker.DockerClient(base_url=docker_host)
            # Test connection
            client.ping()
        except Exception as e:
            raise HTTPException(
                status_code=503, detail=f"Docker daemon is unavailable: {str(e)}"
            )
    return client


# MCP Protocol Implementation
class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


# MCP Tool Functions
async def mcp_run_container(args: Dict[str, Any]) -> str:
    """Run a Docker container via MCP"""
    image = args.get("image", "")
    command = args.get("command", [])
    env_vars = args.get("env_vars", {})
    pull_policy = args.get("pull_policy", "always")

    try:
        # Pull image if requested
        if pull_policy == "always":
            get_docker_client().images.pull(image)

        # Run container
        container = get_docker_client().containers.run(
            image,
            command=command,
            environment=env_vars,
            remove=True,
            detach=False,
        )

        output = container.decode("utf-8").strip()
        return f"Container executed successfully. Output: {output}"
    except Exception as e:
        return f"Failed to run container: {str(e)}"


async def mcp_create_volume(args: Dict[str, Any]) -> str:
    """Create a Docker volume via MCP"""
    name = args.get("name", "")
    driver = args.get("driver", "local")

    try:
        get_docker_client().volumes.create(name, driver=driver)
        return f"Volume '{name}' created successfully"
    except Exception as e:
        return f"Failed to create volume: {str(e)}"


async def mcp_docker_health(args: Dict[str, Any]) -> str:
    """Check Docker daemon health via MCP"""
    try:
        docker_info = get_docker_client().info()
        version = docker_info.get("ServerVersion", "unknown")
        return f"Docker daemon is healthy. Version: {version}"
    except Exception as e:
        return f"Docker daemon is unhealthy: {str(e)}"


async def mcp_list_containers(args: Dict[str, Any]) -> str:
    """List Docker containers via MCP"""
    try:
        show_all = args.get("all", False)
        containers = get_docker_client().containers.list(all=show_all)

        if not containers:
            return "No containers found"

        result = []
        for container in containers:
            info = {
                "id": container.short_id,
                "name": container.name,
                "status": container.status,
                "image": container.image.tags[0] if container.image.tags else "unknown",
            }
            result.append(info)

        return f"Found {len(containers)} containers:\n" + "\n".join(
            [f"- {c['name']} ({c['id']}): {c['status']} [{c['image']}]" for c in result]
        )
    except Exception as e:
        return f"Failed to list containers: {str(e)}"


async def mcp_list_images(args: Dict[str, Any]) -> str:
    """List Docker images via MCP"""
    try:
        images = get_docker_client().images.list()

        if not images:
            return "No images found"

        result = []
        for image in images:
            tags = image.tags if image.tags else ["<none>"]
            for tag in tags:
                info = {
                    "id": image.short_id,
                    "tag": tag,
                    "size": f"{image.attrs['Size'] / (1024*1024):.1f}MB",
                }
                result.append(info)

        return f"Found {len(result)} image tags:\n" + "\n".join(
            [f"- {i['tag']} ({i['id']}): {i['size']}" for i in result]
        )
    except Exception as e:
        return f"Failed to list images: {str(e)}"


# Global session storage
active_sessions: Dict[str, Dict[str, Any]] = {}


def create_mcp_app() -> FastAPI:
    """Create FastAPI app with MCP Streamable HTTP endpoint"""
    app = FastAPI(title="Docker Runner MCP Server")

    async def handle_mcp_request(
        request: MCPRequest, session_id: str
    ) -> Optional[MCPResponse]:
        """Handle individual MCP request"""
        try:
            if request.method == "initialize":
                response = MCPResponse(
                    id=request.id,
                    result={
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "Docker Runner MCP Server",
                            "version": "1.0.0",
                        },
                    },
                )
                # Initialize session
                active_sessions[session_id] = {"initialized": True}
                return response

            elif request.method == "notifications/initialized":
                # Notification - no response needed
                return None

            elif request.method == "tools/list":
                return MCPResponse(
                    id=request.id,
                    result={
                        "tools": [
                            {
                                "name": "run_container",
                                "description": "Run a Docker container",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "image": {
                                            "type": "string",
                                            "description": "Docker image name",
                                        },
                                        "command": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Command to run in container",
                                        },
                                        "env_vars": {
                                            "type": "object",
                                            "description": "Environment variables",
                                        },
                                        "pull_policy": {
                                            "type": "string",
                                            "enum": ["always", "never"],
                                            "default": "always",
                                            "description": "Image pull policy",
                                        },
                                    },
                                    "required": ["image"],
                                },
                            },
                            {
                                "name": "create_volume",
                                "description": "Create a Docker volume",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "Volume name",
                                        },
                                        "driver": {
                                            "type": "string",
                                            "default": "local",
                                            "description": "Volume driver",
                                        },
                                    },
                                    "required": ["name"],
                                },
                            },
                            {
                                "name": "docker_health",
                                "description": "Check Docker daemon health",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                            {
                                "name": "list_containers",
                                "description": "List Docker containers",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "all": {
                                            "type": "boolean",
                                            "default": False,
                                            "description": "Show all containers (including stopped)",
                                        }
                                    },
                                },
                            },
                            {
                                "name": "list_images",
                                "description": "List Docker images",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                        ]
                    },
                )

            elif request.method == "tools/call":
                if not request.params:
                    return MCPResponse(
                        id=request.id,
                        error={"code": -32602, "message": "Missing params"},
                    )

                tool_name = request.params.get("name")
                tool_args = request.params.get("arguments", {})

                if tool_name == "run_container":
                    result = await mcp_run_container(tool_args)
                elif tool_name == "create_volume":
                    result = await mcp_create_volume(tool_args)
                elif tool_name == "docker_health":
                    result = await mcp_docker_health(tool_args)
                elif tool_name == "list_containers":
                    result = await mcp_list_containers(tool_args)
                elif tool_name == "list_images":
                    result = await mcp_list_images(tool_args)
                else:
                    return MCPResponse(
                        id=request.id,
                        error={
                            "code": -32601,
                            "message": f"Method not found: {tool_name}",
                        },
                    )

                return MCPResponse(
                    id=request.id,
                    result={"content": [{"type": "text", "text": result}]},
                )

            else:
                return MCPResponse(
                    id=request.id,
                    error={
                        "code": -32601,
                        "message": f"Method not found: {request.method}",
                    },
                )

        except Exception as e:
            return MCPResponse(
                id=request.id,
                error={"code": -32603, "message": f"Internal error: {str(e)}"},
            )

    @app.post("/mcp")
    async def mcp_endpoint(request: Request):
        """MCP Streamable HTTP endpoint"""

        # Get or create session ID
        session_id = request.headers.get("mcp-session-id")
        if not session_id:
            session_id = str(uuid.uuid4())

        # Parse request body
        try:
            body = await request.body()
            if not body:
                raise HTTPException(status_code=400, detail="Empty request body")
            mcp_request = MCPRequest.model_validate(json.loads(body))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")

        # Check Accept header to determine response type
        accept_header = request.headers.get("accept", "application/json")

        if "text/event-stream" in accept_header:
            # SSE streaming response
            async def event_generator():
                try:
                    yield ": stream opened\n\n"

                    response = await handle_mcp_request(mcp_request, session_id)
                    if response is not None:
                        response_data = response.model_dump(exclude_none=True)
                        yield f"data: {json.dumps(response_data)}\n\n"

                    # Keep-alive heartbeat
                    while True:
                        await asyncio.sleep(30)
                        yield ": keep-alive\n\n"

                except asyncio.CancelledError:
                    return
                except Exception as e:
                    error_response = MCPResponse(
                        id=mcp_request.id,
                        error={"code": -32603, "message": f"Internal error: {str(e)}"},
                    )
                    yield f"data: {json.dumps(error_response.model_dump(exclude_none=True))}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, x-api-key, Mcp-Session-Id, Last-Event-ID",
                    "Access-Control-Expose-Headers": "Content-Type, Authorization, x-api-key, Mcp-Session-Id",
                    "Access-Control-Allow-Credentials": "true",
                    "Mcp-Session-Id": session_id,
                },
            )
        else:
            # Regular JSON response
            response = await handle_mcp_request(mcp_request, session_id)

            # Handle notifications (no response)
            if response is None:
                return JSONResponse(
                    content={},
                    status_code=202,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, x-api-key, Mcp-Session-Id, Last-Event-ID",
                        "Access-Control-Expose-Headers": "Content-Type, Authorization, x-api-key, Mcp-Session-Id",
                        "Access-Control-Allow-Credentials": "true",
                        "Mcp-Session-Id": session_id,
                    },
                )

            # Regular response
            return JSONResponse(
                content=[response.model_dump(exclude_none=True)],
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, x-api-key, Mcp-Session-Id, Last-Event-ID",
                    "Access-Control-Expose-Headers": "Content-Type, Authorization, x-api-key, Mcp-Session-Id",
                    "Access-Control-Allow-Credentials": "true",
                    "Mcp-Session-Id": session_id,
                },
            )

    @app.options("/mcp")
    async def mcp_options():
        """Handle CORS preflight requests"""
        return JSONResponse(
            content={},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, x-api-key, Mcp-Session-Id, Last-Event-ID",
                "Access-Control-Expose-Headers": "Content-Type, Authorization, x-api-key, Mcp-Session-Id",
                "Access-Control-Allow-Credentials": "true",
            },
        )

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_mcp_app()

    print("🚀 Starting MCP Server on port 8001")
    print("  - MCP Streamable HTTP endpoint: http://localhost:8001/mcp")
    print("  - Protocol: MCP Streamable HTTP (2024-11-05)")
    print("  - Supports both JSON and SSE responses based on Accept header")

    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False, log_level="info")
