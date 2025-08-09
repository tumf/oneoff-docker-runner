import asyncio
import base64
import json
import logging
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

import docker
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mcp_server")

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

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log all requests for debugging"""
        start_time = time.time()

        # Get client information
        client_ip = request.client.host if request.client else "unknown"
        client_port = request.client.port if request.client else "unknown"

        # Log basic request info
        logger.info(f"🔍 REQUEST: {request.method} {request.url}")
        logger.info(f"   Client: {client_ip}:{client_port}")
        logger.info(f"   Path: {request.url.path}")
        logger.info(
            f"   Query: {str(request.query_params) if request.query_params else 'None'}"
        )

        # Log detailed headers
        logger.info("📋 REQUEST HEADERS:")
        headers = dict(request.headers)

        # Important headers first
        important_headers = [
            "accept",
            "content-type",
            "content-length",
            "user-agent",
            "authorization",
            "mcp-session-id",
            "x-forwarded-for",
            "x-real-ip",
            "host",
            "referer",
            "origin",
        ]

        for header_name in important_headers:
            header_value = headers.get(header_name)
            if header_value:
                # Truncate very long values
                display_value = (
                    header_value
                    if len(header_value) <= 100
                    else f"{header_value[:97]}..."
                )
                logger.info(f"   🔸 {header_name}: {display_value}")

        # Other headers
        other_headers = {
            k: v for k, v in headers.items() if k.lower() not in important_headers
        }
        if other_headers:
            logger.info("   📎 Other headers:")
            for name, value in other_headers.items():
                display_value = value if len(value) <= 100 else f"{value[:97]}..."
                logger.info(f"      • {name}: {display_value}")

        # Log request body info for POST/PUT/PATCH
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = headers.get("content-length", "0")
            content_type = headers.get("content-type", "unknown")
            logger.info(
                f"📦 REQUEST BODY: Content-Length = {content_length} bytes, Content-Type = {content_type}"
            )

            # Note: We don't read the body here to avoid consuming the stream
            # The body will be logged in the endpoint handlers if needed

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Log response details
            if response.status_code >= 400:
                logger.warning(
                    f"❌ ERROR RESPONSE: {response.status_code} for {request.method} {request.url.path}"
                )
                logger.warning(f"   Processing time: {process_time:.3f}s")
                logger.warning("📤 RESPONSE HEADERS:")
                for name, value in response.headers.items():
                    display_value = value if len(value) <= 100 else f"{value[:97]}..."
                    logger.warning(f"      • {name}: {display_value}")
            else:
                logger.info(
                    f"✅ SUCCESS: {response.status_code} for {request.method} {request.url.path} ({process_time:.3f}s)"
                )
                # Only log response headers for successful requests if they contain important info
                important_resp_headers = [
                    "content-type",
                    "mcp-session-id",
                    "location",
                    "set-cookie",
                ]
                logged_headers = []
                for name, value in response.headers.items():
                    if name.lower() in important_resp_headers:
                        display_value = (
                            value if len(value) <= 100 else f"{value[:97]}..."
                        )
                        logged_headers.append(f"{name}: {display_value}")
                if logged_headers:
                    logger.info(f"   Key response headers: {', '.join(logged_headers)}")

            return response

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(f"💥 EXCEPTION: {str(e)} for {request.method} {request.url}")
            logger.error(f"   Processing time: {process_time:.3f}s")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception details: {repr(e)}")
            raise

    @app.options("/mcp")
    @app.options("/sse")  # n8n compatibility
    @app.options("/stream")  # n8n compatibility
    async def options_mcp(request: Request):
        """Handle CORS preflight requests"""
        logger.info(f"🔍 CORS PREFLIGHT: {request.method} {request.url}")
        logger.info(f"   Origin: {request.headers.get('Origin', 'not specified')}")
        logger.info(
            f"   Access-Control-Request-Method: {request.headers.get('Access-Control-Request-Method', 'not specified')}"
        )
        logger.info(
            f"   Access-Control-Request-Headers: {request.headers.get('Access-Control-Request-Headers', 'not specified')}"
        )

        return JSONResponse(
            content={},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS, HEAD",
                "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Mcp-Session-Id, User-Agent, Cache-Control, Connection",
                "Access-Control-Expose-Headers": "Mcp-Session-Id, Content-Type",
                "Access-Control-Max-Age": "86400",  # Cache preflight for 24 hours
            },
        )

    @app.post("/mcp")
    async def post_mcp(request: Request):
        """Handle MCP requests via POST (supports both JSON and SSE responses)"""
        try:
            # Check if client wants SSE response (Streamable HTTP support)
            accept_header = request.headers.get("Accept", "")
            wants_sse = "text/event-stream" in accept_header

            logger.info(f"📨 POST MCP: Accept='{accept_header}', SSE={wants_sse}")

            # Get session ID from header or create new one
            session_id = request.headers.get("Mcp-Session-Id")
            if not session_id:
                session_id = create_session()
                logger.info(f"🆕 NEW SESSION: Created session {session_id}")
            elif not validate_session(session_id):
                # Auto-recreate expired session
                session_id = create_session(session_id)
                logger.info(f"🔄 RENEWED SESSION: Recreated session {session_id}")
            else:
                logger.info(f"📋 EXISTING SESSION: Using session {session_id}")

            # Parse request
            body = await request.json()
            logger.info(f"📥 MCP REQUEST BODY: {json.dumps(body, indent=2)}")

            mcp_request = MCPRequest(**body)

            # Handle request
            response = handle_mcp_request(mcp_request, session_id)

            if response:
                response_data = response.model_dump(exclude_none=True)
                logger.info(f"📤 MCP RESPONSE: {json.dumps(response_data, indent=2)}")

                # Return SSE format if requested (Streamable HTTP)
                if wants_sse:
                    logger.info(
                        f"🌊 STREAMABLE HTTP: Sending SSE response for {mcp_request.method}"
                    )

                    async def sse_response_generator():
                        yield f"event: response\n"
                        yield f"data: {json.dumps(response_data)}\n"
                        yield f"id: {session_id}-{mcp_request.id}\n"
                        yield f"\n"

                    return StreamingResponse(
                        sse_response_generator(),
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "Mcp-Session-Id": session_id,
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Expose-Headers": "Mcp-Session-Id",
                        },
                    )
                else:
                    # Return standard JSON response
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
                logger.info(
                    f"📨 MCP NOTIFICATION: No response for {mcp_request.method}"
                )

                if wants_sse:
                    # Return empty SSE stream for notifications
                    async def empty_sse_generator():
                        yield f"event: notification\n"
                        yield f"data: {json.dumps({'message': f'Notification received: {mcp_request.method}'})}\n"
                        yield f"id: {session_id}-notification\n"
                        yield f"\n"

                    return StreamingResponse(
                        empty_sse_generator(),
                        media_type="text/event-stream",
                        status_code=200,
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "Mcp-Session-Id": session_id,
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Expose-Headers": "Mcp-Session-Id",
                        },
                    )
                else:
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
            logger.error(f"💥 MCP PARSE ERROR: {str(e)}")
            logger.error(f"   Exception type: {type(e).__name__}")
            # Note: Cannot read request body again after JSON parse failure

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
        # Check Accept header - n8n sends "application/json, text/event-stream"
        accept_header = request.headers.get("Accept", "")
        logger.info(f"🔍 SSE REQUEST: Accept header = '{accept_header}'")

        # Allow both text/event-stream and mixed content types for n8n compatibility
        if "text/event-stream" not in accept_header and accept_header != "*/*":
            logger.warning(
                f"❌ SSE REJECTED: Missing text/event-stream in Accept header"
            )
            logger.warning(f"   Available headers: {dict(request.headers)}")
            logger.warning(
                f"   Note: n8n typically sends 'application/json, text/event-stream'"
            )
            return JSONResponse(
                content={
                    "error": "SSE endpoint requires Accept: text/event-stream header (or mixed types like 'application/json, text/event-stream')"
                },
                status_code=406,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        # Get or create session ID (n8n compatibility: create if missing)
        session_id = request.headers.get("Mcp-Session-Id")
        if not session_id:
            session_id = create_session()
            logger.info(f"🆕 SSE NEW SESSION: Created session {session_id}")
        elif not validate_session(session_id):
            session_id = create_session(session_id)
            logger.info(f"🔄 SSE RENEWED SESSION: Recreated session {session_id}")
        else:
            logger.info(f"📋 SSE EXISTING SESSION: Using session {session_id}")

        async def server_event_generator():
            """Generate SSE events for the client"""
            try:
                logger.info(
                    f"🚀 SSE STREAM: Starting event stream for session {session_id}"
                )

                # MCP initialization sequence for n8n compatibility
                logger.info(
                    f"🔄 MCP INIT: Starting initialization sequence for session {session_id}"
                )

                # Step 1: Send connection ready signal
                yield f"event: ready\n"
                yield f"data: {json.dumps({'sessionId': session_id, 'status': 'connected'})}\n"
                yield f"id: {session_id}-ready\n"
                yield f"\n"

                # Step 2: Auto-initialize session (n8n expects this)
                if not sessions[session_id].get("initialized", False):
                    logger.info(
                        f"🔧 AUTO INIT: Initializing session {session_id} for n8n compatibility"
                    )

                    # Create initialize request internally
                    init_request = MCPRequest(
                        method="initialize",
                        id=f"{session_id}-auto-init",
                        params={"protocolVersion": "2024-11-05"},
                    )
                    init_response = handle_mcp_request(init_request, session_id)

                    if init_response:
                        # Send initialization response as SSE event
                        yield f"event: initialized\n"
                        yield f"data: {json.dumps(init_response.model_dump(exclude_none=True))}\n"
                        yield f"id: {session_id}-init\n"
                        yield f"\n"
                        logger.info(
                            f"✅ AUTO INIT: Session {session_id} initialized successfully"
                        )

                    # Small delay for n8n client processing
                    await asyncio.sleep(0.1)

                # Step 3: Auto-send tools list (n8n expects immediate tool availability)
                logger.info(
                    f"📋 AUTO TOOLS: Sending tools list for session {session_id}"
                )

                tools_request = MCPRequest(
                    method="tools/list", id=f"{session_id}-auto-tools"
                )
                tools_response = handle_mcp_request(tools_request, session_id)

                if tools_response:
                    # Send tools list as SSE event
                    yield f"event: tools_available\n"
                    yield f"data: {json.dumps(tools_response.model_dump(exclude_none=True))}\n"
                    yield f"id: {session_id}-tools\n"
                    yield f"\n"
                    tool_names = [
                        tool["name"]
                        for tool in (tools_response.result or {}).get("tools", [])
                    ]
                    logger.info(
                        f"✅ AUTO TOOLS: Tools list sent for session {session_id} - {len(tool_names)} tools available: {', '.join(tool_names)}"
                    )

                # Step 4: Send ready-for-commands signal
                yield f"event: ready_for_commands\n"
                yield f"data: {json.dumps({'sessionId': session_id, 'status': 'ready', 'message': 'MCP server ready for tool calls'})}\n"
                yield f"id: {session_id}-ready-commands\n"
                yield f"\n"

                logger.info(
                    f"🎯 N8N READY: Session {session_id} fully initialized and ready for n8n MCP client"
                )

                # Keep connection alive with heartbeat
                event_id = 0
                while True:
                    await asyncio.sleep(30)  # 30-second heartbeat

                    event_id += 1
                    logger.info(
                        f"💗 SSE HEARTBEAT: Keeping session {session_id} alive ({event_id})"
                    )

                    # Send heartbeat
                    yield f"event: ping\n"
                    yield f"data: {json.dumps({'sessionId': session_id, 'ping': event_id, 'timestamp': time.time()})}\n"
                    yield f"id: {session_id}-ping-{event_id}\n"
                    yield f"\n"

            except asyncio.CancelledError:
                # Client disconnected
                logger.info(
                    f"🔌 SSE DISCONNECT: Client disconnected from session {session_id}"
                )
                if session_id in sessions:
                    sessions.pop(session_id, None)
                    logger.info(f"🗑️ SSE CLEANUP: Removed session {session_id}")
                return
            except Exception as e:
                logger.error(f"💥 SSE ERROR: {str(e)} in session {session_id}")
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

    # 404 handler for debugging
    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    )
    async def catch_all(request: Request, path: str):
        """Catch all unmatched routes for debugging"""
        logger.error(f"🚫 404 NOT FOUND: {request.method} /{path}")
        logger.error(f"   Full URL: {request.url}")
        logger.error(f"   Headers: {dict(request.headers)}")
        logger.error(f"   Query params: {dict(request.query_params)}")

        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                body = await request.body()
                if body:
                    # Decode bytes safely for logging
                    try:
                        body_str = body.decode("utf-8")
                        logger.error(f"   Request body: {body_str}")
                    except UnicodeDecodeError:
                        logger.error(f"   Request body (binary): {body!r}")
        except Exception as e:
            logger.error(f"   Could not read request body: {e}")

        return JSONResponse(
            content={
                "error": f"Path /{path} not found",
                "method": request.method,
                "available_endpoints": [
                    "/mcp (POST, GET, DELETE)",
                    "/sse (POST, GET, DELETE) - n8n compatibility",
                    "/stream (POST, GET, DELETE) - n8n compatibility",
                    "/health (GET)",
                ],
            },
            status_code=404,
            headers={"Access-Control-Allow-Origin": "*"},
        )

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
