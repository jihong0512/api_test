"""
应用配置模块
所有配置项都可以通过 .env 文件覆盖
"""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置 - 所有配置项都可以通过 .env 文件覆盖"""
    
    # 应用基础配置
    APP_NAME: str = Field(
        default="API接口智能测试系统",
        description="应用名称"
    )
    DEBUG: bool = Field(
        default=True,
        description="调试模式"
    )
    
    # MySQL配置
    MYSQL_HOST: str = Field(
        default="localhost",
        description="MySQL主机地址"
    )
    MYSQL_PORT: int = Field(
        default=3309,
        description="MySQL端口（本地开发模式：3309，Docker模式：3306）"
    )
    MYSQL_USER: str = Field(
        default="root",
        description="MySQL用户名"
    )
    MYSQL_PASSWORD: str = Field(
        default="123456",
        description="MySQL密码"
    )
    MYSQL_DATABASE: str = Field(
        default="api_test",
        description="MySQL数据库名"
    )
    
    # Redis配置
    REDIS_HOST: str = Field(
        default="localhost",
        description="Redis主机地址"
    )
    REDIS_PORT: int = Field(
        default=6382,
        description="Redis端口（本地开发模式：6382，Docker模式：6379）"
    )
    REDIS_PASSWORD: Optional[str] = Field(
        default=None,
        description="Redis密码"
    )
    
    # ChromaDB配置
    CHROMA_PERSIST_DIR: str = Field(
        default="./chroma_db",
        description="ChromaDB持久化目录"
    )
    
    # MinIO配置
    MINIO_ENDPOINT: str = Field(
        default="localhost:9005",
        description="MinIO端点（本地开发模式：localhost:9005，Docker模式：minio:9000）"
    )
    MINIO_ACCESS_KEY: str = Field(
        default="minioadmin",
        description="MinIO访问密钥"
    )
    MINIO_SECRET_KEY: str = Field(
        default="minioadmin123456",
        description="MinIO密钥"
    )
    MINIO_BUCKET: str = Field(
        default="api-test",
        description="MinIO存储桶名称"
    )
    
    # Neo4j配置
    NEO4J_URI: str = Field(
        default="bolt://localhost:7687",
        description="Neo4j连接URI"
    )
    NEO4J_USER: str = Field(
        default="neo4j",
        description="Neo4j用户名"
    )
    NEO4J_PASSWORD: str = Field(
        default="123456789",
        description="Neo4j密码"
    )
    
    # DeepSeek API配置（用于测试用例生成和脚本生成）
    DEEPSEEK_API_KEY: str = Field(
        default="",
        description="DeepSeek API密钥（必须从.env配置）"
    )
    DEEPSEEK_BASE_URL: str = Field(
        default="https://api.deepseek.com/v1",
        description="DeepSeek API基础URL"
    )
    DEEPSEEK_MODEL: str = Field(
        default="deepseek-chat",
        description="DeepSeek模型名称"
    )
    
    # 阿里云DashScope配置 - Qwen模型
    QWEN_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="阿里云DashScope API基础URL"
    )
    QWEN_API_KEY: str = Field(
        default="",
        description="阿里云Qwen API密钥（必须从.env配置）"
    )
    QWEN_MODEL: str = Field(
        default="qwen-vl-plus",
        description="Qwen模型名称"
    )
    
    # 嵌入模型配置（使用通义千问API）
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-v3",
        description="嵌入模型名称（使用通义千问文本embedding）"
    )
    
    # 重排序模型配置
    RERANKER_MODEL: str = Field(
        default="qwen3-rerank",
        description="重排序模型名称"
    )
    
    # JWT配置
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="JWT密钥（生产环境必须修改）"
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="JWT算法"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=1440,
        description="访问令牌过期时间（分钟）"
    )
    
    # 文件上传配置
    UPLOAD_DIR: str = Field(
        default="uploads",
        description="文件上传目录"
    )
    MAX_UPLOAD_SIZE: int = Field(
        default=100 * 1024 * 1024,
        description="最大上传文件大小（字节），默认100MB"
    )
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 允许额外的环境变量


# 创建全局配置实例
settings = Settings()




