from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal, Union, Any
import docker
import os
import base64
import tempfile
import shutil
import time

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
                status_code=503, 
                detail=f"Docker daemon is unavailable: {str(e)}"
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
        volume_binds, response_volumes, temp_dirs = prepare_volumes(request.volumes or {})
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


def prepare_volumes(volumes):
    volume_binds = {}
    response_volumes = {}
    temp_dirs = []
    
    if not volumes:
        return volume_binds, response_volumes, temp_dirs

    for volumes_key, vol_info in volumes.items():
        volumes_key_parts = volumes_key.split(":")
        container_path = volumes_key_parts[0]
        bind_option = volumes_key_parts[1] if len(volumes_key_parts) > 1 else "rw"

        if vol_info.type in ["file", "directory"]:
            vol_content = vol_info.content
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
                shutil.unpack_archive(archive_path, temp_dir)
                source_path = temp_dir
                print(f"wrote directory: {source_path}")
        elif vol_info.type == "volume":
            source_path = vol_info.name

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


def collect_response_volumes(response_volumes, volumes):
    response_volume_contents = {}
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
        return {"status": "ok", "docker_version": docker_info.get("ServerVersion", "unknown")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Docker daemon is unavailable: {str(e)}")


# MCP Tool Models
class ToolRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

class ToolResponse(BaseModel):
    content: List[Dict[str, str]]
    isError: Optional[bool] = False

# MCP Endpoints
@app.get("/mcp")
async def mcp_root():
    return {
        "name": "Docker Runner MCP Server",
        "version": "1.0.0",
        "tools": ["run_container", "create_volume", "docker_health"]
    }

@app.get("/mcp/tools")
async def list_mcp_tools():
    return {
        "tools": [
            {
                "name": "run_container",
                "description": "Run a Docker container",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string", "description": "Docker image name"},
                        "command": {"type": "array", "items": {"type": "string"}, "description": "Command to run"},
                        "env_vars": {"type": "object", "description": "Environment variables"},
                        "pull_policy": {"type": "string", "enum": ["always", "never"], "default": "always"}
                    },
                    "required": ["image"]
                }
            },
            {
                "name": "create_volume", 
                "description": "Create a Docker volume",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Volume name"},
                        "driver": {"type": "string", "default": "local", "description": "Volume driver"}
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "docker_health",
                "description": "Check Docker daemon health",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    }

@app.post("/mcp/tools/call")
async def call_mcp_tool(request: ToolRequest):
    try:
        if request.name == "run_container":
            return await mcp_run_container_tool(request.arguments)
        elif request.name == "create_volume":
            return await mcp_create_volume_tool(request.arguments)
        elif request.name == "docker_health":
            return await mcp_docker_health_tool(request.arguments)
        else:
            raise HTTPException(status_code=404, detail=f"Tool '{request.name}' not found")
    except Exception as e:
        return ToolResponse(
            content=[{"type": "text", "text": f"Error: {str(e)}"}],
            isError=True
        )

async def mcp_run_container_tool(args: Dict[str, Any]) -> ToolResponse:
    """Run a Docker container via MCP"""
    image = args.get("image")
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
        
        output = container.decode('utf-8').strip()
        return ToolResponse(
            content=[{"type": "text", "text": f"Container executed successfully. Output: {output}"}]
        )
    except Exception as e:
        raise Exception(f"Failed to run container: {str(e)}")

async def mcp_create_volume_tool(args: Dict[str, Any]) -> ToolResponse:
    """Create a Docker volume via MCP"""
    name = args.get("name")
    driver = args.get("driver", "local")
    
    try:
        volume = get_docker_client().volumes.create(name, driver=driver)
        return ToolResponse(
            content=[{"type": "text", "text": f"Volume '{name}' created successfully"}]
        )
    except Exception as e:
        raise Exception(f"Failed to create volume: {str(e)}")

async def mcp_docker_health_tool(args: Dict[str, Any]) -> ToolResponse:
    """Check Docker health via MCP"""
    try:
        info = get_docker_client().info()
        version = info.get("ServerVersion", "unknown")
        return ToolResponse(
            content=[{"type": "text", "text": f"Docker is healthy. Version: {version}"}]
        )
    except Exception as e:
        raise Exception(f"Docker health check failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    
    # Run with both REST API and MCP on the same port
    print("🚀 Starting integrated server with both REST API and MCP on port 8000")
    print("  - REST API: http://localhost:8000/run")
    print("  - MCP: http://localhost:8000/mcp")
    print("  - Health: http://localhost:8000/health")
    print("  - Docs: http://localhost:8000/docs")

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
