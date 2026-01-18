@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo API接口智能测试平台 - Docker一键部署
echo ==========================================
echo.

:: 颜色定义（Windows 10支持）
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "NC=[0m"

:: 检查Docker Desktop是否安装
echo %GREEN%1. 检查Docker环境...%NC%
where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%✗ Docker未安装，请先安装Docker Desktop%NC%
    echo.
    echo 请访问以下地址下载并安装Docker Desktop:
    echo https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

:: 检查Docker是否运行
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%✗ Docker未运行，请启动Docker Desktop%NC%
    echo.
    echo 请确保Docker Desktop已启动并运行
    pause
    exit /b 1
)

:: 检测docker compose命令
docker compose version >nul 2>&1
if %errorlevel% equ 0 (
    set "DOCKER_COMPOSE=docker compose"
) else (
    docker-compose version >nul 2>&1
    if %errorlevel% equ 0 (
        set "DOCKER_COMPOSE=docker-compose"
    ) else (
        echo %RED%✗ Docker Compose未安装%NC%
        pause
        exit /b 1
    )
)

echo %GREEN%✓ Docker环境检查通过%NC%
echo.

:: 停止现有服务（如果有）
echo %GREEN%2. 清理现有服务...%NC%
%DOCKER_COMPOSE% down -v 2>nul
if %errorlevel% equ 0 (
    echo %GREEN%✓ 现有服务已清理%NC%
) else (
    echo 没有运行中的服务需要清理
)
echo.

:: 构建镜像
echo %GREEN%3. 构建Docker镜像...%NC%
echo 这可能需要几分钟时间，请耐心等待...
%DOCKER_COMPOSE% build --no-cache
if %errorlevel% neq 0 (
    echo %RED%✗ 镜像构建失败%NC%
    pause
    exit /b 1
)
echo %GREEN%✓ 镜像构建完成%NC%
echo.

:: 启动基础服务（MySQL, Redis, Milvus等）
echo %GREEN%4. 启动基础服务（MySQL, Redis, Milvus等）...%NC%
%DOCKER_COMPOSE% up -d mysql redis milvus-standalone etcd minio neo4j
if %errorlevel% neq 0 (
    echo %RED%✗ 基础服务启动失败%NC%
    pause
    exit /b 1
)
echo %GREEN%✓ 基础服务启动中...%NC%

:: 等待MySQL就绪
echo.
echo %YELLOW%等待MySQL数据库就绪...%NC%
set "mysql_ready=0"
for /l %%i in (1,1,60) do (
    timeout /t 2 /nobreak >nul
    docker exec api_test_mysql mysqladmin ping -h localhost -uroot -p123456 --silent >nul 2>&1
    if !errorlevel! equ 0 (
        echo %GREEN%✓ MySQL就绪%NC%
        set "mysql_ready=1"
        goto :mysql_done
    )
    echo|set /p="."
)
:mysql_done
if !mysql_ready! equ 0 (
    echo.
    echo %RED%✗ MySQL启动超时%NC%
    pause
    exit /b 1
)
echo.

:: 等待数据库初始化完成
echo %YELLOW%等待数据库初始化...%NC%
set "db_init=0"
for /l %%i in (1,1,30) do (
    timeout /t 2 /nobreak >nul
    docker exec api_test_mysql mysql -uroot -p123456 -e "USE api_test; SHOW TABLES;" 2>nul | findstr /i "users" >nul
    if !errorlevel! equ 0 (
        echo %GREEN%✓ 数据库表已初始化%NC%
        set "db_init=1"
        goto :db_init_done
    )
    echo|set /p="."
)
:db_init_done
if !db_init! equ 0 (
    echo.
    echo %YELLOW%⚠ 数据库表可能未完全初始化，将尝试通过SQLAlchemy创建%NC%
)
echo.

:: 等待Redis就绪
echo %YELLOW%等待Redis就绪...%NC%
set "redis_ready=0"
for /l %%i in (1,1,30) do (
    timeout /t 1 /nobreak >nul
    docker exec api_test_redis redis-cli ping 2>nul | findstr /i "PONG" >nul
    if !errorlevel! equ 0 (
        echo %GREEN%✓ Redis就绪%NC%
        set "redis_ready=1"
        goto :redis_done
    )
    echo|set /p="."
)
:redis_done
if !redis_ready! equ 0 (
    echo.
    echo %YELLOW%⚠ Redis可能未完全就绪，继续启动其他服务%NC%
)
echo.

:: 等待Milvus就绪
echo %YELLOW%等待Milvus就绪...%NC%
timeout /t 10 /nobreak >nul
echo %GREEN%✓ Milvus启动中（需要额外时间完成初始化）%NC%
echo.

:: 启动后端服务
echo %GREEN%5. 启动后端服务...%NC%
%DOCKER_COMPOSE% up -d backend
if %errorlevel% neq 0 (
    echo %RED%✗ 后端服务启动失败%NC%
    pause
    exit /b 1
)
echo %GREEN%✓ 后端服务启动中...%NC%

:: 等待后端就绪
echo.
echo %YELLOW%等待后端服务就绪...%NC%
set "backend_ready=0"
for /l %%i in (1,1,60) do (
    timeout /t 2 /nobreak >nul
    :: 尝试使用curl，如果不可用则使用PowerShell
    curl -f http://localhost:8004/health >nul 2>&1
    if !errorlevel! equ 0 (
        echo %GREEN%✓ 后端服务就绪%NC%
        set "backend_ready=1"
        goto :backend_done
    )
    :: 备用检查方法：使用PowerShell
    powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:8004/health' -UseBasicParsing -TimeoutSec 1; exit 0 } catch { exit 1 }" >nul 2>&1
    if !errorlevel! equ 0 (
        echo %GREEN%✓ 后端服务就绪%NC%
        set "backend_ready=1"
        goto :backend_done
    )
    echo|set /p="."
)
:backend_done
if !backend_ready! equ 0 (
    echo.
    echo %YELLOW%⚠ 后端服务启动超时，请检查日志: %DOCKER_COMPOSE% logs backend%NC%
)
echo.

:: 启动Celery Worker
echo %GREEN%6. 启动Celery Worker...%NC%
%DOCKER_COMPOSE% up -d celery_worker
if %errorlevel% neq 0 (
    echo %RED%✗ Celery Worker启动失败%NC%
    pause
    exit /b 1
)
echo %GREEN%✓ Celery Worker启动中...%NC%
timeout /t 5 /nobreak >nul

:: 启动前端服务
echo %GREEN%7. 启动前端服务...%NC%
%DOCKER_COMPOSE% up -d frontend
if %errorlevel% neq 0 (
    echo %RED%✗ 前端服务启动失败%NC%
    pause
    exit /b 1
)
echo %GREEN%✓ 前端服务启动中...%NC%
timeout /t 10 /nobreak >nul

:: 检查所有服务状态
echo.
echo %GREEN%8. 检查服务状态...%NC%
%DOCKER_COMPOSE% ps
echo.

echo %GREEN%9. 验证服务健康状态...%NC%

:: 检查后端
set "backend_health=0"
curl -f http://localhost:8004/health >nul 2>&1
if !errorlevel! equ 0 (
    set "backend_health=1"
) else (
    powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:8004/health' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
    if !errorlevel! equ 0 (
        set "backend_health=1"
    )
)
if !backend_health! equ 1 (
    echo %GREEN%✓ 后端服务健康%NC%
) else (
    echo %YELLOW%⚠ 后端服务可能未就绪，查看日志: %DOCKER_COMPOSE% logs backend%NC%
)

:: 检查前端（简单检查端口）
netstat -an | findstr ":3006" >nul
if !errorlevel! equ 0 (
    echo %GREEN%✓ 前端服务运行中%NC%
) else (
    echo %YELLOW%⚠ 前端服务可能未就绪，查看日志: %DOCKER_COMPOSE% logs frontend%NC%
)

echo.
echo ==========================================
echo %GREEN%部署完成！%NC%
echo ==========================================
echo.
echo %GREEN%服务访问地址：%NC%
echo   前端界面: http://localhost:3006
echo   后端API: http://localhost:8004
echo   API文档: http://localhost:8004/docs
echo   ReDoc文档: http://localhost:8004/redoc
echo.
echo %GREEN%服务管理：%NC%
echo   MySQL: localhost:3309 (用户: root, 密码: 123456)
echo   Redis: localhost:6382
echo   Milvus: localhost:9004
echo   MinIO控制台: http://localhost:9006 (用户: minioadmin, 密码: minioadmin123456)
echo   Neo4j浏览器: http://localhost:7474 (用户: neo4j, 密码: 123456789)
echo.
echo %GREEN%默认管理员账号：%NC%
echo   用户名: admin
echo   密码: 123456
echo.
echo %GREEN%常用命令：%NC%
echo   查看所有日志: %DOCKER_COMPOSE% logs -f
echo   查看后端日志: %DOCKER_COMPOSE% logs -f backend
echo   查看前端日志: %DOCKER_COMPOSE% logs -f frontend
echo   查看Celery日志: %DOCKER_COMPOSE% logs -f celery_worker
echo   停止服务: %DOCKER_COMPOSE% stop
echo   重启服务: %DOCKER_COMPOSE% restart
echo   完全停止并清理: %DOCKER_COMPOSE% down -v
echo.
echo %YELLOW%注意：%NC%
echo   - 首次启动时，Milvus和Neo4j可能需要额外时间完成初始化
echo   - 如果服务无法访问，请检查日志排查问题
echo   - 前端服务首次启动可能需要较长时间编译
echo.
pause

