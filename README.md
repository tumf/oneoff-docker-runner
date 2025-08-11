# OneOffDockerRunner

OneOffDockerPython is a REST API service built with FastAPI that allows you to run Docker containers with one-off commands. It supports pulling images from Docker registries with authentication, setting environment variables, and customizing command and entrypoint.

## Features

* Run Docker containers with one-off commands
* Pull images from private Docker registries with authentication
* Set environment variables for container execution
* Customize command and entrypoint for container execution
* Capture and return both stdout and stderr output
* Create Docker volume with base64 tar.gz image
* **Separate MCP (Model Context Protocol) server with Streamable HTTP transport**
* Bind mount host files/directories into the container (`type: "host"`)

## Requirements

* Python 3.10 or higher
* Docker
* `uv` (recommended) or `pip` for package management
* Dependencies managed via `pyproject.toml`

## Run on localhost ports

```bash
docker run --rm -p 8000:8000 -p 8001:8001 -v /var/run/docker.sock:/var/run/docker.sock ghcr.io/tumf/oneoff-docker-runner
```

Run One-off docker command like as:

```bash
curl -X 'POST' \
  'http://0.0.0.0:8000/run' \
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

### Dual Server Architecture

1. Start both servers:

```bash
# Option 1: Start both servers manually
python main.py &    # REST API on port 8000
python mcp.py &     # MCP Server on port 8001

# Option 2: Use the start script (recommended)
./start.sh

# Option 3: Use Docker (includes both servers)
docker run -d --name oneoff-docker-runner \
  -p 8000:8000 -p 8001:8001 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  oneoff-docker-runner
```

This starts:
- **REST API** (main.py): `http://localhost:8000` - `/run`,          `/volume`,          `/health`,          `/docs`
- **MCP Server** (mcp.py): `http://localhost:8001` - `/mcp` (Streamable HTTP)

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

Execute Docker containers directly from AI clients (Claude Desktop, Cursor, n8n, etc.) using MCP Streamable HTTP transport.

#### 1. Start Server

```bash
# Both servers
./start.sh

# Or just MCP server
python mcp.py
```

The MCP server provides Streamable HTTP transport at:
- **MCP Endpoint**: `http://localhost:8001/mcp`
- **Protocol**: MCP Streamable HTTP (2024-11-05)
- **Content Types**: JSON and Server-Sent Events (SSE)

#### 2. AI Client Configuration

**n8n MCP Client Tool:**
- MCP Endpoint: `http://localhost:8001/mcp`
- Authentication: None
- Tools to Include: All

**Claude Desktop:**
Add to `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "docker-runner": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-stdio", "http://localhost:8001/mcp"]
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
- **list_containers**: List Docker containers
- **list_images**: List Docker images

### POST /run

Run a one-off Docker container.

All parameters conform to the Pydantic schemas in `main.py` ( `RunContainerRequest` , `AuthConfig` , `VolumeConfig` ). The following documents every field.

#### Request Body (RunContainerRequest)

| Field | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| image | string | Yes | - | Docker image to run (e.g., `alpine:latest` ) |
| command | string or string[] | No | null | Command to run in the container (e.g., `["echo", "Hello"]` or `"echo Hello"` ) |
| entrypoint | string or string[] | No | null | Entrypoint for the container (e.g., `["/bin/sh", "-c"]` ) |
| env_vars | object<string, string|number|boolean> | No | null | Environment variables passed to the container |
| pull_policy | string (enum: "always" or "never") | No | "always" | Image pull policy. "always": always pull image, "never": use local image only |
| auth_config | object | No | null | Registry auth. See AuthConfig below |
| volumes | object<string, VolumeConfig> | No | null | Mount settings. Keys are container-side paths (optional suffix `:ro` / `:rw` , default `rw` ) |

Notes for volumes key:
- Key format: `<container_path>[:ro|:rw]`, e.g.,       `/app/data`,       `/etc/config:ro`
- Bind source is:
  - a temporary host directory/file expanded from `content` for `type=file|directory`
  - an existing Docker volume name when `type=volume`
  - an absolute host path provided via `host_path` when `type=host`

##### AuthConfig

| Field | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| username | string | Yes | - | Registry username (for GCR use `_json_key` ) |
| password | string | Yes | - | Registry password (for GCR use the entire service account JSON encoded in base64) |
| email | string | No | null | Registry email |
| serveraddress | string | No | `https://index.docker.io/v1/` | Registry server address |

##### VolumeConfig

| Field | Type | Required | Default | Applies to | Description |
|------|------|----------|---------|------------|-------------|
| type | string (enum: "file", "directory", "volume", "host") | Yes | - | all | Volume definition type |
| content | base64 string | Conditionally | null | file, directory | For `file` , provide raw file bytes (base64). For `directory` , provide a `tar.gz` (base64) of the directory |
| response | boolean | No | false | file, directory | Whether to return the mounted content in the API response after execution |
| mode | string (e.g. "0644") | No | null | file | File permission for the created file |
| name | string | Conditionally | null | volume | Existing Docker volume name (required when `type=volume` ) |
| host_path | string | Conditionally | null | host | Absolute host path to bind mount (required when `type=host` ) |

Directory content format:
- For `directory`,  `content` must be a base64 of a `tar.gz` archive created from the target directory (e.g.,       `tar czf dir.tar.gz dir && base64 < dir.tar.gz`).

#### Request Example

```json
{
  "image": "alpine:latest",
  "command": ["/bin/sh", "-c", "echo Hello > /mnt/out.txt && ls -l /mnt"],
  "entrypoint": null,
  "env_vars": {"MY_VAR": "value", "FLAG": true, "NUM": 123},
  "pull_policy": "always",
  "auth_config": {
    "username": "your-username",
    "password": "your-password",
    "email": "your-email@example.com",
    "serveraddress": "https://index.docker.io/v1/"
  },
  "volumes": {
    "/mnt/in:ro": {
      "type": "directory",
      "content": "<base64-of-tar-gz>",
      "response": false
    },
    "/mnt/out": {
      "type": "directory",
      "content": "<base64-of-empty-tar-gz>",
      "response": true
    },
    "/mnt/script.sh:ro": {
      "type": "file",
      "mode": "0755",
      "content": "<base64-of-script>"
    }
  }
}
```

Notes:
- When `pull_policy` is `always`, the image is pulled and `auth_config` is used if provided.
- For `type=volume` with `response: true`, the content is not returned in the response (current behavior).
- For `type=host`,  `response` is not supported and will be rejected.

#### Host bind example

Minimal request to bind a host file and directory:

```json
{
  "image": "alpine:latest",
  "command": ["sh", "-c", "ls -la /app && cat /app/host.txt || true"],
  "volumes": {
    "/app/host.txt:ro": { "type": "host", "host_path": "/absolute/path/to/host.txt" },
    "/app/data": { "type": "host", "host_path": "/absolute/path/to/dir" }
  }
}
```

#### Response Body (RunContainerResponse)

| Field | Type | Description |
|------|------|-------------|
| status | string | `success` or `error: <exit_code>` |
| stdout | string | Full standard output |
| stderr | string | Full standard error output |
| volumes | object<string, {type: "file"|"directory", content: base64 string}> | Base64-encoded content for `file` / `directory` where `response: true` was requested |
| execution_time | number | Execution time in seconds (float) |

Error handling:
- If the container exits with a non-zero code, the API returns HTTP 500, and the above object is included in the `detail` field.

#### Response Example

```json
{
  "status": "success",
  "stdout": "Hello, World!\n",
  "stderr": "",
  "volumes": {
    "/mnt/out": {
      "type": "directory",
      "content": "<base64-of-tar-gz>"
    }
  },
  "execution_time": 1.234
}
```

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

### 1. Start Both Servers

```bash
# Start both REST API and MCP servers
./start.sh

# Or with uv
uv run ./start.sh

# Or manually
uv run python main.py &    # REST API on port 8000
uv run python mcp.py &     # MCP Server on port 8001
```

Output:

```
Starting Docker Runner servers...
- REST API (main.py) on port 8000
- MCP Server (mcp.py) on port 8001
```

### 2. Test REST API

```bash
# Check server health
curl http://localhost:8000/health

# Run a simple container
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "image": "alpine:latest",
    "command": ["echo", "Hello from REST API!"],
    "pull_policy": "always"
  }'

# Run container with environment variables
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "image": "alpine:latest", 
    "command": ["sh", "-c", "echo \"Env var: $TEST_VAR\""],
    "env_vars": {"TEST_VAR": "production"},
    "pull_policy": "always"
  }'
```

### 3. Test MCP Streamable HTTP

Test the MCP Streamable HTTP implementation:

```bash
# Initialize MCP connection
curl -X POST "http://localhost:8001/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {"tools": {}},
      "clientInfo": {"name": "test-client", "version": "1.0.0"}
    }
  }'

# List available tools
curl -X POST "http://localhost:8001/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list"
  }'

# Run a container via MCP
curl -X POST "http://localhost:8001/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "run_container",
      "arguments": {
        "image": "alpine:latest",
        "command": ["echo", "Hello from MCP!"]
      }
    }
  }'

# Test SSE (Server-Sent Events) response
curl -X POST "http://localhost:8001/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "docker_health",
      "arguments": {}
    }
  }'
```

### 4. Integration with AI Clients

The MCP server is compatible with standard MCP clients:

**n8n Integration:**
1. Add MCP Client Tool node to your workflow
2. Configure MCP Endpoint: `http://localhost:8001/mcp`
3. Set Authentication to None
4. Select Tools to Include: All
5. Use the available tools (run_container, create_volume, docker_health, list_containers, list_images) in your workflows

### n8n MCP Client Node Compatibility

This server has been optimized for compatibility with n8n's MCP Client Node:

**Enhanced Features:**
- **Accept Header Flexibility**: Supports both `text/event-stream` and mixed content types like `application/json, text/event-stream`
- **Automatic Initialization**: SSE connections automatically perform MCP initialization sequence
- **Auto Tools Discovery**: Tools list is immediately sent upon SSE connection for instant availability
- **Streamable HTTP Support**: POST requests can return SSE responses based on Accept header
- **Enhanced CORS**: Full CORS support with extended headers for web-based clients

**Connection Modes:**
1. **SSE Mode** (GET /mcp): Long-lived connection with automatic tool discovery
2. **Streamable HTTP** (POST /mcp): Single request/response with optional SSE streaming
3. **Legacy HTTP** (POST /mcp): Standard JSON request/response

**Troubleshooting n8n Connection Issues:**

If tools/list is not loading in n8n MCP Client Node:

1. **Check Accept Headers**: Ensure your reverse proxy doesn't strip Accept headers
2. **Disable Compression**: For Traefik/NGINX, disable gzip for `/mcp` endpoints:
   

```nginx
   location /mcp {
       gzip off;
       proxy_buffering off;
       proxy_cache off;
   }
   ```

3. **HTTPS Requirements**: Use HTTPS in production (MCP clients often require it)
4. **Session Management**: Check logs for session creation and tool list transmission
5. **Network Paths**: Use container names, not localhost, in Docker environments

**Debug Commands:**

```bash
# Test SSE connection
curl -H "Accept: text/event-stream" http://localhost:8001/mcp

# Test tools/list via POST
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'

# Test with n8n-style Accept header
curl -X POST http://localhost:8001/mcp \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

**Claude Desktop/Cursor:**
Configure the MCP server in your client settings using the endpoint `http://localhost:8001/mcp` to enable AI-powered Docker container management.

## Architecture

The dual-server architecture provides:

- **REST API Server** (port 8000): Traditional HTTP REST API for direct integration
  - FastAPI with automatic OpenAPI documentation at `/docs`
  - Endpoints: `/run`,          `/volume`,          `/health`
  - Direct Docker container execution
  
- **MCP Server** (port 8001): Model Context Protocol for AI agent integration
  - **MCP Streamable HTTP** (2024-11-05 specification)
  - Single endpoint: `/mcp` for all MCP communication
  - **Dual Response Types**: JSON and SSE based on `Accept` header
  - **Session Management**: `Mcp-Session-Id` header support
  - **Tools**: run_container, create_volume, docker_health, list_containers, list_images

- **Unified Management**: Both servers managed via `start.sh` script
  - Concurrent execution with proper signal handling
  - Graceful shutdown for both processes
  - Docker integration with shared socket mounting

This design provides maximum flexibility, allowing direct REST API usage for traditional integrations while offering full MCP compatibility for AI-powered workflows through dedicated, standards-compliant transport.
