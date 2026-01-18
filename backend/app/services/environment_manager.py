from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models import TestEnvironment, Project, User


class EnvironmentManager:
    """环境管理器：管理不同测试环境的配置"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def get_environment(
        self,
        environment_id: int,
        user_id: int
    ) -> Optional[TestEnvironment]:
        """
        获取测试环境（验证权限）
        
        Args:
            environment_id: 环境ID
            user_id: 用户ID
        
        Returns:
            测试环境对象
        """
        environment = self.db.query(TestEnvironment).filter(
            TestEnvironment.id == environment_id
        ).first()
        
        if not environment:
            return None
        
        # 验证权限
        project = self.db.query(Project).filter(
            Project.id == environment.project_id,
            Project.user_id == user_id
        ).first()
        
        if not project:
            return None
        
        return environment
    
    def get_environments_by_project(
        self,
        project_id: int,
        user_id: int
    ) -> List[TestEnvironment]:
        """
        获取项目的所有测试环境
        
        Args:
            project_id: 项目ID
            user_id: 用户ID
        
        Returns:
            测试环境列表
        """
        # 验证项目权限
        project = self.db.query(Project).filter(
            Project.id == project_id,
            Project.user_id == user_id
        ).first()
        
        if not project:
            return []
        
        environments = self.db.query(TestEnvironment).filter(
            TestEnvironment.project_id == project_id
        ).all()
        
        return environments
    
    def get_default_environment(
        self,
        project_id: int,
        user_id: int
    ) -> Optional[TestEnvironment]:
        """
        获取默认测试环境
        
        Args:
            project_id: 项目ID
            user_id: 用户ID
        
        Returns:
            默认测试环境
        """
        environments = self.get_environments_by_project(project_id, user_id)
        
        for env in environments:
            if env.is_default:
                return env
        
        # 如果没有默认环境，返回第一个
        return environments[0] if environments else None
    
    def build_request_url(
        self,
        environment: TestEnvironment,
        api_path: str
    ) -> str:
        """
        构建完整的请求URL
        
        Args:
            environment: 测试环境
            api_path: API路径
        
        Returns:
            完整URL
        """
        base_url = environment.base_url.rstrip("/")
        api_path = api_path.lstrip("/")
        
        return f"{base_url}/{api_path}" if api_path else base_url
    
    def get_auth_config(
        self,
        environment: TestEnvironment
    ) -> Dict[str, Any]:
        """
        获取环境的认证配置
        
        Args:
            environment: 测试环境
        
        Returns:
            认证配置
        """
        # 从环境的description或其他字段解析认证信息
        # 这里简化处理，实际可能需要更复杂的解析
        
        auth_config = {
            "type": "bearer",  # 默认
            "value": None
        }
        
        # 如果环境有认证信息（可以存储在description或额外的字段中）
        if hasattr(environment, 'auth_config') and environment.auth_config:
            import json
            try:
                auth_config = json.loads(environment.auth_config)
            except:
                pass
        
        return auth_config
    
    def get_environment_config(
        self,
        environment_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """
        获取完整的环境配置（包含URL和认证）
        
        Args:
            environment_id: 环境ID
            user_id: 用户ID
        
        Returns:
            环境配置字典
        """
        environment = self.get_environment(environment_id, user_id)
        
        if not environment:
            return {}
        
        return {
            "id": environment.id,
            "name": environment.name,
            "type": environment.type,
            "base_url": environment.base_url,
            "description": environment.description,
            "is_default": environment.is_default,
            "auth_config": self.get_auth_config(environment)
        }
    
    def validate_environment(
        self,
        environment: TestEnvironment
    ) -> Dict[str, Any]:
        """
        验证环境配置的有效性
        
        Args:
            environment: 测试环境
        
        Returns:
            验证结果
        """
        errors = []
        warnings = []
        
        # 验证base_url格式
        base_url = environment.base_url
        if not base_url:
            errors.append("base_url不能为空")
        elif not (base_url.startswith("http://") or base_url.startswith("https://")):
            warnings.append("base_url应该以http://或https://开头")
        
        # 验证环境类型
        valid_types = ["development", "testing", "staging", "production"]
        if environment.type not in valid_types:
            warnings.append(f"环境类型应该是: {', '.join(valid_types)}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def create_test_code_with_environment(
        self,
        api_interface: Dict[str, Any],
        environment: TestEnvironment,
        extracted_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        生成包含环境配置的测试代码
        
        Args:
            api_interface: API接口信息
            environment: 测试环境
            extracted_data: 提取的数据
        
        Returns:
            Python测试代码
        """
        method = api_interface.get("method", "GET").upper()
        path = api_interface.get("path", "") or api_interface.get("url", "")
        full_url = self.build_request_url(environment, path)
        
        auth_config = self.get_auth_config(environment)
        
        code = f"""import requests

# 环境配置
BASE_URL = "{environment.base_url}"
"""
        
        # 构建请求头
        code += "headers = {\n"
        code += '    "Content-Type": "application/json"\n'
        
        # 添加认证
        if auth_config.get("value") or (extracted_data and extracted_data.get("authToken")):
            token = extracted_data.get("authToken") if extracted_data else auth_config.get("value")
            code += f',    "Authorization": f"Bearer {token}"\n'
        
        code += "}\n\n"
        
        # 构建请求参数
        params = api_interface.get("params", {})
        if params:
            if isinstance(params, str):
                import json
                try:
                    params = json.loads(params)
                except:
                    params = {}
            
            code += f"params = {params}\n\n"
        
        # 构建请求体
        body = api_interface.get("body") or api_interface.get("request_body")
        if body:
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except:
                    pass
            
            code += f"json_data = {body}\n\n"
        
        # 发送请求
        code += f"url = f\"{{BASE_URL}}{path.lstrip('/')}\"\n"
        code += f"response = requests.{method.lower()}(url"
        
        if params:
            code += ", params=params"
        if body and method in ["POST", "PUT", "PATCH"]:
            code += ", json=json_data"
        code += ", headers=headers)\n\n"
        
        code += "print(f\"Status Code: {response.status_code}\")\n"
        code += "print(f\"Response: {response.json()}\")\n"
        
        return code









































