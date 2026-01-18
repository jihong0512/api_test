from typing import Dict, Any, Optional, List
import json
import re


class ResponseExtractor:
    """响应数据提取器：从API响应中提取token、ID等数据"""
    
    def __init__(self):
        self.extraction_patterns = {
            "token": [
                r'"token"\s*:\s*"([^"]+)"',
                r'"access_token"\s*:\s*"([^"]+)"',
                r'"accessToken"\s*:\s*"([^"]+)"',
                r'Bearer\s+([^\s"]+)',
            ],
            "user_id": [
                r'"user_id"\s*:\s*(\d+)',
                r'"userId"\s*:\s*(\d+)',
                r'"id"\s*:\s*(\d+)',
            ],
            "device_id": [
                r'"device_id"\s*:\s*(\d+)',
                r'"deviceId"\s*:\s*(\d+)',
                r'"equipment_id"\s*:\s*(\d+)',
            ],
            "course_id": [
                r'"course_id"\s*:\s*(\d+)',
                r'"courseId"\s*:\s*(\d+)',
            ]
        }
    
    def extract_token(self, response_data: Any, response_schema: Optional[str] = None) -> Optional[str]:
        """从响应中提取token"""
        # 如果提供了schema，优先使用schema定义的路径
        if response_schema:
            token_paths = self._parse_token_paths_from_schema(response_schema)
            for path in token_paths:
                value = self._extract_by_path(response_data, path)
                if value:
                    return str(value)
        
        # 尝试从响应文本中提取
        response_text = self._to_string(response_data)
        
        for pattern in self.extraction_patterns["token"]:
            match = re.search(pattern, response_text)
            if match:
                return match.group(1)
        
        # 尝试从JSON对象中提取
        if isinstance(response_data, dict):
            # 常见路径
            for path in ["token", "access_token", "accessToken", "data.token", "result.token"]:
                value = self._extract_by_path(response_data, path)
                if value:
                    return str(value)
        
        return None
    
    def extract_value(self, response_data: Any, field_name: str, response_schema: Optional[str] = None) -> Optional[Any]:
        """从响应中提取指定字段的值"""
        if field_name in self.extraction_patterns:
            patterns = self.extraction_patterns[field_name]
            response_text = self._to_string(response_data)
            
            for pattern in patterns:
                match = re.search(pattern, response_text)
                if match:
                    return match.group(1)
        
        # 从JSON对象中提取
        if isinstance(response_data, dict):
            # 尝试多种可能的字段名
            field_variants = [
                field_name,
                field_name.replace("_", ""),
                self._camel_case(field_name),
                self._pascal_case(field_name)
            ]
            
            for variant in field_variants:
                if variant in response_data:
                    return response_data[variant]
            
            # 尝试嵌套路径
            for key, value in response_data.items():
                if isinstance(value, dict):
                    nested_value = self.extract_value(value, field_name)
                    if nested_value:
                        return nested_value
        
        return None
    
    def _parse_token_paths_from_schema(self, schema: str) -> List[str]:
        """从响应schema中解析token路径"""
        paths = []
        
        try:
            if isinstance(schema, str):
                schema_obj = json.loads(schema)
            else:
                schema_obj = schema
            
            if isinstance(schema_obj, dict):
                # 查找token相关字段
                def find_token_paths(obj, current_path=""):
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            path = f"{current_path}.{key}" if current_path else key
                            if "token" in key.lower():
                                paths.append(path)
                            find_token_paths(value, path)
                    elif isinstance(obj, list) and obj:
                        find_token_paths(obj[0], current_path)
                
                find_token_paths(schema_obj)
        except:
            pass
        
        return paths if paths else ["token", "access_token", "data.token"]
    
    def _extract_by_path(self, data: Any, path: str) -> Optional[Any]:
        """按路径提取数据"""
        if not path:
            return None
        
        parts = path.split(".")
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
    
    def _to_string(self, data: Any) -> str:
        """将数据转换为字符串"""
        if isinstance(data, str):
            return data
        elif isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False)
        else:
            return str(data)
    
    def _camel_case(self, name: str) -> str:
        """转换为驼峰命名"""
        parts = name.split("_")
        return parts[0].lower() + "".join(word.capitalize() for word in parts[1:])
    
    def _pascal_case(self, name: str) -> str:
        """转换为帕斯卡命名"""
        parts = name.split("_")
        return "".join(word.capitalize() for word in parts)









































