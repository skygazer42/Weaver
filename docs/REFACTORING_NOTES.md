# 项目重构说明

## 重构日期
2024年12月17日

## 重构目的
优化项目结构，使其更清晰、更易维护

## 主要变更

### 1. 目录结构重组

#### Before (之前)
```
manus-app/
├── frontend/
│   ├── app/
│   ├── components/
│   └── lib/
└── backend/
    ├── agent/
    ├── tools/
    ├── main.py
    ├── config.py
    └── requirements.txt
```

#### After (现在)
```
manus-app/
├── web/              # 重命名自 frontend
│   ├── app/
│   ├── components/
│   └── lib/
├── agent/            # 从 backend/agent 移出
├── tools/            # 从 backend/tools 移出
├── main.py           # 从 backend 移出
├── config.py         # 从 backend 移出
└── requirements.txt  # 从 backend 移出
```

### 2. 文件变更清单

#### 重命名
- `frontend/` → `web/`

#### 移动
- `backend/agent/` → `agent/`
- `backend/tools/` → `tools/`
- `backend/main.py` → `main.py`
- `backend/config.py` → `config.py`
- `backend/requirements.txt` → `requirements.txt`
- `backend/Dockerfile` → `Dockerfile`

#### 删除
- `backend/` 目录（内容已移出）
- `backend/.env.example` → 合并到根目录 `.env.example`

#### 更新的配置文件
1. **package.json**
   - `workspaces`: `frontend` → `web`
   - `dev:frontend` → `dev:web`
   - `dev:backend`: 移除 `cd backend`
   - `install:all`: 更新路径

2. **docker-compose.yml**
   - `build`: `./backend` → `.`
   - `volumes`: `./backend:/app` → `.:/app`

3. **scripts/setup.sh**
   - 移除 `cd backend`
   - `frontend` → `web`
   - Python venv 现在在根目录创建

4. **scripts/dev.sh**
   - 移除 `cd backend`
   - `frontend` → `web`
   - 更新 PID 变量名

5. **.env.example**
   - 合并了 `backend/.env.example` 的内容
   - 添加了 `DEBUG` 和 `CORS_ORIGINS` 配置

#### 更新的文档
- README.md
- DEVELOPMENT.md
- PROJECT_SUMMARY.md
- QUICKSTART.md
- TROUBLESHOOTING.md
- API.md

所有文档中的路径引用已更新：
- `backend/` → 根目录路径
- `frontend/` → `web/`

### 3. 代码影响

#### Python 导入
✅ **无需修改** - 所有 Python 导入路径保持不变：
- `from common.config import settings`
- `from agent import create_research_graph`
- `from tools import tavily_search`

原因：模块在根目录时，Python 可以直接导入

#### TypeScript/React
✅ **无需修改** - 所有前端代码路径保持不变
- 内部导入都是相对路径
- 只有配置文件需要更新

### 4. 开发流程变更

#### 之前
```bash
# 后端
cd backend
source venv/bin/activate
uvicorn main:app --reload

# 前端
cd frontend
npm run dev
```

#### 现在
```bash
# 后端（更简单！）
source venv/bin/activate
uvicorn main:app --reload

# 前端
cd web
npm run dev
```

### 5. 优势

1. **更清晰的结构**
   - 后端核心代码直接在根目录
   - 减少一层目录嵌套
   - 更符合 Python 项目标准

2. **更短的路径**
   - `backend/agent/nodes.py` → `agent/nodes.py`
   - `backend/tools/search.py` → `tools/search.py`

3. **更好的命名**
   - `web` 比 `frontend` 更准确（包含了完整的 Web 应用）

4. **简化的开发**
   - 后端虚拟环境在根目录
   - 减少 `cd` 命令的使用
   - 更直观的项目导航

## 迁移指南

### 如果你之前克隆了旧版本

1. **拉取最新代码**
   ```bash
   git pull origin main
   ```

2. **清理旧的依赖**
   ```bash
   rm -rf backend/venv
   rm -rf frontend/node_modules
   rm -rf node_modules
   ```

3. **重新安装**
   ```bash
   ./scripts/setup.sh
   ```

### IDE 配置更新

#### VS Code
更新 `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.analysis.extraPaths": [
    "${workspaceFolder}"
  ]
}
```

#### PyCharm
- Python 解释器: `<项目根>/venv/bin/python`
- 源码根目录: 项目根目录
- Web 源码: `web/` 目录

## 验证

### 检查项目结构
```bash
tree -L 2 -I 'node_modules|venv|__pycache__|.git'
```

应该看到：
- ✅ `web/` 目录存在
- ✅ `agent/` 目录在根目录
- ✅ `tools/` 目录在根目录
- ✅ `main.py` 在根目录
- ❌ `backend/` 目录不存在
- ❌ `frontend/` 目录不存在

### 测试启动
```bash
# 1. 启动数据库
docker-compose up -d postgres

# 2. 启动应用
npm run dev

# 3. 验证访问
# Web: http://localhost:3000
# API: http://localhost:8000
```

## 兼容性

### 向后兼容
❌ **不兼容** - 这是一个破坏性变更

旧的路径引用将不再工作。所有依赖此项目的脚本或配置都需要更新。

### 数据库
✅ **兼容** - 数据库结构没有变化

### API
✅ **兼容** - API 端点没有变化

### Docker
✅ **兼容** - Docker 镜像会自动使用新结构

## 回滚方案

如果需要回滚到旧结构：

```bash
# 创建目录
mkdir backend frontend

# 移动文件
mv agent tools main.py config.py requirements.txt Dockerfile backend/
mv web/* frontend/
rmdir web

# 恢复配置文件
git checkout package.json docker-compose.yml scripts/
```

## 常见问题

### Q: 为什么要做这个重构？
A: 为了简化项目结构，使其更符合标准 Python 项目布局，同时让前端命名更准确。

### Q: 我的虚拟环境在哪？
A: 现在在项目根目录的 `venv/`，而不是 `backend/venv/`

### Q: 如何运行后端？
A: 在项目根目录执行 `source venv/bin/activate` 然后 `uvicorn main:app --reload`

### Q: 前端在哪？
A: `web/` 目录，之前叫 `frontend/`

### Q: Docker 还能用吗？
A: 可以，已经更新了 docker-compose.yml

## 相关 PR/Commits

- Commit: 重构项目结构 - 移动 backend 到根目录，重命名 frontend 为 web
- Files changed: 20+
- Lines changed: ~200

## 联系

如有问题，请查看：
- TROUBLESHOOTING.md
- DEVELOPMENT.md
- 或提交 GitHub Issue
