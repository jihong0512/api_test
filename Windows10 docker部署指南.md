# Windows 10 下一键 Docker 部署指南

## 目录
1. [系统要求](#系统要求)
2. [Docker Desktop 安装配置](#docker-desktop-安装配置)
3. [一键部署](#一键部署)
4. [验证部署](#验证部署)
5. [常见问题](#常见问题)
6. [服务管理](#服务管理)

---

## 系统要求

### 硬件要求
- **CPU**: 64位处理器，支持虚拟化（Intel VT-x 或 AMD-V）
- **内存**: 至少 8GB RAM（推荐 16GB）
- **磁盘空间**: 至少 20GB 可用空间
- **网络**: 稳定的互联网连接（用于下载镜像）

### 软件要求
- **操作系统**: Windows 10 64位（版本 1903 或更高）
- **Docker Desktop**: 4.0 或更高版本
- **WSL 2**: Windows Subsystem for Linux 2（Docker Desktop 会自动安装）

---

## Docker Desktop 安装配置

### 步骤 1: 下载 Docker Desktop

1. 访问 Docker 官网：https://www.docker.com/products/docker-desktop
2. 点击 "Download for Windows" 下载安装包
3. 或者直接访问：https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe

### 步骤 2: 安装 Docker Desktop

1. 双击下载的 `Docker Desktop Installer.exe`
2. 如果提示需要管理员权限，点击"是"
3. 在安装向导中：
   - ✅ 勾选 "Use WSL 2 instead of Hyper-V"（推荐）
   - ✅ 勾选 "Add shortcut to desktop"（可选）
4. 点击 "Ok" 开始安装
5. 安装完成后，点击 "Close and restart" 重启计算机

### 步骤 3: 启动并配置 Docker Desktop

1. **首次启动**
   - 重启后，从开始菜单或桌面快捷方式启动 Docker Desktop
   - 首次启动会显示服务协议，点击 "Accept"
   - 等待 Docker Desktop 启动完成（系统托盘图标变为绿色）

2. **配置资源分配**（重要）
   - 右键点击系统托盘中的 Docker 图标
   - 选择 "Settings" 或 "设置"
   - 进入 "Resources" 或 "资源" 选项卡
   - 推荐配置：
     ```
     CPU: 4 核心或更多（根据你的CPU核心数调整）
     内存: 至少 6GB（推荐 8GB 或更多）
     磁盘: 至少 20GB
     ```
   - 点击 "Apply & Restart" 应用设置

3. **配置镜像加速**（可选，但推荐）
   - 在 Settings 中，进入 "Docker Engine"
   - 添加以下配置（使用国内镜像源加速）：
     ```json
     {
       "registry-mirrors": [
         "https://docker.mirrors.ustc.edu.cn",
         "https://hub-mirror.c.163.com",
         "https://mirror.baidubce.com"
       ]
     }
     ```
   - 点击 "Apply & Restart"

4. **启用 WSL 2 集成**（如果使用 WSL 2）
   - 在 Settings 中，进入 "Resources" > "WSL Integration"
   - 启用你的 WSL 2 发行版（如 Ubuntu）
   - 点击 "Apply & Restart"

### 步骤 4: 验证 Docker 安装

1. 打开 PowerShell 或命令提示符（CMD）
2. 运行以下命令验证：
   ```bash
   docker --version
   docker-compose --version
   # 或者
   docker compose version
   ```
3. 运行测试容器：
   ```bash
   docker run hello-world
   ```
4. 如果看到 "Hello from Docker!" 消息，说明安装成功

---

## 一键部署

### 方法一：使用批处理脚本（推荐）

1. **准备项目文件**
   - 确保项目文件已下载到本地
   - 进入项目根目录（包含 `docker-compose.yml` 的目录）

2. **运行部署脚本**
   - 双击 `deploy.bat` 文件
   - 或者在命令提示符中运行：
     ```cmd
     deploy.bat
     ```

3. **等待部署完成**
   - 脚本会自动执行以下步骤：
     - 检查 Docker 环境
     - 清理现有服务
     - 构建 Docker 镜像（首次可能需要 10-30 分钟）
     - 启动基础服务（MySQL、Redis、Milvus 等）
     - 等待服务就绪
     - 启动应用服务（后端、Celery、前端）
     - 验证服务状态

### 方法二：手动部署

如果脚本执行失败，可以手动执行以下命令：

```cmd
:: 1. 停止现有服务
docker compose down -v

:: 2. 构建镜像
docker compose build --no-cache

:: 3. 启动所有服务
docker compose up -d

:: 4. 查看服务状态
docker compose ps

:: 5. 查看日志
docker compose logs -f
```

---

## 验证部署

### 1. 检查容器状态

```cmd
docker compose ps
```

所有服务应该显示为 "Up" 状态。

### 2. 访问服务

- **前端界面**: http://localhost:3006
- **后端API**: http://localhost:8004
- **API文档**: http://localhost:8004/docs
- **ReDoc文档**: http://localhost:8004/redoc

### 3. 检查服务健康

```cmd
:: 检查后端健康状态
curl http://localhost:8004/health

:: 或者使用浏览器访问
:: http://localhost:8004/health
```

### 4. 登录系统

- 打开浏览器访问：http://localhost:3006
- 使用默认管理员账号登录：
  - **用户名**: `admin`
  - **密码**: `123456`

---

## 常见问题

### 问题 1: Docker Desktop 无法启动

**症状**: Docker Desktop 启动失败，显示错误信息

**解决方案**:
1. 确保已启用虚拟化功能（在 BIOS 中启用 Intel VT-x 或 AMD-V）
2. 确保已安装 WSL 2：
   ```powershell
   wsl --install
   ```
3. 更新 WSL 2 内核：https://aka.ms/wsl2kernel
4. 重启计算机

### 问题 2: 端口被占用

**症状**: 启动服务时提示端口已被占用

**解决方案**:
1. 检查端口占用：
   ```cmd
   netstat -ano | findstr :8004
   netstat -ano | findstr :3006
   ```
2. 停止占用端口的进程，或修改 `docker-compose.yml` 中的端口映射

### 问题 3: 镜像构建失败

**症状**: 构建镜像时出现网络错误或超时

**解决方案**:
1. 配置 Docker 镜像加速（见上方配置步骤）
2. 检查网络连接
3. 重试构建：
   ```cmd
   docker compose build --no-cache
   ```

### 问题 4: MySQL 连接失败

**症状**: 后端服务无法连接 MySQL

**解决方案**:
1. 检查 MySQL 容器是否运行：
   ```cmd
   docker compose ps mysql
   ```
2. 查看 MySQL 日志：
   ```cmd
   docker compose logs mysql
   ```
3. 等待 MySQL 完全启动（可能需要 1-2 分钟）

### 问题 5: 前端无法访问后端

**症状**: 前端页面显示 API 请求失败

**解决方案**:
1. 检查后端服务是否正常运行：
   ```cmd
   curl http://localhost:8004/health
   ```
2. 检查前端环境变量配置（`docker-compose.yml` 中的 `REACT_APP_API_URL`）
3. 查看前端日志：
   ```cmd
   docker compose logs frontend
   ```

### 问题 6: 内存不足

**症状**: 容器频繁重启或系统卡顿

**解决方案**:
1. 增加 Docker Desktop 的内存分配（Settings > Resources）
2. 关闭其他占用内存的应用程序
3. 考虑减少并发服务数量

---

## 服务管理

### 查看服务状态

```cmd
docker compose ps
```

### 查看服务日志

```cmd
:: 查看所有服务日志
docker compose logs -f

:: 查看特定服务日志
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f celery_worker
docker compose logs -f mysql
```

### 停止服务

```cmd
:: 停止所有服务（保留数据）
docker compose stop

:: 停止并删除容器（保留数据卷）
docker compose down

:: 完全停止并删除所有数据
docker compose down -v
```

### 重启服务

```cmd
:: 重启所有服务
docker compose restart

:: 重启特定服务
docker compose restart backend
docker compose restart frontend
```

### 更新服务

```cmd
:: 1. 停止服务
docker compose down

:: 2. 拉取最新代码（如果有更新）

:: 3. 重新构建镜像
docker compose build --no-cache

:: 4. 启动服务
docker compose up -d
```

### 清理资源

```cmd
:: 清理未使用的镜像
docker image prune -a

:: 清理未使用的数据卷
docker volume prune

:: 清理所有未使用的资源
docker system prune -a --volumes
```

---

## 服务访问信息

### 应用服务

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端界面 | http://localhost:3006 | Web 用户界面 |
| 后端API | http://localhost:8004 | RESTful API |
| API文档 | http://localhost:8004/docs | Swagger UI |
| ReDoc文档 | http://localhost:8004/redoc | ReDoc 文档 |

### 基础服务

| 服务 | 地址 | 用户名 | 密码 |
|------|------|--------|------|
| MySQL | localhost:3309 | root | 123456 |
| Redis | localhost:6382 | - | - |
| Milvus | localhost:9004 | root | 123456 |
| MinIO控制台 | http://localhost:9006 | minioadmin | minioadmin123456 |
| Neo4j浏览器 | http://localhost:7474 | neo4j | 123456789 |

### 登录说明

- 首次使用请在前端登录页完成注册，系统不预置默认账号
- 也可以通过后端API创建用户后再登录

---

## 数据持久化

所有数据都存储在 Docker 数据卷中，即使删除容器也不会丢失数据：

- `mysql_data`: MySQL 数据库数据
- `redis_data`: Redis 数据（如果有）
- `milvus_data`: Milvus 向量数据库数据
- `etcd_data`: etcd 数据
- `minio_data`: MinIO 对象存储数据
- `neo4j_data`: Neo4j 图数据库数据
- `uploads`: 上传的文件

查看数据卷：
```cmd
docker volume ls
```

备份数据卷：
```cmd
docker run --rm -v apitest_mysql_data:/data -v %cd%:/backup alpine tar czf /backup/mysql_backup.tar.gz /data
```

---

## 性能优化建议

1. **资源分配**: 根据实际使用情况调整 Docker Desktop 的 CPU 和内存分配
2. **镜像加速**: 配置国内镜像源以加快镜像下载速度
3. **SSD 存储**: 将 Docker 数据存储在 SSD 上以提高性能
4. **关闭不必要的服务**: 如果不需要某些服务，可以在 `docker-compose.yml` 中注释掉

---

## 技术支持

如果遇到问题，可以：

1. 查看服务日志排查问题
2. 检查 Docker Desktop 的系统资源使用情况
3. 参考 Docker 官方文档：https://docs.docker.com/desktop/windows/
4. 查看项目 README 或联系技术支持

---

## 附录：完整部署命令参考

```cmd
:: ==========================================
:: 完整部署流程
:: ==========================================

:: 1. 检查 Docker 环境
docker --version
docker compose version

:: 2. 进入项目目录
cd /d D:\path\to\apitest

:: 3. 停止现有服务
docker compose down -v

:: 4. 构建镜像
docker compose build --no-cache

:: 5. 启动所有服务
docker compose up -d

:: 6. 查看服务状态
docker compose ps

:: 7. 查看日志
docker compose logs -f

:: 8. 验证服务
curl http://localhost:8004/health

:: 9. 访问前端
:: 浏览器打开: http://localhost:3006
```

---


