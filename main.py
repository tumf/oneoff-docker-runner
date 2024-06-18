from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import docker
import os

# envvars
os.environ["DOCKER_HOST"] = "tcp://192.168.99.100:2376"
os.environ["DOCKER_TLS_VERIFY"] = "1"
os.environ["DOCKER_CERT_PATH"] = "/path/to/certs"

app = FastAPI()
client = docker.from_env()


class AuthConfig(BaseModel):
    username: str
    password: str
    email: str = None
    serveraddress: str = "https://index.docker.io/v1/"


class RunContainerRequest(BaseModel):
    image: str
    command: list = None
    entrypoint: str = None
    env_vars: dict = {}
    auth_config: AuthConfig = None


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

        # Run the container
        container = client.containers.run(
            request.image,
            command=request.command,
            entrypoint=request.entrypoint,
            environment=request.env_vars,
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

        return {"status": "success", "stdout": stdout_output, "stderr": stderr_output}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
