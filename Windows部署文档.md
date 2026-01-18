# API接口智能测试系统 - Windows 10/11 部署文档

## 📋 目录

1. [系统要求](#系统要求)
2. [组件版本清单](#组件版本清单)
3. [环境准备](#环境准备)
4. [组件安装](#组件安装)
5. [系统部署](#系统部署)
6. [服务启动](#服务启动)
7. [验证部署](#验证部署)
8. [常见问题](#常见问题)

---

## 系统要求

### 硬件要求
- **CPU**: 4核心及以上
- **内存**: 16GB及以上（推荐32GB）
- **硬盘**: 50GB可用空间
- **操作系统**: Windows 10 (64位) 或 Windows 11 (64位)

### 软件要求
- 管理员权限
- 网络连接（用于下载依赖）

---

## 组件版本清单

| 组件 | 版本 | 说明 |
|------|------|------|
| **Python** | 3.11.7 | 后端开发语言 |
| **Node.js** | 20.11.0 LTS | 前端开发环境 |
| **MySQL** | 8.0.36 | 关系型数据库 |
| **Redis** | 7.2.4 | 缓存和消息队列 |
| **MinIO** | RELEASE.2024-01-16T16-07-38Z | 对象存储服务 |
| **ChromaDB** | 0.4.22 | 向量数据库（Python包） |
| **Celery** | 5.3.4 | 异步任务队列 |
| **JMeter** | 5.6.3 | 性能测试工具 |
| **Milvus** | 2.3.0 | 向量数据库服务 |
| **etcd** | 3.5.10 | Milvus元数据存储 |
| **Neo4j** | 5.15.0 | 图数据库 |

---

## 环境准备

### 1. 设置系统时区

系统时区需要设置为上海时区（UTC+8）。

**方法一：使用命令（需要管理员权限）**
```cmd
tzutil /s "China Standard Time"
```

**方法二：图形界面设置**
1. 打开"设置" → "时间和语言" → "日期和时间"
2. 点击"时区"，选择"(UTC+08:00) 北京，重庆，香港特别行政区，乌鲁木齐"

### 2. 检查系统环境

确保系统已安装：
- Windows 10/11 64位
- 管理员权限
- 网络连接正常

---

## 组件安装

### 1. Python 3.11.7 安装

#### 1.1 下载
- **官方下载**: https://www.python.org/downloads/release/python-3117/
- **阿里云镜像**: https://mirrors.aliyun.com/python-release/windows/
- **推荐下载**: `python-3.11.7-amd64.exe`

#### 1.2 安装步骤
1. 运行安装程序 `python-3.11.7-amd64.exe`
2. **重要**: 勾选 "Add Python 3.11 to PATH"
3. 选择 "Install Now" 或 "Customize installation"
4. 如果选择自定义安装，确保勾选：
   - ✅ pip
   - ✅ tcl/tk and IDLE
   - ✅ Python test suite
   - ✅ py launcher
   - ✅ for all users (推荐)
5. 点击 "Install" 开始安装
6. 安装完成后，点击 "Close"

#### 1.3 验证安装
打开命令提示符（CMD）或PowerShell，执行：
```cmd
python --version
```
应显示：`Python 3.11.7`

```cmd
pip --version
```
应显示pip版本信息

#### 1.4 配置pip使用阿里云镜像
创建或编辑文件：`%APPDATA%\pip\pip.ini`

**Windows路径**: `C:\Users\你的用户名\AppData\Roaming\pip\pip.ini`

文件内容：
```ini
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
[install]
trusted-host = mirrors.aliyun.com
```

验证配置：
```cmd
pip config list
```

---

### 2. Node.js 20.11.0 LTS 安装

#### 2.1 下载
- **官方下载**: https://nodejs.org/dist/v20.11.0/
- **阿里云镜像**: https://npmmirror.com/mirrors/node/v20.11.0/
- **推荐下载**: `node-v20.11.0-x64.msi` (Windows Installer)

#### 2.2 安装步骤
1. 运行安装程序 `node-v20.11.0-x64.msi`
2. 点击 "Next" → 接受许可协议 → "Next"
3. 选择安装路径（默认：`C:\Program Files\nodejs\`）
4. 确保勾选所有组件：
   - ✅ Node.js runtime
   - ✅ npm package manager
   - ✅ Add to PATH
5. 点击 "Install" 开始安装
6. 安装完成后，点击 "Finish"

#### 2.3 验证安装
```cmd
node --version
```
应显示：`v20.11.0`

```cmd
npm --version
```
应显示npm版本信息

#### 2.4 配置npm使用阿里云镜像
```cmd
npm config set registry https://registry.npmmirror.com
npm config set disturl https://npmmirror.com/dist
npm config set electron_mirror https://npmmirror.com/mirrors/electron/
npm config set sass_binary_site https://npmmirror.com/mirrors/node-sass/
npm config set chromedriver_cdnurl https://npmmirror.com/mirrors/chromedriver/
```

验证配置：
```cmd
npm config get registry
```
应显示：`https://registry.npmmirror.com/`

---

### 3. MySQL 8.0.36 安装

#### 3.1 下载
- **官方下载**: https://dev.mysql.com/downloads/mysql/
- **阿里云镜像**: https://mirrors.aliyun.com/mysql/downloads/MySQL-8.0/
- **推荐下载**: `mysql-installer-community-8.0.36.0.msi`

#### 3.2 安装步骤
1. 运行安装程序 `mysql-installer-community-8.0.36.0.msi`
2. 选择安装类型：**Developer Default** 或 **Server only**
3. 点击 "Execute" 安装所需组件
4. 配置类型选择：**Development Computer**（开发环境）
5. 认证方式选择：**Use Strong Password Encryption**
6. 设置root密码：**123456**（或自定义，记住此密码）
7. 配置Windows服务：
   - Service Name: `MySQL80`
   - ✅ Start the MySQL Server at System Startup
8. 点击 "Execute" 完成配置
9. 安装完成后，点击 "Finish"

#### 3.3 验证安装
打开命令提示符，执行：
```cmd
mysql --version
```
应显示MySQL版本信息

```cmd
mysql -uroot -p123456
```
应能成功连接到MySQL

#### 3.4 配置MySQL
编辑MySQL配置文件：`C:\ProgramData\MySQL\MySQL Server 8.0\my.ini`

在 `[mysqld]` 部分添加：
```ini
[mysqld]
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
default-time-zone='+08:00'
max_connections=200
```

重启MySQL服务：
```cmd
net stop MySQL80
net start MySQL80
```

---

### 4. Redis 7.2.4 安装

#### 4.1 下载
- **GitHub下载**: https://github.com/tporadowski/redis/releases
- **推荐下载**: `Redis-x64-7.2.4.zip`

#### 4.2 安装步骤
1. 解压 `Redis-x64-7.2.4.zip` 到 `C:\Redis\`
2. 打开命令提示符（管理员权限），执行：
```cmd
cd C:\Redis
redis-server --service-install redis.windows.conf --service-name Redis --port 6379
redis-server --service-start
```

#### 4.3 验证安装
```cmd
redis-cli ping
```
应返回：`PONG`

#### 4.4 配置Redis
编辑配置文件：`C:\Redis\redis.windows.conf`

修改以下配置：
```conf
# 绑定地址（允许本地连接）
bind 127.0.0.1

# 端口
port 6379

# 密码（可选，如需要）
# requirepass 123456

# 持久化
save 900 1
save 300 10
save 60 10000
```

重启Redis服务：
```cmd
redis-server --service-stop
redis-server --service-start
```

---

### 5. MinIO RELEASE.2024-01-16T16-07-38Z 安装

#### 5.1 下载
- **官方下载**: https://dl.min.io/server/minio/release/windows-amd64/
- **推荐下载**: `minio.exe` (RELEASE.2024-01-16T16-07-38Z)

#### 5.2 安装步骤
1. 创建目录：`C:\MinIO\`
2. 将 `minio.exe` 复制到 `C:\MinIO\`
3. 创建数据目录：`C:\MinIO\data`
4. 创建启动脚本：`C:\MinIO\start_minio.bat`

**start_minio.bat 内容**：
```batch
@echo off
cd /d C:\MinIO
minio.exe server C:\MinIO\data --console-address ":9001"
```

#### 5.3 配置为Windows服务（可选）
使用NSSM（Non-Sucking Service Manager）将MinIO配置为服务：

1. 下载NSSM: https://nssm.cc/download
2. 解压并运行：`nssm.exe install MinIO`
3. 配置：
   - Path: `C:\MinIO\minio.exe`
   - Startup directory: `C:\MinIO`
   - Arguments: `server C:\MinIO\data --console-address ":9001"`
   - Service name: `MinIO`
4. 启动服务：
```cmd
nssm start MinIO
```

#### 5.4 验证安装
访问：http://localhost:9001
- 用户名：`minioadmin`
- 密码：`minioadmin123456`

#### 5.5 创建存储桶
1. 登录MinIO控制台
2. 创建Bucket：`api-test-uploads`
3. 设置访问策略为公开（如需要）

---

### 6. Neo4j 5.15.0 安装

#### 6.1 下载
- **官方下载**: https://neo4j.com/download/
- **推荐下载**: `neo4j-community-5.15.0-windows.zip`

#### 6.2 安装步骤
1. 解压 `neo4j-community-5.15.0-windows.zip` 到 `C:\neo4j\`
2. 打开命令提示符（管理员权限），执行：
```cmd
cd C:\neo4j\neo4j-community-5.15.0\bin
neo4j.bat install-service
neo4j.bat start
```

#### 6.3 配置Neo4j
编辑配置文件：`C:\neo4j\neo4j-community-5.15.0\conf\neo4j.conf`

修改以下配置：
```conf
# 数据库位置
dbms.directories.data=C:/neo4j/neo4j-community-5.15.0/data

# 监听地址
dbms.default_listen_address=0.0.0.0

# HTTP端口
dbms.connector.http.listen_address=:7474

# Bolt端口
dbms.connector.bolt.listen_address=:7687

# 内存设置（根据系统内存调整）
dbms.memory.heap.initial_size=2g
dbms.memory.heap.max_size=4g
dbms.memory.pagecache.size=2g

# 认证
dbms.security.auth_enabled=true
```

#### 6.4 设置密码
1. 访问：http://localhost:7474
2. 首次登录用户名/密码：`neo4j` / `neo4j`
3. 设置新密码：`123456789`

#### 6.5 验证安装
```cmd
neo4j.bat status
```
应显示服务正在运行

---

### 7. Milvus 2.3.0 安装

#### 7.1 前置要求
- 已安装etcd 3.5.10
- 已安装MinIO（见步骤5）

#### 7.2 下载
- **GitHub下载**: https://github.com/milvus-io/milvus/releases/tag/v2.3.0
- **推荐下载**: `milvus-windows-amd64.exe` 或使用Docker Desktop

#### 7.3 安装方式一：使用Docker Desktop（推荐）
1. 安装Docker Desktop for Windows: https://www.docker.com/products/docker-desktop
2. 拉取镜像：
```cmd
docker pull milvusdb/milvus:v2.3.0
docker pull quay.io/coreos/etcd:v3.5.5
```

3. 创建docker-compose.yml（仅Milvus部分）：
```yaml
version: '3.8'
services:
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    container_name: milvus-etcd
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd

  minio:
    image: minio/minio:RELEASE.2024-01-16T16-07-38Z
    container_name: milvus-minio
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin123456
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    command: minio server /data --console-address ":9001"

  milvus:
    image: milvusdb/milvus:v2.3.0
    container_name: milvus-standalone
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
      - "9091:9091"
    volumes:
      - milvus_data:/var/lib/milvus
    depends_on:
      - etcd
      - minio

volumes:
  etcd_data:
  minio_data:
  milvus_data:
```

4. 启动服务：
```cmd
docker-compose up -d
```

#### 7.4 安装方式二：Windows原生安装（复杂，不推荐）
由于Milvus在Windows上原生安装较复杂，建议使用Docker Desktop方式。

#### 7.5 验证安装
```cmd
docker ps
```
应看到milvus、etcd、minio容器运行

访问：http://localhost:9091 查看Milvus监控

---

### 8. etcd 3.5.10 安装

#### 8.1 下载
- **GitHub下载**: https://github.com/etcd-io/etcd/releases/tag/v3.5.10
- **推荐下载**: `etcd-v3.5.10-windows-amd64.zip`

#### 8.2 安装步骤
1. 解压 `etcd-v3.5.10-windows-amd64.zip` 到 `C:\etcd\`
2. 创建数据目录：`C:\etcd\data`
3. 创建启动脚本：`C:\etcd\start_etcd.bat`

**start_etcd.bat 内容**：
```batch
@echo off
cd /d C:\etcd
etcd.exe --name default --data-dir C:\etcd\data --listen-client-urls http://0.0.0.0:2379 --advertise-client-urls http://127.0.0.1:2379 --listen-peer-urls http://0.0.0.0:2380 --initial-advertise-peer-urls http://127.0.0.1:2380 --initial-cluster default=http://127.0.0.1:2380
```

#### 8.3 配置为Windows服务（使用NSSM）
```cmd
nssm install etcd
```
配置：
- Path: `C:\etcd\etcd.exe`
- Arguments: `--name default --data-dir C:\etcd\data --listen-client-urls http://0.0.0.0:2379 --advertise-client-urls http://127.0.0.1:2379`
- Startup directory: `C:\etcd`

#### 8.4 验证安装
```cmd
C:\etcd\etcdctl.exe version
```

---

### 9. JMeter 5.6.3 安装

#### 9.1 下载
- **官方下载**: https://jmeter.apache.org/download_jmeter.cgi
- **阿里云镜像**: https://mirrors.aliyun.com/apache/jmeter/binaries/
- **推荐下载**: `apache-jmeter-5.6.3.zip`

#### 9.2 安装步骤
1. 解压 `apache-jmeter-5.6.3.zip` 到 `C:\JMeter\`
2. 配置环境变量：
   - 变量名：`JMETER_HOME`
   - 变量值：`C:\JMeter\apache-jmeter-5.6.3`
   - 添加到PATH：`%JMETER_HOME%\bin`

#### 9.3 验证安装
```cmd
jmeter --version
```
应显示JMeter版本信息

---

### 10. ChromaDB 0.4.22 安装

ChromaDB是Python包，将在后端依赖安装时自动安装。

如需单独安装：
```cmd
pip install chromadb==0.4.22 -i https://mirrors.aliyun.com/pypi/simple/
```

---

## 系统部署

### 1. 使用一键部署脚本（推荐）

1. 以**管理员身份**运行 `deploy_windows.bat`
2. 脚本会自动：
   - 设置时区
   - 检查环境
   - 配置镜像源
   - 创建虚拟环境
   - 安装依赖
   - 初始化数据库

### 2. 手动部署步骤

#### 2.1 克隆/下载项目
确保项目文件在本地，例如：`C:\Projects\apitest\`

#### 2.2 创建Python虚拟环境
```cmd
cd C:\Projects\apitest\backend
python -m venv venv
```

#### 2.3 激活虚拟环境
```cmd
venv\Scripts\activate.bat
```

#### 2.4 安装Python依赖
```cmd
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
```

#### 2.5 安装前端依赖
```cmd
cd C:\Projects\apitest\frontend
npm install
```

#### 2.6 初始化数据库
确保MySQL服务已启动，然后执行：
```cmd
mysql -uroot -p123456 < C:\Projects\apitest\backend\init.sql
```

#### 2.7 配置环境变量
创建文件：`backend\.env`

```env
# MySQL配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=api_test

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379

# Milvus配置
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_USER=root
MILVUS_PASSWORD=123456

# MinIO配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123456

# Neo4j配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=123456789

# API Keys（请替换为实际值）
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
QWEN_API_KEY=sk-your-key-here
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-vl-plus
```

---

## 服务启动

### 方式一：使用启动脚本（推荐）

运行 `start_all.bat`，脚本会自动启动：
1. 后端服务（端口8004）
2. Celery Worker
3. 前端服务（端口3000）

### 方式二：手动启动

#### 1. 启动后端服务
```cmd
cd C:\Projects\apitest\backend
venv\Scripts\activate.bat
uvicorn main:app --host 0.0.0.0 --port 8004
```

#### 2. 启动Celery Worker（新开一个命令行窗口）
```cmd
cd C:\Projects\apitest\backend
venv\Scripts\activate.bat
celery -A app.celery_app worker --loglevel=info --concurrency=4
```

#### 3. 启动前端服务（新开一个命令行窗口）
```cmd
cd C:\Projects\apitest\frontend
npm start
```

### 停止服务

运行 `stop_all.bat` 或手动关闭各个命令行窗口。

---

## 验证部署

### 1. 检查服务状态

| 服务 | 地址 | 验证方法 |
|------|------|----------|
| 后端API | http://localhost:8004 | 浏览器访问 http://localhost:8004/docs |
| 前端 | http://localhost:3000 | 浏览器访问 http://localhost:3000 |
| MySQL | localhost:3306 | `mysql -uroot -p123456` |
| Redis | localhost:6379 | `redis-cli ping` |
| MinIO | http://localhost:9001 | 浏览器访问控制台 |
| Neo4j | http://localhost:7474 | 浏览器访问Web界面 |
| Milvus | localhost:19530 | 查看Docker容器状态 |

### 2. 测试API接口

访问：http://localhost:8004/docs

测试健康检查接口：
```bash
curl http://localhost:8004/health
```

### 3. 测试前端

访问：http://localhost:3000

登录说明：首次使用请在前端登录页完成注册（系统不预置默认账号）。也可以在 http://localhost:8004/docs 使用 /api/auth/register 接口创建用户后登录。

---

## 常见问题

### 1. Python虚拟环境激活失败

**问题**: `venv\Scripts\activate.bat` 执行失败

**解决方案**:
- 检查Python是否正确安装
- 检查虚拟环境是否创建成功
- 尝试使用：`python -m venv --clear venv` 重新创建

### 2. pip安装依赖失败

**问题**: 下载速度慢或连接超时

**解决方案**:
- 确认pip.ini配置文件正确
- 使用命令：`pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com`
- 检查网络连接

### 3. MySQL连接失败

**问题**: 无法连接到MySQL

**解决方案**:
- 检查MySQL服务是否启动：`net start MySQL80`
- 检查端口3306是否被占用
- 确认用户名和密码正确
- 检查防火墙设置

### 4. Redis连接失败

**问题**: 无法连接到Redis

**解决方案**:
- 检查Redis服务是否启动
- 确认端口6379未被占用
- 检查redis.windows.conf配置

### 5. 前端npm install失败

**问题**: 依赖安装失败

**解决方案**:
- 确认npm镜像配置正确
- 清除缓存：`npm cache clean --force`
- 删除node_modules后重新安装：`rmdir /s /q node_modules && npm install`

### 6. Milvus连接失败

**问题**: 无法连接到Milvus

**解决方案**:
- 检查Docker容器是否运行：`docker ps`
- 检查etcd和MinIO是否正常
- 查看Milvus日志：`docker logs milvus-standalone`

### 7. Celery Worker启动失败

**问题**: Celery无法启动

**解决方案**:
- 检查Redis是否正常运行
- 确认虚拟环境已激活
- 检查celery_app.py配置

### 8. 端口被占用

**问题**: 端口已被其他程序占用

**解决方案**:
- 查找占用端口的进程：`netstat -ano | findstr :8004`
- 结束进程或修改配置文件中的端口

### 9. 时区设置问题

**问题**: 时间显示不正确

**解决方案**:
- 运行：`tzutil /s "China Standard Time"`
- 或在系统设置中手动设置时区

### 10. 权限问题

**问题**: 某些操作需要管理员权限

**解决方案**:
- 右键点击命令提示符，选择"以管理员身份运行"
- 确保有足够的系统权限

---

## 技术支持

如遇到其他问题，请：
1. 查看系统日志
2. 检查各服务的状态
3. 参考官方文档
4. 联系技术支持

---

## 附录

### 端口清单

| 服务 | 端口 | 说明 |
|------|------|------|
| 后端API | 8004 | FastAPI服务 |
| 前端 | 3000 | React开发服务器 |
| MySQL | 3306 | 数据库服务 |
| Redis | 6379 | 缓存服务 |
| MinIO API | 9000 | 对象存储API |
| MinIO Console | 9001 | 对象存储控制台 |
| Neo4j HTTP | 7474 | Neo4j Web界面 |
| Neo4j Bolt | 7687 | Neo4j数据库连接 |
| Milvus | 19530 | 向量数据库服务 |
| Milvus监控 | 9091 | Milvus监控界面 |
| etcd | 2379 | etcd服务端口 |

### 环境变量说明

详细的环境变量配置请参考 `backend/app/config.py` 文件。

---

**文档版本**: 1.0  
**最后更新**: 2024年1月  
**维护者**: API测试系统开发团队

