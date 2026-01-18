from typing import List, Dict, Any, Optional
import json
import re

from app.config import settings
from app.services.vector_service import VectorService
from app.services.db_service import DatabaseService
from app.services.reranker_service import RerankerService


class HybridRAGService:
    """混合RAG检索服务，使用ChromaDB + BM25 + 重排序"""
    
    def __init__(self):
        self.vector_service = VectorService()
        self.db_service = DatabaseService()
        self.reranker_service = RerankerService()
    
    async def index_documents(
        self,
        project_id: int,
        documents: List[Dict[str, Any]]
    ):
        """索引文档到向量数据库"""
        if not documents:
            return
        
        chunks = []
        metadata_list = []
        
        for doc in documents:
            text = doc.get("text", doc.get("content", ""))
            if text and text.strip():
                chunks.append(text)
                metadata = doc.get("metadata", {})
                metadata["project_id"] = project_id
                metadata_list.append(metadata)
        
        if chunks:
            # 使用document_id作为project_id的映射
            # 这里简化处理，直接使用project_id作为document_id
            await self.vector_service.add_documents(project_id, chunks, metadata_list)
    
    async def hybrid_search(
        self,
        query: str,
        project_id: int,
        top_k: int = 10,
        use_rerank: bool = True
    ) -> List[Dict[str, Any]]:
        """混合检索：向量检索 + BM25 + 重排序"""
        # 直接使用VectorService的混合检索功能
        results = await self.vector_service.search(query, top_k, use_rerank)
        
        # 转换结果格式以保持接口兼容性
        formatted_results = []
        for r in results:
            formatted_results.append({
                "text": r.get("chunk_text", ""),
                "score": r.get("final_score", r.get("score", 0)),
                "metadata": r.get("metadata", {}),
                "content_type": r.get("content_type", "text"),
                "document_id": r.get("document_id")
            })
        
        return formatted_results
    
    async def graph_rag_search(
        self,
        query: str,
        project_id: int,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """GraphRAG检索：基于知识图谱的检索增强生成"""
        # 1. 从Neo4j知识图谱中检索相关实体和关系
        cypher_query = f"""
        MATCH (n)
        WHERE n.project_id = $project_id
        AND (
            n.name CONTAINS $query
            OR n.description CONTAINS $query
        )
        OPTIONAL MATCH (n)-[r]->(m)
        RETURN n, r, m
        LIMIT {top_k * 2}
        """
        
        try:
            graph_results = self.db_service.query_knowledge_graph(
                cypher_query,
                project_id
            )
        except Exception as e:
            # 如果知识图谱查询失败，返回空结果
            graph_results = []
        
        # 2. 从向量数据库检索相关文档
        vector_results = await self.hybrid_search(query, project_id, top_k)
        
        # 3. 融合图谱和向量检索结果
        # 提取图谱中的关键信息
        graph_context = self._extract_graph_context(graph_results)
        
        # 提取向量检索的关键信息
        vector_context = "\n".join([r["text"] for r in vector_results[:5]])
        
        return {
            "query": query,
            "graph_context": graph_context,
            "vector_context": vector_context,
            "graph_results": graph_results,
            "vector_results": vector_results
        }
    
    def _extract_graph_context(self, graph_results: List[Dict[str, Any]]) -> str:
        """从图谱结果中提取上下文"""
        context_parts = []
        
        for result in graph_results:
            node = result.get("n", {})
            rel = result.get("r", {})
            target = result.get("m", {})
            
            if node:
                node_info = f"实体: {node.get('name', '')}, 类型: {node.get('type', '')}"
                context_parts.append(node_info)
            
            if rel and target:
                rel_info = f"关系: {rel.get('type', '')} -> {target.get('name', '')}"
                context_parts.append(rel_info)
        
        return "\n".join(context_parts)
    
    async def query(
        self,
        query: str,
        project_id: int,
        mode: str = "hybrid",  # hybrid, graph, graph_rag
        top_k: int = 10
    ) -> Dict[str, Any]:
        """统一查询接口"""
        if mode == "hybrid":
            results = await self.hybrid_search(query, project_id, top_k)
            return {"results": results, "mode": "hybrid"}
        
        elif mode == "graph":
            graph_results = self.db_service.query_knowledge_graph(
                f"MATCH (n) WHERE n.project_id = $project_id RETURN n LIMIT {top_k}",
                project_id
            )
            return {"results": graph_results, "mode": "graph"}
        
        elif mode == "graph_rag":
            return await self.graph_rag_search(query, project_id, top_k)
        
        else:
            raise ValueError(f"不支持的查询模式: {mode}")

