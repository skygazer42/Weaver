# 开发指南

---

## 本地开发（推荐脚本）

```bash
# 一键初始化依赖 + 启动数据库（推荐）
./scripts/setup.sh

# 同时启动后端/前端（推荐）
./scripts/dev.sh
```

也可以分开启动：

```bash
# 数据库（PostgreSQL + Redis）
docker compose -f docker/docker-compose.yml up -d postgres redis

# 后端
make setup
.venv/bin/python main.py

# 前端
pnpm -C web install --frozen-lockfile
pnpm -C web dev
```

---

## 测试与质量检查

```bash
# 后端
make test
make lint
make format

#（可选）本地 secret 扫描
.venv/bin/python scripts/secret_scan.py

# OpenAPI 合约对齐（后端 ↔ 前端 types）
make openapi-types

# 前端
pnpm -C web test
pnpm -C web lint
pnpm -C web build
```

---

## 调试与日志

在 `.env` 中启用调试：

```bash
DEBUG=true
LOG_LEVEL=DEBUG
ENABLE_FILE_LOGGING=true
```

查看日志：

```bash
# 主日志
tail -f logs/weaver.log

# 线程日志
tail -f logs/threads/{thread_id}.log
```
