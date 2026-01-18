#!/bin/bash

echo "启动API接口智能测试系统..."

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "错误: Docker未运行，请先启动Docker"
    exit 1
fi

# 检查docker-compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo "错误: docker-compose未安装"
    exit 1
fi

# 启动服务
echo "正在启动所有服务..."
docker-compose up -d

# 等待服务启动
echo "等待服务启动..."
sleep 10

# 检查服务状态
echo "检查服务状态..."
docker-compose ps

echo ""
echo "服务启动完成！"
echo ""
echo "访问地址："
echo "  前端: http://localhost:3006"
echo "  后端API: http://localhost:8004"
echo "  API文档: http://localhost:8004/docs"
echo "  MinIO控制台: http://localhost:9006 (minioadmin/123456)"
echo "  Neo4j浏览器: http://localhost:7474 (neo4j/123456)"
echo ""
echo "查看日志: docker-compose logs -f"
echo "停止服务: docker-compose down"










































