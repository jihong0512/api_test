from typing import List, Dict, Any, Optional
import json
import re
from sqlalchemy.orm import Session

from app.services.db_service import DatabaseService
from app.services.metadata_service import MetadataService
from app.services.response_extractor import ResponseExtractor


class DependencyAnalyzer:
    """接口依赖分析器：分析接口间的依赖关系和业务逻辑流程"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.db_service = DatabaseService()
        self.metadata_service = MetadataService()
        
        # 业务规则定义
        self.business_rules = {
            # 认证相关
            "authentication": {
                "required_for": [
                    "创建家庭活动",
                    "领取积分",
                    "打卡",
                    "进行训练计划",
                    "绑定运动设备"
                ],
                "endpoints": ["/login", "/auth/login", "/user/login"],
                "token_extraction": {
                    "response_path": ["token", "access_token", "data.token", "result.token"],
                    "header_name": "Authorization",
                    "header_format": "Bearer {token}"  # 或 "Token {token}"
                }
            },
            
            # 设备绑定相关
            "device_binding": {
                "required_for": [
                    "进行运动",
                    "开始训练",
                    "训练计划"
                ],
                "endpoints": ["/device/bind", "/equipment/bind", "/bind/device"],
                "prerequisites": ["authentication"]
            },
            
            # 查看权限（无需登录）
            "public_access": {
                "allowed_for": [
                    "查看运动课程",
                    "查看运动计划",
                    "浏览课程",
                    "浏览计划"
                ],
                "endpoints": ["/courses", "/plans", "/course/list", "/plan/list"]
            }
        }
    
    def analyze_api_dependencies(
        self,
        api_interfaces: List[Dict[str, Any]],
        connection_id: int,
        project_id: int
    ) -> Dict[str, Any]:
        """分析所有接口的依赖关系（增强版）"""
        dependency_graph = {
            "nodes": [],
            "edges": [],
            "business_flows": [],
            "call_chains": []
        }
        
        # 1. 识别各类接口
        auth_apis = self._identify_auth_apis(api_interfaces)
        register_apis = self._identify_register_apis(api_interfaces)
        device_bind_apis = self._identify_device_bind_apis(api_interfaces)
        family_apis = self._identify_family_apis(api_interfaces)
        
        # 2. 分析每个接口的依赖
        for api in api_interfaces:
            api_id = api.get("id")
            api_name = api.get("name", "")
            api_url = api.get("path", "").lower()
            api_method = api.get("method", "").upper()
            
            # 构建节点
            node = {
                "id": api_id,
                "name": api_name,
                "url": api.get("path", ""),
                "method": api_method,
                "dependencies": [],
                "requirements": [],
                "data_flow_deps": [],  # 数据流依赖
                "business_logic_deps": []  # 业务逻辑依赖
            }
            
            # 分析认证需求（业务逻辑依赖）
            requires_auth = self._requires_authentication(api_name, api_url)
            if requires_auth:
                # 登录接口可能依赖注册接口
                if auth_apis and api_id == auth_apis[0].get("id"):
                    if register_apis:
                        node["business_logic_deps"].append({
                            "type": "business_logic",
                            "dependency_type": "register_before_login",
                            "api_id": register_apis[0].get("id"),
                            "api_name": register_apis[0].get("name"),
                            "description": "用户登录前需要先注册",
                            "extract_fields": []  # 登录不需要提取注册的数据
                        })
                elif auth_apis:
                    # 其他接口依赖登录接口（数据流依赖：提取token）
                    node["data_flow_deps"].append({
                        "type": "data_flow",
                        "dependency_type": "requires_token",
                        "api_id": auth_apis[0].get("id"),
                        "api_name": auth_apis[0].get("name"),
                        "description": "需要登录获取token",
                        "extract_fields": ["token"],
                        "usage": "Authorization header"
                    })
            
            # 分析设备绑定需求
            requires_device = self._requires_device_binding(api_name, api_url)
            if requires_device and device_bind_apis:
                node["data_flow_deps"].append({
                    "type": "data_flow",
                    "dependency_type": "requires_device_binding",
                    "api_id": device_bind_apis[0].get("id"),
                    "api_name": device_bind_apis[0].get("name"),
                    "description": "需要先绑定设备",
                    "extract_fields": ["device_id"],
                    "requires_auth": True
                })
            
            # 分析家庭相关依赖
            if self._is_family_activity_api(api_name, api_url):
                # 发起家庭活动依赖创建家庭
                create_family_api = self._find_create_family_api(family_apis)
                if create_family_api:
                    node["business_logic_deps"].append({
                        "type": "business_logic",
                        "dependency_type": "requires_family",
                        "api_id": create_family_api.get("id"),
                        "api_name": create_family_api.get("name"),
                        "description": "发起家庭活动需要先创建家庭",
                        "extract_fields": ["family_id"]
                    })
            
            # 分析数据依赖（通过参数和知识图谱）
            data_deps = self._analyze_data_dependencies(
                api, api_interfaces, connection_id, project_id
            )
            for dep in data_deps:
                if dep.get("type") == "data_dependency":
                    node["data_flow_deps"].append(dep)
                else:
                    node["business_logic_deps"].append(dep)
            
            # 合并所有依赖到dependencies（用于向后兼容）
            node["dependencies"] = node["data_flow_deps"] + node["business_logic_deps"]
            
            dependency_graph["nodes"].append(node)
        
        # 4. 构建业务流程图
        business_flows = self._build_business_flows(
            dependency_graph["nodes"], auth_apis, device_bind_apis, register_apis, family_apis
        )
        dependency_graph["business_flows"] = business_flows
        
        # 5. 构建边（依赖关系）
        for node in dependency_graph["nodes"]:
            # 数据流依赖边
            for dep in node.get("data_flow_deps", []):
                dependency_graph["edges"].append({
                    "source": dep.get("api_id"),
                    "target": node["id"],
                    "type": "data_flow",
                    "dependency_type": dep.get("dependency_type", "data_dependency"),
                    "description": dep.get("description", ""),
                    "extract_fields": dep.get("extract_fields", []),
                    "usage": dep.get("usage", "")
                })
            
            # 业务逻辑依赖边
            for dep in node.get("business_logic_deps", []):
                dependency_graph["edges"].append({
                    "source": dep.get("api_id"),
                    "target": node["id"],
                    "type": "business_logic",
                    "dependency_type": dep.get("dependency_type", "business_dependency"),
                    "description": dep.get("description", ""),
                    "extract_fields": dep.get("extract_fields", [])
                })
        
        # 6. 构建调用链路图
        call_chains = self._build_call_chains(dependency_graph["nodes"])
        dependency_graph["call_chains"] = call_chains
        
        return dependency_graph
    
    def _identify_auth_apis(self, api_interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """识别认证接口（登录接口）"""
        auth_apis = []
        
        for api in api_interfaces:
            url = api.get("path", "").lower()
            name = api.get("name", "").lower()
            method = api.get("method", "").upper()
            
            # 匹配登录接口模式
            if any(keyword in url or keyword in name for keyword in [
                "/login", "/auth/login", "/user/login", "登录", "login"
            ]) and method == "POST":
                auth_apis.append(api)
        
        return auth_apis
    
    def _identify_register_apis(self, api_interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """识别用户注册接口"""
        register_apis = []
        
        for api in api_interfaces:
            url = api.get("path", "").lower()
            name = api.get("name", "").lower()
            method = api.get("method", "").upper()
            
            if any(keyword in url or keyword in name for keyword in [
                "/register", "/signup", "/user/register", "注册", "register", "signup"
            ]) and method == "POST":
                register_apis.append(api)
        
        return register_apis
    
    def _identify_device_bind_apis(self, api_interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """识别设备绑定接口"""
        bind_apis = []
        
        for api in api_interfaces:
            url = api.get("path", "").lower()
            name = api.get("name", "").lower()
            method = api.get("method", "").upper()
            
            if any(keyword in url or keyword in name for keyword in [
                "/bind", "/device/bind", "/equipment/bind", "绑定", "bind"
            ]) and method in ["POST", "PUT"]:
                bind_apis.append(api)
        
        return bind_apis
    
    def _identify_family_apis(self, api_interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """识别家庭相关接口"""
        family_apis = []
        
        for api in api_interfaces:
            url = api.get("path", "").lower()
            name = api.get("name", "").lower()
            
            if any(keyword in url or keyword in name for keyword in [
                "/family", "/home", "家庭", "family", "home"
            ]):
                family_apis.append(api)
        
        return family_apis
    
    def _is_family_activity_api(self, api_name: str, api_url: str) -> bool:
        """判断是否是家庭活动相关接口"""
        name_lower = api_name.lower()
        url_lower = api_url.lower()
        
        activity_keywords = [
            "/activity", "/event", "/family/activity", "/home/activity",
            "家庭活动", "发起活动", "创建活动", "activity", "event"
        ]
        
        return any(keyword in url_lower or keyword in name_lower for keyword in activity_keywords)
    
    def _find_create_family_api(self, family_apis: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """查找创建家庭的接口"""
        for api in family_apis:
            url = api.get("path", "").lower()
            name = api.get("name", "").lower()
            method = api.get("method", "").upper()
            
            if method == "POST" and any(keyword in url or keyword in name for keyword in [
                "/create", "/add", "创建", "添加", "create", "add"
            ]):
                return api
        
        return None
    
    def _requires_authentication(self, api_name: str, api_url: str) -> bool:
        """判断接口是否需要认证"""
        name_lower = api_name.lower()
        url_lower = api_url.lower()
        
        # 明确不需要认证的接口
        public_keywords = [
            "/login", "/register", "/courses", "/plans",
            "查看课程", "查看计划", "浏览", "查看"
        ]
        
        if any(keyword in url_lower or keyword in name_lower for keyword in public_keywords):
            return False
        
        # 明确需要认证的接口
        auth_keywords = [
            "/create", "/add", "/bind", "/unbind", "/checkin", "/punch",
            "创建", "添加", "绑定", "解绑", "打卡", "领取积分", "训练", "运动"
        ]
        
        if any(keyword in url_lower or keyword in name_lower for keyword in auth_keywords):
            return True
        
        # 默认需要认证
        return True
    
    def _requires_device_binding(self, api_name: str, api_url: str) -> bool:
        """判断接口是否需要设备绑定"""
        name_lower = api_name.lower()
        url_lower = api_url.lower()
        
        device_keywords = [
            "/sport", "/exercise", "/training", "/start", "/workout",
            "运动", "训练", "开始训练", "开始运动", "进行训练"
        ]
        
        return any(keyword in url_lower or keyword in name_lower for keyword in device_keywords)
    
    def _analyze_data_dependencies(
        self,
        api: Dict[str, Any],
        all_apis: List[Dict[str, Any]],
        connection_id: int,
        project_id: int
    ) -> List[Dict[str, Any]]:
        """分析接口的数据依赖（通过参数和知识图谱）"""
        dependencies = []
        
        # 从请求参数中识别可能的依赖
        params = json.loads(api.get("params", "{}")) if api.get("params") else {}
        body = api.get("request_body", "")
        if isinstance(body, str):
            try:
                body_dict = json.loads(body)
            except:
                body_dict = {}
        else:
            body_dict = body if isinstance(body, dict) else {}
        
        # 合并所有字段
        all_fields = {}
        all_fields.update(params)
        if isinstance(body_dict, dict):
            all_fields.update(body_dict)
        
        # 识别外键字段（需要从其他表获取数据）
        for field_name, field_value in all_fields.items():
            if "id" in field_name.lower() or "record" in field_name.lower():
                # 推断可能依赖的表和接口
                dep = self._find_data_source(field_name, all_apis, connection_id, project_id)
                if dep:
                    dependencies.append(dep)
        
        # 特别处理：查看运动记录接口依赖登录接口
        api_name = api.get("name", "").lower()
        api_url = api.get("path", "").lower()
        if any(keyword in api_name or keyword in api_url for keyword in [
            "查看", "记录", "/record", "/history", "运动记录", "运动历史"
        ]):
            # 查找登录接口
            auth_apis = self._identify_auth_apis(all_apis)
            if auth_apis:
                dependencies.append({
                    "type": "data_flow",
                    "dependency_type": "requires_token",
                    "api_id": auth_apis[0].get("id"),
                    "api_name": auth_apis[0].get("name"),
                    "description": "查看运动记录需要登录",
                    "extract_fields": ["token"],
                    "usage": "Authorization header"
                })
        
        return dependencies
    
    def _find_data_source(
        self,
        field_name: str,
        all_apis: List[Dict[str, Any]],
        connection_id: int,
        project_id: int
    ) -> Optional[Dict[str, Any]]:
        """查找字段数据的来源接口"""
        field_lower = field_name.lower()
        
        # 基于字段名推断可能的创建接口
        if "user" in field_lower:
            # 查找用户创建接口
            for api in all_apis:
                url = api.get("path", "").lower()
                name = api.get("name", "").lower()
                if ("/user" in url or "/users" in url) and "create" in name:
                    return {
                        "type": "data_dependency",
                        "api_id": api.get("id"),
                        "api_name": api.get("name"),
                        "field": field_name,
                        "description": f"需要先创建用户，获取{field_name}"
                    }
        
        elif "device" in field_lower or "equipment" in field_lower:
            for api in all_apis:
                url = api.get("path", "").lower()
                name = api.get("name", "").lower()
                if ("/device" in url or "/equipment" in url) and "bind" in name:
                    return {
                        "type": "device_binding",
                        "api_id": api.get("id"),
                        "api_name": api.get("name"),
                        "field": field_name,
                        "description": f"需要先绑定设备，获取{field_name}"
                    }
        
        elif "course" in field_lower:
            for api in all_apis:
                url = api.get("path", "").lower()
                if "/course" in url or "/courses" in url:
                    return {
                        "type": "data_dependency",
                        "api_id": api.get("id"),
                        "api_name": api.get("name"),
                        "field": field_name,
                        "description": f"需要先获取课程列表，选择课程ID"
                    }
        
        return None
    
    def _build_call_chains(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建接口调用链路图"""
        chains = []
        
        # 构建从起始节点到目标节点的所有路径
        def find_chains(start_id: int, target_id: int, visited: set, path: List[int], max_depth: int = 5) -> List[List[int]]:
            """递归查找所有调用链"""
            if len(path) > max_depth:
                return []
            
            if start_id == target_id:
                return [path.copy()]
            
            if start_id in visited:
                return []
            
            visited.add(start_id)
            all_chains = []
            
            # 查找所有依赖于start_id的接口
            for node in nodes:
                node_id = node.get("id")
                if node_id == start_id:
                    continue
                
                # 检查是否有依赖关系
                all_deps = node.get("data_flow_deps", []) + node.get("business_logic_deps", [])
                if any(dep.get("api_id") == start_id for dep in all_deps):
                    new_path = path + [node_id]
                    chains = find_chains(node_id, target_id, visited.copy(), new_path, max_depth)
                    all_chains.extend(chains)
            
            return all_chains
        
        # 找出所有起始节点（没有依赖的接口）
        start_nodes = []
        for node in nodes:
            if not node.get("data_flow_deps") and not node.get("business_logic_deps"):
                start_nodes.append(node)
        
        # 找出所有目标节点（最终调用的接口）
        target_nodes = []
        for node in nodes:
            # 检查是否有其他接口依赖它
            is_target = True
            for other_node in nodes:
                if other_node.get("id") == node.get("id"):
                    continue
                all_deps = other_node.get("data_flow_deps", []) + other_node.get("business_logic_deps", [])
                if any(dep.get("api_id") == node.get("id") for dep in all_deps):
                    is_target = False
                    break
            
            if is_target:
                target_nodes.append(node)
        
        # 构建从每个起始节点到每个目标节点的调用链
        for start_node in start_nodes:
            for target_node in target_nodes:
                if start_node.get("id") == target_node.get("id"):
                    continue
                
                paths = find_chains(start_node.get("id"), target_node.get("id"), set(), [start_node.get("id")])
                
                for path in paths:
                    chain_nodes = []
                    for node_id in path:
                        node = next((n for n in nodes if n.get("id") == node_id), None)
                        if node:
                            chain_nodes.append({
                                "api_id": node_id,
                                "api_name": node.get("name"),
                                "url": node.get("url"),
                                "method": node.get("method")
                            })
                    
                    if len(chain_nodes) > 1:
                        chains.append({
                            "chain_name": f"{start_node.get('name')} → {target_node.get('name')}",
                            "nodes": chain_nodes,
                            "length": len(chain_nodes),
                            "description": self._generate_chain_description(chain_nodes, nodes)
                        })
        
        # 去重并排序
        unique_chains = []
        seen_paths = set()
        for chain in chains:
            path_key = tuple(node["api_id"] for node in chain["nodes"])
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                unique_chains.append(chain)
        
        # 按长度排序
        unique_chains.sort(key=lambda x: x["length"], reverse=True)
        
        return unique_chains[:20]  # 返回前20个最长的调用链
    
    def _generate_chain_description(self, chain_nodes: List[Dict[str, Any]], all_nodes: List[Dict[str, Any]]) -> str:
        """生成调用链描述"""
        descriptions = []
        
        for i, node in enumerate(chain_nodes):
            if i == 0:
                descriptions.append(f"开始：{node['api_name']}")
            else:
                prev_node_id = chain_nodes[i-1]["api_id"]
                current_node = next((n for n in all_nodes if n.get("id") == node["api_id"]), None)
                
                if current_node:
                    all_deps = current_node.get("data_flow_deps", []) + current_node.get("business_logic_deps", [])
                    dep = next((d for d in all_deps if d.get("api_id") == prev_node_id), None)
                    
                    if dep:
                        dep_type = dep.get("dependency_type", "")
                        desc = dep.get("description", "")
                        descriptions.append(f"→ {node['api_name']}（{desc}）")
                    else:
                        descriptions.append(f"→ {node['api_name']}")
        
        return " → ".join(descriptions)
    
    def _build_business_flows(
        self,
        nodes: List[Dict[str, Any]],
        auth_apis: List[Dict[str, Any]],
        device_bind_apis: List[Dict[str, Any]],
        register_apis: List[Dict[str, Any]] = None,
        family_apis: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """构建业务流程图"""
        flows = []
        
        # 流程1：查看公开内容（无需登录）
        public_flow = {
            "name": "查看公开内容",
            "description": "未登录用户可以查看运动课程和运动计划",
            "steps": []
        }
        for node in nodes:
            if not node.get("dependencies") or not any(
                d.get("type") == "authentication" for d in node["dependencies"]
            ):
                if "course" in node.get("url", "").lower() or "plan" in node.get("url", "").lower():
                    public_flow["steps"].append({
                        "api_id": node["id"],
                        "api_name": node["name"],
                        "action": "GET"
                    })
        if public_flow["steps"]:
            flows.append(public_flow)
        
        # 流程2：用户注册和登录流程
        register_login_flow = {
            "name": "用户注册登录流程",
            "description": "用户注册 → 用户登录",
            "steps": []
        }
        if register_apis:
            register_login_flow["steps"].append({
                "api_id": register_apis[0].get("id"),
                "api_name": register_apis[0].get("name"),
                "action": "POST"
            })
        if auth_apis:
            register_login_flow["steps"].append({
                "api_id": auth_apis[0].get("id"),
                "api_name": auth_apis[0].get("name"),
                "action": "POST",
                "extract_token": True,
                "token_path": ["token", "access_token", "data.token"],
                "depends_on": register_apis[0].get("id") if register_apis else None
            })
        if len(register_login_flow["steps"]) >= 2:
            flows.append(register_login_flow)
        
        # 流程3：登录后操作（需要认证）
        auth_flow = {
            "name": "登录后操作",
            "description": "登录后可以创建家庭活动、领取积分、打卡等",
            "steps": []
        }
        if auth_apis:
            auth_flow["steps"].append({
                "api_id": auth_apis[0].get("id"),
                "api_name": auth_apis[0].get("name"),
                "action": "POST",
                "extract_token": True,
                "token_path": ["token", "access_token", "data.token"]
            })
        
        for node in nodes:
            if any(d.get("type") == "authentication" for d in node.get("dependencies", [])):
                if not any("device" in req.lower() for req in node.get("requirements", [])):
                    auth_flow["steps"].append({
                        "api_id": node["id"],
                        "api_name": node["name"],
                        "action": node.get("method"),
                        "requires_token": True
                    })
        
        if len(auth_flow["steps"]) > 1:
            flows.append(auth_flow)
        
        # 流程4：家庭活动流程
        family_activity_flow = {
            "name": "家庭活动流程",
            "description": "创建家庭 → 发起家庭活动",
            "steps": []
        }
        if auth_apis:
            family_activity_flow["steps"].append({
                "api_id": auth_apis[0].get("id"),
                "api_name": auth_apis[0].get("name"),
                "action": "POST",
                "extract_token": True
            })
        
        create_family_api = self._find_create_family_api(family_apis if family_apis else [])
        if create_family_api:
            family_activity_flow["steps"].append({
                "api_id": create_family_api.get("id"),
                "api_name": create_family_api.get("name"),
                "action": "POST",
                "requires_token": True,
                "extract_family_id": True
            })
        
        # 查找发起家庭活动接口
        for node in nodes:
            if self._is_family_activity_api(node.get("name", ""), node.get("url", "")):
                family_activity_flow["steps"].append({
                    "api_id": node["id"],
                    "api_name": node["name"],
                    "action": node.get("method"),
                    "requires_token": True,
                    "requires_family_id": True
                })
        
        if len(family_activity_flow["steps"]) >= 2:
            flows.append(family_activity_flow)
        
        # 流程5：运动训练（需要登录+设备绑定）
        training_flow = {
            "name": "运动训练流程",
            "description": "进行训练需要：登录 → 绑定设备 → 选择课程 → 开始训练",
            "steps": []
        }
        
        if auth_apis:
            training_flow["steps"].append({
                "api_id": auth_apis[0].get("id"),
                "api_name": auth_apis[0].get("name"),
                "action": "POST",
                "extract_token": True
            })
        
        if device_bind_apis:
            training_flow["steps"].append({
                "api_id": device_bind_apis[0].get("id"),
                "api_name": device_bind_apis[0].get("name"),
                "action": "POST",
                "requires_token": True,
                "extract_device_id": True
            })
        
        # 查找课程选择接口
        for node in nodes:
            if "course" in node.get("url", "").lower() and node.get("method") == "GET":
                training_flow["steps"].append({
                    "api_id": node["id"],
                    "api_name": node["name"],
                    "action": "GET",
                    "requires_token": True,
                    "extract_course_id": True
                })
        
        # 查找开始训练接口
        for node in nodes:
            if any(keyword in node.get("url", "").lower() for keyword in ["/start", "/training/start", "/exercise/start"]):
                training_flow["steps"].append({
                    "api_id": node["id"],
                    "api_name": node["name"],
                    "action": "POST",
                    "requires_token": True,
                    "requires_device_id": True,
                    "requires_course_id": True
                })
        
        if len(training_flow["steps"]) >= 3:
            flows.append(training_flow)
        
        return flows


class TestFlowGenerator:
    """测试流程生成器：生成完整的测试流程和数据"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.dependency_analyzer = DependencyAnalyzer(db_session)
        self.db_service = DatabaseService()
        self.response_extractor = ResponseExtractor()
        
    def generate_test_flow(
        self,
        api_interfaces: List[Dict[str, Any]],
        connection_id: int,
        project_id: int,
        flow_type: str = "auto"
    ) -> Dict[str, Any]:
        """生成测试流程"""
        # 分析依赖关系
        dependency_graph = self.dependency_analyzer.analyze_api_dependencies(
            api_interfaces, connection_id, project_id
        )
        
        # 根据流程类型选择流程
        if flow_type == "auto":
            # 自动选择最完整的流程
            flows = dependency_graph.get("business_flows", [])
            if flows:
                selected_flow = flows[-1]  # 选择最复杂的流程
            else:
                selected_flow = {"name": "基础流程", "steps": []}
        else:
            # 根据名称选择
            flows = dependency_graph.get("business_flows", [])
            selected_flow = next(
                (f for f in flows if f["name"] == flow_type),
                flows[0] if flows else {"name": "基础流程", "steps": []}
            )
        
        # 生成每个步骤的测试数据
        flow_data = {
            "flow_name": selected_flow["name"],
            "description": selected_flow.get("description", ""),
            "steps": []
        }
        
        # 存储提取的数据（token, device_id等）
        extracted_data = {}
        
        for step in selected_flow.get("steps", []):
            api_id = step.get("api_id")
            api = next((a for a in api_interfaces if a.get("id") == api_id), None)
            
            if not api:
                continue
            
            # 生成测试数据（结合已提取的数据）
            step_test_data = self._generate_step_data(
                api, step, extracted_data, connection_id, project_id
            )
            
            # 记录提取的数据（这些数据会在后续步骤中使用）
            if step.get("extract_token"):
                # 分析response_schema确定token提取路径
                token_paths = self.response_extractor._parse_token_paths_from_schema(
                    api.get("response_schema", "")
                )
                # 生成模拟token（实际执行时会从真实响应提取）
                token = self._extract_token_from_response(api)
                extracted_data["token"] = token
                extracted_data["token_path"] = token_paths[0] if token_paths else "token"
                extracted_data["headers"] = {
                    "Authorization": f"Bearer {token}"
                }
            
            if step.get("extract_device_id"):
                device_id = self._generate_device_id(connection_id)
                extracted_data["device_id"] = device_id
            
            if step.get("extract_course_id"):
                course_id = self._generate_course_id(connection_id)
                extracted_data["course_id"] = course_id
            
            step_info = {
                "step_index": len(flow_data["steps"]) + 1,
                "api_id": api_id,
                "api_name": step.get("api_name"),
                "method": step.get("action"),
                "url": api.get("path", ""),
                "test_data": step_test_data,
                "expected_response": self._get_expected_response(api, step)
            }
            
            # 添加数据提取信息
            if step.get("extract_token"):
                step_info["extract"] = {
                    "type": "token",
                    "path": extracted_data.get("token_path", "token"),
                    "usage": "后续接口的Authorization header"
                }
            
            if step.get("extract_device_id"):
                step_info["extract"] = {
                    "type": "device_id",
                    "usage": "后续接口的device_id参数"
                }
            
            if step.get("extract_course_id"):
                step_info["extract"] = {
                    "type": "course_id",
                    "usage": "后续接口的course_id参数"
                }
            
            flow_data["steps"].append(step_info)
        
        return flow_data
    
    def _generate_step_data(
        self,
        api: Dict[str, Any],
        step: Dict[str, Any],
        extracted_data: Dict[str, Any],
        connection_id: int,
        project_id: int
    ) -> Dict[str, Any]:
        """生成步骤的测试数据"""
        from app.services.smart_test_data_generator import SmartTestDataGenerator
        from app.models import DBConnection
        from app.services.db_service import DatabaseService
        
        generator = SmartTestDataGenerator()
        db_service = DatabaseService()
        
        # 连接数据库获取engine
        connection = self.db.query(DBConnection).filter(
            DBConnection.id == connection_id
        ).first()
        
        engine = None
        if connection:
            try:
                engine = db_service.connect_database(
                    connection.db_type,
                    connection.host,
                    connection.port,
                    connection.database_name,
                    connection.username,
                    connection.password
                )
            except:
                pass
        
        # 构建API信息
        api_info = {
            "id": api.get("id"),
            "name": api.get("name"),
            "method": api.get("method"),
            "url": api.get("path"),
            "base_url": api.get("base_url"),
            "params": json.loads(api.get("params", "{}")) if api.get("params") else {},
            "body": api.get("request_body"),
            "headers": {}
        }
        
        # 如果需要token，添加到headers
        if step.get("requires_token") and extracted_data.get("token"):
            api_info["headers"]["Authorization"] = extracted_data.get("headers", {}).get("Authorization", f"Bearer {extracted_data.get('token', '')}")
        
        # 生成基础测试数据
        test_data = generator.generate_test_data_for_api(
            api_info=api_info,
            connection_id=connection_id,
            project_id=project_id,
            use_real_data=True,
            db_session=self.db,
            engine=engine
        )
        
        # 使用已提取的数据填充字段
        if step.get("requires_device_id") and extracted_data.get("device_id"):
            # 查找device_id字段并填充
            if isinstance(test_data.get("body"), dict):
                if "device_id" in test_data["body"]:
                    test_data["body"]["device_id"] = extracted_data["device_id"]
                if "equipment_id" in test_data["body"]:
                    test_data["body"]["equipment_id"] = extracted_data["device_id"]
            if isinstance(test_data.get("params"), dict):
                if "device_id" in test_data["params"]:
                    test_data["params"]["device_id"] = extracted_data["device_id"]
        
        if step.get("requires_course_id") and extracted_data.get("course_id"):
            if isinstance(test_data.get("body"), dict):
                if "course_id" in test_data["body"]:
                    test_data["body"]["course_id"] = extracted_data["course_id"]
                if "training_course_id" in test_data["body"]:
                    test_data["body"]["training_course_id"] = extracted_data["course_id"]
            if isinstance(test_data.get("params"), dict):
                if "course_id" in test_data["params"]:
                    test_data["params"]["course_id"] = extracted_data["course_id"]
        
        return test_data
    
    def _extract_token_from_response(self, api: Dict[str, Any]) -> str:
        """从API响应中提取token（模拟）"""
        # 分析response_schema确定token路径
        response_schema = api.get("response_schema", "")
        if isinstance(response_schema, str):
            try:
                schema = json.loads(response_schema)
                # 查找token字段路径
                if isinstance(schema, dict):
                    if "token" in schema:
                        return "extracted_token_from_token"
                    if "data" in schema and isinstance(schema["data"], dict):
                        if "token" in schema["data"]:
                            return "extracted_token_from_data_token"
                    if "access_token" in schema:
                        return "extracted_token_from_access_token"
            except:
                pass
        
        # 默认token格式
        return "mock_token_" + str(api.get("id", 0))
    
    def _generate_device_id(self, connection_id: int) -> int:
        """生成或获取设备ID（从数据库）"""
        from app.models import DBConnection
        from app.services.db_service import DatabaseService
        from app.services.smart_test_data_generator import SmartTestDataGenerator
        
        generator = SmartTestDataGenerator()
        
        connection = self.db.query(DBConnection).filter(
            DBConnection.id == connection_id
        ).first()
        
        if connection:
            try:
                db_service = DatabaseService()
                engine = db_service.connect_database(
                    connection.db_type,
                    connection.host,
                    connection.port,
                    connection.database_name,
                    connection.username,
                    connection.password
                )
                
                # 尝试从设备表获取真实ID
                device_id = generator._get_real_id_from_table("devices", engine) or \
                           generator._get_real_id_from_table("equipment", engine)
                if device_id:
                    return device_id
            except:
                pass
        
        return 1001
    
    def _generate_course_id(self, connection_id: int) -> int:
        """生成或获取课程ID（从数据库）"""
        from app.models import DBConnection
        from app.services.db_service import DatabaseService
        from app.services.smart_test_data_generator import SmartTestDataGenerator
        
        generator = SmartTestDataGenerator()
        
        connection = self.db.query(DBConnection).filter(
            DBConnection.id == connection_id
        ).first()
        
        if connection:
            try:
                db_service = DatabaseService()
                engine = db_service.connect_database(
                    connection.db_type,
                    connection.host,
                    connection.port,
                    connection.database_name,
                    connection.username,
                    connection.password
                )
                
                # 尝试从课程表获取真实ID
                course_id = generator._get_real_id_from_table("courses", engine) or \
                           generator._get_real_id_from_table("course", engine)
                if course_id:
                    return course_id
            except:
                pass
        
        return 2001
    
    def _get_expected_response(self, api: Dict[str, Any], step: Dict[str, Any]) -> Dict[str, Any]:
        """获取期望的响应"""
        extract_fields = []
        
        if step.get("extract_token"):
            extract_fields.append("token")
        if step.get("extract_device_id"):
            extract_fields.append("device_id")
        if step.get("extract_course_id"):
            extract_fields.append("course_id")
        if step.get("extract_family_id"):
            extract_fields.append("family_id")
        
        return {
            "status_code": 200,
            "extract_fields": extract_fields
        }

