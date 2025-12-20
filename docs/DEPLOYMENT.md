# 部署与运行方式

本文档给出 Weaver 的常见运行方式：本地开发、Docker（后端 + 数据库）、以及简单的部署建议。

## 1. 本地开发

见：`docs/QUICKSTART.md`、`docs/DEVELOPMENT.md`。

## 2. Docker（后端 + Postgres）

项目提供：

- `Dockerfile`：后端镜像
- `docker-compose.yml`：postgres + backend

启动：

```powershell
docker-compose up --build
```

说明：

- compose 里只启动后端和数据库；前端 `web/` 需要你单独部署或本地启动
- `.env` 中的 Key 会通过 compose 注入到 backend 容器

## 3. 生产部署建议（简版）

- 前端：可部署到 Vercel（Next.js）
- 后端：建议使用能跑长连接/流式响应的容器平台（例如 Railway/Fargate/自建 K8s）
- 数据库：生产建议独立托管 Postgres（并配置 `DATABASE_URL`）

