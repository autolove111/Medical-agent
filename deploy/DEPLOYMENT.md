# 🚀 医检AI系统 - 生产环境部署指南

## 📋 目录
- [部署方案选择](#部署方案选择)
- [云服务器部署（推荐）](#云服务器部署推荐)
- [混合云架构](#混合云架构)
- [环境变量配置](#环境变量配置)
- [域名和SSL配置](#域名和ssl配置)
- [监控和维护](#监控和维护)
- [成本估算](#成本估算)

---

## 🎯 部署方案选择

### 方案A：云服务器部署（推荐）
**适合场景**：完全控制、自定义需求多
**优势**：
- ✅ 完全控制
- ✅ 可自定义配置
- ✅ 长期成本可控

**劣势**：
- ❌ 需要运维能力
- ❌ 需要自己处理扩缩容

### 方案B：混合云架构（成本优化）
**适合场景**：减少服务器成本，使用云端AI服务
**架构**：
```
用户 → 轻量云服务器（后端逻辑） → 云端MinerU API（OCR）
                                → 云端LLM API（大模型）
                                → 云数据库RDS
```

**优势**：
- ✅ 服务器成本低（无需GPU）
- ✅ AI服务弹性伸缩
- ✅ 数据库高可用

**劣势**：
- ❌ 依赖第三方API
- ❌ API调用成本

### 方案C：Serverless架构
**适合场景**：流量波动大、按需付费
**优势**：
- ✅ 零运维
- ✅ 自动扩缩容
- ✅ 按调用次数付费

**劣势**：
- ❌ 冷启动延迟
- ❌ 长期成本可能更高

---

## ☁️ 云服务器部署（推荐）

### 第一步：购买云服务器

#### 推荐配置（阿里云/腾讯云/AWS）
```
CPU：4核（Intel Xeon 或 AMD EPYC）
内存：16GB
存储：100GB SSD
带宽：5Mbps（初期）→ 后期按需升级
操作系统：Ubuntu 22.04 LTS / CentOS 8

预算：约 ¥200-500/月（按年付费更优惠）
```

#### 如果需要本地LLM（可选）
```
GPU：NVIDIA T4 16GB 或 A10 24GB
内存：32GB+
存储：500GB SSD（存放模型）

预算：约 ¥1000-3000/月
```

### 第二步：服务器初始化

```bash
# 1. 连接服务器
ssh root@your_server_ip

# 2. 更新系统
apt update && apt upgrade -y  # Ubuntu
# 或
yum update -y  # CentOS

# 3. 安装必要工具
apt install -y curl wget git vim

# 4. 创建非root用户
adduser deploy
usermod -aG sudo deploy

# 5. 配置防火墙
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw enable

# 6. 切换到deploy用户
su - deploy
```

### 第三步：安装Docker

```bash
# 安装Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 将用户添加到docker组
sudo usermod -aG docker $USER

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version

# 重新登录使组生效
exit
ssh deploy@your_server_ip
```

### 第四步：部署应用

```bash
# 1. 克隆代码
cd /home/deploy
git clone https://github.com/yourusername/medlab-ai.git
cd medlab-ai

# 2. 创建环境配置
cp deploy/.env.example deploy/.env.production
vim deploy/.env.production
```

### 第五步：配置环境变量

编辑 `deploy/.env.production`：

```bash
# ========================
# 数据库配置
# ========================
POSTGRES_DB=medlab_db
POSTGRES_USER=medlab_user
POSTGRES_PASSWORD=your_strong_password_here

# ========================
# Redis配置
# ========================
REDIS_PASSWORD=your_redis_password

# ========================
# MinerU OCR配置
# ========================
MINERU_API_BASE_URL=https://mineru.net
MINERU_API_TOKEN=your_mineru_api_token

# ========================
# LLM配置（使用云端API）
# ========================
LLM_PROVIDER=cloud_api
LLM_API_KEY=your_llm_api_key
LLM_API_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4

# 或者使用国内大模型
# LLM_API_BASE_URL=https://dashscope.aliyuncs.com/api/v1
# LLM_MODEL_NAME=qwen-max

# ========================
# Embedding配置
# ========================
RAG_USE_LOCAL_EMBEDDING=false
RAG_EMBEDDING_API_KEY=your_embedding_api_key
RAG_EMBEDDING_API_BASE_URL=https://api.openai.com/v1

# ========================
# 应用配置
# ========================
APP_NAME=MedLab AI
DEBUG=false
LOG_LEVEL=INFO
CORS_ORIGINS=https://yourdomain.com

# ========================
# 安全配置
# ========================
SECRET_KEY=generate_a_random_secret_key_here
JWT_SECRET=generate_a_random_jwt_secret_here
```

### 第六步：启动服务

```bash
# 进入部署目录
cd /home/deploy/medlab-ai/deploy

# 启动所有服务
docker-compose -f docker-compose.prod.yml up -d

# 查看服务状态
docker-compose -f docker-compose.prod.yml ps

# 查看日志
docker-compose -f docker-compose.prod.yml logs -f backend

# 停止服务
docker-compose -f docker-compose.prod.yml down
```

---

## 🔷 混合云架构

### 架构图
```
┌─────────────────────────────────────────────────────────┐
│                    用户浏览器/APP                        │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│              轻量云服务器（2核4G）                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Nginx     │  │  FastAPI    │  │  Celery     │     │
│  │  反向代理   │→ │   后端      │  │  任务队列   │     │
│  └─────────────┘  └──────┬──────┘  └─────────────┘     │
└──────────────────────────┼──────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  MinerU API  │  │  LLM API     │  │  云数据库     │
│   (OCR)      │  │  (大模型)    │  │  (RDS)       │
└───────────────┘  └───────────────┘  └───────────────┘
```

### 优势
1. **服务器成本低**：2核4G轻量服务器 ¥50-100/月
2. **无需GPU**：使用云端AI API
3. **数据库高可用**：云数据库自动备份
4. **弹性伸缩**：API按调用次数计费

### 配置示例

```python
# backend/app/core/config.py
import os

class Settings:
    # OCR配置（云端MinerU）
    OCR_ENGINE = os.getenv("OCR_ENGINE", "mineru_api")
    MINERU_API_BASE_URL = os.getenv("MINERU_API_BASE_URL", "https://mineru.net")
    MINERU_API_TOKEN = os.getenv("MINERU_API_TOKEN")

    # LLM配置（云端API）
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "cloud_api")
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gpt-4")

    # 数据库配置（云数据库）
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Redis配置（云Redis）
    REDIS_HOST = os.getenv("REDIS_HOST")
    REDIS_PORT = os.getenv("REDIS_PORT", 6379)
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
```

---

## 🌐 域名和SSL配置

### 购买域名
1. 在阿里云/腾讯云/Namecheap购买域名
2. 域名备案（国内服务器必须）
3. 配置DNS解析指向服务器IP

### 配置SSL证书（免费）

```bash
# 安装Certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# 自动续期
sudo certbot renew --dry-run

# 添加到crontab
echo "0 12 * * * /usr/bin/certbot renew --quiet" | sudo tee -a /var/spool/cron/crontabs/root
```

### Nginx SSL配置

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # SSL优化
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000" always;

    # 其他配置...
}

# HTTP重定向到HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

---

## 📊 监控和维护

### 1. 日志管理

```bash
# 查看应用日志
docker-compose -f docker-compose.prod.yml logs -f backend

# 查看特定服务日志
docker-compose -f docker-compose.prod.yml logs -f postgres
docker-compose -f docker-compose.prod.yml logs -f redis

# 日志轮转配置（/etc/logrotate.d/docker）
/var/lib/docker/containers/*/*.log {
    rotate 7
    daily
    compress
    missingok
    delaycompress
    copytruncate
}
```

### 2. 数据库备份

```bash
# 创建备份脚本
cat > /home/deploy/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/deploy/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# 备份PostgreSQL
docker exec medlab-postgres pg_dump -U medlab_user medlab_db | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

# 删除7天前的备份
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /home/deploy/backup.sh

# 添加到crontab（每天凌晨2点）
echo "0 2 * * * /home/deploy/backup.sh >> /home/deploy/backup.log 2>&1" | crontab -
```

### 3. 监控脚本

```bash
cat > /home/deploy/monitor.sh << 'EOF'
#!/bin/bash

# 检查服务状态
check_service() {
    service_name=$1
    if docker-compose -f /home/deploy/medlab-ai/deploy/docker-compose.prod.yml ps | grep -q "$service_name.*Up"; then
        echo "✅ $service_name is running"
    else
        echo "❌ $service_name is down"
        # 发送告警（可配置邮件/钉钉/微信）
    fi
}

check_service "medlab-backend"
check_service "medlab-postgres"
check_service "medlab-redis"
check_service "medlab-nginx"

# 检查磁盘空间
disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $disk_usage -gt 80 ]; then
    echo "⚠️ Disk usage is high: ${disk_usage}%"
fi

# 检查内存
free -h
EOF

chmod +x /home/deploy/monitor.sh

# 每5分钟检查一次
echo "*/5 * * * * /home/deploy/monitor.sh >> /home/deploy/monitor.log 2>&1" | crontab -
```

### 4. 性能监控

安装Prometheus + Grafana（可选）：

```bash
# 创建docker-compose.monitoring.yml
cat > /home/deploy/medlab-ai/deploy/docker-compose.monitoring.yml << 'EOF'
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    ports:
      - "9100:9100"
    restart: unless-stopped
EOF
```

---

## 💰 成本估算

### 方案A：云服务器部署（本地LLM）

| 项目 | 配置 | 月成本（人民币） |
|------|------|------------------|
| 云服务器 | 4核16G + GPU T4 | ¥1500-3000 |
| 数据库 | 自建PostgreSQL | ¥0 |
| Redis | 自建Redis | ¥0 |
| 对象存储 | 10GB | ¥5 |
| 带宽 | 5Mbps | ¥100 |
| 域名 | .com域名 | ¥60/年 |
| **总计** | | **¥1600-3100/月** |

### 方案B：混合云架构（推荐）

| 项目 | 配置 | 月成本（人民币） |
|------|------|------------------|
| 云服务器 | 2核4G轻量 | ¥50-100 |
| 云数据库RDS | 1核1G | ¥100-200 |
| 云Redis | 1GB | ¥50-100 |
| MinerU API | 1000次/月 | ¥50-100 |
| LLM API | 100万token/月 | ¥100-300 |
| 带宽 | 3Mbps | ¥50 |
| 域名 | .com域名 | ¥60/年 |
| **总计** | | **¥400-850/月** |

### 方案C：Serverless架构

| 项目 | 配置 | 月成本（人民币） |
|------|------|------------------|
| 云函数 | 100万次调用 | ¥100-200 |
| API网关 | 100万次调用 | ¥50-100 |
| 云数据库 | 按量计费 | ¥100-300 |
| 云存储 | 10GB | ¥10 |
| MinerU API | 1000次/月 | ¥50-100 |
| LLM API | 100万token/月 | ¥100-300 |
| **总计** | | **¥400-1000/月** |

---

## 🔧 常见问题

### Q1: 如何扩展服务？
```bash
# 水平扩展后端服务
docker-compose -f docker-compose.prod.yml up -d --scale backend=3

# 配置Nginx负载均衡
upstream backend {
    server backend:8080 weight=1;
    server backend:8081 weight=1;
    server backend:8082 weight=1;
}
```

### Q2: 如何更新应用？
```bash
# 拉取最新代码
cd /home/deploy/medlab-ai
git pull origin main

# 重新构建并重启
cd deploy
docker-compose -f docker-compose.prod.yml up -d --build

# 或者只重启后端
docker-compose -f docker-compose.prod.yml up -d --build backend
```

### Q3: 如何恢复数据库？
```bash
# 从备份恢复
gunzip < /home/deploy/backups/postgres_20240101_020000.sql.gz | docker exec -i medlab-postgres psql -U medlab_user medlab_db
```

### Q4: 如何配置CDN加速？
1. 在阿里云/腾讯云开通CDN服务
2. 添加加速域名
3. 配置源站为你的服务器IP
4. 修改DNS解析到CDN提供的CNAME

### Q5: 如何处理高并发？
```nginx
# Nginx限流配置
http {
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    server {
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://backend;
        }
    }
}
```

---

## 📚 相关资源

- [Docker官方文档](https://docs.docker.com/)
- [Nginx配置指南](https://nginx.org/en/docs/)
- [Let's Encrypt SSL](https://letsencrypt.org/)
- [PostgreSQL备份恢复](https://www.postgresql.org/docs/current/backup.html)
- [Redis持久化](https://redis.io/topics/persistence)

---

## ✅ 部署检查清单

- [ ] 云服务器购买并初始化
- [ ] Docker和Docker Compose安装
- [ ] 域名购买和备案（国内）
- [ ] DNS解析配置
- [ ] 环境变量配置
- [ ] 数据库初始化
- [ ] SSL证书配置
- [ ] 防火墙配置
- [ ] 备份策略配置
- [ ] 监控告警配置
- [ ] 性能测试
- [ ] 文档整理

---

**部署完成！🎉**

如有问题，请查看日志或联系技术支持。
