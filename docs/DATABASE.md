# 数据库（PostgreSQL / pgvector）

Weaver 后端在以下场景会用到数据库：

1) LangGraph checkpoint（可恢复执行）  
2) LangGraph store（长期记忆后端=postgres）  

如果你不启用这些能力，后端也可以在纯内存模式运行（但重启后不可恢复）。

## 1. docker-compose 提供的默认数据库

项目自带 `docker-compose.yml`（pgvector/pg16），默认参数：

- 用户：`manus`
- 密码：`manus_dev_password`
- DB：`manus_db`
- 端口：`5432`

启动：

```powershell
docker-compose up -d postgres
```

## 2. DATABASE_URL

`.env` 里配置：

```env
DATABASE_URL=postgresql://manus:manus_dev_password@localhost:5432/manus_db
```

后端启动时会：

- 用该连接串初始化 LangGraph checkpointer（并自动 `setup()` 创建所需表）
- 如果你把 `MEMORY_STORE_BACKEND=postgres`，也会用对应的 store 逻辑写入

