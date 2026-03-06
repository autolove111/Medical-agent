#!/bin/bash

# 百炼千问 API 集成测试脚本
# 用于验证后端集成是否正确

BASE_URL="http://localhost:8080"
API_VERSION="v1"

echo "════════════════════════════════════════════════════"
echo "  百炼千问 API 集成验证测试"
echo "════════════════════════════════════════════════════"
echo ""

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试计数
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 测试函数
test_endpoint() {
    local test_name=$1
    local method=$2
    local endpoint=$3
    local params=$4
    
    echo ""
    echo -e "${YELLOW}测试: $test_name${NC}"
    echo "方法: $method $endpoint"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -X GET "$BASE_URL$endpoint")
    else
        response=$(curl -s -X POST "$BASE_URL$endpoint?$params")
    fi
    
    if echo "$response" | grep -q '"success":true'; then
        echo -e "${GREEN}✅ 成功${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo "响应: ${response:0:100}..."
    else
        echo -e "${RED}❌ 失败${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo "响应: $response"
    fi
}

# 检查服务是否运行
echo "【步骤 1】检查服务状态..."
if ! curl -s -f "$BASE_URL/api/$API_VERSION/agent/health" > /dev/null 2>&1; then
    echo -e "${RED}❌ 错误: 无法连接到服务 ($BASE_URL)${NC}"
    echo ""
    echo "请确保:"
    echo "  1. 后端服务已启动 (mvn spring-boot:run)"
    echo "  2. 服务运行在 http://localhost:8080"
    exit 1
fi
echo -e "${GREEN}✅ 服务正常运行${NC}"

echo ""
echo "【步骤 2】执行 API 测试..."

# 测试 1: 健康检查
test_endpoint "健康检查" "GET" "/api/$API_VERSION/agent/health" ""

# 测试 2: AI 对话
test_endpoint "AI 对话" "POST" "/api/$API_VERSION/agent/chat" "userQuery=请解释什么是血糖"

# 测试 3: 分析医疗报告
test_endpoint "分析医疗报告" "POST" "/api/$API_VERSION/agent/analyze-report" "reportContent=血红蛋白120g/L，正常"

# 测试 4: 诊断建议
test_endpoint "获取诊断建议" "POST" "/api/$API_VERSION/agent/diagnosis" "symptoms=头痛,发热"

# 测试 5: 医学知识
test_endpoint "获取医学知识" "POST" "/api/$API_VERSION/agent/knowledge" "topic=糖尿病"

# 测试 6: 解释术语
test_endpoint "解释医学术语" "POST" "/api/$API_VERSION/agent/explain-term" "term=HbA1c"

# 输出测试结果
echo ""
echo "════════════════════════════════════════════════════"
echo "  测试结果"
echo "════════════════════════════════════════════════════"
echo "总测试数: $TOTAL_TESTS"
echo -e "通过数: ${GREEN}$PASSED_TESTS${NC}"
echo -e "失败数: ${RED}$FAILED_TESTS${NC}"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✅ 所有测试通过！集成成功！${NC}"
    exit 0
else
    echo -e "${RED}❌ 有测试失败，请检查日志${NC}"
    exit 1
fi
