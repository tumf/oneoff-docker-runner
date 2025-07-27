# OneOffDockerRunner

OneOffDockerPython is a REST API service built with FastAPI that allows you to run Docker containers with one-off commands. It supports pulling images from Docker registries with authentication, setting environment variables, and customizing command and entrypoint.

## Features

* Run Docker containers with one-off commands
* Pull images from private Docker registries with authentication
* Set environment variables for container execution
* Customize command and entrypoint for container execution
* Capture and return both stdout and stderr output
* Create Docker volume with base64 tar.gz image
* **Integrated MCP (Model Context Protocol) server with JSON-RPC 2.0 support on the same port**

## Requirements

* Python 3.10 or higher
* Docker
* `uv` (recommended) or `pip` for package management
* Dependencies managed via `pyproject.toml`

## Run on localhost 8223 port

```bash
docker run --rm -p 8223:8001 -v /var/run/docker.sock:/var/run/docker.sock ghcr.io/tumf/oneoff-docker-runner
```

Run One-off docker command like as:

```bash
curl -X 'POST' \
  'http://0.0.0.0:8223/run' \
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

### Option 1: Using uv (Recommended)

1. Install `uv` if you haven't already:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone the repository:

```bash
git clone https://github.com/tumf/oneoff-docker-runner.git
cd oneoff-docker-runner
```

3. Install dependencies and create virtual environment:

```bash
uv sync
```

### Option 2: Using pip

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
pip install -e .
```

### Environment Configuration

Create a `.env` file in the project root (if needed) to set environment variables for Docker:

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

This starts both the REST API and MCP server on port 8001:
- REST API endpoints: `http://localhost:8001/run`,          `/volume`,          `/health`
- MCP JSON-RPC endpoint: `http://localhost:8001/mcp`
- API Documentation: `http://localhost:8001/docs`

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

### MCP Server (Model Context Protocol)

Execute Docker containers directly from AI clients (Claude Desktop, Cursor, etc.).

#### 1. Start Server

```bash
python main.py
```

The server accepts MCP JSON-RPC 2.0 requests at `http://localhost:8001/mcp` .

#### 2. AI Client Configuration

**Claude Desktop:**
Add to `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "docker-runner": {
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

**Cursor:**
Add to Cursor settings under "MCP Servers":
- Name: `docker-runner`  
- URL: `http://localhost:8001/mcp`

**Other MCP-compatible clients:**
Configure MCP server URL as `http://localhost:8001/mcp` .

#### 3. Available Functions

- **run_container**: Execute Docker containers
- **create_volume**: Create Docker volumes  
- **docker_health**: Check Docker environment status

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

## Quick Start

### 1. Start the Server

```bash
# Start the integrated server (both REST API and MCP on port 8001)
uv run python main.py

# Or with pip (if using pip instead of uv)
python main.py
```

Output:

```
🚀 Starting integrated server with both REST API and MCP on port 8001
  - REST API: http://localhost:8001/run
  - MCP JSON-RPC: http://localhost:8001/mcp
  - Health: http://localhost:8001/health
  - Docs: http://localhost:8001/docs
```

### 2. Test REST API

```bash
# Check server health
curl http://localhost:8001/health

# Run a simple container
curl -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d '{
    "image": "alpine:latest",
    "command": ["echo", "Hello from REST API!"],
    "pull_policy": "always"
  }'

# Run container with environment variables
curl -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d '{
    "image": "alpine:latest", 
    "command": ["sh", "-c", "echo \"Env var: $TEST_VAR\""],
    "env_vars": {"TEST_VAR": "production"},
    "pull_policy": "always"
  }'
```

### 3. Test MCP (Using Python Client)

Create a test file `test_mcp.py` :

```python
#!/usr/bin/env python3
import asyncio
import requests
from fastmcp import Client

async def test_mcp():
    print("🔧 Testing MCP API")
    
    # Check if server is running
    try:
        response = requests.get("http://localhost:8001/health", timeout=5)
        print(f"✅ Server is running: {response.json()}")
    except:
        print("❌ Server not running. Start with: uv run python main.py")
        return
    
    try:
        # Connect to MCP server
        async with Client("http://localhost:8001/mcp") as client:
            print("✅ Connected to MCP server!")
            
            # List available tools
            tools = await client.list_tools()
            print(f"🛠️ Available tools: {[tool.name for tool in tools.tools]}")
            
            # Test container run
            result = await client.call_tool("run_container", {
                "image": "alpine:latest",
                "command": ["echo", "Hello from MCP!"],
                "pull_policy": "always"
            })
            print(f"🐳 Container result: {result.text}")
            
            # Test volume creation
            result = await client.call_tool("create_volume", {
                "name": "mcp-test-volume",
                "driver": "local"
            })
            print(f"🗃️ Volume result: {result.text}")
            
            # Test Docker health
            result = await client.call_tool("docker_health", {})
            print(f"💊 Health result: {result.text}")
            
    except Exception as e:
        print(f"❌ MCP test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp())
```

Run the test:

```bash
uv run python test_mcp.py
```

### 4. Test MCP Manually (JSON-RPC 2.0)

You can also test the MCP endpoint directly using curl:

```bash
# Test MCP initialize
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'

# Test MCP tools list
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'

# Test run_container tool
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "run_container", "arguments": {"image": "alpine:latest", "command": ["echo", "Hello from MCP!"]}}}'

# Test docker_health tool
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "docker_health", "arguments": {}}}'
```

## Architecture

The integrated server provides:

- **Single Port (8001)**: Both REST API and MCP on the same port
- **FastAPI Integration**: Automatic OpenAPI documentation at `/docs`
- **MCP Implementation**: Manual JSON-RPC 2.0 protocol implementation
- **JSON-RPC Transport**: MCP over JSON-RPC 2.0 at `/mcp`
- **Unified Logging**: All requests logged through the same system

This design eliminates the need to manage multiple servers while providing full compatibility with both traditional HTTP clients and MCP-aware AI systems.
