from typing import Dict, Any
import logging
from datetime import datetime

from app.celery_tasks_execution import execute_test_task_task
from app.database import SessionLocal
from app.models import TestTask

logger = logging.getLogger(__name__)

# 延迟导入apscheduler（可选依赖）
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import croniter
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("apscheduler not available, scheduled tasks will not work")


class TaskScheduler:
    """任务调度器：管理定时任务"""
    
    _instance = None
    _scheduler = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TaskScheduler, cls).__new__(cls)
            if APSCHEDULER_AVAILABLE:
                cls._scheduler = BackgroundScheduler()
                cls._scheduler.start()
        return cls._instance
    
    def execute_task(self, task_id: int):
        """立即执行任务（异步）"""
        # 在提交Celery任务之前，先更新任务状态为running，确保前端能立即看到状态变化
        db = SessionLocal()
        try:
            task = db.query(TestTask).filter(TestTask.id == task_id).first()
            if task:
                task.status = "running"
                task.executed_at = datetime.now()
                task.progress = 0
                db.commit()
                logger.info(f"任务 {task_id} 状态已更新为 running")
        except Exception as e:
            logger.error(f"更新任务 {task_id} 状态失败: {str(e)}")
            db.rollback()
        finally:
            db.close()
        
        # 使用新的Celery执行任务
        execute_test_task_task.delay(task_id)
        logger.info(f"任务 {task_id} 已提交到Celery队列")
    
    def schedule_task(self, task_id: int, cron_expression: str):
        """调度定时任务"""
        try:
            # 验证cron表达式
            croniter.croniter(cron_expression, datetime.now())
            
            # 解析cron表达式
            parts = cron_expression.split()
            if len(parts) == 5:
                minute, hour, day, month, weekday = parts
                
                # 处理特殊值
                if day == "*":
                    day = None
                if month == "*":
                    month = None
                if weekday == "*":
                    weekday = None
                
                trigger = CronTrigger(
                    minute=minute if minute != "*" else None,
                    hour=hour if hour != "*" else None,
                    day=day if day and day != "*" else None,
                    month=month if month and month != "*" else None,
                    day_of_week=weekday if weekday and weekday != "*" else None
                )
                
                self._scheduler.add_job(
                    execute_test_task,
                    trigger=trigger,
                    args=[task_id],
                    id=f"task_{task_id}",
                    replace_existing=True
                )
                
                logger.info(f"任务 {task_id} 已调度: {cron_expression}")
            else:
                raise ValueError(f"无效的cron表达式: {cron_expression}，应为5个字段")
        
        except Exception as e:
            logger.error(f"调度任务失败 {task_id}: {str(e)}")
            raise
    
    def cancel_task(self, task_id: int):
        """取消定时任务"""
        job_id = f"task_{task_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info(f"任务 {task_id} 已取消")
