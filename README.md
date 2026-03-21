# Kimi Coding MCP

Kimi Coding MCP 是一个把 Kimi Coding Search / Fetch 接口封装成 MCP 工具的服务，适合部署到服务器后，以远程 MCP 的方式接入你的客户端。

它提供两个工具：

- `kimi_search`：调用 `POST https://api.kimi.com/coding/v1/search`
- `kimi_fetch`：调用 `POST https://api.kimi.com/coding/v1/fetch`

核心实现是 [server.py](/D:/删除/git/request-head/server.py)，容器入口是 [Dockerfile](/D:/删除/git/request-head/Dockerfile)。

## 1. 快速开始

安装依赖：

```bash
pip install -r requirements.txt
```

远程模式启动：

```bash
python server.py --transport streamable-http --host 0.0.0.0 --port 8000
```

默认 MCP 地址：

```text
http://127.0.0.1:8000/mcp
```

如果你部署在带 HTTPS 的域名上，对外地址通常就是：

```text
https://your-domain.com/mcp
```

## 2. 工具说明

### `kimi_search`

输入参数：

```json
{
  "text_query": "食贫道 最新视频 2025 2026",
  "limit": 10,
  "enable_page_crawling": false,
  "timeout_seconds": 30
}
```

### `kimi_fetch`

输入参数：

```json
{
  "url": "https://search.bilibili.com/all?keyword=食贫道"
}
```

## 3. Docker 部署

### 方式 A：不带代理，直接暴露端口

这种方式适合内网使用、临时测试，或者你已经有其他网关负责对外转发。

构建镜像：

```bash
docker build -t kimi-coding-mcp .
```

单租户模式：

```bash
docker run -d \
  --name kimi-coding-mcp \
  -p 8000:8000 \
  -e KIMI_API_KEY=sk-kimi-你的key \
  kimi-coding-mcp
```

多租户模式：

```bash
docker run -d \
  --name kimi-coding-mcp \
  -p 8000:8000 \
  kimi-coding-mcp
```

部署完成后，对外 MCP 地址通常是：

```text
http://你的服务器IP:8000/mcp
```

### 方式 B：带代理，通过 HTTPS 域名访问

这种方式适合公网部署。仓库里已经提供了 [compose.yaml](/D:/删除/git/request-head/compose.yaml) 和 [Caddyfile](/D:/删除/git/request-head/Caddyfile)。

1. 复制环境变量模板：

```bash
cp .env.production.example .env.production
```

2. 编辑 `.env.production`

单租户模式：

```bash
KIMI_API_KEY=sk-kimi-你的key
APP_DOMAIN=kimi-mcp.example.com
```

多租户模式：

```bash
KIMI_API_KEY=
APP_DOMAIN=kimi-mcp.example.com
```

3. 确保域名已经解析到服务器公网 IP，并放行 `80` 和 `443`

4. 启动：

```bash
docker compose up -d --build
```

部署完成后，对外 MCP 地址通常是：

```text
https://kimi-mcp.example.com/mcp
```

## 4. 客户端配置

推荐使用多租户模式，让每个客户端自己携带 Kimi key。

多租户模式：

```json
{
  "mcpServers": {
    "kimi-coding-remote": {
      "type": "streamable_http",
      "url": "https://kimi-mcp.example.com/mcp",
      "headers": {
        "X-Kimi-Api-Key": "sk-kimi-替换成你的key"
      }
    }
  }
}
```

单租户模式：

```json
{
  "mcpServers": {
    "kimi-coding-remote": {
      "type": "streamable_http",
      "url": "https://kimi-mcp.example.com/mcp"
    }
  }
}
```

远程模式下，API key 的优先级是：

1. `X-Kimi-Api-Key` 请求头
2. `Authorization: Bearer sk-...` 请求头
3. 服务端环境变量 `KIMI_API_KEY`

## 5. 环境变量

常用环境变量如下：

```bash
KIMI_API_KEY=sk-kimi-你的key
KIMI_BASE_URL=https://api.kimi.com/coding/v1
KIMI_USER_AGENT=KimiCLI/1.24.0
KIMI_MSH_PLATFORM=kimi_cli
KIMI_MSH_VERSION=1.24.0
KIMI_DEVICE_NAME=YOUR-PC
KIMI_DEVICE_MODEL=Windows 11 AMD64
KIMI_OS_VERSION=10.0.26200
KIMI_DEVICE_ID=自定义设备ID
KIMI_LOG_DIR=logs
KIMI_LOG_LEVEL=INFO
KIMI_LOG_MAX_BYTES=5242880
KIMI_LOG_BACKUP_COUNT=3
KIMI_LOG_PREVIEW_BYTES=100
MCP_TRANSPORT=streamable-http
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_STREAMABLE_HTTP_PATH=/mcp
```

如果没有显式设置 `KIMI_DEVICE_ID`，服务会优先读取 `~/.kimi/device_id`；读不到时才会按 `device_name` 生成一个稳定 UUID。

日志默认写入 `logs/server.log`，并按大小轮转。日志会记录：

- 调用的 endpoint
- 入参预览（默认最多 100 字节）
- 返回结果预览（默认最多 100 字节）
- 状态码与耗时

为了安全，`api_key`、`authorization`、`token`、`secret` 等敏感字段会自动脱敏。

本地运行时可以参考 [.env.example](/D:/删除/git/request-head/.env.example)，带代理的 Docker 部署可以参考 [.env.production.example](/D:/删除/git/request-head/.env.production.example)。

## 6. 本地调试

如果你需要本地调试 stdio 模式，可以直接运行：

```bash
python server.py --transport stdio
```

如果你需要本地验证容器：

```bash
docker build -t kimi-coding-mcp .
docker run --rm -p 8000:8000 -e KIMI_API_KEY=sk-kimi-你的key kimi-coding-mcp
```

## 7. 说明

- `kimi_search` 使用 `text_query`、`limit`、`enable_page_crawling`、`timeout_seconds` 请求搜索接口；如果响应是 JSON，会自动格式化。
- `kimi_fetch` 使用 `url` 请求抓取接口，并默认按 `Accept: text/markdown` 返回文本。
