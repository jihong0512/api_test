import time
import random
import httpx
import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class SmartErrorHandler:
    """智能错误处理器"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        初始化错误处理器
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            exponential_base: 指数退避基数
            jitter: 是否添加随机抖动
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def handle_429_error(
        self,
        retry_count: int,
        response: Optional[httpx.Response] = None
    ) -> Dict[str, Any]:
        """
        处理429限流错误
        
        Args:
            retry_count: 当前重试次数
            response: HTTP响应（可选）
        
        Returns:
            处理结果，包含是否重试、延迟时间等信息
        """
        if retry_count >= self.max_retries:
            return {
                "should_retry": False,
                "error": "已达到最大重试次数",
                "retry_count": retry_count
            }
        
        # 从响应头获取限流信息
        retry_after = None
        rate_limit_remaining = None
        rate_limit_reset = None
        
        if response:
            # Retry-After头（秒数）
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header:
                try:
                    retry_after = int(retry_after_header)
                except ValueError:
                    pass
            
            # X-RateLimit-* 头（常见格式）
            rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
            rate_limit_reset = response.headers.get("X-RateLimit-Reset")
        
        # 计算延迟时间
        if retry_after:
            # 使用服务器建议的重试时间
            delay = min(retry_after, self.max_delay)
        else:
            # 指数退避
            delay = min(
                self.base_delay * (self.exponential_base ** retry_count),
                self.max_delay
            )
        
        # 添加随机抖动（避免雷群效应）
        if self.jitter:
            jitter_amount = delay * 0.1  # 10%的抖动
            delay += random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay)  # 确保不为负
        
        return {
            "should_retry": True,
            "delay": delay,
            "retry_count": retry_count + 1,
            "retry_after": retry_after,
            "rate_limit_remaining": rate_limit_remaining,
            "rate_limit_reset": rate_limit_reset,
            "error_type": "rate_limit"
        }
    
    def handle_network_error(
        self,
        retry_count: int,
        error: Exception
    ) -> Dict[str, Any]:
        """
        处理网络异常
        
        Args:
            retry_count: 当前重试次数
            error: 异常对象
        
        Returns:
            处理结果
        """
        if retry_count >= self.max_retries:
            return {
                "should_retry": False,
                "error": "已达到最大重试次数",
                "retry_count": retry_count
            }
        
        # 判断错误类型
        error_type = self._classify_network_error(error)
        
        # 根据错误类型决定延迟
        if error_type == "connection_error":
            # 连接错误：快速重试
            delay = self.base_delay * (self.exponential_base ** retry_count)
        elif error_type == "timeout":
            # 超时：中等延迟
            delay = self.base_delay * 2 * (self.exponential_base ** retry_count)
        else:
            # 其他错误：标准延迟
            delay = self.base_delay * (self.exponential_base ** retry_count)
        
        delay = min(delay, self.max_delay)
        
        # 添加抖动
        if self.jitter:
            jitter_amount = delay * 0.1
            delay += random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay)
        
        return {
            "should_retry": True,
            "delay": delay,
            "retry_count": retry_count + 1,
            "error_type": error_type,
            "error_message": str(error)
        }
    
    def _classify_network_error(self, error: Exception) -> str:
        """分类网络错误"""
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        if "timeout" in error_str or "timed out" in error_str:
            return "timeout"
        elif "connection" in error_str or "connect" in error_str:
            return "connection_error"
        elif "dns" in error_str or "resolve" in error_str:
            return "dns_error"
        elif "ssl" in error_str or "certificate" in error_str:
            return "ssl_error"
        else:
            return "unknown_error"
    
    def should_retry(self, status_code: int, error: Optional[Exception] = None) -> bool:
        """
        判断是否应该重试
        
        Args:
            status_code: HTTP状态码
            error: 异常对象（可选）
        
        Returns:
            是否应该重试
        """
        # 429错误：限流，应该重试
        if status_code == 429:
            return True
        
        # 5xx错误：服务器错误，可以重试
        if 500 <= status_code < 600:
            return True
        
        # 网络错误：应该重试
        if error:
            if isinstance(error, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)):
                return True
        
        return False
    
    def get_retry_delay(
        self,
        retry_count: int,
        status_code: Optional[int] = None,
        response: Optional[httpx.Response] = None,
        error: Optional[Exception] = None
    ) -> float:
        """
        获取重试延迟时间
        
        Args:
            retry_count: 当前重试次数
            status_code: HTTP状态码
            response: HTTP响应
            error: 异常对象
        
        Returns:
            延迟时间（秒）
        """
        if status_code == 429:
            result = self.handle_429_error(retry_count, response)
            return result.get("delay", self.base_delay)
        
        if error:
            result = self.handle_network_error(retry_count, error)
            return result.get("delay", self.base_delay)
        
        # 默认延迟
        delay = self.base_delay * (self.exponential_base ** retry_count)
        return min(delay, self.max_delay)


class RetryableRequest:
    """可重试的请求包装器"""
    
    def __init__(self, error_handler: SmartErrorHandler):
        self.error_handler = error_handler
    
    async def execute_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行带重试的请求
        
        Args:
            client: httpx客户端
            method: HTTP方法
            url: URL
            **kwargs: 其他请求参数
        
        Returns:
            执行结果
        """
        retry_count = 0
        last_error = None
        last_response = None
        
        while retry_count <= self.error_handler.max_retries:
            try:
                # 执行请求
                response = await client.request(method, url, **kwargs)
                
                # 检查状态码
                if response.status_code == 429:
                    # 限流错误
                    handler_result = self.error_handler.handle_429_error(
                        retry_count, response
                    )
                    
                    if not handler_result["should_retry"]:
                        return {
                            "status": "error",
                            "status_code": 429,
                            "error": "限流错误，已达到最大重试次数",
                            "retry_count": retry_count,
                            "response": response
                        }
                    
                    # 等待后重试
                    delay = handler_result["delay"]
                    logger.info(f"遇到429限流，等待{delay:.2f}秒后重试（第{retry_count + 1}次）")
                    await asyncio.sleep(delay)
                    retry_count += 1
                    last_response = response
                    continue
                
                elif 500 <= response.status_code < 600:
                    # 服务器错误，可以重试
                    if retry_count < self.error_handler.max_retries:
                        delay = self.error_handler.get_retry_delay(
                            retry_count, response.status_code, response
                        )
                        logger.info(f"遇到{response.status_code}服务器错误，等待{delay:.2f}秒后重试（第{retry_count + 1}次）")
                        await asyncio.sleep(delay)
                        retry_count += 1
                        last_response = response
                        continue
                    else:
                        return {
                            "status": "error",
                            "status_code": response.status_code,
                            "error": f"服务器错误，已达到最大重试次数",
                            "retry_count": retry_count,
                            "response": response
                        }
                
                # 成功或不可重试的错误
                return {
                    "status": "success",
                    "status_code": response.status_code,
                    "response": response,
                    "retry_count": retry_count
                }
            
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                
                # 网络错误，尝试重试
                handler_result = self.error_handler.handle_network_error(retry_count, e)
                
                if not handler_result["should_retry"]:
                    return {
                        "status": "error",
                        "error": f"网络错误，已达到最大重试次数: {str(e)}",
                        "retry_count": retry_count,
                        "error_type": handler_result.get("error_type")
                    }
                
                # 等待后重试
                delay = handler_result["delay"]
                logger.info(f"遇到网络错误({handler_result.get('error_type')})，等待{delay:.2f}秒后重试（第{retry_count + 1}次）")
                await asyncio.sleep(delay)
                retry_count += 1
                continue
            
            except Exception as e:
                # 其他错误，不重试
                return {
                    "status": "error",
                    "error": str(e),
                    "retry_count": retry_count
                }
        
        # 达到最大重试次数
        if last_response:
            return {
                "status": "error",
                "status_code": last_response.status_code,
                "error": "已达到最大重试次数",
                "retry_count": retry_count,
                "response": last_response
            }
        elif last_error:
            return {
                "status": "error",
                "error": f"网络错误，已达到最大重试次数: {str(last_error)}",
                "retry_count": retry_count
            }
        else:
            return {
                "status": "error",
                "error": "未知错误",
                "retry_count": retry_count
            }

