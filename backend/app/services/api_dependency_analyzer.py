"""
接口依赖分析器：分析接口之间的依赖关系
实现参数溯源、状态依赖分析等核心算法
"""
from typing import List, Dict, Any, Optional, Set, Tuple, Callable
import json
import re
from collections import defaultdict
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import asyncio

import redis
from app.config import settings
from app.services.llm_service import LLMService

# Redis连接
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    encoding='utf-8'
)


class APIDependencyAnalyzer:
    """接口依赖分析器"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.redis_client = redis_client
        self.llm_service = LLMService()
        self.progress_callback: Optional[Callable] = None  # 进度回调函数
    
    def extract_interfaces_from_redis(self, file_id: str) -> List[Dict[str, Any]]:
        """从Redis中提取接口信息"""
        try:
            api_key = f"file:{file_id}:api_interfaces"
            interfaces_json = self.redis_client.get(api_key)
            if interfaces_json:
                return json.loads(interfaces_json)
            
            # 兼容旧格式
            interface_key = f"file:{file_id}:interfaces"
            interfaces_json = self.redis_client.get(interface_key)
            if interfaces_json:
                interfaces = json.loads(interfaces_json)
                # 转换为增强格式
                enhanced_interfaces = []
                for interface in interfaces:
                    enhanced_interface = self._enhance_interface_format(interface, file_id)
                    enhanced_interfaces.append(enhanced_interface)
                return enhanced_interfaces
        except Exception as e:
            print(f"从Redis提取接口信息失败: {e}")
        return []
    
    def _enhance_interface_format(self, interface: Dict[str, Any], file_id: str) -> Dict[str, Any]:
        """将旧格式接口转换为增强格式"""
        url = interface.get("url", "")
        base_url = ""
        path = url
        
        try:
            if url.startswith("http://") or url.startswith("https://"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                path = parsed.path
        except:
            pass
        
        return {
            "interface_id": interface.get("id"),
            "name": interface.get("name", ""),
            "method": interface.get("method", "GET"),
            "url": url,
            "base_url": base_url,
            "path": path,
            "headers": interface.get("headers", {}),
            "params": interface.get("params", {}),
            "request_body": interface.get("body", interface.get("request_body", {})),
            "response_schema": interface.get("response_schema", {}),
            "response_body": interface.get("response_body", {}),
            "status_code": interface.get("status_code", 200),
            "description": interface.get("description", ""),
            "tags": interface.get("tags", []),
            "file_id": file_id
        }
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调函数"""
        self.progress_callback = callback
    
    def _update_progress(self, progress: int, message: str):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(progress, message)
    
    async def _analyze_with_llm(self, source_interface: Dict[str, Any], target_interface: Dict[str, Any]) -> List[Dict[str, Any]]:
        """使用deepseek大模型分析接口间的语义依赖"""
        try:
            prompt = f"""请分析以下两个API接口之间是否存在依赖关系，并说明依赖类型和原因。

接口A（源接口）：
- 名称：{source_interface.get('name', '')}
- 方法：{source_interface.get('method', '')}
- URL：{source_interface.get('url', '')}
- 路径：{source_interface.get('path', '')}
- 服务：{source_interface.get('service', '')}
- 描述：{source_interface.get('description', '')}
- 请求体字段：{json.dumps(self._extract_request_fields(source_interface), ensure_ascii=False, indent=2)}
- 响应体字段：{json.dumps(self._extract_response_fields(source_interface), ensure_ascii=False, indent=2)}

接口B（目标接口）：
- 名称：{target_interface.get('name', '')}
- 方法：{target_interface.get('method', '')}
- URL：{target_interface.get('url', '')}
- 路径：{target_interface.get('path', '')}
- 服务：{target_interface.get('service', '')}
- 描述：{target_interface.get('description', '')}
- 请求体字段：{json.dumps(self._extract_request_fields(target_interface), ensure_ascii=False, indent=2)}
- 响应体字段：{json.dumps(self._extract_response_fields(target_interface), ensure_ascii=False, indent=2)}

请分析：
1. 接口B的请求参数是否依赖接口A的响应数据？（参数溯源）
2. 是否存在业务逻辑依赖？（状态依赖，如创建订单->支付订单）
3. 是否存在认证依赖？（如登录->获取用户信息）

请以JSON格式返回分析结果：
{{
    "has_dependency": true/false,
    "dependency_type": "authentication/parameter/state/none",
    "description": "依赖关系的详细说明",
    "dependency_path": "具体的数据传递路径，如 data.token -> headers.Authorization",
    "confidence": 0.0-1.0之间的置信度
}}

如果不存在依赖关系，返回：
{{
    "has_dependency": false,
    "dependency_type": "none",
    "description": "",
    "dependency_path": "",
    "confidence": 0.0
}}
"""
            result = await self.llm_service.chat(prompt, temperature=0.3, max_tokens=500)
            
            # 尝试解析JSON结果
            try:
                # 提取JSON部分（如果结果包含markdown代码块）
                if "```json" in result:
                    result = result.split("```json")[1].split("```")[0].strip()
                elif "```" in result:
                    result = result.split("```")[1].split("```")[0].strip()
                
                analysis = json.loads(result)
                
                if analysis.get("has_dependency", False) and analysis.get("dependency_type") != "none":
                    return [{
                        "type": analysis.get("dependency_type", "unknown"),
                        "description": analysis.get("description", ""),
                        "dependency_path": analysis.get("dependency_path", ""),
                        "confidence": float(analysis.get("confidence", 0.5))
                    }]
            except json.JSONDecodeError as e:
                print(f"LLM返回结果解析失败: {e}, 原始结果: {result[:200]}")
            
            return []
        except Exception as e:
            print(f"LLM分析接口依赖失败: {e}")
            return []
    
    def analyze_dependencies(self, interfaces: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析接口依赖关系（优化版本：预处理字段，减少重复计算）
        
        返回：
        {
            "nodes": [...],  # 节点列表
            "edges": [...],  # 边列表（依赖关系）
            "dependency_chains": [...],  # 依赖链
            "topological_order": [...],   # 拓扑排序结果
            "auth_interface": {...},     # 登录接口信息
            "token_info": {...}          # Token信息
        }
        """
        nodes = []
        edges = []
        dependency_map = defaultdict(list)  # interface_id -> [dependent_interfaces]
        
        # 预处理：一次性提取所有接口的请求和响应字段，避免重复计算
        print(f"开始预处理 {len(interfaces)} 个接口的字段...")
        interface_fields_cache = {}
        for idx, interface in enumerate(interfaces):
            if idx % 100 == 0:
                print(f"  预处理进度: {idx}/{len(interfaces)}")
            interface_id = self._get_interface_id(interface)
            interface_fields_cache[interface_id] = {
                'response_fields': self._extract_response_fields(interface),
                'request_fields': self._extract_request_fields(interface),
                'interface': interface
            }
        
        print(f"字段预处理完成，开始分析依赖关系...")
        
        # 构建节点
        for interface in interfaces:
            interface_id = self._get_interface_id(interface)
            node = {
                "id": interface_id,
                "name": interface.get("name", ""),
                "method": interface.get("method", "GET"),
                "url": interface.get("url", ""),
                "path": interface.get("path", ""),
                "base_url": interface.get("base_url", ""),
                "description": interface.get("description", "")
            }
            nodes.append(node)
        
        # 0. 首先识别登录接口并提取token信息（优先级最高）
        auth_interface, token_info = self._identify_auth_interface(interfaces)
        
        if auth_interface:
            auth_id = self._get_interface_id(auth_interface)
            auth_response = self._extract_response_fields(auth_interface)
            
            # 识别所有需要认证的接口（请求头中包含Authorization等）
            auth_required_interfaces = self._identify_auth_required_interfaces(interfaces)
            
            # 为所有需要认证的接口添加对登录接口的依赖
            for target_interface in auth_required_interfaces:
                target_id = self._get_interface_id(target_interface)
                
                # 检查是否已存在边（避免重复）
                if not any(e["source"] == auth_id and e["target"] == target_id for e in edges):
                    token_path = token_info.get("path", "token") if token_info else "token"
                    edge = {
                        "source": auth_id,
                        "target": target_id,
                        "type": "authentication",
                        "description": f"{target_interface.get('name', '')}需要{auth_interface.get('name', '')}提供的token进行认证",
                        "dependency_path": f"{token_path} -> Authorization header",
                        "confidence": 0.95  # 认证依赖的置信度很高
                    }
                    edges.append(edge)
                    dependency_map[auth_id].append({
                        "target": target_id,
                        "type": "authentication",
                        "dependency": {"type": "authentication", "path": token_path}
                    })
        
        # 1. 参数溯源分析：检查接口B的请求参数是否来源于接口A的响应（使用多线程并行处理）
        edges_lock = Lock()
        edges_set = set()  # 使用Set快速检查重复边，格式: (source_id, target_id, type)
        
        def analyze_dependency_pair(source_idx, target_idx):
            """分析一对接口的依赖关系（使用缓存的字段）"""
            if source_idx == target_idx:
                return []
            
            source_interface = interfaces[source_idx]
            target_interface = interfaces[target_idx]
            
            source_id = self._get_interface_id(source_interface)
            target_id = self._get_interface_id(target_interface)
            
            # 如果登录接口已经处理过认证依赖，跳过重复处理
            if auth_interface and source_interface == auth_interface:
                # 如果目标接口需要认证且已经添加了认证依赖，跳过参数溯源中的token匹配
                if self._needs_authentication(target_interface):
                    return []
            
            # 使用缓存的字段，避免重复提取
            source_cache = interface_fields_cache.get(source_id)
            target_cache = interface_fields_cache.get(target_id)
            
            if not source_cache or not target_cache:
                return []
            
            source_response = source_cache['response_fields']
            target_request = target_cache['request_fields']
            
            # 快速过滤：如果两个接口的base_url不同，且没有明显的跨域调用，可以跳过
            source_base = source_interface.get("base_url", "")
            target_base = target_interface.get("base_url", "")
            if source_base and target_base and source_base != target_base:
                # 跨域调用通常是认证相关的，已经处理过了
                if source_interface != auth_interface:
                    # 对于非认证接口的跨域调用，依赖关系可能性较低，可以跳过
                    pass
            
            # 检查是否存在参数依赖
            dependencies = self._analyze_parameter_dependency(
                source_response, target_request, source_interface, target_interface
            )
            
            new_edges = []
            for dep in dependencies:
                # 避免重复添加认证依赖
                if dep["type"] == "authentication" and auth_interface:
                    auth_id = self._get_interface_id(auth_interface)
                    if source_id != auth_id:
                        continue
                
                edge_key = (source_id, target_id, dep["type"])
                new_edges.append({
                    "source": source_id,
                    "target": target_id,
                    "type": dep["type"],
                    "description": dep["description"],
                    "dependency_path": dep.get("path", ""),
                    "confidence": dep.get("confidence", 0.5),
                    "dependency": dep,
                    "_edge_key": edge_key  # 用于快速去重
                })
            
            return new_edges
        
        # 使用线程池并行处理接口对
        max_workers = min(8, len(interfaces))  # 最多8个线程，不超过接口数量
        
        # 对于大量接口，采样分析或批量处理
        total_pairs = len(interfaces) * (len(interfaces) - 1)
        print(f"需要分析的接口对数量: {total_pairs}")
        
        if len(interfaces) > 100:  # 接口数量较多时使用批量处理
            # 限制分析的接口对数量，避免超时
            # 优先分析：1) 认证相关 2) 同base_url的接口 3) 采样分析其他接口
            batch_size = 10000  # 每批处理10000对
            processed_count = 0
            
            # 先处理认证相关的依赖（这些依赖最重要）
            if auth_interface:
                auth_id = self._get_interface_id(auth_interface)
                auth_required = self._identify_auth_required_interfaces(interfaces)
                for target_interface in auth_required:
                    target_id = self._get_interface_id(target_interface)
                    edge_key = (auth_id, target_id, "authentication")
                    if edge_key not in edges_set:
                        edges_set.add(edge_key)
                        edges.append({
                            "source": auth_id,
                            "target": target_id,
                            "type": "authentication",
                            "description": f"{target_interface.get('name', '')}需要认证",
                            "dependency_path": "token -> Authorization header",
                            "confidence": 0.95
                        })
                        dependency_map[auth_id].append({
                            "target": target_id,
                            "type": "authentication",
                            "dependency": {"type": "authentication"}
                        })
            
            # 批量处理其他接口对
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                batch_count = 0
                
                for source_idx in range(len(interfaces)):
                    source_interface = interfaces[source_idx]
                    source_id = self._get_interface_id(source_interface)
                    
                    # 跳过已经处理过的认证接口
                    if auth_interface and source_interface == auth_interface:
                        continue
                    
                    for target_idx in range(len(interfaces)):
                        if source_idx == target_idx:
                            continue
                        
                        # 限制处理数量，避免超时
                        if processed_count >= batch_size * 5:  # 最多处理5批
                            break
                        
                        future = executor.submit(analyze_dependency_pair, source_idx, target_idx)
                        futures.append(future)
                        processed_count += 1
                    
                    if processed_count >= batch_size * 5:
                        break
                
                print(f"提交了 {len(futures)} 个分析任务")
                
                # 批量收集结果
                batch_edges = []
                for i, future in enumerate(as_completed(futures)):
                    if i % 1000 == 0:
                        print(f"  处理进度: {i}/{len(futures)}")
                    try:
                        new_edges = future.result()
                        batch_edges.extend(new_edges)
                        
                        # 每100个结果批量添加到edges
                        if len(batch_edges) >= 100:
                            with edges_lock:
                                for edge_data in batch_edges:
                                    edge_key = edge_data.get("_edge_key")
                                    if edge_key and edge_key not in edges_set:
                                        edges_set.add(edge_key)
                                        edges.append({
                                            "source": edge_data["source"],
                                            "target": edge_data["target"],
                                            "type": edge_data["type"],
                                            "description": edge_data["description"],
                                            "dependency_path": edge_data.get("dependency_path", ""),
                                            "confidence": edge_data.get("confidence", 0.5)
                                        })
                                        source_id = edge_data["source"]
                                        dependency_map[source_id].append({
                                            "target": edge_data["target"],
                                            "type": edge_data["type"],
                                            "dependency": edge_data.get("dependency", {})
                                        })
                            batch_edges = []
                    except Exception as e:
                        print(f"处理依赖关系时出错: {e}")
                
                # 处理剩余的结果
                if batch_edges:
                    with edges_lock:
                        for edge_data in batch_edges:
                            edge_key = edge_data.get("_edge_key")
                            if edge_key and edge_key not in edges_set:
                                edges_set.add(edge_key)
                                edges.append({
                                    "source": edge_data["source"],
                                    "target": edge_data["target"],
                                    "type": edge_data["type"],
                                    "description": edge_data["description"],
                                    "dependency_path": edge_data.get("dependency_path", ""),
                                    "confidence": edge_data.get("confidence", 0.5)
                                })
                                source_id = edge_data["source"]
                                dependency_map[source_id].append({
                                    "target": edge_data["target"],
                                    "type": edge_data["type"],
                                    "dependency": edge_data.get("dependency", {})
                                })
        elif len(interfaces) > 10:  # 接口数量中等时使用多线程
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for source_idx in range(len(interfaces)):
                    for target_idx in range(len(interfaces)):
                        future = executor.submit(analyze_dependency_pair, source_idx, target_idx)
                        futures.append(future)
                
                for future in as_completed(futures):
                    try:
                        new_edges = future.result()
                        with edges_lock:
                            for edge_data in new_edges:
                                edge_key = edge_data.get("_edge_key")
                                if edge_key and edge_key not in edges_set:
                                    edges_set.add(edge_key)
                                    edges.append({
                                        "source": edge_data["source"],
                                        "target": edge_data["target"],
                                        "type": edge_data["type"],
                                        "description": edge_data["description"],
                                        "dependency_path": edge_data.get("dependency_path", ""),
                                        "confidence": edge_data.get("confidence", 0.5)
                                    })
                                    source_id = edge_data["source"]
                                    dependency_map[source_id].append({
                                        "target": edge_data["target"],
                                        "type": edge_data["type"],
                                        "dependency": edge_data.get("dependency", {})
                                    })
                    except Exception as e:
                        print(f"处理依赖关系时出错: {e}")
        else:
            # 接口数量较少时使用串行处理
            for source_idx, source_interface in enumerate(interfaces):
                source_id = self._get_interface_id(source_interface)
                source_response = self._extract_response_fields(source_interface)
                
                for target_idx, target_interface in enumerate(interfaces):
                    if source_idx == target_idx:
                        continue
                    
                    # 如果登录接口已经处理过认证依赖，跳过重复处理
                    if auth_interface and source_interface == auth_interface:
                        target_id = self._get_interface_id(target_interface)
                        # 如果目标接口需要认证且已经添加了认证依赖，跳过参数溯源中的token匹配
                        if self._needs_authentication(target_interface):
                            continue
                    
                    target_id = self._get_interface_id(target_interface)
                    target_request = self._extract_request_fields(target_interface)
                    
                    # 检查是否存在参数依赖
                    dependencies = self._analyze_parameter_dependency(
                        source_response, target_request, source_interface, target_interface
                    )
                    
                    for dep in dependencies:
                        # 避免重复添加认证依赖
                        if dep["type"] == "authentication" and auth_interface:
                            auth_id = self._get_interface_id(auth_interface)
                            if any(e["source"] == auth_id and e["target"] == target_id for e in edges):
                                continue
                        
                        edge = {
                            "source": source_id,
                            "target": target_id,
                            "type": dep["type"],
                            "description": dep["description"],
                            "dependency_path": dep.get("path", ""),
                            "confidence": dep.get("confidence", 0.5)
                        }
                        edges.append(edge)
                        dependency_map[source_id].append({
                            "target": target_id,
                            "type": dep["type"],
                            "dependency": dep
                        })
        
        # 2. 状态依赖分析：基于业务逻辑推断依赖关系
        state_dependencies = self._analyze_state_dependencies(interfaces)
        for dep in state_dependencies:
            source_id = dep["source"]
            target_id = dep["target"]
            
            # 检查是否已存在边
            if not any(e["source"] == source_id and e["target"] == target_id for e in edges):
                edge = {
                    "source": source_id,
                    "target": target_id,
                    "type": dep["type"],
                    "description": dep["description"],
                    "dependency_path": "",
                    "confidence": dep.get("confidence", 0.6)
                }
                edges.append(edge)
                dependency_map[source_id].append({
                    "target": target_id,
                    "type": dep["type"],
                    "dependency": dep
                })
        
        # 3. 生成依赖链
        dependency_chains = self._generate_dependency_chains(dependency_map, nodes)
        
        # 4. 拓扑排序（确保登录接口排在第一位）
        topological_order = self._topological_sort(nodes, edges)
        if auth_interface:
            auth_id = self._get_interface_id(auth_interface)
            # 如果登录接口不在第一位，移到第一位
            if auth_id in topological_order and topological_order[0] != auth_id:
                topological_order.remove(auth_id)
                topological_order.insert(0, auth_id)
        
        result = {
            "nodes": nodes,
            "edges": edges,
            "dependency_chains": dependency_chains,
            "topological_order": topological_order
        }
        
        # 添加登录接口和token信息
        if auth_interface:
            result["auth_interface"] = {
                "id": self._get_interface_id(auth_interface),
                "name": auth_interface.get("name", ""),
                "method": auth_interface.get("method", ""),
                "url": auth_interface.get("url", ""),
                "path": auth_interface.get("path", "")
            }
            result["token_info"] = token_info
        
        return result
    
    def _get_interface_id(self, interface: Dict[str, Any]) -> str:
        """获取接口唯一标识"""
        interface_id = interface.get("interface_id")
        if interface_id:
            return f"api_{interface_id}"
        
        # 如果没有ID，使用method+path作为标识
        method = interface.get("method", "GET")
        path = interface.get("path", interface.get("url", ""))
        return f"{method}_{path}".replace("/", "_").replace(":", "")
    
    def _extract_response_fields(self, interface: Dict[str, Any]) -> Dict[str, Any]:
        """提取响应字段"""
        response_fields = {}
        
        # 从response_schema提取字段
        response_schema = interface.get("response_schema", {})
        if isinstance(response_schema, dict):
            response_fields.update(self._extract_schema_fields(response_schema))
        
        # 从response_body提取字段
        response_body = interface.get("response_body", {})
        if isinstance(response_body, dict):
            response_fields.update(self._flatten_dict(response_body, prefix="response"))
        
        return response_fields
    
    def _extract_request_fields(self, interface: Dict[str, Any]) -> Dict[str, Any]:
        """提取请求字段"""
        request_fields = {}
        
        # 从headers提取
        headers = interface.get("headers", {})
        if isinstance(headers, dict):
            request_fields.update({f"header.{k}": v for k, v in headers.items()})
        
        # 从params提取
        params = interface.get("params", {})
        if isinstance(params, dict):
            request_fields.update({f"param.{k}": v for k, v in params.items()})
        
        # 从request_body提取
        request_body = interface.get("request_body", {})
        if isinstance(request_body, dict):
            request_fields.update(self._flatten_dict(request_body, prefix="body"))
        
        return request_fields
    
    def _extract_schema_fields(self, schema: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """从schema中提取字段"""
        fields = {}
        
        if "properties" in schema:
            for key, value in schema["properties"].items():
                field_path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    if "type" in value:
                        fields[field_path] = value.get("example", value.get("default", ""))
                    elif "properties" in value:
                        # 嵌套对象
                        fields.update(self._extract_schema_fields(value, field_path))
        
        return fields
    
    def _flatten_dict(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """扁平化嵌套字典"""
        result = {}
        for key, value in data.items():
            field_path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten_dict(value, field_path))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # 处理数组中的对象
                result.update(self._flatten_dict(value[0], f"{field_path}[0]"))
            else:
                result[field_path] = str(value) if value is not None else ""
        return result
    
    def _analyze_parameter_dependency(
        self, 
        source_response: Dict[str, Any],
        target_request: Dict[str, Any],
        source_interface: Dict[str, Any],
        target_interface: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        分析参数依赖：检查目标接口的请求参数是否来源于源接口的响应
        
        返回值：依赖关系列表
        """
        dependencies = []
        
        # 1. 检查Authorization token依赖（最常见的依赖）
        source_token_paths = [
            "response.token", "response.data.token", "response.access_token",
            "response.result.token", "token", "access_token"
        ]
        
        target_auth_headers = ["header.Authorization", "header.authorization", "header.token"]
        
        source_token = None
        for path in source_token_paths:
            if path in source_response:
                source_token = source_response[path]
                break
        
        if source_token:
            for auth_header in target_auth_headers:
                if auth_header in target_request:
                    target_auth = target_request[auth_header]
                    # 检查是否匹配（可能是Bearer token格式）
                    if str(source_token) in str(target_auth) or str(target_auth).endswith(str(source_token)):
                        dependencies.append({
                            "type": "authentication",
                            "description": f"{source_interface.get('name')}的token用于{target_interface.get('name')}的认证",
                            "path": f"{path} -> {auth_header}",
                            "confidence": 0.9
                        })
        
        # 2. 检查其他参数依赖（精确匹配）
        for req_key, req_value in target_request.items():
            if not req_value:
                continue
            
            # 搜索源响应中是否有匹配的字段
            for resp_key, resp_value in source_response.items():
                if resp_value and str(resp_value) == str(req_value):
                    # 可能有关联
                    dependencies.append({
                        "type": "parameter",
                        "description": f"{target_interface.get('name')}的请求参数{req_key}来源于{source_interface.get('name')}的响应{resp_key}",
                        "path": f"{resp_key} -> {req_key}",
                        "confidence": 0.7
                    })
                elif resp_value and isinstance(resp_value, str) and isinstance(req_value, str):
                    # 检查值是否包含在另一个值中（如ID）
                    if str(resp_value) in str(req_value) or str(req_value) in str(resp_value):
                        dependencies.append({
                            "type": "parameter",
                            "description": f"{target_interface.get('name')}的请求参数{req_key}可能来源于{source_interface.get('name')}的响应{resp_key}",
                            "path": f"{resp_key} -> {req_key}",
                            "confidence": 0.5
                        })
        
        return dependencies
    
    def _identify_auth_interface(self, interfaces: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        识别登录/认证接口并提取token信息
        
        返回：
        (auth_interface, token_info)
        """
        # 登录接口关键字
        auth_keywords = ["login", "auth", "authenticate", "signin", "sign-in", "token", "oauth"]
        
        for interface in interfaces:
            name = (interface.get("name", "") + " " + interface.get("path", "") + " " + interface.get("url", "")).lower()
            method = interface.get("method", "").upper()
            
            # 检查是否是登录接口
            is_auth = any(keyword in name for keyword in auth_keywords)
            
            # 或者方法为POST且路径包含login/auth等
            if not is_auth and method == "POST":
                path_lower = interface.get("path", "").lower()
                if any(keyword in path_lower for keyword in ["login", "auth", "authenticate"]):
                    is_auth = True
            
            if is_auth:
                # 提取token信息
                response = self._extract_response_fields(interface)
                token_info = self._extract_token_info(interface, response)
                
                return interface, token_info
        
        return None, {}
    
    def _extract_token_info(self, interface: Dict[str, Any], response_fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        从登录接口响应中提取token信息
        
        常见的token路径：
        - token
        - data.token
        - access_token
        - data.access_token
        - result.token
        """
        token_paths = [
            "token", "access_token", "accessToken",
            "response.token", "response.data.token", "response.access_token",
            "response.data.access_token", "response.result.token",
            "data.token", "data.access_token", "result.token"
        ]
        
        token_info = {
            "path": None,
            "value": None,
            "type": "Bearer"  # 默认为Bearer token
        }
        
        # 从响应字段中查找token
        for path in token_paths:
            if path in response_fields:
                token_info["path"] = path
                token_info["value"] = response_fields[path]
                break
        
        # 如果没找到，尝试从response_schema中查找
        if not token_info["path"]:
            response_schema = interface.get("response_schema", {})
            if isinstance(response_schema, dict):
                schema_dict = response_schema.get("schema", response_schema)
                token_info = self._find_token_in_schema(schema_dict)
        
        # 如果还是没找到，尝试从response_body中查找
        if not token_info["path"]:
            response_body = interface.get("response_body", {})
            if isinstance(response_body, dict):
                flattened = self._flatten_dict(response_body, "response")
                for path in token_paths:
                    if path in flattened or any(path in k for k in flattened.keys()):
                        token_info["path"] = path
                        token_info["value"] = flattened.get(path, "")
                        break
        
        return token_info
    
    def _find_token_in_schema(self, schema: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """从schema中递归查找token字段"""
        token_info = {"path": None, "value": None, "type": "Bearer"}
        
        if "properties" in schema:
            for key, value in schema["properties"].items():
                field_path = f"{prefix}.{key}" if prefix else key
                key_lower = key.lower()
                
                # 检查是否是token相关字段
                if "token" in key_lower or "access" in key_lower:
                    token_info["path"] = field_path
                    token_info["value"] = value.get("example", value.get("default", ""))
                    return token_info
                
                # 递归查找嵌套对象
                if isinstance(value, dict) and "properties" in value:
                    nested_result = self._find_token_in_schema(value, field_path)
                    if nested_result["path"]:
                        return nested_result
        
        return token_info
    
    def _identify_auth_required_interfaces(self, interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        识别需要认证的接口
        
        判断标准：
        1. 请求头中包含Authorization、token、Bearer等
        2. 路径不包含login、auth等（排除登录接口本身）
        3. 方法不是GET的公开接口
        """
        auth_required = []
        auth_keywords = ["login", "auth", "authenticate", "signin", "sign-in", "register", "signup"]
        
        for interface in interfaces:
            headers = interface.get("headers", {})
            if not isinstance(headers, dict):
                headers = {}
            
            # 检查请求头中是否有认证相关字段
            has_auth_header = any(
                key.lower() in ["authorization", "token", "bearer", "x-token", "x-auth-token", "api-key"]
                for key in headers.keys()
            )
            
            # 检查路径，排除登录接口本身
            path_lower = (interface.get("path", "") + " " + interface.get("name", "")).lower()
            is_auth_interface = any(keyword in path_lower for keyword in auth_keywords)
            
            # 如果请求头中有认证字段，且不是登录接口本身，则需要认证
            if has_auth_header and not is_auth_interface:
                auth_required.append(interface)
            # 或者方法为POST/PUT/DELETE且不是登录接口（通常这些方法需要认证）
            elif interface.get("method", "").upper() in ["POST", "PUT", "DELETE", "PATCH"]:
                if not is_auth_interface:
                    auth_required.append(interface)
        
        return auth_required
    
    def _needs_authentication(self, interface: Dict[str, Any]) -> bool:
        """判断接口是否需要认证"""
        headers = interface.get("headers", {})
        if isinstance(headers, dict):
            has_auth = any(
                key.lower() in ["authorization", "token", "bearer", "x-token", "x-auth-token"]
                for key in headers.keys()
            )
            if has_auth:
                return True
        
        # 检查方法（非GET通常需要认证）
        method = interface.get("method", "").upper()
        if method in ["POST", "PUT", "DELETE", "PATCH"]:
            path_lower = (interface.get("path", "") + " " + interface.get("name", "")).lower()
            auth_keywords = ["login", "auth", "register", "signup"]
            if not any(keyword in path_lower for keyword in auth_keywords):
                return True
        
        return False
    
    def _analyze_state_dependencies(self, interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        分析状态依赖：基于业务逻辑推断依赖关系
        
        例如：
        - 支付接口依赖于创建订单接口
        - 删除接口依赖于创建接口
        """
        dependencies = []
        
        # 定义常见的状态依赖模式
        state_patterns = [
            {
                "source_keywords": ["create", "add", "post", "register", "login"],
                "target_keywords": ["update", "edit", "modify", "pay", "submit", "delete", "remove"],
                "type": "state",
                "description_template": "{source}创建的状态是{target}的前置条件",
                "confidence": 0.6
            },
            {
                "source_keywords": ["login", "auth", "token"],
                "target_keywords": ["profile", "info", "detail", "list"],
                "type": "authentication",
                "description_template": "{source}提供认证，{target}需要认证状态",
                "confidence": 0.8
            },
            {
                "source_keywords": ["order", "cart"],
                "target_keywords": ["pay", "checkout", "submit"],
                "type": "state",
                "description_template": "{source}创建订单是{target}的前置条件",
                "confidence": 0.7
            }
        ]
        
        for source in interfaces:
            source_name = (source.get("name", "") + " " + source.get("path", "")).lower()
            source_method = source.get("method", "").upper()
            
            for target in interfaces:
                if source == target:
                    continue
                
                target_name = (target.get("name", "") + " " + target.get("path", "")).lower()
                target_method = target.get("method", "").upper()
                
                # 检查是否匹配状态依赖模式
                for pattern in state_patterns:
                    source_match = any(keyword in source_name or keyword in source_method for keyword in pattern["source_keywords"])
                    target_match = any(keyword in target_name or keyword in target_method for keyword in pattern["target_keywords"])
                    
                    if source_match and target_match:
                        dependencies.append({
                            "source": self._get_interface_id(source),
                            "target": self._get_interface_id(target),
                            "type": pattern["type"],
                            "description": pattern["description_template"].format(
                                source=source.get("name", ""),
                                target=target.get("name", "")
                            ),
                            "confidence": pattern["confidence"]
                        })
                        break
        
        return dependencies
    
    def _generate_dependency_chains(self, dependency_map: Dict, nodes: List[Dict]) -> List[List[str]]:
        """生成依赖链"""
        chains = []
        visited = set()
        
        def dfs(node_id: str, chain: List[str]):
            if node_id in visited or node_id in chain:
                if len(chain) > 1:
                    chains.append(chain[:])
                return
            
            visited.add(node_id)
            chain.append(node_id)
            
            if node_id in dependency_map:
                for dep in dependency_map[node_id]:
                    dfs(dep["target"], chain)
            else:
                # 链的末端
                if len(chain) > 1:
                    chains.append(chain[:])
            
            chain.pop()
            visited.remove(node_id)
        
        for node in nodes:
            node_id = node["id"]
            if node_id not in visited:
                dfs(node_id, [])
        
        # 去重并排序
        unique_chains = []
        seen = set()
        for chain in chains:
            chain_str = "->".join(chain)
            if chain_str not in seen:
                seen.add(chain_str)
                unique_chains.append(chain)
        
        return sorted(unique_chains, key=len, reverse=True)[:20]  # 返回最长20条链
    
    def _topological_sort(self, nodes: List[Dict], edges: List[Dict]) -> List[str]:
        """拓扑排序：确定接口执行顺序"""
        # 构建图
        graph = {node["id"]: [] for node in nodes}
        in_degree = {node["id"]: 0 for node in nodes}
        
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            if source in graph:
                graph[source].append(target)
                if target in in_degree:
                    in_degree[target] += 1
        
        # Kahn算法
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node_id = queue.pop(0)
            result.append(node_id)
            
            for neighbor in graph[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # 如果有剩余节点（存在环），添加到末尾
        remaining = [node_id for node_id, degree in in_degree.items() if degree > 0]
        result.extend(remaining)
        
        return result
    
    def save_dependency_analysis(self, project_id: int, file_id: str, analysis_result: Dict[str, Any]) -> str:
        """保存依赖分析结果到Redis"""
        try:
            analysis_key = f"project:{project_id}:file:{file_id}:dependencies"
            self.redis_client.set(
                analysis_key,
                json.dumps(analysis_result, ensure_ascii=False),
                ex=86400 * 30  # 30天过期
            )
            
            # 添加到项目依赖分析索引
            index_key = f"project:{project_id}:dependencies"
            self.redis_client.sadd(index_key, file_id)
            self.redis_client.expire(index_key, 86400 * 30)
            
            return analysis_key
        except Exception as e:
            print(f"保存依赖分析结果失败: {e}")
            return ""
    
    def get_dependency_analysis(self, project_id: int, file_id: str) -> Optional[Dict[str, Any]]:
        """从Redis获取依赖分析结果"""
        try:
            analysis_key = f"project:{project_id}:file:{file_id}:dependencies"
            analysis_json = self.redis_client.get(analysis_key)
            if analysis_json:
                return json.loads(analysis_json)
        except Exception as e:
            print(f"获取依赖分析结果失败: {e}")
        return None

