from celery import Celery
from app.config import settings

# 从settings获取Redis配置（支持从.env文件读取）
redis_host = settings.REDIS_HOST
redis_port = settings.REDIS_PORT
redis_password = settings.REDIS_PASSWORD

# 构建Redis连接URL
if redis_password:
    redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
else:
    redis_url = f"redis://{redis_host}:{redis_port}/0"

celery_app = Celery(
    "api_service",
    broker=redis_url,
    backend=redis_url
)

# Celery配置
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30分钟硬超时（元数据解析可能需要较长时间）
    task_soft_time_limit=1500,  # 25分钟软超时
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    imports=('app.celery_tasks', 'app.celery_tasks_execution'),  # 明确导入任务模块
)

# 自动发现任务
celery_app.autodiscover_tasks(['app'], force=True)







