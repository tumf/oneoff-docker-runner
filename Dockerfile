FROM python:3.12-slim
WORKDIR /usr/src/app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY main.py ./
COPY mcp.py ./
COPY healthcheck.py ./
COPY start.sh ./

# Install dependencies
RUN uv sync --frozen --no-cache

# Make startup script executable
RUN chmod +x start.sh

# Expose ports for both REST API and MCP
EXPOSE 8000 8001

# Run both servers
CMD ["./start.sh"]