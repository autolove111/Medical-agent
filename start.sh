#!/bin/bash
# MedLabAgent System - Quick Start Script
# 快速启动所有服务

set -e

echo "=========================================="
echo "MedLabAgent System - Quick Start"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker 和 Docker Compose
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}⚠️  Docker 未安装，请先安装 Docker${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}⚠️  Docker Compose 未安装，请先安装 Docker Compose${NC}"
    exit 1
fi

echo -e "${BLUE}✓ Docker 和 Docker Compose 已安装${NC}"
echo ""

# 进入 infrastructure 目录
cd infrastructure

echo -e "${BLUE}📦 启动所有服务...${NC}"
echo ""

# 启动服务
docker-compose up -d

echo ""
echo -e "${GREEN}✓ 所有服务已启动${NC}"
echo ""

# 等待服务就绪
echo -e "${BLUE}⏳ 等待服务就绪...${NC}"
sleep 10

# 检查服务状态
echo ""
echo -e "${BLUE}📊 服务状态:${NC}"
docker-compose ps

echo ""
echo -e "${GREEN}🎉 MedLabAgent System 已启动！${NC}"
echo ""
echo -e "${BLUE}服务地址:${NC}"
echo "  后端 API:     http://localhost:8080/api/v1/health"
echo "  数据库:       localhost:5432"
echo "  Redis:       localhost:6379"
echo "  Ollama:      http://localhost:11434"
echo "  OCR 服务:     http://localhost:8000/health"
echo ""
echo -e "${YELLOW}💡 提示:${NC}"
echo "  查看日志:     docker-compose logs -f backend"
echo "  停止服务:     docker-compose down"
echo "  重启服务:     docker-compose restart"
echo ""
