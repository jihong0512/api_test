@echo off
chcp 65001 >nul

echo ==========================================
echo API接口智能测试平台 - 查看日志
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

if "%1"=="" (
    echo [信息] 查看所有服务日志（按 Ctrl+C 退出）...
    %DOCKER_COMPOSE% logs -f
) else (
    echo [信息] 查看 %1 服务日志（按 Ctrl+C 退出）...
    %DOCKER_COMPOSE% logs -f %1
)

