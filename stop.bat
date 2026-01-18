@echo off
chcp 65001 >nul

echo ==========================================
echo API接口智能测试平台 - 停止服务
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

echo [信息] 停止所有服务...
%DOCKER_COMPOSE% stop

if %errorlevel% equ 0 (
    echo [成功] 服务已停止
) else (
    echo [警告] 部分服务可能未运行
)

echo.
pause

