#!/usr/bin/env python3
"""
Simple Demo for Integrated Docker Runner

This script demonstrates the integrated server that provides both REST API 
and MCP functionality on the same port.

Usage:
    python demo_integrated.py
"""

import subprocess
import time
import sys
import signal
import os


def main():
    """Run the integrated server demo"""
    print("🎭 Docker Runner Integrated Server Demo")
    print("=" * 50)
    
    # Check if Docker is available
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
        print("✅ Docker is available")
    except:
        print("❌ Docker is not available. Please install Docker first.")
        return
    
    print("\n🚀 Starting integrated server...")
    print("This will provide both REST API and MCP on port 8000:")
    print("  - REST API: http://localhost:8000/run")
    print("  - MCP SSE: http://localhost:8000/mcp") 
    print("  - Health: http://localhost:8000/health")
    print("  - Docs: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 50)
    
    try:
        # Start the integrated server
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )
        
        # Wait a moment for server to start
        time.sleep(3)
        
        print("\n✨ Server should be running!")
        print("Try these examples:")
        print("\n1. Open browser to http://localhost:8000/docs for API docs")
        print("\n2. Test REST API with curl:")
        print("""   curl -X POST http://localhost:8000/run \\
     -H "Content-Type: application/json" \\
     -d '{"image":"alpine:latest","command":["echo","Hello REST!"]}'""")
        
        print("\n3. Test MCP with the example client:")
        print("   python example_client.py")
        
        print("\n4. Use in AI clients with MCP config:")
        print('   {"mcpServers": {"docker": {"url": "http://localhost:8000/mcp"}}}')
        
        # Keep running and show server output
        print("\n" + "=" * 50)
        print("Server output:")
        print("=" * 50)
        
        try:
            while True:
                output = process.stdout.readline()
                if output:
                    print(output.strip())
                elif process.poll() is not None:
                    break
        except KeyboardInterrupt:
            print("\n\n👋 Shutting down server...")
            
    except KeyboardInterrupt:
        print("\n👋 Demo interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Clean up
        try:
            if os.name != 'nt':
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
            print("✅ Server stopped")
        except:
            print("⚠️  Could not stop server cleanly")


if __name__ == "__main__":
    main() 