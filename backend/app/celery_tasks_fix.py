from app.celery_app import celery_app
from app.database import SessionLocal

@celery_app.task(bind=True, time_limit=600, soft_time_limit=500)
def fix_test_case_with_deepseek_task(
    self,
    test_case_id: int,
    error_output: str,
    user_suggestion: str = ""
):
    """
    使用DeepSeek修复测试用例代码
    
    Args:
        test_case_id: 测试用例ID
        error_output: 执行错误信息
        user_suggestion: 用户提供的修复建议
    """
    db = SessionLocal()
    test_case = None
    
    try:
        from app.models import TestCase
        import requests
        import re
        
        # 获取测试用例
        test_case = db.query(TestCase).filter(TestCase.id == test_case_id).first()
        if not test_case:
            raise Exception(f"测试用例不存在: {test_case_id}")
        
        if not test_case.test_code:
            raise Exception("测试用例没有测试代码")
        
        # 登录密码
        LOGIN_PASSWORD = "5973ea46bea2afae24c2ce6517fa6f7f"
        
        # 获取当前测试代码
        current_code = test_case.test_code
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 50,
                'message': '正在调用DeepSeek修复代码...'
            }
        )
        
        # 构建修复提示词
        user_suggestion_text = f"\n## 用户修复建议：\n{user_suggestion}\n" if user_suggestion else ""
        
        fix_prompt = f"""请修复以下Python测试代码中的错误。

## 测试用例信息：
- 用例名称: {test_case.name}
- 用例类型: {test_case.case_type}
- 用例描述: {test_case.description or '无'}

## 当前测试代码：
```python
{current_code}
```

## 执行错误信息：
```
{error_output}
```
{user_suggestion_text}
## 要求：
1. 修复代码中的错误，确保测试能够通过
2. 保留登录密码配置：{LOGIN_PASSWORD}
3. 保留所有调试日志（logger.debug）
4. 确保代码结构完整，包含所有必要的导入和类定义
5. 只返回修复后的Python代码，不要包含其他解释性文字
6. {"请参考用户的修复建议。" if user_suggestion else ""}

## 修复后的代码：
```python
"""
        
        # 调用DeepSeek API
        deepseek_api_key = "sk-da6cff2aa0ba4c95b2b62f6693a677b8"
        deepseek_url = "https://api.deepseek.com/v1/chat/completions"
        
        response = requests.post(
            deepseek_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_api_key}"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的Python测试代码修复专家。请根据错误信息修复测试代码，确保代码能够正确执行。"
                    },
                    {
                        "role": "user",
                        "content": fix_prompt
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 4000
            },
            timeout=120
        )
        
        if response.status_code != 200:
            raise Exception(f"DeepSeek API请求失败: {response.status_code} - {response.text}")
        
        result_json = response.json()
        fixed_code = result_json["choices"][0]["message"]["content"]
        
        # 清理生成的代码（移除markdown代码块标记）
        fixed_code = re.sub(r'```python\s*\n?', '', fixed_code)
        fixed_code = re.sub(r'```\s*\n?', '', fixed_code)
        fixed_code = fixed_code.strip()
        
        # 更新测试用例代码
        test_case.test_code = fixed_code
        db.commit()
        
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 100,
                'message': '代码修复完成'
            }
        )
        
        return {
            "status": "success",
            "message": "代码修复完成",
            "test_case_id": test_case_id,
            "fixed_code": fixed_code
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        return {
            "status": "error",
            "message": f"修复失败: {error_msg}",
            "test_case_id": test_case_id
        }
    
    finally:
        db.close()






















