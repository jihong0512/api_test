#!/bin/bash

# Docker一键部署脚本 - 完整版
set -e

echo "=========================================="
echo "API接口智能测试平台 - Docker一键部署"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Docker和Docker Compose
echo -e "${GREEN}1. 检查Docker环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker未安装，请先安装Docker${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose未安装，请先安装Docker Compose${NC}"
    exit 1
fi

# 检测docker compose命令
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo -e "${GREEN}✓ Docker环境检查通过${NC}"
echo ""

# 停止现有服务（如果有）
echo -e "${GREEN}2. 清理现有服务...${NC}"
$DOCKER_COMPOSE down -v 2>/dev/null || true
echo -e "${GREEN}✓ 现有服务已清理${NC}"
echo ""

# 构建镜像
echo -e "${GREEN}3. 构建Docker镜像...${NC}"
$DOCKER_COMPOSE build --no-cache
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ 镜像构建失败${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 镜像构建完成${NC}"
echo ""

# 启动基础服务（MySQL, Redis, Milvus等）
echo -e "${GREEN}4. 启动基础服务（MySQL, Redis, Milvus等）...${NC}"
$DOCKER_COMPOSE up -d mysql redis milvus-standalone etcd minio neo4j
echo -e "${GREEN}✓ 基础服务启动中...${NC}"

# 等待MySQL就绪
echo ""
echo -e "${YELLOW}等待MySQL数据库就绪...${NC}"
for i in {1..60}; do
    if $DOCKER_COMPOSE exec -T mysql mysqladmin ping -h localhost -uroot -p123456 --silent 2>/dev/null; then
        echo -e "${GREEN}✓ MySQL就绪${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e "${RED}✗ MySQL启动超时${NC}"
        exit 1
    fi
    echo -n "."
    sleep 2
done
echo ""

# 等待数据库初始化完成
echo -e "${YELLOW}等待数据库初始化...${NC}"
for i in {1..30}; do
    if $DOCKER_COMPOSE exec -T mysql mysql -uroot -p123456 -e "USE api_test; SHOW TABLES;" 2>/dev/null | grep -q "users"; then
        echo -e "${GREEN}✓ 数据库表已初始化${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${YELLOW}⚠ 数据库表可能未完全初始化，将尝试通过SQLAlchemy创建${NC}"
    fi
    echo -n "."
    sleep 2
done
echo ""

# 等待Redis就绪
echo -e "${YELLOW}等待Redis就绪...${NC}"
for i in {1..30}; do
    if $DOCKER_COMPOSE exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        echo -e "${GREEN}✓ Redis就绪${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Redis启动超时${NC}"
        exit 1
    fi
    echo -n "."
    sleep 1
done
echo ""

# 等待Milvus就绪
echo -e "${YELLOW}等待Milvus就绪...${NC}"
sleep 10
echo -e "${GREEN}✓ Milvus启动中（需要额外时间完成初始化）${NC}"
echo ""

# 启动后端服务
echo -e "${GREEN}5. 启动后端服务...${NC}"
$DOCKER_COMPOSE up -d backend
echo -e "${GREEN}✓ 后端服务启动中...${NC}"

# 等待后端就绪
echo ""
echo -e "${YELLOW}等待后端服务就绪...${NC}"
for i in {1..60}; do
    if curl -f http://localhost:8004/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 后端服务就绪${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e "${YELLOW}⚠ 后端服务启动超时，请检查日志: $DOCKER_COMPOSE logs backend${NC}"
    fi
    echo -n "."
    sleep 2
done
echo ""

# 启动Celery Worker
echo -e "${GREEN}6. 启动Celery Worker...${NC}"
$DOCKER_COMPOSE up -d celery_worker
echo -e "${GREEN}✓ Celery Worker启动中...${NC}"
sleep 5

# 启动前端服务
echo -e "${GREEN}7. 启动前端服务...${NC}"
$DOCKER_COMPOSE up -d frontend
echo -e "${GREEN}✓ 前端服务启动中...${NC}"
sleep 10

# 检查所有服务状态
echo ""
echo -e "${GREEN}8. 检查服务状态...${NC}"
$DOCKER_COMPOSE ps

echo ""
echo -e "${GREEN}9. 验证服务健康状态...${NC}"

# 检查后端
if curl -f http://localhost:8004/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 后端服务健康${NC}"
else
    echo -e "${YELLOW}⚠ 后端服务可能未就绪，查看日志: $DOCKER_COMPOSE logs backend${NC}"
fi

# 检查前端（简单检查端口）
if curl -f http://localhost:3000 > /dev/null 2>&1 || nc -z localhost 3000 2>/dev/null; then
    echo -e "${GREEN}✓ 前端服务运行中${NC}"
else
    echo -e "${YELLOW}⚠ 前端服务可能未就绪，查看日志: $DOCKER_COMPOSE logs frontend${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}部署完成！${NC}"
echo "=========================================="
echo ""
echo -e "${GREEN}服务访问地址：${NC}"
echo "  前端界面: http://localhost:3000"
echo "  后端API: http://localhost:8004"
echo "  API文档: http://localhost:8004/docs"
echo "  ReDoc文档: http://localhost:8004/redoc"
echo ""
echo -e "${GREEN}服务管理：${NC}"
echo "  MySQL: localhost:3309 (用户: root, 密码: 123456)"
echo "  Redis: localhost:6382"
echo "  Milvus: localhost:9004"
echo "  MinIO控制台: http://localhost:9006 (用户: minioadmin, 密码: 123456)"
echo "  Neo4j浏览器: http://localhost:7474 (用户: neo4j, 密码: 123456)"
echo ""
echo -e "${GREEN}常用命令：${NC}"
echo "  查看所有日志: $DOCKER_COMPOSE logs -f"
echo "  查看后端日志: $DOCKER_COMPOSE logs -f backend"
echo "  查看前端日志: $DOCKER_COMPOSE logs -f frontend"
echo "  查看Celery日志: $DOCKER_COMPOSE logs -f celery_worker"
echo "  停止服务: $DOCKER_COMPOSE stop"
echo "  重启服务: $DOCKER_COMPOSE restart"
echo "  完全停止并清理: $DOCKER_COMPOSE down -v"
echo ""
echo -e "${YELLOW}注意：${NC}"
echo "  - 首次启动时，Milvus和Neo4j可能需要额外时间完成初始化"
echo "  - 如果服务无法访问，请检查日志排查问题"
echo "  - 默认管理员账号需通过API注册或数据库直接创建"
echo ""
