#!/bin/bash

# 重新构建并部署容器的脚本

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DOCKER_COMPOSE="docker-compose"

echo "=========================================="
echo "重新构建并部署容器"
echo "=========================================="
echo ""

# 检查 docker-compose 是否可用
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: 未找到 docker-compose 或 docker 命令${NC}"
    exit 1
fi

# 如果 docker-compose 不可用，尝试使用 docker compose
if ! command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
    echo -e "${YELLOW}使用 docker compose (v2)${NC}"
fi

# 停止现有容器
echo -e "${GREEN}1. 停止现有容器...${NC}"
$DOCKER_COMPOSE down
echo ""

# 清理旧的构建（可选）
read -p "是否清理旧的构建缓存？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}清理构建缓存...${NC}"
    $DOCKER_COMPOSE build --no-cache
else
    echo -e "${GREEN}使用缓存构建...${NC}"
    $DOCKER_COMPOSE build
fi
echo ""

# 启动服务
echo -e "${GREEN}2. 启动服务...${NC}"
$DOCKER_COMPOSE up -d
echo ""

# 等待服务启动
echo -e "${GREEN}3. 等待服务启动...${NC}"
sleep 10

# 检查服务状态
echo -e "${GREEN}4. 检查服务状态...${NC}"
$DOCKER_COMPOSE ps
echo ""

# 等待后端就绪
echo -e "${GREEN}5. 等待后端服务就绪...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f -s http://localhost:8004/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 后端服务已就绪${NC}"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -n "."
    sleep 2
done
echo ""

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${YELLOW}⚠ 后端服务可能未完全就绪，请检查日志: $DOCKER_COMPOSE logs backend${NC}"
fi

# 等待前端就绪
echo -e "${GREEN}6. 等待前端服务就绪...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f -s http://localhost:3006 > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 前端服务已就绪${NC}"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -n "."
    sleep 2
done
echo ""

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${YELLOW}⚠ 前端服务可能未完全就绪，请检查日志: $DOCKER_COMPOSE logs frontend${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}部署完成！${NC}"
echo "=========================================="
echo ""
echo "服务访问地址："
echo "  前端界面: http://localhost:3006"
echo "  后端API: http://localhost:8004"
echo "  API文档: http://localhost:8004/docs"
echo ""
echo "常用命令："
echo "  查看所有日志: $DOCKER_COMPOSE logs -f"
echo "  查看后端日志: $DOCKER_COMPOSE logs -f backend"
echo "  查看前端日志: $DOCKER_COMPOSE logs -f frontend"
echo "  停止服务: $DOCKER_COMPOSE down"
echo ""
echo "运行测试脚本验证修复:"
echo "  ./test_fixes.sh"

