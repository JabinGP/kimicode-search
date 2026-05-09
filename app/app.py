import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import create_server, DEFAULT_STREAMABLE_HTTP_PATH


class QueryKeyMiddleware:
    """ASGI middleware: extract api_key from URL query string and inject into headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            query_string = scope.get("query_string", b"").decode("utf-8")
            params = urllib.parse.parse_qs(query_string)
            api_keys = params.get("api_key", [])
            if api_keys:
                headers = list(scope.get("headers", []))
                headers.append(
                    (b"x-kimi-api-key", api_keys[0].encode("utf-8"))
                )
                scope["headers"] = headers
        await self.app(scope, receive, send)


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
app = QueryKeyMiddleware(mcp.streamable_http_app())
