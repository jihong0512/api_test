from typing import List, Tuple, Optional
import numpy as np
import dashscope

from app.config import settings


class RerankerService:
    """重排序服务，使用通义千问qwen3-rerank API"""
    
    def __init__(self):
        self.qwen_api_key = settings.QWEN_API_KEY
        self.reranker_model = settings.RERANKER_MODEL
        # 设置dashscope API key
        dashscope.api_key = self.qwen_api_key
    
    def rerank(
        self,
        query: str,
        texts: List[str],
        top_k: Optional[int] = None
    ) -> List[Tuple[int, float]]:
        """使用通义千问qwen3-rerank API对检索结果进行重排序"""
        if not texts:
            return []
        
        try:
            from dashscope import TextReRank
            
            # 调用rerank API
            resp = TextReRank.call(
                model=self.reranker_model,
                query=query,
                documents=texts
            )
            
            if resp.status_code == 200:
                # 解析响应
                output = resp.get("output", {})
                results_data = output.get("results", [])
                if results_data:
                    # 格式: [{"index": 0, "relevance_score": 0.95}, ...]
                    reranked = [(item["index"], item["relevance_score"]) for item in results_data]
                    
                    # 按分数降序排序（通常API已经排序，但为了安全再排序一次）
                    reranked.sort(key=lambda x: x[1], reverse=True)
                    
                    if top_k:
                        reranked = reranked[:top_k]
                    
                    return reranked
                else:
                    print(f"Rerank API响应中未找到results: {output}")
                    # 返回原始顺序
                    return [(i, 1.0) for i in range(len(texts))]
            else:
                print(f"Rerank API调用失败: {resp.status_code}, {resp.message}")
                # 返回原始顺序
                return [(i, 1.0) for i in range(len(texts))]
        except Exception as e:
            print(f"重排序失败: {e}")
            import traceback
            traceback.print_exc()
            # 返回原始顺序
            return [(i, 1.0) for i in range(len(texts))]

