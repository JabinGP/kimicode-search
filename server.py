import argparse
import json
import os
import platform
import socket
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP


SERVER_NAME = "kimi-coding-mcp"
SERVER_VERSION = "0.2.0"
DEFAULT_BASE_URL = "https://api.kimi.com/coding/v1"
DEFAULT_USER_AGENT = "KimiCLI/1.23.0"
DEFAULT_MSH_PLATFORM = "kimi_cli"
DEFAULT_MSH_VERSION = "1.23.0"
DEFAULT_TRANSPORT = "stdio"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_STREAMABLE_HTTP_PATH = "/mcp"
REMOTE_API_KEY_HEADER = "x-kimi-api-key"


class ToolCallError(Exception):
    pass


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_api_key(value: str | None) -> str:
    if value is None:
        return ""

    stripped = value.strip()
    if not stripped:
        return ""

    if stripped.lower().startswith("bearer "):
        return stripped.split(" ", 1)[1].strip()

    return stripped


def default_device_id(device_name: str) -> str:
    kimi_device_id_path = Path.home() / ".kimi" / "device_id"

    try:
        device_id = kimi_device_id_path.read_text(encoding="utf-8").strip()
        if device_id:
            return device_id
    except OSError:
        pass

    return uuid.uuid5(uuid.NAMESPACE_DNS, device_name).hex


def resolve_request_api_key(ctx: Context | None) -> str:
    if ctx is None:
        return ""

    request = getattr(ctx.request_context, "request", None)
    if request is None:
        return ""

    header_value = normalize_api_key(request.headers.get(REMOTE_API_KEY_HEADER))
    if header_value:
        return header_value

    authorization = request.headers.get("authorization", "")
    candidate = normalize_api_key(authorization)
    if candidate.startswith("sk-"):
        return candidate

    return ""


def format_tool_text(status_code: int, content_type: str, body: bytes) -> str:
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()

    text = body.decode(charset, errors="replace")
    if "application/json" in content_type:
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass

    if status_code >= 400:
        return f"HTTP {status_code}\n{text}"
    return text


class KimiCodingClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = normalize_api_key(api_key) or normalize_api_key(os.getenv("KIMI_API_KEY", ""))
        self.base_url = os.getenv("KIMI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.user_agent = os.getenv("KIMI_USER_AGENT", DEFAULT_USER_AGENT)
        self.msh_platform = os.getenv("KIMI_MSH_PLATFORM", DEFAULT_MSH_PLATFORM)
        self.msh_version = os.getenv("KIMI_MSH_VERSION", DEFAULT_MSH_VERSION)
        self.device_name = os.getenv("KIMI_DEVICE_NAME", socket.gethostname() or "unknown-host")
        self.device_model = os.getenv(
            "KIMI_DEVICE_MODEL",
            f"{platform.system()} {platform.machine()}".strip() or "unknown-device",
        )
        self.os_version = os.getenv(
            "KIMI_OS_VERSION",
            platform.version() or platform.release() or "unknown-os",
        )
        self.device_id = os.getenv(
            "KIMI_DEVICE_ID",
            default_device_id(self.device_name),
        )

    def ensure_ready(self):
        if not self.api_key:
            raise ValueError(
                "未提供 Kimi API key。远程模式请在请求头传 X-Kimi-Api-Key，本地/单租户模式可设置 KIMI_API_KEY。"
            )

    def _headers(self, accept: str):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": accept,
            "User-Agent": self.user_agent,
            "X-Msh-Tool-Call-Id": f"tool_{uuid.uuid4().hex}",
            "X-Msh-Platform": self.msh_platform,
            "X-Msh-Version": self.msh_version,
            "X-Msh-Device-Name": self.device_name,
            "X-Msh-Device-Model": self.device_model,
            "X-Msh-Os-Version": self.os_version,
            "X-Msh-Device-Id": self.device_id,
        }

    def post(self, endpoint: str, payload, accept: str, timeout: int):
        self.ensure_ready()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=data,
            headers=self._headers(accept),
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "text/plain; charset=utf-8")
                body = response.read()
                return format_tool_text(response.status, content_type, body)
        except urllib.error.HTTPError as exc:
            content_type = exc.headers.get("Content-Type", "text/plain; charset=utf-8")
            body = exc.read()
            raise ToolCallError(format_tool_text(exc.code, content_type, body)) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise ToolCallError(f"请求失败: {reason}") from exc

    def search(self, url: str):
        payload = {"url": url}
        return self.post("search", payload, "*/*", 30)

    def fetch(
        self,
        text_query: str,
        limit: int = 10,
        enable_page_crawling: bool = False,
        timeout_seconds: int = 30,
    ):
        payload = {
            "text_query": text_query,
            "limit": int(limit),
            "enable_page_crawling": bool(enable_page_crawling),
            "timeout_seconds": int(timeout_seconds),
        }
        request_timeout = max(payload["timeout_seconds"] + 10, 30)
        return self.post("fetch", payload, "text/markdown", request_timeout)


def create_server(args) -> FastMCP:
    mcp = FastMCP(
        name=SERVER_NAME,
        instructions=(
            "Use kimi_search and kimi_fetch to access Kimi coding search/fetch APIs. "
            "In remote HTTP mode, pass the downstream Kimi API key via X-Kimi-Api-Key, "
            "or configure a server-side KIMI_API_KEY for single-tenant deployment."
        ),
        host=args.host,
        port=args.port,
        streamable_http_path=args.streamable_http_path,
        stateless_http=args.stateless_http,
        json_response=args.json_response,
    )

    @mcp.tool(
        name="kimi_search",
        description="调用 Kimi 的 /coding/v1/search 接口，根据 URL 执行搜索。",
    )
    def kimi_search(url: str, ctx: Context) -> str:
        cleaned_url = url.strip()
        if not cleaned_url:
            raise ValueError("kimi_search 需要非空字符串参数 url。")

        client = KimiCodingClient(api_key=resolve_request_api_key(ctx))
        return client.search(cleaned_url)

    @mcp.tool(
        name="kimi_fetch",
        description="调用 Kimi 的 /coding/v1/fetch 接口，根据文本查询抓取结果。",
    )
    def kimi_fetch(
        text_query: str,
        ctx: Context,
        limit: int = 10,
        enable_page_crawling: bool = False,
        timeout_seconds: int = 30,
    ) -> str:
        cleaned_query = text_query.strip()
        if not cleaned_query:
            raise ValueError("kimi_fetch 需要非空字符串参数 text_query。")

        client = KimiCodingClient(api_key=resolve_request_api_key(ctx))
        return client.fetch(
            text_query=cleaned_query,
            limit=limit,
            enable_page_crawling=enable_page_crawling,
            timeout_seconds=timeout_seconds,
        )

    return mcp


def parse_args():
    parser = argparse.ArgumentParser(description="Kimi Coding MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=os.getenv("MCP_TRANSPORT", DEFAULT_TRANSPORT),
        help="MCP transport mode. 默认保持 stdio，本地兼容；远程部署请使用 streamable-http。",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", DEFAULT_HOST),
        help="HTTP transport bind host.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", str(DEFAULT_PORT))),
        help="HTTP transport bind port.",
    )
    parser.add_argument(
        "--streamable-http-path",
        default=os.getenv("MCP_STREAMABLE_HTTP_PATH", DEFAULT_STREAMABLE_HTTP_PATH),
        help="Path for streamable HTTP endpoint.",
    )
    parser.add_argument(
        "--stateless-http",
        action="store_true",
        default=env_flag("MCP_STATELESS_HTTP", False),
        help="Enable stateless HTTP mode for easier horizontal scaling.",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        default=env_flag("MCP_JSON_RESPONSE", False),
        help="Prefer plain JSON responses when the client supports them.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    mcp = create_server(args)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
