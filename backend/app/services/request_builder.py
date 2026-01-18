from typing import Dict, Any, List, Optional
import json
import urllib.parse
from enum import Enum


class ContentType(Enum):
    """Content-Type枚举"""
    JSON = "application/json"
    XML = "application/xml"
    FORM_URLENCODED = "application/x-www-form-urlencoded"
    FORM_DATA = "multipart/form-data"
    TEXT_PLAIN = "text/plain"
    TEXT_HTML = "text/html"


class RequestBuilder:
    """请求构造器：自动生成完整的HTTP请求"""
    
    def __init__(self):
        pass
    
    def build_request(
        self,
        method: str,
        base_url: str,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        content_type: Optional[str] = None,
        auth_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构造完整的HTTP请求
        
        Args:
            method: HTTP方法
            base_url: 基础URL
            path: 路径
            path_params: 路径参数
            query_params: 查询参数
            headers: 请求头
            body: 请求体
            content_type: Content-Type
            auth_config: 认证配置
        
        Returns:
            完整的请求信息
        """
        # 处理路径参数
        full_path = self._process_path_params(path, path_params or {})
        
        # 构建完整URL
        full_url = self._build_url(base_url, full_path, query_params or {})
        
        # 处理Content-Type
        if not content_type:
            content_type = self._detect_content_type(body, headers)
        
        # 处理请求头
        final_headers = self._build_headers(headers or {}, content_type, auth_config)
        
        # 处理请求体
        processed_body = self._process_body(body, content_type)
        
        return {
            "method": method.upper(),
            "url": full_url,
            "path": full_path,
            "base_url": base_url,
            "path_params": path_params or {},
            "query_params": query_params or {},
            "headers": final_headers,
            "body": processed_body,
            "content_type": content_type
        }
    
    def _process_path_params(self, path: str, path_params: Dict[str, Any]) -> str:
        """处理路径参数"""
        result = path
        
        for key, value in path_params.items():
            # 支持 {key} 和 ${key} 格式
            result = result.replace(f"{{{key}}}", str(value))
            result = result.replace(f"${{{key}}}", str(value))
            result = result.replace(f"{{${key}}}", str(value))
        
        return result
    
    def _build_url(self, base_url: str, path: str, query_params: Dict[str, Any]) -> str:
        """构建完整URL"""
        base_url = base_url.rstrip("/")
        path = path.lstrip("/")
        full_url = f"{base_url}/{path}" if path else base_url
        
        if query_params:
            query_string = urllib.parse.urlencode(query_params)
            full_url = f"{full_url}?{query_string}"
        
        return full_url
    
    def _detect_content_type(self, body: Any, headers: Dict[str, Any]) -> str:
        """检测Content-Type"""
        # 从headers中获取
        if headers:
            content_type = headers.get("Content-Type") or headers.get("content-type")
            if content_type:
                return content_type.split(";")[0].strip()
        
        # 根据body类型推断
        if body is None:
            return ContentType.JSON.value
        
        if isinstance(body, str):
            # 尝试解析JSON
            try:
                json.loads(body)
                return ContentType.JSON.value
            except:
                # 检查是否是XML
                if body.strip().startswith("<"):
                    return ContentType.XML.value
                return ContentType.TEXT_PLAIN.value
        
        if isinstance(body, dict):
            return ContentType.JSON.value
        
        return ContentType.JSON.value
    
    def _build_headers(
        self,
        headers: Dict[str, Any],
        content_type: str,
        auth_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """构建请求头"""
        final_headers = headers.copy() if headers else {}
        
        # 设置Content-Type
        if content_type and "Content-Type" not in final_headers:
            final_headers["Content-Type"] = content_type
        
        # 处理认证
        if auth_config:
            auth_headers = self._build_auth_headers(auth_config)
            final_headers.update(auth_headers)
        
        # 设置默认Accept
        if "Accept" not in final_headers:
            final_headers["Accept"] = content_type
        
        return final_headers
    
    def _build_auth_headers(self, auth_config: Dict[str, Any]) -> Dict[str, Any]:
        """构建认证请求头"""
        headers = {}
        
        auth_type = auth_config.get("type", "").lower()
        auth_value = auth_config.get("value")
        
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "basic":
            headers["Authorization"] = f"Basic {auth_value}"
        elif auth_type == "apikey":
            api_key_name = auth_config.get("name", "X-API-Key")
            headers[api_key_name] = auth_value
        elif auth_type == "oauth2":
            token = auth_value or auth_config.get("token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        
        return headers
    
    def _process_body(self, body: Any, content_type: str) -> Any:
        """根据Content-Type处理请求体"""
        if body is None:
            return None
        
        if content_type == ContentType.JSON.value:
            if isinstance(body, str):
                try:
                    return json.loads(body)
                except:
                    return body
            return body
        
        elif content_type == ContentType.FORM_URLENCODED.value:
            if isinstance(body, dict):
                return urllib.parse.urlencode(body)
            return body
        
        elif content_type == ContentType.FORM_DATA.value:
            # Form-data格式需要特殊处理（通常用于文件上传）
            return body
        
        elif content_type == ContentType.XML.value:
            # XML格式保持字符串
            return body if isinstance(body, str) else str(body)
        
        else:
            return body
    
    def generate_request_code(
        self,
        request: Dict[str, Any],
        language: str = "python",
        framework: str = "httprunner"
    ) -> str:
        """
        生成请求代码
        
        Args:
            request: 请求信息
            language: 编程语言（python/javascript）
            framework: 框架（httprunner/requests/axios）
        
        Returns:
            生成的代码
        """
        if language == "python":
            if framework == "httprunner":
                return self._generate_httprunner_code(request)
            elif framework == "requests":
                return self._generate_requests_code(request)
            else:
                return self._generate_requests_code(request)
        elif language == "javascript":
            if framework == "axios":
                return self._generate_axios_code(request)
            else:
                return self._generate_axios_code(request)
        else:
            return self._generate_requests_code(request)
    
    def _generate_httprunner_code(self, request: Dict[str, Any]) -> str:
        """生成HttpRunner格式的代码"""
        method = request["method"].lower()
        url = request["url"]
        headers = request["headers"]
        body = request["body"]
        content_type = request.get("content_type", ContentType.JSON.value)
        
        code = f'RunRequest("test_request")\n'
        code += f'    .{method}("{url}")\n'
        
        # 添加请求头
        if headers:
            code += f'    .with_headers(**{json.dumps(headers, ensure_ascii=False, indent=4)})\n'
        
        # 添加请求体
        if body and request["method"] in ["POST", "PUT", "PATCH"]:
            if content_type == ContentType.JSON.value:
                code += f'    .with_json({json.dumps(body, ensure_ascii=False, indent=4)})\n'
            elif content_type == ContentType.FORM_URLENCODED.value:
                code += f'    .with_data({repr(body)})\n'
            elif content_type == ContentType.XML.value:
                code += f'    .with_data({repr(body)})\n'
        
        return code
    
    def _generate_requests_code(self, request: Dict[str, Any]) -> str:
        """生成requests库格式的代码"""
        method = request["method"].lower()
        url = request["url"]
        headers = request["headers"]
        body = request["body"]
        params = request.get("query_params", {})
        content_type = request.get("content_type", ContentType.JSON.value)
        
        code = "import requests\n\n"
        code += f"url = \"{url}\"\n"
        
        if headers:
            code += f"headers = {json.dumps(headers, ensure_ascii=False, indent=4)}\n"
        else:
            code += "headers = {}\n"
        
        if params:
            code += f"params = {json.dumps(params, ensure_ascii=False, indent=4)}\n"
        else:
            code += "params = {}\n"
        
        # 根据Content-Type设置请求体
        if body and request["method"] in ["POST", "PUT", "PATCH"]:
            if content_type == ContentType.JSON.value:
                code += f"json_data = {json.dumps(body, ensure_ascii=False, indent=4)}\n"
                code += f"response = requests.{method}(url, headers=headers, params=params, json=json_data)\n"
            elif content_type == ContentType.FORM_URLENCODED.value:
                code += f"data = {json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else repr(body)}\n"
                code += f"response = requests.{method}(url, headers=headers, params=params, data=data)\n"
            elif content_type == ContentType.FORM_DATA.value:
                code += f"files = {json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else repr(body)}\n"
                code += f"response = requests.{method}(url, headers=headers, params=params, files=files)\n"
            else:
                code += f"data = {repr(body)}\n"
                code += f"response = requests.{method}(url, headers=headers, params=params, data=data)\n"
        else:
            code += f"response = requests.{method}(url, headers=headers, params=params)\n"
        
        code += "\nprint(response.status_code)\n"
        code += "print(response.json())\n"
        
        return code
    
    def _generate_axios_code(self, request: Dict[str, Any]) -> str:
        """生成axios格式的代码（JavaScript）"""
        method = request["method"].lower()
        url = request["url"]
        headers = request["headers"]
        body = request["body"]
        params = request.get("query_params", {})
        content_type = request.get("content_type", ContentType.JSON.value)
        
        code = "const axios = require('axios');\n\n"
        code += f"const url = \"{url}\";\n"
        
        config = {
            "method": method,
            "url": url
        }
        
        if headers:
            config["headers"] = headers
        
        if params:
            config["params"] = params
        
        # 根据Content-Type设置请求体
        if body and request["method"] in ["POST", "PUT", "PATCH"]:
            if content_type == ContentType.JSON.value:
                config["data"] = body
            elif content_type == ContentType.FORM_URLENCODED.value:
                config["data"] = urllib.parse.urlencode(body) if isinstance(body, dict) else body
                config["headers"]["Content-Type"] = ContentType.FORM_URLENCODED.value
            elif content_type == ContentType.FORM_DATA.value:
                # FormData需要特殊处理
                config["data"] = body
            else:
                config["data"] = body
        
        code += f"const config = {json.dumps(config, ensure_ascii=False, indent=2)};\n\n"
        code += "axios(config)\n"
        code += "    .then(response => {\n"
        code += "        console.log(response.status);\n"
        code += "        console.log(response.data);\n"
        code += "    })\n"
        code += "    .catch(error => {\n"
        code += "        console.error(error);\n"
        code += "    });\n"
        
        return code
    
    def parse_security_schemes(self, openapi_doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        从OpenAPI文档解析securitySchemes
        
        Args:
            openapi_doc: OpenAPI文档（字典格式）
        
        Returns:
            认证配置
        """
        security_schemes = {}
        
        components = openapi_doc.get("components", {})
        schemes = components.get("securitySchemes", {})
        
        for scheme_name, scheme_config in schemes.items():
            scheme_type = scheme_config.get("type", "").lower()
            
            if scheme_type == "http":
                # HTTP Basic或Bearer
                auth_scheme = scheme_config.get("scheme", "bearer").lower()
                security_schemes[scheme_name] = {
                    "type": auth_scheme,
                    "description": scheme_config.get("description", "")
                }
            
            elif scheme_type == "apiKey":
                # API Key认证
                security_schemes[scheme_name] = {
                    "type": "apikey",
                    "name": scheme_config.get("name", "X-API-Key"),
                    "in": scheme_config.get("in", "header"),  # header, query, cookie
                    "description": scheme_config.get("description", "")
                }
            
            elif scheme_type == "oauth2":
                # OAuth2认证
                flows = scheme_config.get("flows", {})
                security_schemes[scheme_name] = {
                    "type": "oauth2",
                    "flows": flows,
                    "description": scheme_config.get("description", "")
                }
            
            elif scheme_type == "openIdConnect":
                # OpenID Connect
                security_schemes[scheme_name] = {
                    "type": "openidconnect",
                    "openIdConnectUrl": scheme_config.get("openIdConnectUrl", ""),
                    "description": scheme_config.get("description", "")
                }
        
        return security_schemes
    
    def apply_security_to_request(
        self,
        request: Dict[str, Any],
        security_schemes: Dict[str, Any],
        scheme_name: Optional[str] = None,
        auth_value: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        将认证配置应用到请求
        
        Args:
            request: 请求信息
            security_schemes: 认证方案字典
            scheme_name: 使用的认证方案名称
            auth_value: 认证值（token、apikey等）
        
        Returns:
            更新后的请求信息
        """
        if not scheme_name or not security_schemes:
            return request
        
        scheme_config = security_schemes.get(scheme_name)
        if not scheme_config:
            return request
        
        scheme_type = scheme_config.get("type", "").lower()
        
        if scheme_type in ["bearer", "basic"]:
            request["headers"]["Authorization"] = f"{scheme_type.capitalize()} {auth_value}"
        
        elif scheme_type == "apikey":
            key_name = scheme_config.get("name", "X-API-Key")
            key_in = scheme_config.get("in", "header")
            
            if key_in == "header":
                request["headers"][key_name] = auth_value
            elif key_in == "query":
                request["query_params"][key_name] = auth_value
        
        elif scheme_type == "oauth2":
            if auth_value:
                request["headers"]["Authorization"] = f"Bearer {auth_value}"
        
        return request









































