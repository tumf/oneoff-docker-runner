import asyncio
import base64
import json
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

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
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Docker connection failed: {str(e)}"
            )
    return client


# MCP Protocol Models
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


# Global sessions storage
sessions: Dict[str, Dict[str, Any]] = {}


def create_session(
    session_id: Optional[str] = None, protocol_version: str = "2024-11-05"
) -> str:
    """Create a new session with given or generated ID"""
    if not session_id:
        session_id = str(uuid.uuid4())

    sessions[session_id] = {
        "id": session_id,
        "protocol_version": protocol_version,
        "created_at": time.time(),
        "initialized": False,
    }
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session by ID with automatic cleanup of expired sessions"""
    if not session_id:
        return None

    current_time = time.time()
    # Clean up expired sessions (older than 1 hour)
    expired_sessions = [
        sid
        for sid, session in sessions.items()
        if current_time - session.get("created_at", 0) > 3600
    ]
    for expired_id in expired_sessions:
        sessions.pop(expired_id, None)

    return sessions.get(session_id)


def validate_session(session_id: str) -> bool:
    """Validate if session exists and is not expired"""
    session = get_session(session_id)
    return session is not None


# MCP Tool Functions
def mcp_run_container(
    image: str,
    command: Optional[List[str]] = None,
    environment: Optional[Dict[str, str]] = None,
    volumes: Optional[Dict[str, str]] = None,
    pull_policy: str = "missing",
) -> Dict[str, Any]:
    """Execute a Docker container with specified parameters"""
    try:
        docker_client = get_docker_client()

        # Pull image if needed
        if pull_policy in ["always", "missing"]:
            try:
                docker_client.images.get(image)
            except docker.errors.ImageNotFound:
                if pull_policy == "always" or pull_policy == "missing":
                    docker_client.images.pull(image)

        # Run container
        result = docker_client.containers.run(
            image=image,
            command=command,
            environment=environment,
            volumes=volumes,
            remove=True,
            stdout=True,
            stderr=True,
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Container executed successfully. Output: {result.decode('utf-8').strip()}",
                }
            ]
        }
    except Exception as e:
        return {
            "content": [
                {"type": "text", "text": f"Container execution failed: {str(e)}"}
            ],
            "isError": True,
        }


def mcp_create_volume(
    name: str, driver: str = "local", driver_opts: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a Docker volume"""
    try:
        docker_client = get_docker_client()
        volume = docker_client.volumes.create(
            name=name, driver=driver, driver_opts=driver_opts or {}
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Volume '{name}' created successfully. ID: {volume.id}",
                }
            ]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Volume creation failed: {str(e)}"}],
            "isError": True,
        }


def mcp_docker_health() -> Dict[str, Any]:
    """Check Docker daemon health"""
    try:
        docker_client = get_docker_client()
        info = docker_client.info()
        version = docker_client.version()

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Docker daemon is healthy. Version: {version.get('Version', 'unknown')}",
                }
            ]
        }
    except Exception as e:
        return {
            "content": [
                {"type": "text", "text": f"Docker health check failed: {str(e)}"}
            ],
            "isError": True,
        }


def mcp_list_containers(all_containers: bool = False) -> Dict[str, Any]:
    """List Docker containers"""
    try:
        docker_client = get_docker_client()
        containers = docker_client.containers.list(all=all_containers)

        container_list = []
        for container in containers:
            container_list.append(
                {
                    "id": container.id[:12],
                    "name": container.name,
                    "image": (
                        container.image.tags[0] if container.image.tags else "unknown"
                    ),
                    "status": container.status,
                }
            )

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Found {len(container_list)} containers:\n"
                    + "\n".join(
                        [
                            f"- {c['name']} ({c['id']}): {c['status']}"
                            for c in container_list
                        ]
                    ),
                }
            ]
        }
    except Exception as e:
        return {
            "content": [
                {"type": "text", "text": f"Container listing failed: {str(e)}"}
            ],
            "isError": True,
        }


def mcp_list_images() -> Dict[str, Any]:
    """List Docker images"""
    try:
        docker_client = get_docker_client()
        images = docker_client.images.list()

        image_list = []
        for image in images:
            tags = image.tags if image.tags else ["<none>:<none>"]
            image_list.append(
                {
                    "id": image.id[:12],
                    "tags": tags,
                    "size": f"{image.attrs.get('Size', 0) / (1024*1024):.1f} MB",
                }
            )

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Found {len(image_list)} images:\n"
                    + "\n".join(
                        [
                            f"- {', '.join(img['tags'])} ({img['id']}): {img['size']}"
                            for img in image_list
                        ]
                    ),
                }
            ]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Image listing failed: {str(e)}"}],
            "isError": True,
        }


# Available MCP tools
MCP_TOOLS = {
    "run_container": {
        "name": "run_container",
        "description": "Execute a Docker container with specified image and command",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Docker image to run"},
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command to execute (optional)",
                },
                "environment": {
                    "type": "object",
                    "description": "Environment variables (optional)",
                },
                "volumes": {
                    "type": "object",
                    "description": "Volume mounts (optional)",
                },
                "pull_policy": {
                    "type": "string",
                    "enum": ["always", "missing", "never"],
                    "default": "missing",
                    "description": "When to pull the image",
                },
            },
            "required": ["image"],
        },
        "handler": mcp_run_container,
    },
    "create_volume": {
        "name": "create_volume",
        "description": "Create a Docker volume",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Volume name"},
                "driver": {
                    "type": "string",
                    "default": "local",
                    "description": "Volume driver",
                },
                "driver_opts": {
                    "type": "object",
                    "description": "Driver options (optional)",
                },
            },
            "required": ["name"],
        },
        "handler": mcp_create_volume,
    },
    "docker_health": {
        "name": "docker_health",
        "description": "Check Docker daemon health and version",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "handler": mcp_docker_health,
    },
    "list_containers": {
        "name": "list_containers",
        "description": "List Docker containers",
        "inputSchema": {
            "type": "object",
            "properties": {
                "all_containers": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include stopped containers",
                }
            },
            "required": [],
        },
        "handler": mcp_list_containers,
    },
    "list_images": {
        "name": "list_images",
        "description": "List Docker images",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "handler": mcp_list_images,
    },
}


def handle_mcp_request(request: MCPRequest, session_id: str) -> Optional[MCPResponse]:
    """Handle MCP request and return response"""
    try:
        if request.method == "initialize":
            # Initialize session
            params = request.params or {}
            protocol_version = params.get("protocolVersion", "2024-11-05")

            if session_id not in sessions:
                create_session(session_id, protocol_version)

            sessions[session_id]["initialized"] = True
            sessions[session_id]["protocol_version"] = protocol_version

            return MCPResponse(
                id=request.id,
                result={
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "Docker Runner MCP Server",
                        "version": "1.0.0",
                    },
                },
            )

        elif request.method == "tools/list":
            # Return available tools
            tools = []
            for tool_name, tool_info in MCP_TOOLS.items():
                tools.append(
                    {
                        "name": tool_info["name"],
                        "description": tool_info["description"],
                        "inputSchema": tool_info["inputSchema"],
                    }
                )

            return MCPResponse(id=request.id, result={"tools": tools})

        elif request.method == "tools/call":
            # Execute tool
            params = request.params or {}
            tool_name_raw = params.get("name")
            arguments = params.get("arguments", {})

            if not tool_name_raw or not isinstance(tool_name_raw, str):
                return MCPResponse(
                    id=request.id,
                    error={"code": -32601, "message": "Missing or invalid tool name"},
                )

            selected_tool_name: str = tool_name_raw
            if selected_tool_name not in MCP_TOOLS:
                return MCPResponse(
                    id=request.id,
                    error={
                        "code": -32601,
                        "message": f"Tool '{selected_tool_name}' not found",
                    },
                )

            tool_info = MCP_TOOLS[selected_tool_name]
            # Type ignore for mypy as we know the handler is callable
            tool_handler = tool_info["handler"]  # type: ignore
            result = tool_handler(**arguments)  # type: ignore

            return MCPResponse(id=request.id, result=result)

        else:
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32601,
                    "message": f"Method '{request.method}' not found",
                },
            )

    except Exception as e:
        return MCPResponse(
            id=request.id,
            error={"code": -32603, "message": f"Internal error: {str(e)}"},
        )


def create_mcp_app():
    """Create and configure the MCP FastAPI application"""
    app = FastAPI(title="Docker Runner MCP Server", version="1.0.0")

    @app.options("/mcp")
    @app.options("/sse")  # n8n compatibility
    @app.options("/stream")  # n8n compatibility
    async def options_mcp():
        """Handle CORS preflight requests"""
        return JSONResponse(
            content={},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Mcp-Session-Id",
                "Access-Control-Expose-Headers": "Mcp-Session-Id",
            },
        )

    @app.post("/mcp")
    async def post_mcp(request: Request):
        """Handle MCP requests via POST (JSON-only)"""
        try:
            # Get session ID from header or create new one
            session_id = request.headers.get("Mcp-Session-Id")
            if not session_id:
                session_id = create_session()
            elif not validate_session(session_id):
                # Auto-recreate expired session
                session_id = create_session(session_id)

            # Parse request
            body = await request.json()
            mcp_request = MCPRequest(**body)

            # Handle request
            response = handle_mcp_request(mcp_request, session_id)

            if response:
                response_data = response.model_dump(exclude_none=True)
                return JSONResponse(
                    content=response_data,
                    headers={
                        "Mcp-Session-Id": session_id,
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Expose-Headers": "Mcp-Session-Id",
                    },
                )
            else:
                # For notifications (no response expected)
                return JSONResponse(
                    content={},
                    status_code=204,
                    headers={
                        "Mcp-Session-Id": session_id,
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Expose-Headers": "Mcp-Session-Id",
                    },
                )

        except Exception as e:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                },
                status_code=400,
                headers={"Access-Control-Allow-Origin": "*"},
            )

    # n8n compatibility endpoints
    @app.post("/sse")
    @app.post("/stream")
    async def post_mcp_compat(request: Request):
        """n8n compatibility endpoints"""
        return await post_mcp(request)

    @app.get("/mcp")
    @app.get("/sse")  # n8n compatibility
    @app.get("/stream")  # n8n compatibility
    async def get_mcp(request: Request):
        """Handle MCP Server-Sent Events via GET"""
        # Check Accept header
        accept_header = request.headers.get("Accept", "")
        if "text/event-stream" not in accept_header:
            return JSONResponse(
                content={
                    "error": "SSE endpoint requires Accept: text/event-stream header"
                },
                status_code=406,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        # Get or create session ID (n8n compatibility: create if missing)
        session_id = request.headers.get("Mcp-Session-Id")
        if not session_id:
            session_id = create_session()
        elif not validate_session(session_id):
            session_id = create_session(session_id)

        async def server_event_generator():
            """Generate SSE events for the client"""
            try:
                # Connection acknowledgment
                connection_event = {
                    "type": "connection",
                    "sessionId": session_id,
                    "timestamp": time.time(),
                }

                yield f"event: connection\n"
                yield f"data: {json.dumps(connection_event)}\n"
                yield f"id: {session_id}-{int(time.time())}\n"
                yield f"\n"

                # Heartbeat loop
                event_id = 0
                while True:
                    await asyncio.sleep(30)  # 30-second heartbeat

                    event_id += 1
                    heartbeat_event = {
                        "type": "heartbeat",
                        "sessionId": session_id,
                        "timestamp": time.time(),
                    }

                    yield f"event: heartbeat\n"
                    yield f"data: {json.dumps(heartbeat_event)}\n"
                    yield f"id: {session_id}-{event_id}\n"
                    yield f"\n"

            except asyncio.CancelledError:
                # Client disconnected
                if session_id in sessions:
                    sessions.pop(session_id, None)
                return
            except Exception as e:
                error_event = {
                    "type": "error",
                    "message": str(e),
                    "timestamp": time.time(),
                }
                yield f"event: error\n"
                yield f"data: {json.dumps(error_event)}\n"
                yield f"\n"

        return StreamingResponse(
            server_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Mcp-Session-Id": session_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Expose-Headers": "Mcp-Session-Id",
            },
        )

    @app.delete("/mcp")
    @app.delete("/sse")  # n8n compatibility
    @app.delete("/stream")  # n8n compatibility
    async def delete_mcp(request: Request):
        """Terminate MCP session"""
        session_id = request.headers.get("Mcp-Session-Id")
        if session_id and session_id in sessions:
            sessions.pop(session_id, None)
            return JSONResponse(
                content={"message": f"Session {session_id} terminated"},
                headers={"Access-Control-Allow-Origin": "*"},
            )
        else:
            return JSONResponse(
                content={"error": "Session not found"},
                status_code=404,
                headers={"Access-Control-Allow-Origin": "*"},
            )

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy", "timestamp": time.time()}

    return app


# Create the app instance
app = create_mcp_app()

if __name__ == "__main__":
    import uvicorn

    print("Starting Docker Runner MCP Server...")
    print("- Standard MCP endpoint: http://localhost:8001/mcp")
    print("- n8n SSE compatibility: http://localhost:8001/sse")
    print("- n8n Stream compatibility: http://localhost:8001/stream")
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
