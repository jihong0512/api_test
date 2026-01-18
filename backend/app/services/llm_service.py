from openai import OpenAI
from typing import List, Dict, Any, Optional
import json
import base64
from pathlib import Path

from app.config import settings


class LLMService:
    """大模型服务，使用DeepSeek-VL"""
    
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL
        )
        self.model = settings.DEEPSEEK_MODEL
        self.vision_model = "deepseek-chat"  # DeepSeek-VL视觉模型
    
    async def chat(
        self,
        prompt: str,
        messages: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """调用大模型进行对话"""
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"LLM调用失败: {str(e)}")
    
    async def extract_structured_data(
        self,
        text: str,
        schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """从文本中提取结构化数据"""
        prompt = f"""
请从以下文本中提取结构化数据，输出JSON格式，符合以下schema：
{json.dumps(schema, ensure_ascii=False, indent=2)}

文本内容：
{text}

请输出JSON格式的数据：
"""
        result = await self.chat(prompt)
        try:
            return json.loads(result)
        except:
            return {}
    
    async def generate_test_case(
        self,
        api_info: Dict[str, Any],
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成测试用例"""
        prompt = f"""
基于以下API接口信息，生成测试用例：

接口信息：
{json.dumps(api_info, ensure_ascii=False, indent=2)}

{"上下文信息：" + context if context else ""}

请生成以下格式的测试用例：
{{
    "name": "测试用例名称",
    "description": "测试用例描述",
    "test_data": {{
        "params": {{}},
        "headers": {{}},
        "body": {{}}
    }},
    "assertions": [
        {{"type": "status_code", "expected": 200}},
        {{"type": "response_time", "expected": 1000}},
        {{"type": "contains", "field": "data", "value": ""}}
    ]
}}

请输出JSON格式：
"""
        result = await self.chat(prompt, temperature=0.5)
        try:
            return json.loads(result)
        except:
            return {}
    
    async def analyze_error(
        self,
        error_message: str,
        request_data: Dict[str, Any],
        response_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """分析测试失败原因"""
        prompt = f"""
测试执行失败，请分析失败原因并提供建议：

错误信息：{error_message}
请求数据：{json.dumps(request_data, ensure_ascii=False, indent=2)}
{"响应数据：" + json.dumps(response_data, ensure_ascii=False, indent=2) if response_data else ""}

请输出以下格式的分析结果：
{{
    "error_type": "错误类型",
    "root_cause": "根本原因分析",
    "suggestions": ["建议1", "建议2"],
    "fix_method": "修复方法"
}}

请输出JSON格式：
"""
        result = await self.chat(prompt, temperature=0.3)
        try:
            return json.loads(result)
        except:
            return {}
    
    def _encode_image(self, image_path: str) -> str:
        """将图片编码为base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    async def vision_parse(
        self,
        image_paths: List[str],
        prompt: str
    ) -> str:
        """使用视觉模型解析图片内容"""
        try:
            messages = [{"role": "user", "content": []}]
            
            # 添加文本提示
            messages[0]["content"].append({
                "type": "text",
                "text": prompt
            })
            
            # 添加图片
            for image_path in image_paths:
                base64_image = self._encode_image(image_path)
                messages[0]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                })
            
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=messages,
                max_tokens=4000
            )
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"视觉模型调用失败: {str(e)}")
    
    async def parse_visual_document(
        self,
        image_paths: List[str],
        document_type: str = "pdf"
    ) -> Dict[str, Any]:
        """解析视觉文档（PDF、Word等）"""
        prompt = f"""
请分析以下{document_type}文档截图，提取其中的API接口信息。

请识别并提取以下信息：
1. 接口名称
2. HTTP方法（GET/POST/PUT/DELETE等）
3. 接口URL/路径
4. 请求参数（查询参数、路径参数、请求体）
5. 请求头
6. 响应格式
7. 接口描述

请以JSON格式输出，格式如下：
{{
    "interfaces": [
        {{
            "name": "接口名称",
            "method": "GET",
            "url": "/api/example",
            "headers": {{}},
            "params": {{}},
            "body": {{}},
            "description": "接口描述",
            "response_schema": {{}}
        }}
    ]
}}

请仔细分析图片中的内容，确保提取的信息准确完整。
"""
        result = await self.vision_parse(image_paths, prompt)
        try:
            # 尝试从结果中提取JSON
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(result)
        except:
            return {"interfaces": [], "raw_text": result}


