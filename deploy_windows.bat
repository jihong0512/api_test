@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo API接口智能测试系统 - Windows一键部署脚本
echo ========================================
echo.

:: 设置颜色
color 0A

:: 设置时区为上海
echo [1/15] 设置系统时区为上海...
tzutil /s "China Standard Time"
if %errorlevel% equ 0 (
    echo ✓ 时区设置成功
) else (
    echo ✗ 时区设置失败，请手动设置
)
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请以管理员身份运行此脚本！
    pause
    exit /b 1
)

:: 设置变量
set PROJECT_ROOT=%~dp0
set PYTHON_VERSION=3.11.7
set NODEJS_VERSION=20.11.0
set MYSQL_VERSION=8.0.36
set REDIS_VERSION=7.2.4
set MINIO_VERSION=RELEASE.2024-01-16T16-07-38Z
set CHROMADB_VERSION=0.4.22
set CELERY_VERSION=5.3.4
set JMETER_VERSION=5.6.3
set MILVUS_VERSION=2.3.0
set ETCD_VERSION=3.5.10
set NEO4J_VERSION=5.15.0

set INSTALL_DIR=%PROJECT_ROOT%install
set VENV_DIR=%PROJECT_ROOT%backend\venv
set BACKEND_DIR=%PROJECT_ROOT%backend
set FRONTEND_DIR=%PROJECT_ROOT%frontend

:: 创建安装目录
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo [2/15] 检查并创建必要的目录...
if not exist "%BACKEND_DIR%\uploads" mkdir "%BACKEND_DIR%\uploads"
if not exist "%BACKEND_DIR%\reports" mkdir "%BACKEND_DIR%\reports"
if not exist "%BACKEND_DIR%\jmeter-results" mkdir "%BACKEND_DIR%\jmeter-results"
if not exist "%FRONTEND_DIR%\node_modules" mkdir "%FRONTEND_DIR%\node_modules"
echo ✓ 目录创建完成
echo.

:: 检查Python
echo [3/15] 检查Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ✗ Python未安装，请先安装Python %PYTHON_VERSION%
    echo   下载地址: https://www.python.org/downloads/
    echo   或使用: https://mirrors.aliyun.com/python-release/windows/
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
    echo ✓ Python已安装: !PYTHON_VER!
)
echo.

:: 检查Node.js
echo [4/15] 检查Node.js环境...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ✗ Node.js未安装，请先安装Node.js %NODEJS_VERSION%
    echo   下载地址: https://nodejs.org/dist/v%NODEJS_VERSION%/
    echo   或使用: https://npmmirror.com/mirrors/node/v%NODEJS_VERSION%/
    pause
    exit /b 1
) else (
    for /f %%i in ('node --version') do set NODE_VER=%%i
    echo ✓ Node.js已安装: !NODE_VER!
)
echo.

:: 配置pip使用阿里云镜像
echo [5/15] 配置pip使用阿里云镜像...
if not exist "%APPDATA%\pip" mkdir "%APPDATA%\pip"
(
echo [global]
echo index-url = https://mirrors.aliyun.com/pypi/simple/
echo [install]
echo trusted-host = mirrors.aliyun.com
) > "%APPDATA%\pip\pip.ini"
echo ✓ pip镜像配置完成
echo.

:: 配置npm使用阿里云镜像
echo [6/15] 配置npm使用阿里云镜像...
call npm config set registry https://registry.npmmirror.com
call npm config set disturl https://npmmirror.com/dist
call npm config set electron_mirror https://npmmirror.com/mirrors/electron/
call npm config set sass_binary_site https://npmmirror.com/mirrors/node-sass/
call npm config set phantomjs_cdnurl https://npmmirror.com/mirrors/phantomjs/
call npm config set chromedriver_cdnurl https://npmmirror.com/mirrors/chromedriver/
call npm config set operadriver_cdnurl https://npmmirror.com/mirrors/operadriver/
call npm config set selenium_cdnurl https://npmmirror.com/mirrors/selenium/
call npm config set node_inspector_cdnurl https://npmmirror.com/mirrors/node-inspector/
echo ✓ npm镜像配置完成
echo.

:: 创建Python虚拟环境
echo [7/15] 创建Python虚拟环境...
if exist "%VENV_DIR%" (
    echo ✓ 虚拟环境已存在，跳过创建
) else (
    python -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo ✗ 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo ✓ 虚拟环境创建成功
)
echo.

:: 激活虚拟环境并安装Python依赖
echo [8/15] 安装Python依赖包...
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r "%BACKEND_DIR%\requirements.txt" -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
if %errorlevel% neq 0 (
    echo ✗ Python依赖安装失败
    pause
    exit /b 1
)
echo ✓ Python依赖安装完成
echo.

:: 安装前端依赖
echo [9/15] 安装前端依赖...
cd /d "%FRONTEND_DIR%"
call npm install
if %errorlevel% neq 0 (
    echo ✗ 前端依赖安装失败
    pause
    exit /b 1
)
echo ✓ 前端依赖安装完成
cd /d "%PROJECT_ROOT%"
echo.

:: 检查MySQL
echo [10/15] 检查MySQL服务...
sc query MySQL80 >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ MySQL服务未运行，请确保MySQL %MYSQL_VERSION% 已安装并启动
    echo   下载地址: https://dev.mysql.com/downloads/mysql/
    echo   或使用: https://mirrors.aliyun.com/mysql/downloads/MySQL-8.0/
) else (
    echo ✓ MySQL服务正在运行
)
echo.

:: 检查Redis
echo [11/15] 检查Redis服务...
sc query Redis >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ Redis服务未运行，请确保Redis %REDIS_VERSION% 已安装并启动
    echo   下载地址: https://github.com/microsoftarchive/redis/releases
    echo   或使用: https://github.com/tporadowski/redis/releases
) else (
    echo ✓ Redis服务正在运行
)
echo.

:: 检查MinIO
echo [12/15] 检查MinIO服务...
tasklist /FI "IMAGENAME eq minio.exe" 2>NUL | find /I /N "minio.exe">NUL
if %errorlevel% neq 0 (
    echo ⚠ MinIO未运行，请确保MinIO %MINIO_VERSION% 已安装并启动
    echo   下载地址: https://dl.min.io/server/minio/release/windows-amd64/
) else (
    echo ✓ MinIO正在运行
)
echo.

:: 检查Neo4j
echo [13/15] 检查Neo4j服务...
sc query neo4j >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠ Neo4j服务未运行，请确保Neo4j %NEO4J_VERSION% 已安装并启动
    echo   下载地址: https://neo4j.com/download/
) else (
    echo ✓ Neo4j服务正在运行
)
echo.

:: 检查Milvus和etcd
echo [14/15] 检查Milvus和etcd服务...
echo ⚠ Milvus %MILVUS_VERSION% 和 etcd %ETCD_VERSION% 需要单独安装
echo   请参考部署文档进行安装配置
echo.

:: 初始化数据库
echo [15/15] 初始化数据库...
echo 请确保MySQL服务已启动，然后按任意键继续初始化数据库...
pause >nul

set /p MYSQL_ROOT_PASSWORD="请输入MySQL root密码（默认: 123456）: "
if "%MYSQL_ROOT_PASSWORD%"=="" set MYSQL_ROOT_PASSWORD=123456

mysql -uroot -p%MYSQL_ROOT_PASSWORD% < "%BACKEND_DIR%\init.sql"
if %errorlevel% neq 0 (
    echo ✗ 数据库初始化失败，请检查MySQL连接和密码
) else (
    echo ✓ 数据库初始化成功
)
echo.

:: 创建启动脚本
echo 创建启动脚本...
(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%~dp0"
echo.
echo echo 启动后端服务...
echo call backend\venv\Scripts\activate.bat
echo cd backend
echo start "API Test Backend" cmd /k "uvicorn main:app --host 0.0.0.0 --port 8004"
echo timeout /t 3 /nobreak ^>nul
echo.
echo echo 启动Celery Worker...
echo start "API Test Celery" cmd /k "celery -A app.celery_app worker --loglevel=info --concurrency=4"
echo timeout /t 2 /nobreak ^>nul
echo.
echo echo 启动前端服务...
echo cd ..\frontend
echo start "API Test Frontend" cmd /k "npm start"
echo.
echo echo 所有服务已启动！
echo echo 后端地址: http://localhost:8004
echo echo 前端地址: http://localhost:3000
echo pause
) > "%PROJECT_ROOT%start_all.bat"

:: 创建停止脚本
(
echo @echo off
echo chcp 65001 ^>nul
echo echo 停止所有服务...
echo taskkill /F /FI "WINDOWTITLE eq API Test Backend*" 2^>nul
echo taskkill /F /FI "WINDOWTITLE eq API Test Celery*" 2^>nul
echo taskkill /F /FI "WINDOWTITLE eq API Test Frontend*" 2^>nul
echo taskkill /F /IM node.exe 2^>nul
echo taskkill /F /IM python.exe 2^>nul
echo echo 所有服务已停止
echo pause
) > "%PROJECT_ROOT%stop_all.bat"

echo ✓ 启动和停止脚本创建完成
echo.

echo ========================================
echo 部署完成！
echo ========================================
echo.
echo 已创建的脚本：
echo   - start_all.bat  : 启动所有服务
echo   - stop_all.bat   : 停止所有服务
echo.
echo 下一步：
echo   1. 确保所有服务（MySQL、Redis、MinIO、Neo4j、Milvus、etcd）已安装并运行
echo   2. 运行 start_all.bat 启动系统
echo   3. 访问 http://localhost:3000 使用系统
echo.
echo 详细部署说明请查看：Windows部署文档.md
echo.
pause

