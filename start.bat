@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo API接口智能测试平台 - 快速启动
echo ==========================================
echo.

:: 检测docker compose命令
docker compose version >nul 2>&1
if %errorlevel% equ 0 (
    set "DOCKER_COMPOSE=docker compose"
) else (
    docker-compose version >nul 2>&1
    if %errorlevel% equ 0 (
        set "DOCKER_COMPOSE=docker-compose"
    ) else (
        echo [错误] Docker Compose未安装
        pause
        exit /b 1
    )
)

:: 检查Docker是否运行
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Docker未运行，请启动Docker Desktop
    pause
    exit /b 1
)

echo [信息] 启动所有服务...
%DOCKER_COMPOSE% up -d

if %errorlevel% neq 0 (
    echo [错误] 服务启动失败
    pause
    exit /b 1
)

echo.
echo [成功] 服务启动完成！
echo.
echo 服务访问地址：
echo   前端界面: http://localhost:3006
echo   后端API: http://localhost:8004
echo   API文档: http://localhost:8004/docs
echo.
echo 查看日志: %DOCKER_COMPOSE% logs -f
echo 停止服务: %DOCKER_COMPOSE% stop
echo.
pause

