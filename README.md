# OneOffDockerRunner

OneOffDockerPython is a REST API service built with FastAPI that allows you to run Docker containers with one-off commands. It supports pulling images from Docker registries with authentication, setting environment variables, and customizing command and entrypoint.

## Features

* Run Docker containers with one-off commands
* Pull images from private Docker registries with authentication
* Set environment variables for container execution
* Customize command and entrypoint for container execution
* Capture and return both stdout and stderr output
* Create Docker volume with base64 tar.gz image
* **Integrated MCP (Model Context Protocol) server with SSE support on the same port**

## Requirements

* Python 3.9 or higher
* Docker
* FastAPI
* Uvicorn
* Docker-py
* FastMCP (for MCP server functionality)

## Run on localhost 8222 port

```bash
docker run --rm -p 8222:8000 -v /var/run/docker.sock:/var/run/docker.sock ghcr.io/tumf/oneoff-docker-runner
```

Run One-off docker command like as:

```bash
curl -X 'POST' \
  'http://0.0.0.0:8222/run' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "image": "alpine:latest",
  "command": [
     "/test.sh"
  ],
  "volumes": {
    "/app/data": {
      "content": "H4sIAGq4eGYAA0tJLEnUZ6AtMDAwMDc1VQDTZhDawMgEQkOBgqGJmbGZobGJobGBgoGhkaGBGYOCKY3dBQalxSWJRUCnlJTmpuFTB1SWhk8B1B9wehSMglEwCgY5AADBaWLyAAYAAA==",
      "response": true,
      "type": "directory"
    },
    "/test.sh:ro": {
      "mode" : "0755",
      "content": "IyEvYmluL2FzaAoKZWNobyAiSGVsbG8sIFdvcmxkISIgPiAvYXBwL2RhdGEvdGVzdC50eHQ=",
      "type": "file"
    }
  }
}'
```

## Installation

1. Clone the repository:
    

```bash
    git clone https://github.com/tumf/oneoff-docker-runner.git
    cd oneoff-docker-runner
```

2. Create and activate a virtual environment:
    

```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

3. Install the dependencies:
    

```bash
    pip install -r requirements.txt
```

4. Create a `.env` file in the project root (if needed) to set environment variables for Docker:
    

```env
    DOCKER_HOST=tcp://your-docker-host:2376
    DOCKER_TLS_VERIFY=1
    DOCKER_CERT_PATH=/path/to/certs
```

## Usage

### Integrated Server (REST API + MCP on Same Port)

1. Start the integrated server:

```bash
python main.py
```

This starts both the REST API and MCP server on port 8000:
- REST API endpoints: `http://localhost:8000/run`,   `/volume`,   `/health`
- MCP SSE endpoint: `http://localhost:8000/mcp`
- API Documentation: `http://localhost:8000/docs`

### REST API Usage

2. Send a POST request to the `/run` endpoint with the following JSON body to run a Docker container:

```json
{
    "image": "alpine:latest",
    "command": ["echo", "Hello, World!"],
    "env_vars": {
        "MY_VAR": "value"
    },
    "auth_config": {
        "username": "your-username",
        "password": "your-password",
        "email": "your-email@example.com",
        "serveraddress": "https://index.docker.io/v1/"
    }
}
```

3. The API will return a JSON response with the stdout and stderr output from the container:

```json
{
    "status": "success",
    "stdout": "Hello, World!\n",
    "stderr": ""
}
```

### MCP Integration (Model Context Protocol)

The integrated server automatically provides MCP functionality alongside the REST API.

#### Available MCP Tools

All REST API endpoints are automatically available as MCP tools:
- `run`: Run Docker containers with full configuration support
- `volume`: Create and manage Docker volumes  
- `health`: Check Docker daemon health

#### Using the MCP Server

The MCP server can be used with any MCP-compatible client:

```python
from fastmcp import Client
import asyncio

async def main():
    # Connect to the integrated MCP server
    async with Client("http://localhost:8000/mcp") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools.tools]}")
        
        # Run a Docker container
        result = await client.call_tool("run", {
            "image": "alpine:latest",
            "command": ["echo", "Hello from MCP!"],
            "env_vars": {"TEST": "value"}
        })
        print(f"Container output: {result.text}")
        
        # Check Docker health
        health = await client.call_tool("health", {})
        print(f"Docker status: {health.text}")

asyncio.run(main())
```

#### MCP Configuration for AI Clients

For AI clients like Claude Desktop, add this configuration to your MCP settings:

```json
{
  "mcpServers": {
    "docker-runner": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

#### Example Client

Run the example client to test both REST API and MCP functionality:

```bash
python example_client.py
```

#### Running Tests

Test the MCP functionality:

```bash
python -m pytest tests/test_mcp_server.py -v
```

### POST /run

Execute one-off docker container

#### Request Example

Use the following `curl` command to make a POST request to the `/run` endpoint. Replace the placeholders with your actual image details and authentication information.

```json
{
  "image": "your-registry/your-image:tag",
  "command": ["echo", "Hello, World!"],
  "env_vars": {
    "MY_VAR": "value"
  },
  "pull_policy": "always"
}
```

#### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| pull_policy | string | No | "always" | Image pull policy. Possible values: "always" (always pull image), "never" (use local image only) |

#### Response Example

The API will return a JSON response with the `stdout` and `stderr` output from the container:

```json
{
  "status": "success",
  "stdout": "Hello, World!\n",
  "stderr": ""
}
```

This example demonstrates how to use the API to run a one-off Docker container with specified image, command, environment variables, and authentication information. The response will include the standard output and standard error from the executed command within the container.

### POST /volume

Create Docker volume

```bash
$ tar czf tmp.tar.gz target_dir
$ base64 < tmp.tar.gz
```

#### Request Example

Create `my-volume` Docker volume with content.

```json
{
  "name": "my-volume",
  "content": "H4sIAIQOfmYAA+2TMQ7DIAxFcxRO0Biw4TxIabYsjSPl+HUhStWFjdCqfgxeLPHh6U+J0zi0BQAikckzlAkOyzwwFoOPCBEoGLBOzmCoca7MtnJ6SBTelrm2J2tzbeF4xzl/hOnln+8r2xvv3OYO+Y+AWPNPb/8RxL+PVvxDmzif/Ln/rL53CKUbZ//dt/Tfl/6T9v8KsvreIRRFUZTLeQL28PKYAA4AAA=="
}
```

#### Response Example

```json
{
  "status": "success",
  "detail": "success"
}
```

## Docker Registry Authentication

### Docker Hub

For Docker Hub, you can use your Docker Hub username and password:

```json
{
    "image": "your-dockerhub-repo/your-image:tag",
    "auth_config": {
        "username": "your-username",
        "password": "your-password",
        "email": "your-email@example.com",
        "serveraddress": "https://index.docker.io/v1/"
    }
}
```

### Google Container Registry (GCR)

For Google Container Registry, you need to use a service account key. Here is how to set it up:

1. **Create a service account in the Google Cloud Console:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Navigate to **IAM & Admin** > **Service Accounts**.
   - Click on **+ CREATE SERVICE ACCOUNT** at the top.
   - Enter a name for the service account and click **CREATE AND CONTINUE**.
   - Grant the service account the necessary permissions (e.g., `Storage Admin` for accessing GCR).
   - Click **DONE**.

2. **Download the service account key as a JSON file:**
   - Find the created service account in the list.
   - Click the **Actions** (three dots) button and select **Manage keys**.
   - Click on **ADD KEY** > **Create new key**.
   - Select **JSON** and click **CREATE**.
   - The JSON file will be downloaded to your computer.

3. **Encode the JSON key file in base64:**
   - Open the downloaded JSON file.
   - Encode the entire contents of this JSON file to base64.

For example, on a Unix-based system (Linux, macOS), you can use the following command to encode the JSON file:

```bash
base64 /path/to/your-service-account-file.json
```

On Windows, you can use PowerShell:

```powershell
[Convert]::ToBase64String([System.IO.File]::ReadAllBytes("path\to\your-service-account-file.json"))
```

4. **Use the base64 encoded string for authentication:**
   - Use the base64 encoded string as the `password` in the `auth_config` .

Here is an example of what the service account JSON key file might look like before encoding:

```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "somekeyid",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account-email@your-project-id.iam.gserviceaccount.com",
  "client_id": "someclientid",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account-email%40your-project-id.iam.gserviceaccount.com"
}
```

### Example Request

Use the base64 encoded string as shown below:

```json
{
    "image": "gcr.io/your-project/your-image:tag",
    "auth_config": {
        "username": "_json_key",
        "password": "your-base64-encoded-service-account-json-key-content",
        "email": "your-service-account-email@your-project-id.iam.gserviceaccount.com",
        "serveraddress": "https://gcr.io"
    }
}
```

In this example, replace `your-base64-encoded-service-account-json-key-content` and other placeholder values with the actual base64 encoded string and other values from your downloaded service account JSON file.

### GitHub Container Registry (GHCR)

For GitHub Container Registry, you need to use your GitHub username and a Personal Access Token (PAT):

	1.	Generate a Personal Access Token in your GitHub account settings with the read:packages scope.
	2.	Use your GitHub username and the generated PAT for authentication.

```json
  {
    "image": "ghcr.io/your-username/your-image:tag",
    "auth_config": {
        "username": "your-github-username",
        "password": "your-github-pat",
        "email": "your-email@example.com",
        "serveraddress": "https://ghcr.io"
    }
}
```

## Quick Start Demo

For a quick demonstration of both REST API and MCP functionality:

```bash
python demo_integrated.py
```

This will start the integrated server and show examples of how to use both interfaces.

## Architecture

The integrated server provides:

- **Single Port (8000)**: Both REST API and MCP on the same port
- **FastAPI Integration**: Automatic OpenAPI documentation at `/docs`
- **MCP Auto-generation**: All REST endpoints automatically available as MCP tools
- **SSE Transport**: MCP over Server-Sent Events at `/mcp`
- **Unified Logging**: All requests logged through the same system

This design eliminates the need to manage multiple servers while providing full compatibility with both traditional HTTP clients and MCP-aware AI systems.
