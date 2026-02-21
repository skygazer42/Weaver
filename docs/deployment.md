# 部署与加固

这份文档把根目录 `README.md` 中偏“生产化”的内容（Docker/Compose 部署、反代鉴权、限流）集中到一起，方便查阅与维护。

> 如果你只是本地自用/内网开发，可以先跳过“加固”章节，只按最小部署跑起来即可。

---

## 最小部署（Docker Compose，全栈）

仓库已提供 `docker/docker-compose.yml`（PostgreSQL + Redis + Backend）。

1) 准备环境变量（建议仍然使用根目录 `.env`）：

```bash
cp .env.example .env
```

2) 启动：

```bash
docker compose -f docker/docker-compose.yml up -d
```

3) 访问：

- Backend：http://localhost:8001
- OpenAPI：http://localhost:8001/docs

停止：

```bash
docker compose -f docker/docker-compose.yml down
```

---

## 仅后端部署（Docker）

镜像定义在 `docker/Dockerfile`（容器内默认端口 `8000`，建议宿主机映射到 `8001`）。

```bash
docker build -f docker/Dockerfile -t weaver-backend .

docker run -d \
  -p 8001:8000 \
  --env-file .env \
  --name weaver-backend \
  weaver-backend
```

> 说明：如果你启用了长期记忆/会话存储等能力，仍建议配合 PostgreSQL/Redis（推荐直接用 Compose）。

---

## 前端部署（Vercel 示例）

```bash
cd web
vercel deploy --prod
```

在 Vercel 环境变量中至少配置：

```bash
NEXT_PUBLIC_API_URL=https://your-backend.example.com
NEXT_PUBLIC_CHAT_STREAM_PROTOCOL=sse
NEXT_PUBLIC_RESEARCH_STREAM_PROTOCOL=sse
```

---

## 后端部署（Railway/Render 等）

启动命令（示例）：

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

建议：

- 生产环境关闭 `--reload`
- 确保平台/反代对 SSE 连接的超时/缓冲策略可控（见下文）

---

## 生产加固：内部鉴权（反向代理注入）

当你在后端配置了 `WEAVER_INTERNAL_API_KEY`（非空）时：

- 除 `/api/webhook/*` 外，大多数 `/api/*` 默认需要内部鉴权（否则 `401`）
- 如果反向代理注入 `WEAVER_AUTH_USER_HEADER`（默认 `X-Weaver-User`），则线程/会话相关接口会按用户隔离（越权返回 `403`）

为什么推荐“反代注入”：

- SSE / `EventSource` 无法自定义 headers
- 把内部 key 放到浏览器端有泄漏风险

### Nginx 示例（仅示意）

```nginx
location /api/ {
  # 1) 反代完成用户鉴权（此处省略 OIDC / auth_request 等）

  # 2) 注入内部鉴权 key（不要下发给浏览器）
  proxy_set_header Authorization "Bearer <WEAVER_INTERNAL_API_KEY>";

  # 3) 注入可信用户身份（用于线程/会话隔离）
  proxy_set_header X-Weaver-User "<user_id>";

  # 4) SSE 建议关闭缓冲
  proxy_buffering off;

  proxy_pass http://127.0.0.1:8001;
}
```

---

## 生产加固：HTTP 限流（可选）

Weaver 内置轻量 HTTP 限流，用于防止误刷/脚本死循环。

默认行为：

- `APP_ENV=prod|production`：启用
- 其他环境：默认关闭（更适合开源/本地开发）

常用环境变量（根目录 `.env`）：

```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_GENERAL_PER_MINUTE=60
RATE_LIMIT_CHAT_PER_MINUTE=20
RATE_LIMIT_WINDOW_SECONDS=60
```

启用后高频接口可能返回 `429`，并附带 `X-RateLimit-*` headers。

---

## SSE 与反代注意事项

如果你的部署平台/反代对 SSE 支持不佳（缓冲、断连、Header 被改写），可以：

- 优先排查反代是否开启缓冲（Nginx 常见：`proxy_buffering off`）
- 调整上游/下游 idle timeout
- 前端临时回滚到 legacy 行协议（见 `docs/chat-streaming.md`）
