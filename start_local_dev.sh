#!/bin/bash

# APITest 本地开发环境启动脚本
# 只启动基础服务（Docker），应用服务需要在本地手动启动

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=========================================="
echo -e "${BLUE}APITest 本地开发环境启动${NC}"
echo "=========================================="
echo ""

# 检查是否在正确的目录
if [ ! -f "docker-compose.dev.yml" ]; then
    echo -e "${RED}错误: 请在 apitest 目录下运行此脚本${NC}"
    exit 1
fi

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}错误: Docker 未运行，请先启动 Docker${NC}"
    exit 1
fi

# 检测 docker compose 命令
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo -e "${GREEN}1. 启动基础服务（Docker）...${NC}"
$DOCKER_COMPOSE -f docker-compose.dev.yml up -d

echo ""
echo -e "${YELLOW}2. 等待服务就绪...${NC}"

# 等待MySQL就绪
echo -n "等待MySQL..."
for i in {1..60}; do
    if $DOCKER_COMPOSE -f docker-compose.dev.yml exec -T mysql mysqladmin ping -h localhost -uroot -p123456 --silent 2>/dev/null; then
        echo -e " ${GREEN}✓${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e " ${YELLOW}⚠ 超时，但继续${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# 等待Redis就绪
echo -n "等待Redis..."
for i in {1..30}; do
    if $DOCKER_COMPOSE -f docker-compose.dev.yml exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        echo -e " ${GREEN}✓${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e " ${YELLOW}⚠ 超时，但继续${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo -e "${GREEN}3. 检查服务状态...${NC}"
$DOCKER_COMPOSE -f docker-compose.dev.yml ps

echo ""
echo "=========================================="
echo -e "${GREEN}基础服务启动完成！${NC}"
echo "=========================================="
echo ""
echo -e "${YELLOW}接下来请在新的终端窗口中启动应用服务：${NC}"
echo ""
echo -e "${BLUE}【终端2】启动 Backend：${NC}"
echo "  cd $(pwd)/backend"
echo "  source venv/bin/activate  # 如果使用虚拟环境"
echo "  python start_server.py"
echo ""
echo -e "${BLUE}【终端3】启动 Celery Worker：${NC}"
echo "  cd $(pwd)/backend"
echo "  source venv/bin/activate  # 如果使用虚拟环境"
echo "  celery -A app.celery_app worker --loglevel=info --concurrency=4"
echo ""
echo -e "${BLUE}【终端4】启动 Frontend：${NC}"
echo "  cd $(pwd)/frontend"
echo "  npm start"
echo ""
echo -e "${GREEN}服务访问地址：${NC}"
echo "  前端界面: http://localhost:3006"
echo "  后端API: http://localhost:8004"
echo "  API文档: http://localhost:8004/docs"
echo "  MinIO控制台: http://localhost:9006 (minioadmin/minioadmin123456)"
echo "  Neo4j浏览器: http://localhost:7474 (neo4j/123456789)"
echo ""
echo -e "${YELLOW}基础服务管理：${NC}"
echo "  查看状态: $DOCKER_COMPOSE -f docker-compose.dev.yml ps"
echo "  查看日志: $DOCKER_COMPOSE -f docker-compose.dev.yml logs -f"
echo "  停止服务: $DOCKER_COMPOSE -f docker-compose.dev.yml stop"
echo "  完全停止: $DOCKER_COMPOSE -f docker-compose.dev.yml down"
echo ""
