"""LLM同步调用辅助工具"""
import asyncio
from app.services.llm_service import LLMService


class LLMServiceSync:
    """同步版本的LLM服务"""
    def __init__(self):
        self.llm_service = LLMService()
    
    def chat(self, prompt: str, temperature: float = 0.3, max_tokens: int = 50) -> str:
        """同步调用LLM"""
        try:
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    return loop.run_until_complete(
                        self.llm_service.chat(prompt, temperature=temperature, max_tokens=max_tokens)
                    )
            except RuntimeError:
                pass
            
            # 如果循环正在运行或无法获取，创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.llm_service.chat(prompt, temperature=temperature, max_tokens=max_tokens)
                )
            finally:
                loop.close()
        except Exception as e:
            print(f"LLM调用失败: {e}")
            return ""

