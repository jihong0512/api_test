from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from rank_bm25 import BM25Okapi
import numpy as np
import redis
import json
import os
import dashscope

from app.config import settings


class VectorService:
    """向量检索服务，支持混合RAG，使用ChromaDB作为向量数据库"""
    
    def __init__(self):
        # 使用通义千问API进行embedding
        self.embedding_model_name = settings.EMBEDDING_MODEL
        self.qwen_api_key = settings.QWEN_API_KEY
        # 设置dashscope API key
        dashscope.api_key = self.qwen_api_key
        self.collection_name = "api_documents"
        self._chroma_connected = False
        # text-embedding-v3的维度是1536
        self.embedding_dim = 1536
        
        # 初始化Redis用于缓存
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True
        )
        
        # ChromaDB 持久化路径
        self.chroma_persist_dir = settings.CHROMA_PERSIST_DIR
    
    def _ensure_chroma_connected(self):
        """确保ChromaDB连接已建立"""
        if not self._chroma_connected:
            try:
                # 创建持久化目录（如果不存在）
                os.makedirs(self.chroma_persist_dir, exist_ok=True)
                
                # 初始化ChromaDB客户端（持久化模式）
                self.chroma_client = chromadb.PersistentClient(
                    path=self.chroma_persist_dir,
                    settings=ChromaSettings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
                
                # 获取或创建集合
                self._init_collection()
                
                self._chroma_connected = True
                print(f"ChromaDB连接成功，数据目录: {self.chroma_persist_dir}")
            except Exception as e:
                print(f"ChromaDB连接失败: {e}")
                import traceback
                traceback.print_exc()
                raise
    
    def _init_collection(self):
        """初始化ChromaDB集合"""
        try:
            # 尝试获取已存在的集合
            self.collection = self.chroma_client.get_collection(
                name=self.collection_name
            )
            print(f"已加载现有集合: {self.collection_name}")
        except Exception:
            # 集合不存在，创建新集合
            self.collection = self.chroma_client.create_collection(
                name=self.collection_name,
                metadata={"description": "API文档向量集合"}
            )
            print(f"已创建新集合: {self.collection_name}")
    
    def embed(self, texts: List[str], use_threading: bool = True) -> List[List[float]]:
        """使用通义千问text-embedding-v3生成文本向量，支持多线程并发"""
        if not texts:
            return []
        
        all_embeddings = []
        
        # 批量处理（API可能有请求大小限制，分批处理）
        batch_size = 10
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
        
        if use_threading and len(batches) > 1:
            # 使用线程池并发处理多个批次
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def embed_batch(batch_texts, batch_idx):
                """处理单个批次的embedding"""
                try:
                    from dashscope import TextEmbedding
                    resp = TextEmbedding.call(
                        model=self.embedding_model_name,
                        input=batch_texts
                    )
                    
                    if resp.status_code == 200:
                        output = resp.get("output", {})
                        embeddings_data = output.get("embeddings", [])
                        if embeddings_data:
                            return (batch_idx, [item.get("embedding", [0.0] * self.embedding_dim) for item in embeddings_data])
                        else:
                            return (batch_idx, [[0.0] * self.embedding_dim] * len(batch_texts))
                    else:
                        print(f"Embedding API调用失败 (批次 {batch_idx}): {resp.status_code}, {resp.message}")
                        return (batch_idx, [[0.0] * self.embedding_dim] * len(batch_texts))
                except Exception as e:
                    print(f"Embedding生成错误 (批次 {batch_idx}): {e}")
                    return (batch_idx, [[0.0] * self.embedding_dim] * len(batch_texts))
            
            # 使用线程池并发处理（最多5个并发）
            max_workers = min(5, len(batches))
            batch_results = {}
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_batch = {
                    executor.submit(embed_batch, batch, idx): idx 
                    for idx, batch in enumerate(batches)
                }
                
                for future in as_completed(future_to_batch):
                    batch_idx, embeddings = future.result()
                    batch_results[batch_idx] = embeddings
            
            # 按顺序合并结果
            for idx in range(len(batches)):
                all_embeddings.extend(batch_results.get(idx, [[0.0] * self.embedding_dim] * len(batches[idx])))
        else:
            # 单线程顺序处理（保持向后兼容）
            for batch_texts in batches:
                try:
                    from dashscope import TextEmbedding
                    resp = TextEmbedding.call(
                        model=self.embedding_model_name,
                        input=batch_texts
                    )
                    
                    if resp.status_code == 200:
                        output = resp.get("output", {})
                        embeddings_data = output.get("embeddings", [])
                        if embeddings_data:
                            batch_embeddings = [item.get("embedding", [0.0] * self.embedding_dim) for item in embeddings_data]
                            all_embeddings.extend(batch_embeddings)
                        else:
                            all_embeddings.extend([[0.0] * self.embedding_dim] * len(batch_texts))
                    else:
                        print(f"Embedding API调用失败: {resp.status_code}, {resp.message}")
                        all_embeddings.extend([[0.0] * self.embedding_dim] * len(batch_texts))
                except Exception as e:
                    print(f"Embedding生成错误: {e}")
                    all_embeddings.extend([[0.0] * self.embedding_dim] * len(batch_texts))
        
        return all_embeddings
    
    async def add_documents(
        self,
        document_id: int,
        chunks: List[str],
        metadata_list: Optional[List[Dict[str, Any]]] = None,
        content_types: Optional[List[str]] = None
    ):
        """添加文档到向量数据库，支持分类存储（使用线程池避免阻塞）"""
        if not chunks:
            return
        
        # 在线程池中执行ChromaDB操作，避免阻塞事件循环
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        def _chroma_operation():
            """在线程中执行的ChromaDB操作"""
            try:
                self._ensure_chroma_connected()
                
                # 生成向量（使用多线程加速）
                vectors = self.embed(chunks, use_threading=True)
                
                # 准备数据
                ids = [f"{document_id}_{i}" for i in range(len(chunks))]
                documents = chunks
                embeddings = vectors
                
                # 准备metadata
                metadatas = []
                for i, meta in enumerate(metadata_list or [{}] * len(chunks)):
                    metadata = {
                        "document_id": str(document_id),
                        "content_type": (content_types or ["text"])[i] if content_types else "text",
                        **meta
                    }
                    # ChromaDB的metadata值必须是字符串、数字或布尔值
                    # 将复杂对象转换为JSON字符串
                    cleaned_metadata = {}
                    for k, v in metadata.items():
                        if isinstance(v, (str, int, float, bool, type(None))):
                            cleaned_metadata[k] = v
                        else:
                            cleaned_metadata[k] = json.dumps(v, ensure_ascii=False)
                    metadatas.append(cleaned_metadata)
                
                # 插入数据到ChromaDB
                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                
                return True
            except Exception as e:
                print(f"ChromaDB操作失败: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # 在线程池中执行，避免阻塞
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            success = await loop.run_in_executor(executor, _chroma_operation)
            if not success:
                raise Exception("ChromaDB存储失败")
    
    async def add_classified_content(
        self,
        document_id: int,
        parsed_data: Dict[str, Any]
    ):
        """添加分类后的内容到向量数据库，按fileid（document_id）组织"""
        chunks = []
        content_types = []
        metadata_list = []
        
        # 基础metadata，包含document_id
        base_metadata = {
            "document_id": document_id,
            "file_type": parsed_data.get("metadata", {}).get("file_type", "unknown")
        }
        
        # 文本内容
        if parsed_data.get("text"):
            for idx, text in enumerate(parsed_data["text"]):
                if text and text.strip():
                    chunks.append(text)
                    content_types.append("text")
                    metadata = {
                        **base_metadata,
                        "source": "text_content",
                        "text_index": idx,
                        "chunk_type": "text"
                    }
                    metadata_list.append(metadata)
        
        # 图片描述
        if parsed_data.get("images"):
            for idx, img_desc in enumerate(parsed_data["images"]):
                if img_desc and img_desc.strip():
                    chunks.append(f"图片内容: {img_desc}")
                    content_types.append("image")
                    metadata = {
                        **base_metadata,
                        "source": "image_description",
                        "image_index": idx,
                        "chunk_type": "image"
                    }
                    metadata_list.append(metadata)
        
        # 表格内容
        if parsed_data.get("tables"):
            for table in parsed_data["tables"]:
                table_text = self._format_table(table)
                if table_text:
                    chunks.append(table_text)
                    content_types.append("table")
                    metadata = {
                        **base_metadata,
                        "source": "table",
                        "table_index": table.get("table_index", 0),
                        "chunk_type": "table",
                        "page": table.get("page"),
                        "sheet_name": table.get("sheet_name")
                    }
                    metadata_list.append(metadata)
        
        # 公式内容
        if parsed_data.get("formulas"):
            for idx, formula in enumerate(parsed_data["formulas"]):
                if formula and formula.strip():
                    chunks.append(f"公式: {formula}")
                    content_types.append("formula")
                    metadata = {
                        **base_metadata,
                        "source": "formula",
                        "formula_index": idx,
                        "chunk_type": "formula"
                    }
                    metadata_list.append(metadata)
        
        if chunks:
            await self.add_documents(document_id, chunks, metadata_list, content_types)
    
    def _format_table(self, table: Dict[str, Any]) -> str:
        """格式化表格为文本"""
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        
        if not headers and not rows:
            return ""
        
        text = "表格内容:\n"
        if headers:
            text += "表头: " + " | ".join(str(h) for h in headers) + "\n"
        
        if rows:
            text += "数据:\n"
            for row in rows:
                text += " | ".join(str(cell) for cell in row) + "\n"
        
        return text
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
        use_rerank: bool = True,
        document_id: Optional[int] = None  # 可选：按fileid过滤
    ) -> List[Dict[str, Any]]:
        """混合检索（向量检索 + BM25 + 重排序）"""
        self._ensure_chroma_connected()
        
        # 1. 向量检索
        query_vector = self.embed([query])[0]
        
        # 构建where条件（如果指定了document_id）
        where = None
        if document_id is not None:
            where = {"document_id": str(document_id)}
        
        # 执行向量搜索
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k * 2,  # 取更多候选用于重排序
            where=where  # 按document_id过滤
        )
        
        vector_results = []
        corpus = []
        
        # 处理结果
        if results and results.get("ids") and len(results["ids"][0]) > 0:
            ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)
            
            for i, doc_id in enumerate(ids):
                metadata = metadatas[i] if i < len(metadatas) else {}
                doc_text = documents[i] if i < len(documents) else ""
                
                # ChromaDB返回的距离是L2距离，转换为相似度分数（距离越小，相似度越高）
                # 使用 1 / (1 + distance) 作为相似度分数
                score = 1.0 / (1.0 + distances[i]) if distances[i] > 0 else 1.0
                
                vector_results.append({
                    "document_id": int(metadata.get("document_id", 0)) if metadata.get("document_id") else None,
                    "chunk_text": doc_text,
                    "content_type": metadata.get("content_type", "text"),
                    "metadata": metadata,
                    "score": score
                })
                corpus.append(doc_text)
        
        # 2. BM25关键词检索（如果向量检索结果不足）
        if len(corpus) > 0:
            tokenized_corpus = [doc.split() for doc in corpus]
            bm25 = BM25Okapi(tokenized_corpus)
            tokenized_query = query.split()
            bm25_scores = bm25.get_scores(tokenized_query)
            
            # 合并BM25分数
            for i, result in enumerate(vector_results[:len(bm25_scores)]):
                result["bm25_score"] = float(bm25_scores[i])
                # 综合分数（可以调整权重）
                result["final_score"] = result["score"] * 0.7 + result.get("bm25_score", 0) * 0.3
        
        # 3. 重排序（使用BGE-Reranker）
        if use_rerank and len(vector_results) > 1:
            from app.services.reranker_service import RerankerService
            reranker = RerankerService()
            texts = [r["chunk_text"] for r in vector_results]
            reranked = reranker.rerank(query, texts)
            
            # 更新排序
            reranked_results = []
            for idx, score in reranked:
                if idx < len(vector_results):
                    result = vector_results[idx]
                    result["rerank_score"] = score
                    reranked_results.append(result)
            
            vector_results = reranked_results
            vector_results.sort(key=lambda x: x.get("rerank_score", x.get("final_score", x["score"])), reverse=True)
        else:
            vector_results.sort(key=lambda x: x.get("final_score", x["score"]), reverse=True)
        
        return vector_results[:top_k]
    
    def delete_documents(self, document_id: int):
        """按fileid（document_id）删除文档的所有向量数据"""
        self._ensure_chroma_connected()
        
        try:
            # 查询所有匹配的文档ID
            results = self.collection.get(
                where={"document_id": str(document_id)}
            )
            
            if results and results.get("ids"):
                # 删除匹配的文档
                self.collection.delete(ids=results["ids"])
                print(f"已从ChromaDB删除fileid={document_id}的所有向量数据（共{len(results['ids'])}条）")
            else:
                print(f"未找到fileid={document_id}的向量数据")
        except Exception as e:
            print(f"删除ChromaDB数据失败: {e}")
            import traceback
            traceback.print_exc()
    
    def delete_interface_from_chromadb(self, project_id: int, interface_id: str):
        """删除指定接口的向量数据（通过project_id和interface_id）"""
        self._ensure_chroma_connected()
        
        try:
            # 查询匹配的接口数据
            results = self.collection.get(
                where={
                    "document_id": str(project_id),
                    "interface_id": str(interface_id)
                }
            )
            
            if results and results.get("ids"):
                # 删除匹配的向量数据
                self.collection.delete(ids=results["ids"])
                print(f"已从ChromaDB删除接口 {interface_id} 的向量数据（共{len(results['ids'])}条）")
                return len(results["ids"])
            else:
                print(f"未找到接口 {interface_id} 的向量数据")
                return 0
        except Exception as e:
            print(f"删除ChromaDB接口数据失败: {e}")
            import traceback
            traceback.print_exc()
            return 0