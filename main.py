from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal
import docker
import os
import base64
import tempfile
import shutil
import time

app = FastAPI()

docker_host = os.getenv("DOCKER_HOST", "unix://var/run/docker.sock")
tls_verify = os.getenv("DOCKER_TLS_VERIFY", "0")
cert_path = os.getenv("DOCKER_CERT_PATH", None)

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


class AuthConfig(BaseModel):
    username: str = Field(
        ..., example="your-username", description="Docker registry username"
    )
    password: str = Field(
        ..., example="your-password", description="Docker registry password"
    )
    email: Optional[str] = Field(
        None, example="your-email@example.com", description="Docker registry email"
    )
    serveraddress: str = Field(
        "https://index.docker.io/v1/",
        example="https://index.docker.io/v1/",
        description="Docker registry server address",
    )


class VolumeConfig(BaseModel):
    content: str|None = Field(
        None,
        example="base64encodedcontent",
        description="Base64 encoded content for the volume",
    )
    response: Optional[bool] = Field(
        False,
        example=True,
        description="Whether to return the volume",
    )
    type: Literal["file", "directory"] = Field(
        ...,
        example="file",
        description="Type of the volume",
    )


class VolumeResponse(BaseModel):
    content: str | None = Field(
        None,
        example="base64encodedcontent",
        description="Base64 encoded content for the volume",
    )
    type: Literal["file", "directory"] = Field(
        ...,
        example="file",
        description="Type of the volume",
    )


class RunContainerRequest(BaseModel):
    image: str = Field(..., example="alpine:latest", description="Docker image to run")
    command: Optional[List[str]|str] = Field(
        None,
        example=["echo", "Hello, World!"],
        description="Command to run in the container",
    )
    entrypoint: Optional[List[str]|str] = Field(
        None, example=["/bin/sh", "-c"], description="Entrypoint for the container"
    )
    env_vars: Optional[Dict[str, str]] = Field(
        None,
        example={"MY_VAR": "value"},
        description="Environment variables for the container",
    )
    auth_config: Optional[AuthConfig] = Field(
        None, description="Authentication configuration for pulling the image"
    )
    volumes: Optional[Dict[str, VolumeConfig]] = Field(
        None,
        example={
            "vol-1:/mnt/hoge.txt:ro": {
                "type": "file",
                "content": "VGhpcyBpcyB0aGUgY29udGVudCBvZiBob2dlLnR4dA=="
            },
            "vol-2:/mnt/data": {
                "type": "directory",
                "content": "H4sIAAAAAAAAE2NgYGBgBGIGgA2BgYFV8EAAXxGH7gAAAA==",
                "response": True,
            },
        },
        description="Volumes to mount in the container",
    )


class RunContainerResponse(BaseModel):
    status: str = Field(
        ..., example="success", description="Status of the container run"
    )
    stdout: str = Field(
        ..., example="Hello, World!\n", description="Standard output from the container"
    )
    stderr: str = Field(
        ..., example="", description="Standard error output from the container"
    )
    volumes: Optional[Dict[str, VolumeResponse]] = Field(
        None,
        example={
            "/mnt/data": {
                "type": "directory",
                "content": "H4sIAAAAAAAAE2NgYGBgBGIGgA2BgYFV8EAAXxGH7gAAAA==",
                "response": True,
            },
            "/mnt/data/hoge.txt": {
                "type": "file",
                "content": "VGhpcyBpcyB0aGUgY29udGVudCBvZiBob2dlLnR4dA==",
            },
        },
        description="Contents of the volumes",
    )
    execution_time: float = Field(
        ..., example=1.234, description="Execution time in seconds"
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
        client.images.pull(request.image, auth_config=auth_config)

        # Prepare volumes
        volume_binds, response_volumes, temp_dirs = prepare_volumes(request.volumes)

        container = None
        try:
            # Run the container
            container = client.containers.run(
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
            response_volume_contents = collect_response_volumes(response_volumes, request.volumes)
        finally:
            # Cleanup container
            if container:
                container.remove()

            # Cleanup temp directories
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir)

        end_time = time.time()
        execution_time = end_time - start_time
        status = "success" if result['StatusCode'] == 0 else f"error: {result['StatusCode']}"
        return {
            "status": status,
            "stdout": stdout_output,
            "stderr": stderr_output,
            "volumes": response_volume_contents,
            "execution_time": execution_time,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def prepare_volumes(volumes):
    volume_binds = {}
    response_volumes = {}
    temp_dirs = []

    for volumes_key, vol_info in volumes.items():
        volumes_key_parts = volumes_key.split(":")
        container_path = volumes_key_parts[0]
        bind_option = volumes_key_parts[1] if len(volumes_key_parts) > 1 else "rw"
        vol_content = vol_info.content

        temp_dir = tempfile.mkdtemp()
        temp_dirs.append(temp_dir)

        # Decode the base64 content and write it to a temporary file or directory
        decoded_content = base64.b64decode(vol_content)
        if vol_info.type == "file":
            source_path = os.path.join(temp_dir, os.path.basename(container_path))
            with open(source_path, "wb") as f:
                f.write(decoded_content)
        elif vol_info.type == "directory":
            archive_path = os.path.join(temp_dir, "archive.tar.gz")
            with open(archive_path, "wb") as f:
                f.write(decoded_content)
            shutil.unpack_archive(archive_path, temp_dir)
            source_path = temp_dir

        if vol_info.response:
            response_volumes[container_path] = source_path

        volume_binds[source_path] = {"bind": container_path, "mode": bind_option}

    return volume_binds, response_volumes, temp_dirs

def get_container_logs(container):
    stdout_logs = container.logs(stdout=True, stderr=False)
    stderr_logs = container.logs(stdout=False, stderr=True)
    stdout_output = stdout_logs.decode('utf-8')
    stderr_output = stderr_logs.decode('utf-8')
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
                    "content": base64.b64encode(f.read()).decode("utf-8")
                }
        elif vol_info.type == "directory":
            archive_name = tempfile.mktemp(suffix=".tar.gz")
            shutil.make_archive(archive_name[:-7], "gztar", source_path)
            with open(archive_name, "rb") as f:
                response_volume_contents[container_path] = {
                    "type": "directory",
                    "content": base64.b64encode(f.read()).decode("utf-8")
                }
                os.remove(archive_name)
    return response_volume_contents

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="debug")
