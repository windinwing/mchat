# mchat 部署指南

## Docker 部署（推荐）

### 前置要求

- Docker >= 24.0
- Docker Compose >= 2.0
- 至少 4GB 可用内存（含 Milvus 时需 8GB+）

### 1. 克隆项目

```bash
git clone https://github.com/your-org/mchat.git
cd mchat
```

### 2. 配置环境变量

```bash
cp ops/docker/.env.example ops/docker/.env
```

编辑 `ops/docker/.env`，至少修改以下配置：

```bash
# 必须修改
MYSQL_ROOT_PASSWORD=your_secure_password
MYSQL_PASSWORD=your_secure_password
JWT_SECRET=your_random_secret_at_least_32_chars
ADMIN_PASSWORD=your_admin_password

# 可选：如不需要知识库功能
MILVUS_DISABLED=true
```

### 3. 启动服务

```bash
# 完整启动（含 MySQL + Milvus + Redis + 前后端）
docker compose -f ops/docker/docker-compose.yml up -d

# 或使用 Makefile
make docker-up
```

### 4. 访问

- 管理后台: `http://localhost:5173/admin`
- API 文档 (Swagger): `http://localhost:3001/docs`
- 健康检查: `http://localhost:3001/api/health`

### 5. 初始管理员

默认管理员账号（在 .env 中配置）：
- 用户名: `ADMIN_USERNAME`（默认 `admin`）
- 密码: `ADMIN_PASSWORD`（你设置的密码）

**⚠️ 首次登录后请立即修改密码！**

---

## 生产部署

### 环境准备

```bash
# 服务器要求
- OS: Ubuntu 22.04+ / Debian 12+
- CPU: 4 core+
- RAM: 8GB+ (含 Milvus)
- Disk: 50GB+ SSD
```

### Docker Compose 生产配置

```bash
# 1. 创建生产环境变量
cp ops/docker/.env.production.example ops/docker/.env.production
# 编辑 .env.production，配置生产环境参数

# 2. 启动生产服务
docker compose -f ops/docker/docker-compose.prod.yml --env-file ops/docker/.env.production up -d
```

> **旧版本升级安全提示：** 早期的频道租赁流程可能把平台或模板的 AI
> 密钥复制到租户配置中。新版首次以生产模式启动时会清除能够确认的复制项；
> 由于旧接口可能已经返回过明文，升级后仍必须在对应供应商控制台轮换所有曾
> 用作平台默认值或模板默认值的 API 密钥。

### Nginx 反向代理（推荐）

```nginx
server {
    listen 80;
    server_name mchat.example.com;

    # 前端
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 后端 API
    location /api/ {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 上传文件
    location /uploads/ {
        proxy_pass http://127.0.0.1:3001;
    }
}
```

### HTTPS 配置

```bash
# 使用 certbot 获取免费 SSL 证书
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d mchat.example.com
```

---

## 手动部署（开发环境）

### 前置要求

- Python >= 3.12
- Node.js >= 20
- MySQL 8.0+
- Milvus (可选)

### 1. 后端

```bash
cd src/backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env

# 初始化数据库
python -c "from app.core.database import engine, Base; import app.models; Base.metadata.create_all(bind=engine)"

# 启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 3001
```

### 2. 前端

```bash
cd src/frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 3. 一起启动

```bash
# 使用 Makefile
make install
make dev
```

---

## 环境变量参考

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | MySQL 连接字符串 | `mysql://...` |
| `JWT_SECRET` | JWT 签名密钥 | 必须设置 |
| `JWT_EXPIRE_MINUTES` | Token 过期时间(分钟) | `10080` (7天) |
| `SERVER_HOST` | 监听地址 | `0.0.0.0` |
| `SERVER_PORT` | 监听端口 | `3001` |
| `ADMIN_USERNAME` | 默认管理员用户名 | `admin` |
| `ADMIN_PASSWORD` | 默认管理员密码 | 必须设置 |
| `MILVUS_HOST` | Milvus 地址 | `localhost` |
| `MILVUS_PORT` | Milvus 端口 | `19530` |
| `MILVUS_DISABLED` | 禁用 Milvus | `false` |
| `EMBEDDING_PROVIDER` | 嵌入模型提供商 | `openai` |
| `EMBEDDING_MODEL` | 嵌入模型名 | `text-embedding-3-small` |
| `REDIS_URL` | Redis 连接 | (可选) |

---

## 备份与恢复

### 数据库备份

```bash
# MySQL 备份
docker exec mchat-mysql mysqldump -u mchat -p mchat > backup_$(date +%Y%m%d).sql

# 上传文件备份
tar -czf uploads_backup_$(date +%Y%m%d).tar.gz src/backend/uploads/
```

### 恢复

```bash
# MySQL 恢复
docker exec -i mchat-mysql mysql -u mchat -p mchat < backup.sql

# 上传文件恢复
tar -xzf uploads_backup.tar.gz -C src/backend/uploads/
```

---

## 监控

- API 健康检查: `GET /api/health`
- 基础指标: `GET /api/health/metrics`
- Docker 容器状态: `docker compose -f ops/docker/docker-compose.yml ps`
- 日志查看: `docker compose -f ops/docker/docker-compose.yml logs -f backend`
