"""
缓存服务 - 统一管理Redis缓存和MySQL数据同步
支持分页加载、缓存失效、自动同步等功能
"""
import json
import redis
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from functools import wraps
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """通用缓存服务，支持Redis缓存和数据库同步"""
    
    # 缓存过期时间配置（单位：秒）
    CACHE_TTL = {
        'default': 3600,  # 1小时
        'documents': 1800,  # 30分钟
        'test_cases': 1800,  # 30分钟
        'test_suites': 1800,  # 30分钟
        'test_results': 900,  # 15分钟
        'short': 300,  # 5分钟
    }
    
    def __init__(self):
        """初始化缓存服务"""
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            encoding='utf-8'
        )
    
    def get_paginated_list(
        self,
        cache_key: str,
        page: int = 1,
        page_size: int = 20,
        fetch_all_func=None,
        cache_type: str = 'default'
    ) -> Tuple[List[Dict[str, Any]], int, int, int]:
        """
        获取分页列表数据（优先从Redis读取）
        
        Args:
            cache_key: Redis缓存键
            page: 页码（从1开始）
            page_size: 每页数量
            fetch_all_func: 当Redis缺失时的数据获取函数
            cache_type: 缓存类型（用于确定过期时间）
        
        Returns:
            (数据列表, 总数, 总页数, 当前页码)
        """
        try:
            # 1. 尝试从Redis读取全量数据
            cache_data = self.redis_client.get(cache_key)
            
            if cache_data:
                # Redis中有数据，直接返回分页结果
                all_items = json.loads(cache_data)
                logger.info(f"从Redis加载 {cache_key}，总数：{len(all_items)}")
            else:
                # Redis中没有数据，从数据库获取
                if fetch_all_func is None:
                    return [], 0, 0, page
                
                all_items = fetch_all_func()
                
                # 存储到Redis
                try:
                    self.redis_client.setex(
                        cache_key,
                        self.CACHE_TTL.get(cache_type, self.CACHE_TTL['default']),
                        json.dumps(all_items, ensure_ascii=False, default=str)
                    )
                    logger.info(f"已缓存 {cache_key} 到Redis，总数：{len(all_items)}")
                except Exception as e:
                    logger.warning(f"缓存 {cache_key} 失败：{e}")
            
            # 2. 执行分页
            total_count = len(all_items)
            total_pages = (total_count + page_size - 1) // page_size
            
            # 验证页码
            if page < 1:
                page = 1
            if page > total_pages and total_pages > 0:
                page = total_pages
            
            # 计算分页数据
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_data = all_items[start_idx:end_idx]
            
            return paginated_data, total_count, total_pages, page
            
        except Exception as e:
            logger.error(f"获取分页列表 {cache_key} 失败：{e}")
            # 降级处理：直接从数据库获取
            if fetch_all_func:
                all_items = fetch_all_func()
                total_count = len(all_items)
                total_pages = (total_count + page_size - 1) // page_size
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                return all_items[start_idx:end_idx], total_count, total_pages, page
            return [], 0, 0, page
    
    def set_cache(
        self,
        cache_key: str,
        data: Any,
        cache_type: str = 'default'
    ) -> bool:
        """
        设置缓存数据
        
        Args:
            cache_key: 缓存键
            data: 缓存数据
            cache_type: 缓存类型
        
        Returns:
            是否设置成功
        """
        try:
            ttl = self.CACHE_TTL.get(cache_type, self.CACHE_TTL['default'])
            self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(data, ensure_ascii=False, default=str)
            )
            logger.info(f"缓存已设置：{cache_key}，TTL：{ttl}秒")
            return True
        except Exception as e:
            logger.error(f"设置缓存 {cache_key} 失败：{e}")
            return False
    
    def get_cache(self, cache_key: str) -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            cache_key: 缓存键
        
        Returns:
            缓存数据，或None
        """
        try:
            data = self.redis_client.get(cache_key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"获取缓存 {cache_key} 失败：{e}")
            return None
    
    def invalidate_cache(self, cache_key_pattern: str) -> int:
        """
        使缓存失效（支持模式匹配）
        
        Args:
            cache_key_pattern: 缓存键模式（支持通配符*）
        
        Returns:
            删除的键数量
        """
        try:
            cursor = 0
            deleted_count = 0
            
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor,
                    match=cache_key_pattern,
                    count=100
                )
                
                if keys:
                    deleted_count += self.redis_client.delete(*keys)
                
                if cursor == 0:
                    break
            
            if deleted_count > 0:
                logger.info(f"已清除缓存：{cache_key_pattern}，共{deleted_count}个")
            return deleted_count
        except Exception as e:
            logger.error(f"清除缓存 {cache_key_pattern} 失败：{e}")
            return 0
    
    def invalidate_all_caches(self) -> bool:
        """
        清除所有缓存
        
        Returns:
            是否清除成功
        """
        try:
            self.redis_client.flushdb()
            logger.info("已清除所有Redis缓存")
            return True
        except Exception as e:
            logger.error(f"清除所有缓存失败：{e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计数据
        """
        try:
            info = self.redis_client.info('memory')
            keys_count = self.redis_client.dbsize()
            
            return {
                'total_keys': keys_count,
                'used_memory': info.get('used_memory_human', 'N/A'),
                'used_memory_bytes': info.get('used_memory', 0),
                'max_memory': info.get('maxmemory_human', 'N/A'),
                'eviction_policy': info.get('maxmemory_policy', 'N/A')
            }
        except Exception as e:
            logger.error(f"获取缓存统计失败：{e}")
            return {}


# 创建全局缓存服务实例
cache_service = CacheService()


def cache_decorator(cache_key_template: str, cache_type: str = 'default', ttl: Optional[int] = None):
    """
    装饰器：自动缓存函数结果
    
    Args:
        cache_key_template: 缓存键模板，可使用{param}格式引用函数参数
        cache_type: 缓存类型
        ttl: 自定义过期时间（秒），优先于cache_type
    
    Example:
        @cache_decorator('documents:{project_id}')
        def fetch_documents(project_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 构建缓存键
            try:
                cache_key = cache_key_template.format(**kwargs)
            except:
                cache_key = cache_key_template
            
            # 尝试从缓存读取
            cached_data = cache_service.get_cache(cache_key)
            if cached_data is not None:
                logger.info(f"从缓存返回：{cache_key}")
                return cached_data
            
            # 执行函数
            result = await func(*args, **kwargs)
            
            # 保存到缓存
            cache_service.set_cache(cache_key, result, cache_type)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 构建缓存键
            try:
                cache_key = cache_key_template.format(**kwargs)
            except:
                cache_key = cache_key_template
            
            # 尝试从缓存读取
            cached_data = cache_service.get_cache(cache_key)
            if cached_data is not None:
                logger.info(f"从缓存返回：{cache_key}")
                return cached_data
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 保存到缓存
            cache_service.set_cache(cache_key, result, cache_type)
            
            return result
        
        # 判断是否为异步函数
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
