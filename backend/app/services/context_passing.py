from typing import Dict, Any, List, Optional, Set
import json
import re
from collections import defaultdict


class ContextPassing:
    """上下文传递：处理接口间的数据依赖，实现动态提取和注入"""
    
    def __init__(self):
        # 常见的响应字段映射
        self.common_extract_patterns = {
            "token": ["token", "accessToken", "access_token", "authToken", "auth_token"],
            "userId": ["userId", "user_id", "id", "userId"],
            "deviceId": ["deviceId", "device_id", "deviceId"],
            "courseId": ["courseId", "course_id", "id"],
            "postId": ["postId", "post_id", "id"],
            "orderId": ["orderId", "order_id", "id"],
            "familyId": ["familyId", "family_id", "id"]
        }
    
    def identify_dependencies(
        self,
        api_interfaces: List[Dict[str, Any]],
        knowledge_graph: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        识别接口间的数据依赖
        
        Args:
            api_interfaces: API接口列表
            knowledge_graph: 知识图谱信息（可选）
        
        Returns:
            依赖关系字典 {api_id: [依赖的接口信息]}
        """
        dependencies = defaultdict(list)
        
        # 分析每个接口
        for i, api in enumerate(api_interfaces):
            api_deps = []
            
            # 1. 检查路径参数中的占位符
            path = api.get("path", "") or api.get("url", "")
            path_params = self._extract_path_params(path)
            
            # 2. 检查请求体中的字段
            body = api.get("body") or api.get("request_body", "")
            body_deps = self._extract_body_dependencies(body, api_interfaces)
            
            # 3. 检查查询参数
            params = api.get("params", {})
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except:
                    params = {}
            param_deps = self._extract_param_dependencies(params, api_interfaces)
            
            # 合并依赖
            all_deps = set(path_params + body_deps + param_deps)
            
            # 查找提供这些数据的接口
            for dep_var in all_deps:
                source_api = self._find_source_api(dep_var, api_interfaces, i)
                if source_api:
                    api_deps.append({
                        "variable": dep_var,
                        "source_api": source_api,
                        "extract_path": self._guess_extract_path(dep_var, source_api)
                    })
            
            if api_deps:
                dependencies[str(api.get("id", i))] = api_deps
        
        return dict(dependencies)
    
    def _extract_path_params(self, path: str) -> List[str]:
        """提取路径参数"""
        if not path:
            return []
        
        # 匹配 {param} 或 ${param} 格式
        patterns = [
            r'\{(\w+)\}',
            r'\$\{(\w+)\}',
            r'\{(\$?\w+)\}'
        ]
        
        params = []
        for pattern in patterns:
            matches = re.findall(pattern, path)
            params.extend(matches)
        
        return list(set(params))
    
    def _extract_body_dependencies(
        self,
        body: Any,
        api_interfaces: List[Dict[str, Any]]
    ) -> List[str]:
        """从请求体中提取依赖"""
        if not body:
            return []
        
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except:
                return []
        
        if not isinstance(body, dict):
            return []
        
        dependencies = []
        
        # 查找需要从其他接口提取的字段
        for key, value in body.items():
            if isinstance(value, str) and (value.startswith("${") or value.startswith("{")):
                # 变量引用
                var_name = value.strip("${}").strip("{}")
                dependencies.append(var_name)
            elif key.endswith("Id") or key.endswith("ID") or key in ["token", "userId", "deviceId"]:
                # 常见依赖字段
                if isinstance(value, str) and value.startswith("$"):
                    dependencies.append(value.strip("$"))
        
        return dependencies
    
    def _extract_param_dependencies(
        self,
        params: Dict[str, Any],
        api_interfaces: List[Dict[str, Any]]
    ) -> List[str]:
        """从查询参数中提取依赖"""
        if not params:
            return []
        
        dependencies = []
        
        for key, value in params.items():
            if isinstance(value, str) and (value.startswith("${") or value.startswith("{")):
                var_name = value.strip("${}").strip("{}")
                dependencies.append(var_name)
        
        return dependencies
    
    def _find_source_api(
        self,
        variable: str,
        api_interfaces: List[Dict[str, Any]],
        current_index: int
    ) -> Optional[Dict[str, Any]]:
        """查找提供变量的源接口"""
        # 在前面的接口中查找
        for i in range(current_index):
            api = api_interfaces[i]
            
            # 检查接口名称或路径
            api_name = api.get("name", "").lower()
            api_path = (api.get("path", "") or api.get("url", "")).lower()
            
            # 根据变量类型匹配接口
            if variable.lower() in ["token", "authtoken", "auth_token"]:
                if "login" in api_name or "auth" in api_name or "token" in api_name:
                    return api
            elif variable.lower() in ["userid", "user_id"]:
                if "register" in api_name or "create" in api_name or "user" in api_name:
                    return api
            elif variable.lower() in ["deviceid", "device_id"]:
                if "device" in api_name or "bind" in api_name:
                    return api
            elif variable.lower() in ["courseid", "course_id"]:
                if "course" in api_name or "create" in api_name:
                    return api
            elif variable.lower() in ["postid", "post_id"]:
                if "post" in api_name or "create" in api_name:
                    return api
        
        return None
    
    def _guess_extract_path(self, variable: str, source_api: Dict[str, Any]) -> str:
        """猜测从响应中提取变量的路径"""
        # 使用常见模式
        var_lower = variable.lower()
        
        if var_lower in ["token", "authtoken", "auth_token"]:
            # 尝试多个可能的路径
            return "token"  # 默认，实际会根据响应调整
        
        # 尝试匹配字段名模式
        if var_lower.endswith("id"):
            base_name = var_lower.replace("id", "")
            # 尝试 data.id, result.id, response.id 等
            return f"data.{base_name}Id"
        
        return variable
    
    def generate_extract_code(
        self,
        response_variable: str,
        extract_paths: Dict[str, str]
    ) -> str:
        """
        生成数据提取代码
        
        Args:
            response_variable: 响应变量名
            extract_paths: 提取路径字典 {变量名: JSONPath}
        
        Returns:
            Python代码
        """
        code = f"# 从响应中提取数据\n"
        code += f"response_data = {response_variable}.json() if hasattr({response_variable}, 'json') else {response_variable}\n\n"
        
        for var_name, extract_path in extract_paths.items():
            # 处理多种提取路径
            code += f"# 提取 {var_name}\n"
            
            # 尝试多个可能的路径
            possible_paths = self._get_possible_paths(var_name, extract_path)
            
            code += f"{var_name} = None\n"
            for path in possible_paths:
                code += f"if {var_name} is None:\n"
                code += f"    {var_name} = self._extract_value(response_data, {repr(path)})\n"
            
            code += f"if {var_name} is None:\n"
            code += f"    raise ValueError(f\"无法提取 {var_name} 从响应中\")\n\n"
        
        return code
    
    def _get_possible_paths(self, var_name: str, base_path: str) -> List[str]:
        """获取可能的提取路径"""
        paths = [base_path]
        
        # 尝试不同的路径组合
        if "." in base_path:
            parts = base_path.split(".")
            # data.id, result.id, response.data.id
            paths.extend([
                parts[-1],  # 直接字段名
                f"result.{parts[-1]}",
                f"response.{parts[-1]}"
            ])
        else:
            paths.extend([
                f"data.{base_path}",
                f"result.{base_path}",
                f"response.{base_path}"
            ])
        
        return paths
    
    def generate_inject_code(
        self,
        target_api: Dict[str, Any],
        extracted_data: Dict[str, str]
    ) -> str:
        """
        生成数据注入代码
        
        Args:
            target_api: 目标API信息
            extracted_data: 提取的数据字典 {变量名: 值}
        
        Returns:
            Python代码
        """
        code = "# 注入提取的数据到请求\n"
        
        path = target_api.get("path", "") or target_api.get("url", "")
        body = target_api.get("body") or target_api.get("request_body", {})
        params = target_api.get("params", {})
        
        # 处理路径参数
        path_params = self._extract_path_params(path)
        for param in path_params:
            if param in extracted_data:
                code += f"url = url.replace('{{{param}}}', str({extracted_data[param]}))\n"
                code += f"url = url.replace('${{{param}}}', str({extracted_data[param]}))\n"
        
        # 处理请求体
        if body:
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except:
                    pass
            
            if isinstance(body, dict):
                for key, value in body.items():
                    # 检查是否需要注入
                    for var_name in extracted_data.keys():
                        if key.lower() == var_name.lower() or key.lower().endswith(var_name.lower()):
                            code += f"request_body['{key}'] = {extracted_data[var_name]}\n"
        
        # 处理查询参数
        if params and isinstance(params, dict):
            for key, value in params.items():
                for var_name in extracted_data.keys():
                    if key.lower() == var_name.lower():
                        code += f"params['{key}'] = {extracted_data[var_name]}\n"
        
        return code
    
    def generate_context_passing_code(
        self,
        api_sequence: List[Dict[str, Any]],
        dependencies: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        生成完整的上下文传递代码（多步依赖场景）
        
        Args:
            api_sequence: API调用序列
            dependencies: 依赖关系
        
        Returns:
            完整的Python测试代码
        """
        code = """import requests\n\n"""
        code += "class TestAPISequence:\n"
        code += "    def __init__(self, base_url):\n"
        code += "        self.base_url = base_url\n"
        code += "        self.extracted_data = {}\n\n"
        
        code += "    def _extract_value(self, data, path):\n"
        code += "        \"\"\"从响应数据中提取值\"\"\"\n"
        code += "        parts = path.split('.')\n"
        code += "        current = data\n"
        code += "        for part in parts:\n"
        code += "            if isinstance(current, dict):\n"
        code += "                current = current.get(part)\n"
        code += "            elif isinstance(current, list) and part.isdigit():\n"
        code += "                current = current[int(part)]\n"
        code += "            else:\n"
        code += "                return None\n"
        code += "            if current is None:\n"
        code += "                return None\n"
        code += "        return current\n\n"
        
        # 为每个API生成调用代码
        for i, api in enumerate(api_sequence):
            api_id = str(api.get("id", i))
            api_deps = dependencies.get(api_id, [])
            
            code += f"    def test_step_{i}_{api.get('name', 'api').replace(' ', '_')}(self):\n"
            code += f"        \"\"\"{api.get('name', 'API调用')}\"\"\"\n"
            
            # 如果有依赖，先注入数据
            if api_deps:
                code += "        # 注入依赖数据\n"
                for dep in api_deps:
                    var_name = dep["variable"]
                    code += f"        {var_name} = self.extracted_data.get('{var_name}')\n"
                    code += f"        if {var_name} is None:\n"
                    code += f"            raise ValueError(f'缺少依赖数据: {var_name}')\n"
            
            # 构建请求
            method = api.get("method", "GET").upper()
            path = api.get("path", "") or api.get("url", "")
            
            code += f"        url = f\"{{self.base_url}}{path}\"\n"
            
            # 替换路径参数
            path_params = self._extract_path_params(path)
            for param in path_params:
                code += f"        url = url.replace('{{{param}}}', str(self.extracted_data.get('{param}', '')))\n"
            
            # 构建请求参数
            code += "        headers = {}\n"
            code += "        params = {}\n"
            code += "        json_data = {}\n"
            
            # 添加认证
            code += "        if 'authToken' in self.extracted_data:\n"
            code += "            headers['Authorization'] = f\"Bearer {self.extracted_data['authToken']}\"\n"
            
            # 发送请求
            if method == "GET":
                code += "        response = requests.get(url, headers=headers, params=params)\n"
            elif method == "POST":
                code += "        response = requests.post(url, headers=headers, json=json_data, params=params)\n"
            elif method == "PUT":
                code += "        response = requests.put(url, headers=headers, json=json_data, params=params)\n"
            elif method == "DELETE":
                code += "        response = requests.delete(url, headers=headers, params=params)\n"
            
            code += "        assert response.status_code == 200\n"
            
            # 提取响应数据
            if api_deps or i < len(api_sequence) - 1:
                code += "        # 提取响应数据供后续使用\n"
                code += "        response_data = response.json()\n"
                
                for dep in api_deps:
                    extract_path = dep.get("extract_path", dep["variable"])
                    code += f"        extracted_value = self._extract_value(response_data, '{extract_path}')\n"
                    code += f"        if extracted_value:\n"
                    code += f"            self.extracted_data['{dep['variable']}'] = extracted_value\n"
            
            code += "\n"
        
        # 生成主测试方法
        code += "    def run_all(self):\n"
        code += "        \"\"\"运行所有步骤\"\"\"\n"
        for i in range(len(api_sequence)):
            code += f"        self.test_step_{i}_{api_sequence[i].get('name', 'api').replace(' ', '_')}()\n"
        
        return code









































