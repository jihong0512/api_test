from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import sys

from app.config import settings

# 创建数据库引擎
DATABASE_URL = (
    f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
    f"@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
    f"?charset=utf8mb4"
)

# 数据库连接状态标志
db_available = False
engine = None
SessionLocal = None

try:
    engine = create_engine(
        DATABASE_URL,
        poolclass=None,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.DEBUG,
        connect_args={"connect_timeout": 5}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_available = True
except Exception as e:
    print(f"⚠️  数据库引擎创建警告: {e}")
    print(f"⚠️  系统将在无数据库模式下启动，部分功能可能不可用")

Base = declarative_base()


async def init_db():
    """初始化数据库 - 容错处理"""
    global db_available
    
    if not engine or not SessionLocal:
        print("⚠️  数据库未配置，跳过数据库初始化")
        print("💡 系统将在无数据库模式下运行")
        db_available = False
        return
    
    import time
    from app.models import User
    from app.routers.auth import get_password_hash
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            Base.metadata.create_all(bind=engine)
            print("✅ 数据库表初始化完成")
            
            db = SessionLocal()
            try:
                admin_user = db.query(User).filter(User.username == "admin").first()
                if not admin_user:
                    hashed_password = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5LSYqBHpLFyZ2"
                    admin_user = User(
                        username="admin",
                        email="admin@example.com",
                        password_hash=hashed_password
                    )
                    db.add(admin_user)
                    db.commit()
                    print("✅ 默认admin用户创建成功 (用户名: admin, 密码: 123456)")
                else:
                    print("✅ admin用户已存在")
            except Exception as e:
                print(f"⚠️  创建admin用户失败: {e}")
                db.rollback()
            finally:
                db.close()
            
            db_available = True
            print("✅ 数据库连接成功")
            return
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                print(f"⚠️  数据库连接失败，重试中... ({retry_count}/{max_retries}): {str(e)[:100]}")
                time.sleep(2)
            else:
                print(f"❌ 数据库初始化失败: {str(e)[:200]}")
                print("⚠️  系统将在无数据库模式下启动")
                print("💡 请检查数据库配置或稍后手动连接数据库")
                db_available = False
                return


def get_db():
    """获取数据库会话 - 容错处理"""
    if not SessionLocal:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="数据库服务不可用，请检查数据库配置")
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
