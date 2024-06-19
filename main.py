from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import docker
import os
import base64
import tempfile
import shutil

app = FastAPI()

# 環境変数が設定されていない場合のデフォルト設定
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
    content: str = Field(
        ...,
        example="base64encodedcontent",
        description="Base64 encoded content for the volume",
    )


class RunContainerRequest(BaseModel):
    image: str = Field(..., example="alpine:latest", description="Docker image to run")
    command: Optional[List[str]] = Field(
        None,
        example=["echo", "Hello, World!"],
        description="Command to run in the container",
    )
    entrypoint: Optional[str] = Field(
        None, example="/bin/sh", description="Entrypoint for the container"
    )
    env_vars: Dict[str, str] = Field(
        {},
        example={"MY_VAR": "value"},
        description="Environment variables for the container",
    )
    auth_config: Optional[AuthConfig] = Field(
        None, description="Authentication configuration for pulling the image"
    )
    volumes: Dict[str, VolumeConfig] = Field(
        {}, description="Volumes to mount in the container"
    )


@app.post(
    "/run",
    summary="Run a Docker container",
    description="Run a Docker container with the specified configuration",
)
async def run_container(request: RunContainerRequest):
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
        volume_binds = {}
        response_volumes = {}
        temp_dirs = []

        for host_path, vol_info in request.volumes.items():
            container_path, *bind_options = host_path.split(":")
            bind_options = bind_options or ["rw"]
            vol_content = vol_info.content

            temp_dir = tempfile.mkdtemp()
            temp_dirs.append(temp_dir)

            # Decode the base64 content and write it to a temporary file or directory
            decoded_content = base64.b64decode(vol_content)
            archive_path = os.path.join(temp_dir, "archive.tar.gz")
            with open(archive_path, "wb") as f:
                f.write(decoded_content)
            shutil.unpack_archive(archive_path, temp_dir)

            source_path = temp_dir
            if os.path.isfile(os.path.join(temp_dir, os.path.basename(container_path))):
                source_path = os.path.join(temp_dir, os.path.basename(container_path))

            # Prepare volume bind options
            volume_binds[source_path] = ":".join([container_path] + bind_options)

            # Collect response volume information
            if "ro" not in bind_options:
                response_volumes[container_path] = source_path

        # Run the container
        container = client.containers.run(
            request.image,
            command=request.command,
            entrypoint=request.entrypoint,
            environment=request.env_vars,
            volumes=volume_binds,
            detach=True,
            remove=True,
        )

        # Collect logs
        logs = container.logs(stdout=True, stderr=True, stream=True)
        stdout_output = ""
        stderr_output = ""
        for log in logs:
            log_str = log.decode("utf-8")
            if log_str.startswith("STDERR:"):
                stderr_output += log_str[7:]
            else:
                stdout_output += log_str

        # Collect response volumes content
        response_volume_contents = {}
        for container_path, source_path in response_volumes.items():
            archive_name = tempfile.mktemp(suffix=".tar.gz")
            shutil.make_archive(archive_name[:-7], "gztar", source_path)
            with open(archive_name, "rb") as f:
                response_volume_contents[container_path] = base64.b64encode(
                    f.read()
                ).decode("utf-8")

        # Cleanup temp directories
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir)

        return {
            "status": "success",
            "stdout": stdout_output,
            "stderr": stderr_output,
            "volumes": response_volume_contents,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
