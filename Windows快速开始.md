# Windows 10 快速开始指南

## 📋 前置要求

1. **安装 Docker Desktop**
   - 下载地址：https://www.docker.com/products/docker-desktop
   - 详细安装步骤请参考：[Windows10部署指南.md](./Windows10部署指南.md)

2. **确保 Docker Desktop 正在运行**
   - 系统托盘中的 Docker 图标应为绿色

## 🚀 一键部署

### 首次部署

1. 双击运行 `deploy.bat`
2. 等待部署完成（首次部署可能需要 10-30 分钟）
3. 部署完成后，访问 http://localhost:3006

### 日常使用

- **启动服务**: 双击 `start.bat`
- **停止服务**: 双击 `stop.bat`
- **重启服务**: 双击 `restart.bat`
- **查看日志**: 双击 `logs.bat`（或运行 `logs.bat backend` 查看特定服务）

## 🌐 访问地址

- **前端界面**: http://localhost:3006
- **后端API**: http://localhost:8004
- **API文档**: http://localhost:8004/docs
- 提示：首次使用请先在登录页注册账户，或通过接口创建用户（无内置默认账号）

## 📝 常用命令

在项目根目录打开命令提示符（CMD）或 PowerShell：

```cmd
:: 查看服务状态
docker compose ps

:: 查看所有日志
docker compose logs -f

:: 查看特定服务日志
docker compose logs -f backend
docker compose logs -f frontend

:: 停止所有服务
docker compose stop

:: 停止并删除容器（保留数据）
docker compose down

:: 完全清理（删除所有数据）
docker compose down -v
```

## ❓ 遇到问题？

1. 查看详细部署指南：[Windows10部署指南.md](./Windows10部署指南.md)
2. 查看服务日志：运行 `logs.bat`
3. 检查 Docker Desktop 是否正常运行

## 📚 更多信息

- 完整部署指南：[Windows10部署指南.md](./Windows10部署指南.md)
- 项目 README：[README.md](./README.md)

