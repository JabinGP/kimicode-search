import argparse
import json
import logging
import os
import platform
import socket
import time
import urllib.error
import urllib.request
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP


SERVER_NAME = "kimi-coding-mcp"
SERVER_VERSION = "0.2.0"
DEFAULT_BASE_URL = "https://api.kimi.com/coding/v1"
DEFAULT_USER_AGENT = "KimiCLI/1.24.0"
DEFAULT_MSH_PLATFORM = "kimi_cli"
DEFAULT_MSH_VERSION = "1.24.0"
DEFAULT_TRANSPORT = "stdio"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_STREAMABLE_HTTP_PATH = "/mcp"
REMOTE_API_KEY_HEADER = "x-kimi-api-key"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE_NAME = "server.log"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 3
DEFAULT_LOG_PREVIEW_BYTES = 100


class ToolCallError(Exception):
    pass


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def normalize_api_key(value: str | None) -> str:
    if value is None:
        return ""

    stripped = value.strip()
    if not stripped:
        return ""

    if stripped.lower().startswith("bearer "):
        return stripped.split(" ", 1)[1].strip()

    return stripped


def mask_secret(value: str) -> str:
    if not value:
        return ""

    if len(value) <= 8:
        return "***"

    return f"{value[:4]}***{value[-4:]}"


def sanitize_log_value(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered_key = str(key).lower()
            if any(token in lowered_key for token in ("api_key", "authorization", "token", "secret")):
                sanitized[key] = mask_secret(str(item))
            else:
                sanitized[key] = sanitize_log_value(item)
        return sanitized

    if isinstance(value, list):
        return [sanitize_log_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize_log_value(item) for item in value)

    return value


def preview_text_bytes(value: str, limit: int = DEFAULT_LOG_PREVIEW_BYTES) -> str:
    encoded = value.encode("utf-8", errors="replace")
    preview = encoded[:limit]
    suffix = "" if len(encoded) <= limit else "...(truncated)"
    return preview.decode("utf-8", errors="replace") + suffix


def payload_log_text(payload) -> str:
    sanitized_payload = sanitize_log_value(payload)
    serialized = json.dumps(sanitized_payload, ensure_ascii=False, sort_keys=True)
    return preview_text_bytes(serialized, env_int("KIMI_LOG_PREVIEW_BYTES", DEFAULT_LOG_PREVIEW_BYTES))


def response_log_text(text: str) -> str:
    return preview_text_bytes(text, env_int("KIMI_LOG_PREVIEW_BYTES", DEFAULT_LOG_PREVIEW_BYTES))


def build_logger() -> logging.Logger:
    logger = logging.getLogger(SERVER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, os.getenv("KIMI_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    log_dir = Path(os.getenv("KIMI_LOG_DIR", DEFAULT_LOG_DIR))
    log_file = log_dir / DEFAULT_LOG_FILE_NAME

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_file,
            maxBytes=env_int("KIMI_LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES),
            backupCount=env_int("KIMI_LOG_BACKUP_COUNT", DEFAULT_LOG_BACKUP_COUNT),
            encoding="utf-8",
        )
    except OSError:
        handler = logging.StreamHandler()

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


LOGGER = build_logger()


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
        started_at = time.perf_counter()

        LOGGER.info(
            "kimi_request endpoint=%s url=%s accept=%s timeout=%s payload=%s",
            endpoint,
            url,
            accept,
            timeout,
            payload_log_text(payload),
        )

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
                formatted_text = format_tool_text(response.status, content_type, body)
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                LOGGER.info(
                    "kimi_response endpoint=%s status=%s elapsed_ms=%s result_preview=%s",
                    endpoint,
                    response.status,
                    elapsed_ms,
                    response_log_text(formatted_text),
                )
                return formatted_text
        except urllib.error.HTTPError as exc:
            content_type = exc.headers.get("Content-Type", "text/plain; charset=utf-8")
            body = exc.read()
            formatted_text = format_tool_text(exc.code, content_type, body)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            LOGGER.warning(
                "kimi_response endpoint=%s status=%s elapsed_ms=%s result_preview=%s",
                endpoint,
                exc.code,
                elapsed_ms,
                response_log_text(formatted_text),
            )
            raise ToolCallError(formatted_text) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            LOGGER.warning(
                "kimi_response endpoint=%s status=network_error elapsed_ms=%s result_preview=%s",
                endpoint,
                elapsed_ms,
                response_log_text(f"请求失败: {reason}"),
            )
            raise ToolCallError(f"请求失败: {reason}") from exc

    def search(
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
        return self.post("search", payload, "*/*", request_timeout)

    def fetch(self, url: str):
        payload = {"url": url}
        return self.post("fetch", payload, "text/markdown", 30)


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
        description="调用 Kimi 的 /coding/v1/search 接口，根据文本查询执行搜索。",
    )
    def kimi_search(
        text_query: str,
        ctx: Context,
        limit: int = 10,
        enable_page_crawling: bool = False,
        timeout_seconds: int = 30,
    ) -> str:
        cleaned_query = text_query.strip()
        if not cleaned_query:
            raise ValueError("kimi_search 需要非空字符串参数 text_query。")

        client = KimiCodingClient(api_key=resolve_request_api_key(ctx))
        return client.search(
            text_query=cleaned_query,
            limit=limit,
            enable_page_crawling=enable_page_crawling,
            timeout_seconds=timeout_seconds,
        )

    @mcp.tool(
        name="kimi_fetch",
        description="调用 Kimi 的 /coding/v1/fetch 接口，根据 URL 抓取结果。",
    )
    def kimi_fetch(url: str, ctx: Context) -> str:
        cleaned_url = url.strip()
        if not cleaned_url:
            raise ValueError("kimi_fetch 需要非空字符串参数 url。")

        client = KimiCodingClient(api_key=resolve_request_api_key(ctx))
        return client.fetch(cleaned_url)

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
    LOGGER.info(
        "server_start transport=%s host=%s port=%s streamable_http_path=%s log_dir=%s",
        args.transport,
        args.host,
        args.port,
        args.streamable_http_path,
        os.getenv("KIMI_LOG_DIR", DEFAULT_LOG_DIR),
    )
    mcp = create_server(args)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
