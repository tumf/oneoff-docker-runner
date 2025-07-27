#!/bin/bash

echo "Starting Docker Runner servers..."
echo "- REST API (main.py) on port 8000"
echo "- MCP Server (mcp.py) on port 8001"

# Start MCP server in background
uv run python mcp.py &
MCP_PID=$!

# Start main REST API server
uv run python main.py &
MAIN_PID=$!

# Function to handle shutdown
shutdown() {
    echo "Shutting down servers..."
    kill $MCP_PID $MAIN_PID 2>/dev/null
    wait $MCP_PID $MAIN_PID 2>/dev/null
    echo "Servers stopped."
    exit 0
}

# Set up signal handlers
trap shutdown SIGTERM SIGINT

# Wait for both processes
wait $MCP_PID $MAIN_PID 