# Windows 快速部署指南

## 🚀 快速开始

### 第一步：环境检查

运行环境检查脚本，确保所有依赖已正确安装：

```cmd
check_environment.bat
```

### 第二步：一键部署

以**管理员身份**运行部署脚本：

```cmd
deploy_windows.bat
```

### 第三步：启动服务

部署完成后，运行启动脚本：

```cmd
start_all.bat
```

### 第四步：访问系统

- **前端地址**: http://localhost:3000
- **后端API文档**: http://localhost:8004/docs

---

## 📦 必需组件版本

| 组件 | 版本 | 下载地址 |
|------|------|----------|
| Python | 3.11.7 | [下载](https://www.python.org/downloads/release/python-3117/) |
| Node.js | 20.11.0 LTS | [下载](https://nodejs.org/dist/v20.11.0/) |
| MySQL | 8.0.36 | [下载](https://dev.mysql.com/downloads/mysql/) |
| Redis | 7.2.4 | [下载](https://github.com/tporadowski/redis/releases) |
| MinIO | RELEASE.2024-01-16 | [下载](https://dl.min.io/server/minio/release/windows-amd64/) |
| Neo4j | 5.15.0 | [下载](https://neo4j.com/download/) |
| Milvus | 2.3.0 | [Docker方式](https://www.docker.com/products/docker-desktop) |
| etcd | 3.5.10 | [下载](https://github.com/etcd-io/etcd/releases/tag/v3.5.10) |
| JMeter | 5.6.3 | [下载](https://jmeter.apache.org/download_jmeter.cgi) |

---

## ⚙️ 配置说明

### 1. 时区设置

部署脚本会自动设置时区为上海时区。如需手动设置：

```cmd
tzutil /s "China Standard Time"
```

### 2. 镜像源配置

#### Python pip镜像（阿里云）
配置文件位置：`%APPDATA%\pip\pip.ini`

```ini
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
[install]
trusted-host = mirrors.aliyun.com
```

#### Node.js npm镜像（阿里云）
```cmd
npm config set registry https://registry.npmmirror.com
```

### 3. 数据库配置

#### MySQL配置
- 端口：3306
- 用户名：root
- 密码：123456（可在部署时修改）
- 数据库：api_test

#### Redis配置
- 端口：6379
- 密码：无（默认）

#### Neo4j配置
- HTTP端口：7474
- Bolt端口：7687
- 用户名：neo4j
- 密码：123456789

### 4. 对象存储配置

#### MinIO配置
- API端口：9000
- 控制台端口：9001
- 用户名：minioadmin
- 密码：minioadmin123456

### 5. 向量数据库配置

#### Milvus配置
- 端口：19530
- 监控端口：9091
- 依赖：etcd + MinIO

---

## 🔧 服务管理

### 启动所有服务
```cmd
start_all.bat
```

### 停止所有服务
```cmd
stop_all.bat
```

### 单独启动服务

#### 后端服务
```cmd
cd backend
venv\Scripts\activate.bat
uvicorn main:app --host 0.0.0.0 --port 8004
```

#### Celery Worker
```cmd
cd backend
venv\Scripts\activate.bat
celery -A app.celery_app worker --loglevel=info --concurrency=4
```

#### 前端服务
```cmd
cd frontend
npm start
```

---

## 📝 部署检查清单

部署前请确认：

- [ ] Python 3.11.7 已安装并添加到PATH
- [ ] Node.js 20.11.0 已安装并添加到PATH
- [ ] MySQL 8.0.36 已安装并启动
- [ ] Redis 7.2.4 已安装并启动
- [ ] MinIO 已安装并启动
- [ ] Neo4j 5.15.0 已安装并启动
- [ ] Milvus 2.3.0 已安装并启动（Docker方式）
- [ ] etcd 3.5.10 已安装并启动
- [ ] 系统时区已设置为上海时区
- [ ] pip和npm已配置阿里云镜像
- [ ] 有管理员权限运行脚本

---

## ❓ 常见问题

### Q1: 部署脚本运行失败？
**A**: 确保以管理员身份运行，并检查所有必需组件已安装。

### Q2: Python依赖安装失败？
**A**: 检查pip镜像配置，或手动执行：
```cmd
pip install -r backend\requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
```

### Q3: 前端npm install失败？
**A**: 清除缓存后重试：
```cmd
npm cache clean --force
rmdir /s /q node_modules
npm install
```

### Q4: MySQL连接失败？
**A**: 检查MySQL服务是否启动：
```cmd
net start MySQL80
```

### Q5: 端口被占用？
**A**: 查找占用端口的进程：
```cmd
netstat -ano | findstr :8004
```

---

## 📚 详细文档

更多详细信息请参考：
- **完整部署文档**: [Windows部署文档.md](./Windows部署文档.md)
- **系统架构文档**: [系统架构文档.md](./系统架构文档.md)

---

## 🆘 获取帮助

如遇到问题：
1. 运行 `check_environment.bat` 检查环境
2. 查看 `Windows部署文档.md` 中的常见问题部分
3. 检查各服务的日志文件

---

**最后更新**: 2024年1月

