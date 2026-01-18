from typing import List, Dict, Any, Optional
import json
import re
from sqlalchemy.orm import Session

from app.services.dependency_analyzer import DependencyAnalyzer, TestFlowGenerator
from app.services.smart_test_data_generator import SmartTestDataGenerator
from app.services.response_extractor import ResponseExtractor
from app.services.llm_service import LLMService
from app.services.db_service import DatabaseService
from app.models import DBConnection, APIInterface


class ScenarioGenerator:
    """基于用户故事的测试场景生成器"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.dependency_analyzer = DependencyAnalyzer(db_session)
        self.test_flow_generator = TestFlowGenerator(db_session)
        self.data_generator = SmartTestDataGenerator()
        self.response_extractor = ResponseExtractor()
        self.db_service = DatabaseService()
        self.llm_service = LLMService()
    
    def generate_scenario_from_user_story(
        self,
        user_story: str,
        api_interfaces: List[Dict[str, Any]],
        connection_id: int,
        project_id: int
    ) -> Dict[str, Any]:
        """
        基于用户故事生成测试场景
        
        Args:
            user_story: 用户故事描述，如"用户成功发布一篇文章并为自己评论"
            api_interfaces: API接口列表
            connection_id: 数据库连接ID
            project_id: 项目ID
        
        Returns:
            完整的测试场景，包括场景描述、步骤序列、每个步骤的请求数据和数据提取规则
        """
        # 1. 使用LLM分析用户故事，识别需要的接口
        required_apis = self._analyze_user_story_with_llm(user_story, api_interfaces)
        
        # 2. 分析接口依赖关系
        dependency_graph = self.dependency_analyzer.analyze_api_dependencies(
            api_interfaces, connection_id, project_id
        )
        
        # 3. 根据依赖关系构建接口调用序列
        api_sequence = self._build_api_sequence(
            required_apis, 
            dependency_graph,
            api_interfaces
        )
        
        # 4. 生成测试场景的每个步骤
        scenario = {
            "scenario_name": self._extract_scenario_name(user_story),
            "description": f"验证{user_story}的完整流程是否畅通",
            "user_story": user_story,
            "steps": [],
            "extracted_variables": {}
        }
        
        # 存储已提取的数据
        extracted_data = {}
        
        for step_index, api_id in enumerate(api_sequence, 1):
            api = next((a for a in api_interfaces if a.get("id") == api_id), None)
            if not api:
                continue
            
            # 确定这一步需要提取哪些数据
            extraction_rules = self._determine_extraction_rules(
                api, api_sequence, step_index, dependency_graph
            )
            
            # 生成这一步的测试数据（使用已提取的数据填充）
            step_data = self._generate_step_with_context(
                api,
                step_index,
                extracted_data,
                extraction_rules,
                connection_id,
                project_id
            )
            
            # 更新已提取的数据（用于后续步骤）
            if step_data.get("extract"):
                for var_name, extract_detail in step_data["extract"].items():
                    # 保存提取的变量
                    extracted_data[var_name] = extract_detail.get("example_value")
                    scenario["extracted_variables"][var_name] = extract_detail
            
            scenario["steps"].append(step_data)
        
        return scenario
    
    def _analyze_user_story_with_llm(
        self,
        user_story: str,
        api_interfaces: List[Dict[str, Any]]
    ) -> List[int]:
        """使用LLM分析用户故事，识别需要的接口"""
        # 构建API接口列表描述
        api_list_text = "\n".join([
            f"ID: {api['id']}, 名称: {api.get('name', '')}, 方法: {api.get('method')}, URL: {api.get('path', '')}"
            for api in api_interfaces
        ])
        
        prompt = f"""
根据以下用户故事，识别需要的API接口：
用户故事：{user_story}

可用的API接口列表：
{api_list_text}

请分析用户故事，列出完成这个用户故事需要调用的所有API接口ID（按执行顺序）。
只返回JSON格式的接口ID列表，例如：[1, 3, 5]

如果用户故事涉及的操作包括：
- 登录/注册：需要认证相关接口
- 创建/发布：需要POST接口
- 查看/获取：需要GET接口
- 更新：需要PUT/PATCH接口
- 删除：需要DELETE接口
- 评论/回复：需要POST接口（可能依赖创建资源的接口）

请仔细分析用户故事中提到的所有操作，确保包含所有必要的接口。
"""
        
        try:
            response = self.llm_service.chat(prompt, temperature=0.3, max_tokens=500)
            # 提取JSON数组
            json_match = re.search(r'\[[\d,\s]+\]', response)
            if json_match:
                api_ids = json.loads(json_match.group())
                return api_ids
        except Exception as e:
            print(f"LLM分析用户故事失败: {e}")
        
        # 如果LLM分析失败，使用规则匹配
        return self._match_apis_by_keywords(user_story, api_interfaces)
    
    def _match_apis_by_keywords(
        self,
        user_story: str,
        api_interfaces: List[Dict[str, Any]]
    ) -> List[int]:
        """基于关键词匹配API接口"""
        story_lower = user_story.lower()
        matched_ids = []
        
        # 关键词到接口类型的映射
        keyword_patterns = {
            "登录": ["login", "auth"],
            "注册": ["register", "signup"],
            "发布": ["post", "create", "publish", "add"],
            "文章": ["post", "article", "blog"],
            "评论": ["comment", "reply"],
            "查看": ["get", "list", "view", "fetch"],
            "更新": ["update", "put", "patch", "edit"],
            "删除": ["delete", "remove"]
        }
        
        for keyword, patterns in keyword_patterns.items():
            if keyword in story_lower:
                for api in api_interfaces:
                    api_name = api.get("name", "").lower()
                    api_url = api.get("path", "").lower()
                    
                    if any(pattern in api_name or pattern in api_url for pattern in patterns):
                        if api.get("id") not in matched_ids:
                            matched_ids.append(api.get("id"))
        
        return matched_ids
    
    def _build_api_sequence(
        self,
        required_api_ids: List[int],
        dependency_graph: Dict[str, Any],
        api_interfaces: List[Dict[str, Any]]
    ) -> List[int]:
        """根据依赖关系构建接口调用序列"""
        if not required_api_ids:
            return []
        
        # 构建API依赖映射
        api_deps = {}
        for node in dependency_graph.get("nodes", []):
            api_id = node.get("id")
            all_deps = node.get("data_flow_deps", []) + node.get("business_logic_deps", [])
            deps = [dep.get("api_id") for dep in all_deps if dep.get("api_id")]
            api_deps[api_id] = deps
        
        # 拓扑排序：确保依赖的接口先执行
        sequence = []
        remaining = set(required_api_ids)
        visited = set()
        
        def add_with_deps(api_id: int):
            if api_id in visited or api_id not in remaining:
                return
            
            visited.add(api_id)
            
            # 先添加依赖的接口
            for dep_id in api_deps.get(api_id, []):
                if dep_id in remaining and dep_id not in visited:
                    add_with_deps(dep_id)
            
            sequence.append(api_id)
        
        for api_id in required_api_ids:
            add_with_deps(api_id)
        
        # 确保所有依赖的接口都包含在内
        for api_id in list(remaining):
            if api_id not in visited:
                add_with_deps(api_id)
        
        return sequence
    
    def _determine_extraction_rules(
        self,
        api: Dict[str, Any],
        api_sequence: List[int],
        current_index: int,
        dependency_graph: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """确定这一步需要提取哪些数据"""
        rules = []
        
        # 检查后续步骤是否需要这个接口返回的数据
        api_id = api.get("id")
        
        # 查找依赖这个接口的后续接口
        for node in dependency_graph.get("nodes", []):
            if node.get("id") not in api_sequence:
                continue
            
            all_deps = node.get("data_flow_deps", []) + node.get("business_logic_deps", [])
            for dep in all_deps:
                if dep.get("api_id") == api_id:
                    # 需要提取的数据
                    extract_fields = dep.get("extract_fields", [])
                    for field in extract_fields:
                        var_name = self._generate_variable_name(field, api_id)
                        rules.append({
                            "field": field,
                            "variable_name": var_name,
                            "usage": dep.get("usage", ""),
                            "used_by": node.get("id")
                        })
        
        # 检查是否有token需要提取
        if "token" in str(api.get("response_schema", "")).lower() or "登录" in api.get("name", ""):
            rules.append({
                "field": "token",
                "variable_name": "authToken",
                "usage": "后续接口的Authorization header",
                "usage_type": "header"
            })
        
        # 检查是否有ID需要提取（用于后续步骤的路径参数或请求体）
        api_name = api.get("name", "").lower()
        api_url = api.get("path", "").lower()
        
        if any(keyword in api_name or keyword in api_url for keyword in ["创建", "发布", "add", "create", "post"]):
            # 创建类接口通常返回ID
            if "article" in api_name or "post" in api_name or "文章" in api_name:
                rules.append({
                    "field": "post_id",
                    "variable_name": "newPostId",
                    "usage": "后续步骤的文章ID",
                    "usage_type": "path_or_body"
                })
            elif "comment" in api_name or "评论" in api_name:
                rules.append({
                    "field": "comment_id",
                    "variable_name": "newCommentId",
                    "usage": "后续步骤的评论ID",
                    "usage_type": "path_or_body"
                })
        
        return rules
    
    def _generate_variable_name(self, field: str, api_id: int) -> str:
        """生成变量名"""
        field_map = {
            "token": "authToken",
            "device_id": "deviceId",
            "course_id": "courseId",
            "user_id": "userId",
            "post_id": "newPostId",
            "article_id": "articleId",
            "comment_id": "commentId",
            "family_id": "familyId"
        }
        
        return field_map.get(field, f"extracted_{field}_{api_id}")
    
    def _generate_step_with_context(
        self,
        api: Dict[str, Any],
        step_index: int,
        extracted_data: Dict[str, Any],
        extraction_rules: List[Dict[str, Any]],
        connection_id: int,
        project_id: int
    ) -> Dict[str, Any]:
        """生成步骤的测试数据（使用上下文数据）"""
        # 构建API信息
        api_info = {
            "id": api.get("id"),
            "name": api.get("name"),
            "method": api.get("method"),
            "url": api.get("path", ""),
            "base_url": api.get("base_url", ""),
            "params": json.loads(api.get("params", "{}")) if api.get("params") else {},
            "body": api.get("request_body"),
            "headers": json.loads(api.get("headers", "{}")) if api.get("headers") else {},
            "response_schema": api.get("response_schema")
        }
        
        # 生成基础测试数据
        test_data = self.data_generator.generate_test_data_for_api(
            api_info=api_info,
            connection_id=connection_id,
            project_id=project_id,
            use_real_data=True,
            db_session=self.db,
            engine=None  # 可以后续优化传入engine
        )
        
        # 使用已提取的数据填充
        if extracted_data.get("authToken"):
            test_data["headers"]["Authorization"] = f"Bearer {extracted_data['authToken']}"
        
        # 填充各种ID到请求中
        if extracted_data.get("newPostId"):
            # 如果是评论接口，使用postId
            if isinstance(test_data.get("body"), dict):
                test_data["body"]["post_id"] = extracted_data["newPostId"]
            # URL路径参数替换
            if "{post_id}" in api_info.get("url", "") or "/{postId}" in api_info.get("url", ""):
                test_data["path_params"] = test_data.get("path_params", {})
                test_data["path_params"]["post_id"] = extracted_data["newPostId"]
                # 替换URL中的路径参数
                api_info["url"] = api_info["url"].replace("{post_id}", str(extracted_data["newPostId"]))
                api_info["url"] = api_info["url"].replace("{postId}", str(extracted_data["newPostId"]))
        
        if extracted_data.get("deviceId"):
            if isinstance(test_data.get("body"), dict):
                test_data["body"]["device_id"] = extracted_data["deviceId"]
        
        if extracted_data.get("courseId"):
            if isinstance(test_data.get("body"), dict):
                test_data["body"]["course_id"] = extracted_data["courseId"]
        
        # 构建步骤信息
        step = {
            "step_index": step_index,
            "step_name": f"步骤{step_index}：{api.get('name', api.get('path', ''))}",
            "api_id": api.get("id"),
            "api_name": api.get("name"),
            "method": api.get("method"),
            "url": api.get("path", ""),
            "base_url": api.get("base_url", ""),
            "request": {
                "method": api.get("method"),
                "url": api_info.get("url"),
                "headers": test_data.get("headers", {}),
                "params": test_data.get("params", {}),
                "body": test_data.get("body", {})
            },
            "expected_response": {
                "status_code": 200 if api.get("method") in ["GET", "POST", "PUT", "PATCH"] else 201 if api.get("method") == "POST" else 204,
                "validation_rules": self._generate_validation_rules(api, extraction_rules)
            }
        }
        
        # 添加数据提取规则
        if extraction_rules:
            extract_info = {}
            for rule in extraction_rules:
                field = rule.get("field")
                var_name = rule.get("variable_name")
                usage = rule.get("usage", "")
                
                # 确定提取路径
                extract_path = self._determine_extract_path(field, api.get("response_schema"))
                
                extract_info[var_name] = {
                    "field": field,
                    "extract_path": extract_path,
                    "usage": usage,
                    "usage_type": rule.get("usage_type", "auto")
                }
            
            step["extract"] = extract_info
            # 生成示例提取值（实际执行时从响应提取）
            for var_name, extract_detail in extract_info.items():
                example_value = self._generate_example_value(extract_detail["field"])
                extract_detail["example_value"] = example_value
                extract_detail["variable_name"] = var_name
        
        return step
    
    def _determine_extract_path(self, field: str, response_schema: Optional[str]) -> str:
        """确定数据提取路径"""
        if response_schema:
            try:
                schema_obj = json.loads(response_schema) if isinstance(response_schema, str) else response_schema
                if isinstance(schema_obj, dict):
                    # 查找字段路径
                    paths = self.response_extractor._parse_token_paths_from_schema(response_schema)
                    if paths:
                        return paths[0]
            except:
                pass
        
        # 默认路径
        field_map = {
            "token": "token",
            "post_id": "data.id",
            "comment_id": "data.id",
            "user_id": "data.user_id",
            "device_id": "data.device_id"
        }
        
        return field_map.get(field, field)
    
    def _generate_example_value(self, field: str) -> Any:
        """生成示例提取值"""
        if field == "token":
            return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        elif "id" in field:
            return 12345
        elif "user_id" in field:
            return 1001
        else:
            return "extracted_value"
    
    def _generate_validation_rules(
        self,
        api: Dict[str, Any],
        extraction_rules: List[Dict[str, Any]]
    ) -> List[str]:
        """生成响应验证规则"""
        rules = []
        
        method = api.get("method", "").upper()
        if method == "GET":
            rules.append("状态码为 200")
            rules.append("响应体不为空")
        elif method == "POST":
            rules.append("状态码为 201 或 200")
            rules.append("响应体包含创建的资源信息")
        elif method in ["PUT", "PATCH"]:
            rules.append("状态码为 200")
            rules.append("响应体包含更新后的资源信息")
        elif method == "DELETE":
            rules.append("状态码为 204 或 200")
        
        # 根据提取规则添加验证
        for rule in extraction_rules:
            field = rule.get("field")
            if field == "token":
                rules.append("响应体中包含 token 或 access_token")
            elif "id" in field:
                rules.append(f"响应体中包含 {field}")
        
        return rules
    
    def _extract_scenario_name(self, user_story: str) -> str:
        """从用户故事中提取场景名称"""
        # 提取关键动词和名词
        patterns = [
            r"(.+?)(?:并|然后|再)",
            r"(.+?)(?:的|，)",
            r"(.+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, user_story)
            if match:
                name = match.group(1).strip()
                if name:
                    return name
        
        return user_story[:50]  # 截取前50个字符

