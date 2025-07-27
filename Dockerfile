FROM python:3.12-slim
WORKDIR /usr/src/app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY main.py ./
COPY healthcheck.py ./

# Install dependencies
RUN uv sync --frozen --no-cache

# Expose port for both REST API and MCP
EXPOSE 8000

# Run the integrated server with both /run and /mcp endpoints
CMD ["uv", "run", "python", "main.py"]