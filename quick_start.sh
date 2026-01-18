#!/bin/bash

# APITest 快速启动脚本（Mac/Linux）
# 用于在已部署 UITest 的环境中快速启动 APITest

set -e

echo "=========================================="
echo "APITest 快速启动脚本"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查是否在正确的目录
if [ ! -f "docker-compose.yml" ]; then
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

echo -e "${GREEN}1. 检查端口占用...${NC}"

# 检查关键端口是否被占用
check_port() {
    local port=$1
    local service=$2
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "${YELLOW}⚠ 警告: 端口 $port ($service) 已被占用${NC}"
        echo -e "${YELLOW}   如果这是 APITest 的容器，可以继续${NC}"
        echo -e "${YELLOW}   否则请检查是否有其他服务占用此端口${NC}"
    else
        echo -e "${GREEN}✓ 端口 $port ($service) 可用${NC}"
    fi
}

check_port 3309 "MySQL"
check_port 6382 "Redis"
check_port 7474 "Neo4j HTTP"
check_port 7687 "Neo4j Bolt"
check_port 9005 "MinIO API"
check_port 9006 "MinIO Console"
check_port 8004 "Backend"
check_port 3006 "Frontend"

echo ""
echo -e "${GREEN}2. 启动 APITest 服务...${NC}"
$DOCKER_COMPOSE up -d

echo ""
echo -e "${YELLOW}3. 等待服务启动（这可能需要1-2分钟）...${NC}"

# 等待 MySQL 就绪
echo -n "等待 MySQL..."
for i in {1..60}; do
    if $DOCKER_COMPOSE exec -T mysql mysqladmin ping -h localhost -uroot -p123456 --silent 2>/dev/null; then
        echo -e " ${GREEN}✓${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e " ${YELLOW}⚠ 超时，但继续启动${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# 等待 Redis 就绪
echo -n "等待 Redis..."
for i in {1..30}; do
    if $DOCKER_COMPOSE exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        echo -e " ${GREEN}✓${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e " ${YELLOW}⚠ 超时，但继续启动${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# 等待后端就绪
echo -n "等待后端服务..."
for i in {1..60}; do
    if curl -f http://localhost:8004/health > /dev/null 2>&1; then
        echo -e " ${GREEN}✓${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e " ${YELLOW}⚠ 超时，后端可能还在启动中${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

echo ""
echo -e "${GREEN}4. 检查服务状态...${NC}"
$DOCKER_COMPOSE ps

echo ""
echo "=========================================="
echo -e "${GREEN}启动完成！${NC}"
echo "=========================================="
echo ""
echo -e "${GREEN}服务访问地址：${NC}"
echo "  前端界面: http://localhost:3006"
echo "  后端API: http://localhost:8004"
echo "  API文档: http://localhost:8004/docs"
echo "  MinIO控制台: http://localhost:9006"
echo "  Neo4j浏览器: http://localhost:7474"
echo ""
echo -e "${GREEN}常用命令：${NC}"
echo "  查看日志: $DOCKER_COMPOSE logs -f"
echo "  查看状态: $DOCKER_COMPOSE ps"
echo "  停止服务: $DOCKER_COMPOSE stop"
echo "  重启服务: $DOCKER_COMPOSE restart"
echo "  完全停止: $DOCKER_COMPOSE down"
echo ""
echo -e "${YELLOW}注意：${NC}"
echo "  - 如果服务未就绪，请稍等片刻或查看日志"
echo "  - 查看日志: $DOCKER_COMPOSE logs -f [service_name]"
echo "  - UITest 服务不受影响，仍在运行"
echo ""
