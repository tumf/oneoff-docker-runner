import asyncio
import base64
import json
import os
import shutil
import tempfile
import time
from typing import Any, Dict, List, Literal, Optional, Union

import docker
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Integrated FastAPI app with MCP support
app = FastAPI(title="Docker Runner with MCP Integration")

# Docker client setup (lazy initialization)
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


class AuthConfig(BaseModel):
    username: str = Field(
        ...,
        description="Docker registry username",
        json_schema_extra={"example": "your-username"},
    )
    password: str = Field(
        ...,
        description="Docker registry password",
        json_schema_extra={"example": "your-password"},
    )
    email: Optional[str] = Field(
        None,
        description="Docker registry email",
        json_schema_extra={"example": "your-email@example.com"},
    )
    serveraddress: str = Field(
        "https://index.docker.io/v1/",
        description="Docker registry server address",
        json_schema_extra={"example": "https://index.docker.io/v1/"},
    )


class VolumeConfig(BaseModel):
    content: Optional[str] = Field(
        None,
        description="Base64 encoded content for the volume, when type = file|directory",
        json_schema_extra={"example": "base64encodedcontent"},
    )
    response: Optional[bool] = Field(
        False,
        description="Whether to return the volume",
        json_schema_extra={"example": True},
    )
    type: Literal["file", "directory", "volume"] = Field(
        ..., description="Type of the volume", json_schema_extra={"example": "file"}
    )
    mode: Optional[str] = Field(
        None, description="File mode of the file", json_schema_extra={"example": "0644"}
    )
    name: Optional[str] = Field(
        None,
        description="Name of the volume (only use when type=volume)",
        json_schema_extra={"example": "my-volume"},
    )


class VolumeResponse(BaseModel):
    content: Optional[str] = Field(
        None,
        description="Base64 encoded content for the volume",
        json_schema_extra={"example": "base64encodedcontent"},
    )
    type: Literal["file", "directory", "volume"] = Field(
        ..., description="Type of the volume", json_schema_extra={"example": "file"}
    )


class RunContainerRequest(BaseModel):
    image: str = Field(
        ...,
        description="Docker image to run",
        json_schema_extra={"example": "alpine:latest"},
    )
    command: Optional[Union[List[str], str]] = Field(
        None,
        description="Command to run in the container",
        json_schema_extra={"example": ["echo", "Hello, World!"]},
    )
    entrypoint: Optional[Union[List[str], str]] = Field(
        None,
        description="Entrypoint for the container",
        json_schema_extra={"example": ["/bin/sh", "-c"]},
    )
    env_vars: Optional[Dict[str, Union[str, int, bool]]] = Field(
        None,
        description="Environment variables for the container",
        json_schema_extra={"example": {"MY_VAR": "value"}},
    )
    pull_policy: Optional[Literal["always", "never"]] = Field(
        "always",
        description="Pull policy for the image",
        json_schema_extra={"example": "always"},
    )
    auth_config: Optional[AuthConfig] = Field(
        None, description="Authentication configuration for pulling the image"
    )
    volumes: Optional[Dict[str, VolumeConfig]] = Field(
        None,
        json_schema_extra={
            "example": {
                "/app/hoge.txt:ro": {
                    "type": "file",
                    "content": "VGhpcyBpcyB0aGUgY29udGVudCBvZiBob2dlLnR4dA==",
                },
                "/app/data": {
                    "type": "directory",
                    "content": "H4sIAAAAAAAAE2NgYGBgBGIGgA2BgYFV8EAAXxGH7gAAAA==",
                    "response": True,
                },
            }
        },
        description="Volumes to mount in the container",
    )


class RunContainerResponse(BaseModel):
    status: str = Field(
        ...,
        json_schema_extra={"example": "success"},
        description="Status of the container run",
    )
    stdout: str = Field(
        ...,
        json_schema_extra={"example": "Hello, World!\n"},
        description="Standard output from the container",
    )
    stderr: str = Field(
        ...,
        json_schema_extra={"example": ""},
        description="Standard error output from the container",
    )
    volumes: Optional[Dict[str, VolumeResponse]] = Field(
        None,
        json_schema_extra={
            "example": {
                "/mnt/data": {
                    "type": "directory",
                    "content": "H4sIAAAAAAAAE2NgYGBgBGIGgA2BgYFV8EAAXxGH7gAAAA==",
                    "response": True,
                },
                "/mnt/data/hoge.txt": {
                    "mode": "0644",
                    "type": "file",
                    "content": "VGhpcyBpcyB0aGUgY29udGVudCBvZiBob2dlLnR4dA==",
                },
            }
        },
        description="Contents of the volumes",
    )
    execution_time: float = Field(
        ...,
        json_schema_extra={"example": 1.234},
        description="Execution time in seconds",
    )


@app.post(
    "/run",
    summary="Run a Docker container",
    description="Run a Docker container with the specified configuration",
    response_model=RunContainerResponse,
)
async def run_container(request: RunContainerRequest):
    start_time = time.time()

    try:
        # Pull the image with authentication if provided
        auth_config = None
        if request.auth_config:
            auth_config = {
                "username": request.auth_config.username,
                "password": request.auth_config.password,
                "email": request.auth_config.email,
                "serveraddress": request.auth_config.serveraddress,
            }
        if request.pull_policy == "always":
            get_docker_client().images.pull(request.image, auth_config=auth_config)
        # Prepare volumes
        volume_binds, response_volumes, temp_dirs = prepare_volumes(
            request.volumes or {}
        )
        print(f"volume_binds: {volume_binds}")
        container = None
        try:
            # Run the container
            container = get_docker_client().containers.run(
                request.image,
                command=request.command,
                entrypoint=request.entrypoint,
                environment=request.env_vars,
                volumes=volume_binds,
                detach=True,
                remove=False,
            )
            result = container.wait()
            stdout_output, stderr_output = get_container_logs(container)

            # Collect response volumes content
            response_volume_contents = collect_response_volumes(
                response_volumes, request.volumes
            )
        finally:
            # Cleanup container
            if container:
                container.remove()

            # Cleanup temp directories
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir)

        end_time = time.time()
        execution_time = end_time - start_time
        status = (
            "success" if result["StatusCode"] == 0 else f"error: {result['StatusCode']}"
        )
        result = {
            "status": status,
            "stdout": stdout_output,
            "stderr": stderr_output,
            "volumes": response_volume_contents,
            "execution_time": execution_time,
        }
        if status != "success":
            raise HTTPException(status_code=500, detail=result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def prepare_volumes(volumes: Optional[Dict[str, VolumeConfig]]):
    volume_binds: Dict[str, Dict[str, str]] = {}
    response_volumes: Dict[str, str] = {}
    temp_dirs: List[str] = []

    if not volumes:
        return volume_binds, response_volumes, temp_dirs

    for volumes_key, vol_info in volumes.items():
        volumes_key_parts = volumes_key.split(":")
        container_path = volumes_key_parts[0]
        bind_option = volumes_key_parts[1] if len(volumes_key_parts) > 1 else "rw"

        if vol_info.type in ["file", "directory"]:
            vol_content = vol_info.content
            if vol_content is None:
                continue
            temp_dir = tempfile.mkdtemp()
            temp_dirs.append(temp_dir)
            decoded_content = base64.b64decode(vol_content)

            if vol_info.type == "file":
                source_path = os.path.join(temp_dir, os.path.basename(container_path))
                with open(source_path, "wb") as f:
                    f.write(decoded_content)
                if vol_info.mode:
                    os.chmod(source_path, int(vol_info.mode, 8))
                print(f"wrote file: {source_path} with mode {vol_info.mode}")
            elif vol_info.type == "directory":
                archive_path = os.path.join(temp_dir, "archive.tar.gz")
                with open(archive_path, "wb") as f:
                    f.write(decoded_content)
                shutil.unpack_archive(archive_path, temp_dir, filter="data")
                source_path = temp_dir
                print(f"wrote directory: {source_path}")
        elif vol_info.type == "volume":
            source_path = vol_info.name or ""

        if vol_info.response:
            if vol_info.type == "volume":
                print(f"response type volume return: {source_path} is not supported")
            else:
                response_volumes[container_path] = source_path

        volume_binds[source_path] = {"bind": container_path, "mode": bind_option}

    return volume_binds, response_volumes, temp_dirs


def get_container_logs(container):
    stdout_logs = container.logs(stdout=True, stderr=False)
    stderr_logs = container.logs(stdout=False, stderr=True)
    stdout_output = stdout_logs.decode("utf-8")
    stderr_output = stderr_logs.decode("utf-8")
    return stdout_output, stderr_output


def collect_response_volumes(
    response_volumes: Dict[str, str], volumes: Optional[Dict[str, VolumeConfig]]
):
    response_volume_contents: Dict[str, Optional[Dict[str, str]]] = {}
    if not volumes:
        return response_volume_contents

    for container_path, source_path in response_volumes.items():
        if not os.path.exists(source_path):
            response_volume_contents[container_path] = None
            continue
        vol_info = volumes[container_path]

        if vol_info.type == "file":
            with open(source_path, "rb") as f:
                response_volume_contents[container_path] = {
                    "type": "file",
                    "content": base64.b64encode(f.read()).decode("utf-8"),
                }
        elif vol_info.type == "directory":
            archive_name = tempfile.mktemp(suffix=".tar.gz")
            shutil.make_archive(archive_name[:-7], "gztar", source_path)
            with open(archive_name, "rb") as f:
                response_volume_contents[container_path] = {
                    "type": "directory",
                    "content": base64.b64encode(f.read()).decode("utf-8"),
                }
                os.remove(archive_name)
    return response_volume_contents


class CreateVolumeRequest(BaseModel):
    name: str = Field(
        ...,
        description="Name of the volume",
        json_schema_extra={"example": "my-volume"},
    )
    content: Optional[str] = Field(
        None,
        description="Base64 encoded data to put into the volume",
        json_schema_extra={
            "example": "H4sIAIQOfmYAA+2TMQ7DIAxFcxRO0Biw4TxIabYsjSPl+HUhStWFjdCqfgxeLPHh6U+J0zi0BQAikckzlAkOyzwwFoOPCBEoGLBOzmCoca7MtnJ6SBTelrm2J2tzbeF4xzl/hOnln+8r2xvv3OYO+Y+AWPNPb/8RxL+PVvxDmzif/Ln/rL53CKUbZ//dt/Tfl/6T9v8KsvreIRRFUZTLeQL28PKYAA4AAA=="
        },
    )
    driver: Optional[str] = Field(
        "local",
        description="Driver of the volume",
        json_schema_extra={"example": "local"},
    )
    driver_opts: Optional[Dict[str, str]] = Field(
        None,
        description="Driver options of the volume",
        json_schema_extra={"example": {}},
    )
    labels: Optional[Dict[str, str]] = Field(
        None,
        description="Labels of the volume",
        json_schema_extra={"example": {"key": "value"}},
    )


class CreateVolumeResponse(BaseModel):
    status: str = Field(
        ...,
        json_schema_extra={"example": "success"},
        description="Status of the volume creation",
    )
    detail: Optional[str] = Field(
        None,
        json_schema_extra={"example": "success"},
        description="Detail of the volume creation",
    )


def write_content_to_volume(volume, encoded_content):
    container = get_docker_client().containers.run(
        "busybox",
        f"sh -c 'echo $ENCODED_CONTENT | base64 -d | tar -C /volume --strip-components=1 -xz'",
        environment={"ENCODED_CONTENT": encoded_content},
        volumes={
            volume.name: {"bind": "/volume", "mode": "rw"},
        },
        detach=True,
        remove=True,
    )
    container.wait()


@app.post(
    "/volume",
    summary="Create volume on Docker",
    description="Create volume on Docker",
    response_model=CreateVolumeResponse,
)
async def create_volume(request: CreateVolumeRequest):
    # volume = get_docker_client().volumes.get(request.name)
    # if not volume:
    volume = get_docker_client().volumes.create(
        request.name,
        driver=request.driver,
        driver_opts=request.driver_opts,
        labels=request.labels,
    )
    if request.content:
        write_content_to_volume(volume, request.content)

    return {
        "status": "success",
        "detail": f"Volume {request.name} created",
    }


@app.get("/health")
def health():
    try:
        docker_info = get_docker_client().info()
        if not docker_info:
            raise HTTPException(status_code=500, detail="Docker daemon is unavailable")
        return {
            "status": "ok",
            "docker_version": docker_info.get("ServerVersion", "unknown"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Docker daemon is unavailable: {str(e)}"
        )


# MCP Tool Functions (manual implementation)
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


# MCP Protocol Implementation
class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Union[str, int]
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Union[str, int]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    def dict(self, **kwargs) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        response_dict: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.result is not None:
            response_dict["result"] = self.result
        if self.error is not None:
            response_dict["error"] = self.error
        return response_dict


# Standard MCP SSE implementation
# Global storage for SSE sessions
sse_sessions: Dict[str, asyncio.Queue] = {}


@app.get("/sse")
async def mcp_sse_endpoint(request: Request):
    """Standard MCP Server-Sent Events endpoint"""
    session_id = request.query_params.get("sessionId")
    if not session_id:
        session_id = base64.b64encode(os.urandom(16)).decode("utf-8")

    async def event_generator():
        try:
            # Send message endpoint information
            yield f"data: /messages\n\n"

            # Store session for message endpoint
            sse_sessions[session_id] = asyncio.Queue()

            # Keep connection alive and handle messages
            while True:
                try:
                    # Wait for messages from the message endpoint or timeout for heartbeat
                    message = await asyncio.wait_for(
                        sse_sessions[session_id].get(), timeout=30.0
                    )
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                except asyncio.CancelledError:
                    break
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Cleanup session
            if session_id in sse_sessions:
                del sse_sessions[session_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "X-Session-Id": session_id,
        },
    )


@app.post("/messages")
async def mcp_messages_endpoint(request: MCPRequest, http_request: Request):
    """Standard MCP messages endpoint for client-to-server communication"""
    session_id = http_request.query_params.get("sessionId")
    if not session_id or session_id not in sse_sessions:
        raise HTTPException(status_code=400, detail="Invalid or missing session ID")

    try:
        response = None

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

        elif request.method == "tools/list":
            response = MCPResponse(
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
                                    },
                                    "env_vars": {"type": "object"},
                                    "pull_policy": {
                                        "type": "string",
                                        "enum": ["always", "never"],
                                        "default": "always",
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
                                    "driver": {"type": "string", "default": "local"},
                                },
                                "required": ["name"],
                            },
                        },
                        {
                            "name": "docker_health",
                            "description": "Check Docker daemon health",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            )

        elif request.method == "tools/call":
            if not request.params:
                response = MCPResponse(
                    id=request.id, error={"code": -32602, "message": "Missing params"}
                )
            else:
                tool_name = request.params.get("name")
                tool_args = request.params.get("arguments", {})

                if tool_name == "run_container":
                    result = await mcp_run_container(tool_args)
                elif tool_name == "create_volume":
                    result = await mcp_create_volume(tool_args)
                elif tool_name == "docker_health":
                    result = await mcp_docker_health(tool_args)
                else:
                    response = MCPResponse(
                        id=request.id,
                        error={
                            "code": -32601,
                            "message": f"Method not found: {tool_name}",
                        },
                    )

                if response is None:
                    response = MCPResponse(
                        id=request.id,
                        result={"content": [{"type": "text", "text": result}]},
                    )

        else:
            response = MCPResponse(
                id=request.id,
                error={
                    "code": -32601,
                    "message": f"Method not found: {request.method}",
                },
            )

        # Send response back via SSE
        if response and session_id in sse_sessions:
            await sse_sessions[session_id].put(response.dict())

        # Return immediate acknowledgment
        return {"status": "received"}

    except Exception as e:
        error_response = MCPResponse(
            id=request.id,
            error={"code": -32603, "message": f"Internal error: {str(e)}"},
        )
        if session_id in sse_sessions:
            await sse_sessions[session_id].put(error_response.dict())
        return {"status": "error", "message": str(e)}


# Custom SSE heartbeat endpoint for monitoring
@app.get("/sse-heartbeat")
async def sse_heartbeat():
    """Custom SSE heartbeat endpoint for monitoring"""

    async def event_generator():
        yield f"data: {json.dumps({'type': 'connection', 'status': 'connected'})}\n\n"

        while True:
            try:
                await asyncio.sleep(1)
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


# MCP classes moved to top of file for proper import order


# Test-only endpoint for backward compatibility with existing tests
# NOTE: This is NOT part of MCP standard and should only be used for testing
@app.post("/mcp")
async def mcp_test_endpoint(request: MCPRequest):
    """Test-only MCP JSON-RPC 2.0 endpoint for backward compatibility"""
    try:
        if request.method == "initialize":
            return MCPResponse(
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
                                    },
                                    "env_vars": {"type": "object"},
                                    "pull_policy": {
                                        "type": "string",
                                        "enum": ["always", "never"],
                                        "default": "always",
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
                                    "driver": {"type": "string", "default": "local"},
                                },
                                "required": ["name"],
                            },
                        },
                        {
                            "name": "docker_health",
                            "description": "Check Docker daemon health",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            )

        elif request.method == "tools/call":
            if not request.params:
                return MCPResponse(
                    id=request.id, error={"code": -32602, "message": "Missing params"}
                )
            tool_name = request.params.get("name")
            tool_args = request.params.get("arguments", {})

            if tool_name == "run_container":
                result = await mcp_run_container(tool_args)
            elif tool_name == "create_volume":
                result = await mcp_create_volume(tool_args)
            elif tool_name == "docker_health":
                result = await mcp_docker_health(tool_args)
            else:
                return MCPResponse(
                    id=request.id,
                    error={"code": -32601, "message": f"Method not found: {tool_name}"},
                )

            return MCPResponse(
                id=request.id, result={"content": [{"type": "text", "text": result}]}
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


if __name__ == "__main__":
    import uvicorn

    # Run with both REST API and MCP on the same port
    print(
        "🚀 Starting integrated server with both REST API and standard MCP on port 8000"
    )
    print("  - REST API: http://localhost:8000/run")
    print("  - MCP SSE (standard): http://localhost:8000/sse")
    print("  - MCP Messages (standard): http://localhost:8000/messages")
    print("  - MCP Test (legacy): http://localhost:8000/mcp [TEST ONLY]")
    print("  - SSE Heartbeat: http://localhost:8000/sse-heartbeat")
    print("  - Health: http://localhost:8000/health")
    print("  - Docs: http://localhost:8000/docs")

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
