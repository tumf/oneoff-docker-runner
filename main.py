from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import docker
import os
import base64
import tempfile
import shutil

app = FastAPI()
client = docker.from_env()


class AuthConfig(BaseModel):
    username: str
    password: str
    email: str = None
    serveraddress: str = "https://index.docker.io/v1/"


class VolumeConfig(BaseModel):
    content: str


class RunContainerRequest(BaseModel):
    image: str
    command: list = None
    entrypoint: str = None
    env_vars: dict = {}
    auth_config: AuthConfig = None
    volumes: dict = {}


@app.post("/run")
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
            vol_content = vol_info["content"]

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
