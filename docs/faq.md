# 常见问题（FAQ）

---

## 1) 前端无法连接后端

1) 确认你已创建前端 env 文件：

```bash
cp web/.env.local.example web/.env.local
```

2) 检查 `web/.env.local` 中的 API 地址是否正确：

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8001
```

3) 修改后重启前端开发服务器：

```bash
pnpm -C web dev
```

---

## 2) 端口被占用（EACCES / Address already in use）

```bash
# 前端换端口（示例）
pnpm -C web dev -- -p 8080
```

---

## 3) E2B 沙箱连接失败

检查清单：

- API Key 是否正确
- 网络是否可以访问 `e2b.dev`
- 是否有代理设置

快速自检：

```bash
.venv/bin/python -c "from e2b_code_interpreter import Sandbox; Sandbox(); print('OK')"
```

---

## 4) Deep Research 没有按预期执行

排查方向：

- 是否选择了正确模式（deep）
- 查看日志确认路由决策：`rg \"route_decision\" logs/weaver.log`
- 运行诊断脚本：`.venv/bin/python scripts/deep_search_routing_check.py`

---

## 5) 数据库连接错误

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis
```

然后确认你的 `DATABASE_URL` 是否可达。
