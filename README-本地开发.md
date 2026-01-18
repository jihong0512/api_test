# APITest 本地开发快速指南

## 部署架构说明

- **Docker 运行**：MySQL、Redis、Neo4j、MinIO（基础服务）
- **本地运行**：Backend、Frontend、Celery Worker（应用服务）

## 快速开始

### 1. 启动基础服务（Docker）

```bash
cd /Users/jihongqing/new_ai_workspace/apitest
./start_local_dev.sh
```

或者：

```bash
docker-compose -f docker-compose.dev.yml up -d
```

### 2. 配置环境变量（重要！）

```bash
cd backend
cp .env.example .env
# 编辑 .env 文件，确保端口配置正确
```

**关键端口配置**：
- MySQL: `MYSQL_PORT=3309`（不是3306）
- Redis: `REDIS_PORT=6382`（不是6379）
- MinIO: `MINIO_ENDPOINT=localhost:9005`（不是9000）

### 3. 启动应用服务（需要3个终端）

**终端1 - Backend：**
```bash
cd backend
source venv/bin/activate  # 如果使用虚拟环境
python start_server.py
```

**终端2 - Celery Worker：**
```bash
cd backend
source venv/bin/activate  # 如果使用虚拟环境
celery -A app.celery_app worker --loglevel=info --concurrency=4
```

**终端3 - Frontend：**
```bash
cd frontend
npm start
```

### 4. 访问服务

- 前端：http://localhost:3006
- 后端API：http://localhost:8004
- API文档：http://localhost:8004/docs
- MinIO控制台：http://localhost:9006 (minioadmin/minioadmin123456)
- Neo4j浏览器：http://localhost:7475 (neo4j/123456789)

## 详细说明

查看完整文档：`部署说明-本地开发模式.md`

## 与UITest共存

两个项目使用不同的端口，可以同时运行，互不影响。

| 服务 | UITest | APITest (本地) |
|------|--------|----------------|
| MySQL | 3312 | 3309 |
| Redis | 6385 | 6382 |
| Backend | 8007 | 8004 |
| Frontend | 3009 | 3006 |
