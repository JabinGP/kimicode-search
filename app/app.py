import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import create_server, DEFAULT_STREAMABLE_HTTP_PATH


class Args:
    transport = "streamable-http"
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))
    streamable_http_path = os.getenv(
        "MCP_STREAMABLE_HTTP_PATH", DEFAULT_STREAMABLE_HTTP_PATH
    )
    stateless_http = True
    json_response = True


mcp = create_server(Args())
app = mcp.streamable_http_app()
