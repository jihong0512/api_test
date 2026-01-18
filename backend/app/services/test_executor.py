from typing import List, Dict, Any, Optional
import json
import httpx
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import TestCase, TestEnvironment, APIInterface
from app.services.response_extractor import ResponseExtractor
from app.services.error_handler import SmartErrorHandler, RetryableRequest


class TestExecutor:
    """测试用例执行器"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.response_extractor = ResponseExtractor()
        self.error_handler = SmartErrorHandler(
            max_retries=3,
            base_delay=1.0,
            max_delay=60.0
        )
    
    def execute_test_case(
        self,
        test_case: TestCase,
        environment: TestEnvironment,
        extracted_data: Dict[str, Any] = None,
        prepared_test_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行单个测试用例
        
        Args:
            test_case: 测试用例
            environment: 测试环境
            extracted_data: 从前置用例提取的数据
        
        Returns:
            执行结果
        """
        if extracted_data is None:
            extracted_data = {}
        
        result = {
            "test_case_id": test_case.id,
            "test_case_name": test_case.name,
            "status": "pending",
            "request_data": None,
            "response_data": None,
            "error_message": None,
            "execution_time": None,
            "assertions": []
        }
        
        start_time = datetime.now()
        
        try:
            # 获取API接口信息
            api_interface = self.db.query(APIInterface).filter(
                APIInterface.id == test_case.api_interface_id
            ).first()
            
            if not api_interface:
                result["status"] = "skipped"
                result["error_message"] = "API接口不存在"
                return result
            
            # 构建请求URL（统一使用url字段）
            base_url = environment.base_url.rstrip("/")
            api_url = api_interface.url or ""
            if api_url:
                api_url = api_url.lstrip("/")
                full_url = f"{base_url}/{api_url}" if api_url else base_url
            else:
                full_url = base_url
            
            # 替换URL中的路径参数（使用提取的数据）
            if extracted_data:
                for key, value in extracted_data.items():
                    full_url = full_url.replace(f"{{{key}}}", str(value))
                    full_url = full_url.replace(f"{{${key}}}", str(value))
            
            # 解析请求参数（统一使用模型字段）
            method = api_interface.method.upper()
            headers = json.loads(api_interface.headers) if api_interface.headers else {}
            params = json.loads(api_interface.params) if api_interface.params else {}
            # 统一使用body字段
            body = api_interface.body
            
            # 使用提取的数据填充（如token）
            if extracted_data.get("authToken"):
                headers["Authorization"] = f"Bearer {extracted_data['authToken']}"
            
            # 解析请求体（统一JSON格式）
            if body:
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except:
                        body = {}
                # 填充提取的数据
                if isinstance(body, dict) and extracted_data:
                    for key, value in extracted_data.items():
                        if key in ["newPostId", "deviceId", "courseId", "familyId"]:
                            # 转换为下划线命名
                            snake_key = self._camel_to_snake(key)
                            if snake_key in body or f"{snake_key}_id" in body:
                                body[snake_key] = value
            
            # 优先使用任务准备时生成的测试数据
            if prepared_test_data:
                if isinstance(prepared_test_data, dict):
                    params.update(prepared_test_data.get("params", {}))
                    headers.update(prepared_test_data.get("headers", {}))
                    if isinstance(body, dict) and prepared_test_data.get("body"):
                        body.update(prepared_test_data["body"])
            # 如果没有准备数据，使用用例的测试数据
            elif test_case.test_data:
                test_data = json.loads(test_case.test_data)
                if isinstance(test_data, dict):
                    params.update(test_data.get("params", {}))
                    headers.update(test_data.get("headers", {}))
                    if isinstance(body, dict) and test_data.get("body"):
                        body.update(test_data["body"])
            
            result["request_data"] = {
                "method": method,
                "url": full_url,
                "headers": headers,
                "params": params,
                "body": body
            }
            
            # 执行HTTP请求（带智能错误处理）
            response = None
            retry_count = 0
            max_retries = 3
            
            while retry_count <= max_retries:
                try:
                    with httpx.Client(timeout=30.0) as client:
                        if method == "GET":
                            response = client.get(full_url, params=params, headers=headers)
                        elif method == "POST":
                            response = client.post(full_url, json=body, params=params, headers=headers)
                        elif method == "PUT":
                            response = client.put(full_url, json=body, params=params, headers=headers)
                        elif method == "PATCH":
                            response = client.patch(full_url, json=body, params=params, headers=headers)
                        elif method == "DELETE":
                            response = client.delete(full_url, params=params, headers=headers)
                        else:
                            raise ValueError(f"不支持的HTTP方法: {method}")
                        
                        # 检查是否需要重试
                        if response.status_code == 429:
                            # 429限流错误
                            handler_result = self.error_handler.handle_429_error(retry_count, response)
                            if handler_result["should_retry"]:
                                delay = handler_result["delay"]
                                import time
                                time.sleep(delay)
                                retry_count += 1
                                result["retry_info"] = {
                                    "retry_count": retry_count,
                                    "delay": delay,
                                    "error_type": "rate_limit"
                                }
                                continue
                            else:
                                # 不再重试
                                result["status"] = "failed"
                                result["error_message"] = f"限流错误，已达到最大重试次数"
                                result["response_data"] = {
                                    "status_code": 429,
                                    "headers": dict(response.headers),
                                    "body": response.text if hasattr(response, 'text') else None
                                }
                                break
                        
                        elif 500 <= response.status_code < 600 and retry_count < max_retries:
                            # 服务器错误，可以重试
                            delay = self.error_handler.get_retry_delay(retry_count, response.status_code, response)
                            import time
                            time.sleep(delay)
                            retry_count += 1
                            result["retry_info"] = {
                                "retry_count": retry_count,
                                "delay": delay,
                                "error_type": "server_error"
                            }
                            continue
                        
                        # 成功或不可重试的错误
                        break
                
                except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                    # 网络错误
                    handler_result = self.error_handler.handle_network_error(retry_count, e)
                    if handler_result["should_retry"]:
                        delay = handler_result["delay"]
                        import time
                        time.sleep(delay)
                        retry_count += 1
                        result["retry_info"] = {
                            "retry_count": retry_count,
                            "delay": delay,
                            "error_type": handler_result.get("error_type", "network_error")
                        }
                        continue
                    else:
                        # 不再重试
                        result["status"] = "failed"
                        result["error_message"] = f"网络错误: {str(e)}"
                        break
                
                except Exception as e:
                    # 其他错误，不重试
                    result["status"] = "failed"
                    result["error_message"] = str(e)
                    break
            
            # 处理响应
            if response:
                # 解析响应
                try:
                    response_data = response.json()
                except:
                    response_data = response.text
                
                result["response_data"] = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_data
                }
                
                # 执行断言
                assertions_result = self._execute_assertions(
                    test_case, response.status_code, response_data
                )
                result["assertions"] = assertions_result
                
                # 判断状态
                if result["status"] != "failed":  # 如果没有因为错误失败
                    if all(a["passed"] for a in assertions_result):
                        result["status"] = "passed"
                    else:
                        result["status"] = "failed"
                        failed_assertions = [a for a in assertions_result if not a["passed"]]
                        result["error_message"] = f"断言失败: {json.dumps(failed_assertions, ensure_ascii=False)}"
        
        except Exception as e:
            result["status"] = "failed"
            result["error_message"] = str(e)
        
        finally:
            end_time = datetime.now()
            result["execution_time"] = (end_time - start_time).total_seconds()
        
        return result
    
    def _execute_assertions(
        self,
        test_case: TestCase,
        status_code: int,
        response_data: Any
    ) -> List[Dict[str, Any]]:
        """执行断言"""
        assertions = []
        
        # 默认断言：状态码
        method = test_case.api_interface.method if hasattr(test_case, 'api_interface') else "GET"
        if method:
            method = method.upper()
            expected_status = 200
            if method == "POST":
                expected_status = 201
            elif method == "DELETE":
                expected_status = 204
            
            assertions.append({
                "type": "status_code",
                "expected": expected_status,
                "actual": status_code,
                "passed": status_code == expected_status
            })
        
        # 自定义断言
        if test_case.assertions:
            try:
                custom_assertions = json.loads(test_case.assertions)
                if isinstance(custom_assertions, list):
                    for assertion in custom_assertions:
                        assert_type = assertion.get("type", "equal")
                        field = assertion.get("field", "")
                        expected = assertion.get("expected", "")
                        
                        # 从响应中提取字段值
                        actual = self._extract_field_value(response_data, field)
                        
                        passed = False
                        if assert_type == "equal":
                            passed = actual == expected
                        elif assert_type == "not_equal":
                            passed = actual != expected
                        elif assert_type == "contains":
                            passed = expected in str(actual)
                        elif assert_type == "greater_than":
                            passed = actual > expected
                        elif assert_type == "less_than":
                            passed = actual < expected
                        
                        assertions.append({
                            "type": assert_type,
                            "field": field,
                            "expected": expected,
                            "actual": actual,
                            "passed": passed
                        })
            except:
                pass
        
        return assertions
    
    def _extract_field_value(self, data: Any, field_path: str) -> Any:
        """从响应中提取字段值"""
        if not field_path:
            return None
        
        parts = field_path.split(".")
        current = data
        
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                try:
                    current = current[int(part)]
                except:
                    return None
            else:
                return None
            
            if current is None:
                return None
        
        return current
    
    def _camel_to_snake(self, name: str) -> str:
        """驼峰转下划线"""
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
