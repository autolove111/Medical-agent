#!/bin/bash

# MedLabAgent 一键启动脚本 (Linux/macOS)
# 用途: 启动所有 Docker 服务并显示实时日志流
# 使用: ./docker-run.sh [stop|rm|logs]

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/infrastructure/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          MedLabAgent 医疗 AI 系统启动管理器               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

# ============ 检查环境 ============
check_environment() {
    echo -e "\n${YELLOW}[检查]${NC} 检查运行环境..."
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}✗ Docker 未安装${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker 已安装${NC}"
    
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}✗ Docker Compose 未安装${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker Compose 已安装${NC}"
    
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${RED}✗ .env 文件不存在，复制 .env.example${NC}"
        cp "$PROJECT_ROOT/.env.example" "$ENV_FILE" 2>/dev/null || {
            echo -e "${RED}✗ 无法创建 .env 文件${NC}"
            exit 1
        }
    fi
    echo -e "${GREEN}✓ 环境配置文件就绪${NC}"
}

# ============ 启动服务 ============
start_services() {
    echo -e "\n${YELLOW}[启动]${NC} 启动所有 Docker 服务..."
    echo -e "    服务列表: ${BLUE}postgres | redis | python-ocr | python-langchain | java-backend | frontend${NC}"
    
    cd "$PROJECT_ROOT/infrastructure"
    
    # 使用 docker compose 启动
    echo -e "\n${YELLOW}[💻]${NC} 构建镜像并启动容器..."
    docker compose \
        --project-name medlab \
        -f docker-compose.yml \
        --env-file "$ENV_FILE" \
        up -d --build
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 服务启动成功${NC}"
    else
        echo -e "${RED}✗ 服务启动失败${NC}"
        exit 1
    fi
}

# ============ 等待健康检查 ============
wait_for_health() {
    echo -e "\n${YELLOW}[等待]${NC} 等待服务健康检查..."
    
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        echo -ne "\r    进度: $((attempt * 100 / max_attempts))% [$" 
        for i in $(seq 1 $((attempt % 5))); do echo -n "="; done
        echo -n "]"
        
        # 检查 PostgreSQL
        if docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U medlab_user &> /dev/null; then
            # 检查 Redis
            if docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping &> /dev/null; then
                # 检查 Python 服务
                if curl -s http://localhost:8001/health &> /dev/null && \
                   curl -s http://localhost:8000/health &> /dev/null; then
                    echo -e "\r${GREEN}✓ 所有服务健康检查通过${NC}                    "
                    return 0
                fi
            fi
        fi
        
        attempt=$((attempt + 1))
        sleep 2
    done
    
    echo -e "\r${YELLOW}⚠ 健康检查超时，但服务可能已启动${NC}"
}

# ============ 显示启动信息 ============
show_startup_info() {
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                    服务地址与端口                          ║${NC}"
    echo -e "${BLUE}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${BLUE}║${NC} 📱 ${GREEN}前端 UI${NC}              : http://localhost:3000"
    echo -e "${BLUE}║${NC} 🔧 ${GREEN}Java 后端${NC}            : http://localhost:8080"
    echo -e "${BLUE}║${NC} 🤖 ${GREEN}LangChain Agent${NC}      : http://localhost:8000"
    echo -e "${BLUE}║${NC} 👁️  ${GREEN}OCR 视觉服务${NC}         : http://localhost:8001"
    echo -e "${BLUE}║${NC} 🗄️  ${GREEN}PostgreSQL 数据库${NC}     : localhost:5432"
    echo -e "${BLUE}║${NC} 🔴 ${GREEN}Redis 缓存${NC}            : localhost:6379"
    echo -e "${BLUE}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${BLUE}║${NC} 📊 ${GREEN}查看实时日志${NC}          : docker compose logs -f"
    echo -e "${BLUE}║${NC} ⏹️  ${GREEN}停止所有服务${NC}         : docker compose down"
    echo -e "${BLUE}║${NC} 🗑️  ${GREEN}删除所有数据${NC}         : docker compose down -v"
    echo -e "${BLUE}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${BLUE}║${NC} ${YELLOW}💡 测试医学诊断链路:${NC}"
    echo -e "${BLUE}║${NC}    1. 上传化验单 → post /api/v1/file/upload-report"
    echo -e "${BLUE}║${NC}    2. 启动诊断 → post /api/v1/chat"
    echo -e "${BLUE}║${NC}    3. 查看推流输出 (下面的日志流)"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
}

# ============ 显示推流日志 ============
show_streaming_logs() {
    echo -e "\n${YELLOW}[📡]${NC} 显示实时推流日志（按 Ctrl+C 停止）...\n"
    
    cd "$PROJECT_ROOT/infrastructure"
    
    # 并行显示所有关键服务的日志
    docker compose \
        --project-name medlab \
        -f docker-compose.yml \
        logs -f \
        --timestamps \
        java-backend python-langchain python-ocr
}

# ============ 停止服务 ============
stop_services() {
    echo -e "\n${YELLOW}[停止]${NC} 停止所有 Docker 服务..."
    cd "$PROJECT_ROOT/infrastructure"
    docker compose \
        --project-name medlab \
        -f docker-compose.yml \
        down
    echo -e "${GREEN}✓ 服务已停止${NC}"
}

# ============ 删除所有数据 ============
remove_all() {
    echo -e "\n${RED}[删除]${NC} 删除所有容器和数据卷..."
    cd "$PROJECT_ROOT/infrastructure"
    docker compose \
        --project-name medlab \
        -f docker-compose.yml \
        down -v
    echo -e "${GREEN}✓ 所有数据已删除${NC}"
}

# ============ 主函数 ============
main() {
    case "${1:-start}" in
        start)
            check_environment
            start_services
            wait_for_health
            show_startup_info
            show_streaming_logs
            ;;
        stop)
            stop_services
            ;;
        rm)
            remove_all
            ;;
        logs)
            cd "$PROJECT_ROOT/infrastructure"
            docker compose \
                --project-name medlab \
                -f docker-compose.yml \
                logs -f
            ;;
        *)
            echo "用法: $0 {start|stop|rm|logs}"
            echo ""
            echo "命令说明:"
            echo "  start (默认)  : 启动所有服务并显示日志流"
            echo "  stop          : 停止所有服务"
            echo "  rm            : 删除所有容器和数据卷"
            echo "  logs          : 显示所有服务日志"
            exit 1
            ;;
    esac
}

main "$@"
