# AI Agent Hub — 一键 Docker 部署
# 构建: docker build -t ai-agent-hub .
# 运行: docker compose up

# ── 阶段1: 构建前端 ──
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY builder/frontend/package.json builder/frontend/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY builder/frontend/ .
RUN npx vite build --outDir /dist

# ── 阶段2: 后端 + 已构建前端 ──
FROM python:3.12-slim
LABEL org.opencontainers.image.title="LumiWeave"
LABEL org.opencontainers.image.description="AI Agent协作工作台 — 一键部署，浏览器即用"

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY requirements-all.txt .
RUN pip install --no-cache-dir -r requirements-all.txt

# 项目代码
COPY builder/backend/ ./builder/backend/
COPY shared/ ./shared/
COPY runner/ ./runner/
COPY agents/ ./agents/

# 前端静态文件
COPY --from=frontend-builder /dist ./builder/backend/static/

# 工作目录
WORKDIR /app/builder/backend

# 配置文件（可通过挂载覆盖）
COPY builder/backend/runtime_config.json ./runtime_config.json.example

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-c", "\
import uvicorn; \
uvicorn.run('main:app', host='0.0.0.0', port=8000, log_level='info') \
"]
