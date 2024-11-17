from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal, Union
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
            client.images.pull(request.image, auth_config=auth_config)
        # Prepare volumes
        volume_binds, response_volumes, temp_dirs = prepare_volumes(request.volumes)
        print(f"volume_binds: {volume_binds}")
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
    bind_option = None

    for volumes_key, vol_info in volumes.items():
        volumes_key_parts = volumes_key.split(":")
        container_path = volumes_key_parts[0]
        if vol_info.type in ["file", "directory"]:
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

        volume_binds[source_path] = {"bind": container_path}
        if bind_option:
            volume_binds[source_path]["mode"] = bind_option
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
    container = client.containers.run(
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
    # volume = client.volumes.get(request.name)
    # if not volume:
    volume = client.volumes.create(
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
    docker_info = client.info()
    if not docker_info:
        raise HTTPException(status_code=500, detail="Docker daemon is unavailable")

    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="debug")
