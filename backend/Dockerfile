FROM python:3.11-slim-bookworm

WORKDIR /app

# 使用阿里云镜像源（适用于Debian系统）
# 检测Debian版本并配置阿里云镜像源
RUN echo "配置阿里云镜像源..." && \
    DEBIAN_CODENAME=$(cat /etc/os-release 2>/dev/null | grep VERSION_CODENAME | cut -d= -f2 | tr -d '"') && \
    if [ -z "$DEBIAN_CODENAME" ]; then \
        DEBIAN_CODENAME=$(cat /etc/debian_version 2>/dev/null | cut -d. -f1); \
        case "$DEBIAN_CODENAME" in \
            13) DEBIAN_CODENAME="bookworm" ;; \
            12) DEBIAN_CODENAME="bookworm" ;; \
            *) DEBIAN_CODENAME="trixie" ;; \
        esac; \
    fi && \
    echo "检测到Debian版本: $DEBIAN_CODENAME" && \
    echo "deb http://mirrors.aliyun.com/debian/ $DEBIAN_CODENAME main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian/ $DEBIAN_CODENAME-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian-security/ $DEBIAN_CODENAME-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/* 2>/dev/null || true && \
    echo "配置的镜像源:" && \
    cat /etc/apt/sources.list

# 安装系统依赖（包括PDF转换所需的poppler、curl用于健康检查、docker客户端用于JMeter执行）
RUN apt-get update && \
    apt-get install -y --fix-missing \
        gcc \
        g++ \
        poppler-utils \
        curl \
        netcat-openbsd \
        wget \
        unzip \
    && (apt-get install -y --fix-missing docker.io || echo "docker.io安装失败，继续构建") \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 设置时区为北京时间（UTC+8）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone


# 设置pip镜像源（使用阿里云镜像源）
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple && \
    pip config set global.trusted-host mirrors.aliyun.com && \
    pip config set global.timeout 300 && \
    pip config set global.retries 5
# 安装Python依赖（增加超时时间）
RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt

# 确保pydantic版本正确（>=2.0.0）
RUN pip install --no-cache-dir --default-timeout=300 "pydantic>=2.0.0,<3.0.0" "pydantic-settings>=2.0.0"

# 安装httprunner（用于测试用例执行，跳过依赖检查以避免pydantic冲突）
RUN pip install --no-cache-dir --default-timeout=300 --no-deps httprunner || pip install --no-cache-dir --default-timeout=300 httprunner

# 复制应用代码
COPY . .

# 创建uploads目录
RUN mkdir -p /app/uploads

# 暴露端口
EXPOSE 8004

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

# 启动应用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]


