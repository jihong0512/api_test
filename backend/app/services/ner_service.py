from typing import List, Dict, Any, Optional, Tuple
import re
import json
import asyncio
from sqlalchemy import text

try:
    from pyhanlp import HanLP
    HANLP_AVAILABLE = True
except ImportError:
    HANLP_AVAILABLE = False
    print("提示: pyhanlp未安装，将使用LLM进行NER功能")

# 尝试导入LLM服务作为备用
try:
    from app.services.llm_service import LLMService
    from app.services.llm_sync_helper import LLMServiceSync
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    print("警告: LLM服务不可用，NER功能将受限")


class NERService:
    """命名实体识别和关系抽取服务（优先使用HanLP，备用LLM）"""
    
    def __init__(self):
        self.use_llm = False
        if HANLP_AVAILABLE:
            try:
                self.hanlp = HanLP
                self.available = True
            except Exception as e:
                print(f"HanLP初始化失败: {e}")
                self.available = False
        else:
            self.available = False
        
        # 如果没有HanLP，尝试使用LLM
        if not self.available and LLM_AVAILABLE:
            try:
                self.llm_service_sync = LLMServiceSync()
                self.available = True
                self.use_llm = True
                print("NER服务: 使用LLM进行实体识别")
            except Exception as e:
                print(f"LLM服务初始化失败: {e}")
                self.available = False
        
        if not self.available:
            print("警告: NER功能不可用，实体识别将返回空结果")
    
    def extract_text_from_table_data(self, table_data: List[Dict[str, Any]]) -> List[str]:
        """从表数据中提取文本内容"""
        texts = []
        
        for row in table_data:
            for key, value in row.items():
                if value is None:
                    continue
                
                # 转换为字符串
                value_str = str(value)
                
                # 过滤掉纯数字、日期等非文本内容
                if self._is_textual_content(value_str):
                    texts.append(value_str)
        
        return texts
    
    def _is_textual_content(self, text: str) -> bool:
        """判断是否为文本内容"""
        if not text or len(text.strip()) < 2:
            return False
        
        # 纯数字
        if text.strip().isdigit():
            return False
        
        # 日期格式（简单判断）
        date_pattern = r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}'
        if re.match(date_pattern, text.strip()):
            return False
        
        # 包含中文或英文的文本
        if re.search(r'[\u4e00-\u9fa5]|[a-zA-Z]', text):
            return True
        
        return False
    
    def segment_and_ner(self, text: str) -> Dict[str, Any]:
        """分词和命名实体识别"""
        if not self.available:
            return {
                "segments": [],
                "entities": [],
                "error": "NER服务未初始化"
            }
        
        # 使用LLM进行NER
        if self.use_llm:
            return self._ner_with_llm(text)
        
        # 使用HanLP进行NER
        try:
            # 分词
            segments = self.hanlp.segment(text)
            segment_list = [str(term.word) for term in segments]
            
            # 命名实体识别
            ner_result = self.hanlp.newSegment().enableNameRecognize().enableOrganizationRecognize().enablePlaceRecognize()
            entities = []
            
            # 使用NER提取实体
            for term in segments:
                word = str(term.word)
                nature = str(term.nature)
                
                # 识别实体类型
                entity_type = self._get_entity_type(nature, word)
                if entity_type:
                    entities.append({
                        "text": word,
                        "type": entity_type,
                        "position": text.find(word) if word in text else -1
                    })
            
            return {
                "segments": segment_list,
                "entities": entities,
                "original_text": text
            }
        except Exception as e:
            # HanLP失败，尝试使用LLM备用
            if LLM_AVAILABLE:
                return self._ner_with_llm(text)
            return {
                "segments": [],
                "entities": [],
                "error": str(e)
            }
    
    def _ner_with_llm(self, text: str) -> Dict[str, Any]:
        """使用LLM进行命名实体识别"""
        try:
            prompt = f"""请从以下文本中识别命名实体，并以JSON格式返回结果。

文本内容：
{text}

请识别以下类型的实体：
- Person: 人名
- Location: 地名
- Organization: 机构名
- Time: 时间
- Product: 产品名
- Brand: 品牌名
- SportsEntity: 运动相关实体（如设备、课程、计划等）
- Number: 数字实体（如果需要保留）

返回格式（JSON）：
{{
    "entities": [
        {{
            "text": "实体文本",
            "type": "实体类型",
            "position": 位置索引
        }}
    ],
    "segments": ["分词1", "分词2", ...]
}}

只返回JSON，不要其他说明。"""
            
            response = self.llm_service_sync.chat(prompt, temperature=0.3, max_tokens=1000)
            
            # 尝试解析JSON响应
            try:
                # 提取JSON部分（去除可能的markdown格式）
                if '```json' in response:
                    response = response.split('```json')[1].split('```')[0].strip()
                elif '```' in response:
                    response = response.split('```')[1].split('```')[0].strip()
                
                result = json.loads(response)
                
                # 确保格式正确
                entities = result.get('entities', [])
                segments = result.get('segments', [])
                
                # 如果没有segments，使用简单的分词
                if not segments:
                    segments = re.findall(r'\w+|[^\w\s]', text)
                
                # 补充position信息
                for entity in entities:
                    if 'position' not in entity:
                        pos = text.find(entity.get('text', ''))
                        entity['position'] = pos if pos >= 0 else -1
                
                return {
                    "segments": segments,
                    "entities": entities,
                    "original_text": text,
                    "method": "LLM"
                }
            except json.JSONDecodeError:
                # JSON解析失败，使用简单的规则提取
                return self._simple_ner_extraction(text)
        except Exception as e:
            print(f"LLM NER失败: {e}")
            return self._simple_ner_extraction(text)
    
    def _simple_ner_extraction(self, text: str) -> Dict[str, Any]:
        """简单的基于规则的NER提取（备用方案）"""
        entities = []
        segments = re.findall(r'\w+|[^\w\s]', text)
        
        # 简单的实体识别规则
        # 识别可能的人名、地名等（基于常见模式）
        words = text.split()
        for word in words:
            entity_type = None
            # 简单规则：长度大于1的中文词汇可能是实体
            if len(word) >= 2 and re.search(r'[\u4e00-\u9fa5]', word):
                # 可能是产品名、设备名等
                if any(kw in word for kw in ['设备', '手环', '手表', 'APP', '课程', '计划']):
                    entity_type = "SportsEntity"
                elif any(kw in word for kw in ['北京', '上海', '广州', '深圳']):
                    entity_type = "Location"
                elif any(kw in word for kw in ['公司', '集团', '企业']):
                    entity_type = "Organization"
            
            if entity_type:
                entities.append({
                    "text": word,
                    "type": entity_type,
                    "position": text.find(word)
                })
        
        return {
            "segments": segments,
            "entities": entities,
            "original_text": text,
            "method": "Rule-based"
        }
    
    def _get_entity_type(self, nature: str, word: str) -> Optional[str]:
        """根据词性判断实体类型"""
        nature_lower = nature.lower()
        word_lower = word.lower()
        
        # 人名
        if 'nr' in nature_lower or 'person' in nature_lower:
            return "Person"
        
        # 地名
        if 'ns' in nature_lower or 'place' in nature_lower:
            return "Location"
        
        # 机构名
        if 'nt' in nature_lower or 'organization' in nature_lower:
            return "Organization"
        
        # 时间
        if 't' in nature_lower or 'time' in nature_lower:
            return "Time"
        
        # 数字
        if 'm' in nature_lower or 'number' in nature_lower:
            return "Number"
        
        # 专有名词（运动相关）
        sports_keywords = ['跑步', '走步', '划船', '哑铃', '跳绳', '单车', '课程', '计划', 
                          '设备', '手环', '手表', 'APP', '遥控器', '固件', '版本']
        if any(keyword in word for keyword in sports_keywords):
            return "SportsEntity"
        
        # 产品/品牌名
        brand_keywords = ['小金', '小米', '华为', '苹果', 'Google', 'Apple']
        if any(keyword in word for keyword in brand_keywords):
            return "Brand"
        
        return None
    
    def extract_relationships(self, text: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从文本中抽取实体关系"""
        relationships = []
        
        if not entities or len(entities) < 2:
            return relationships
        
        # 基于规则的关系统计和抽取
        relationship_patterns = [
            (r'(\w+)拥有(\w+)', 'owns'),
            (r'(\w+)绑定(\w+)', 'binds_to'),
            (r'(\w+)连接(\w+)', 'connects_to'),
            (r'(\w+)关联(\w+)', 'associates_with'),
            (r'(\w+)创建(\w+)', 'creates'),
            (r'(\w+)使用(\w+)', 'uses'),
            (r'(\w+)控制(\w+)', 'controls'),
            (r'(\w+)包含(\w+)', 'contains'),
            (r'(\w+)属于(\w+)', 'belongs_to'),
            (r'(\w+)生成(\w+)', 'generates'),
            (r'(\w+)分享(\w+)', 'shares_with'),
            (r'(\w+)管理(\w+)', 'manages'),
            (r'(\w+)参与(\w+)', 'participates_in'),
        ]
        
        # 从文本中抽取关系
        for pattern, rel_type in relationship_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                source_entity = match.group(1)
                target_entity = match.group(2)
                
                # 检查实体是否在NER结果中
                source_found = any(e['text'] == source_entity for e in entities)
                target_found = any(e['text'] == target_entity for e in entities)
                
                if source_found or target_found:
                    relationships.append({
                        "source": source_entity,
                        "target": target_entity,
                        "type": rel_type,
                        "context": match.group(0),
                        "confidence": 0.7
                    })
        
        # 基于实体共现抽取关系（实体在同一句话中出现）
        sentences = re.split(r'[。！？\n]', text)
        for sentence in sentences:
            sentence_entities = [e for e in entities if e['text'] in sentence]
            if len(sentence_entities) >= 2:
                for i, source_entity in enumerate(sentence_entities):
                    for target_entity in sentence_entities[i+1:]:
                        # 推断关系类型
                        rel_type = self._infer_relationship_type(
                            source_entity, target_entity, sentence
                        )
                        if rel_type:
                            relationships.append({
                                "source": source_entity['text'],
                                "target": target_entity['text'],
                                "type": rel_type,
                                "context": sentence,
                                "confidence": 0.6
                            })
        
        return relationships
    
    def _infer_relationship_type(
        self,
        source_entity: Dict[str, Any],
        target_entity: Dict[str, Any],
        context: str
    ) -> Optional[str]:
        """推断实体之间的关系类型"""
        source_type = source_entity.get('type', '')
        target_type = target_entity.get('type', '')
        source_text = source_entity.get('text', '')
        target_text = target_entity.get('text', '')
        
        context_lower = context.lower()
        
        # 基于实体类型和上下文推断
        type_combination = (source_type, target_type)
        
        # 用户相关关系
        if 'Person' in source_type or '用户' in source_text:
            if '设备' in target_text or 'Device' in target_type:
                if '绑定' in context or 'bind' in context_lower:
                    return 'binds_to'
                if '拥有' in context or 'own' in context_lower:
                    return 'owns'
            
            if '记录' in target_text or '数据' in target_text:
                return 'owns'
            
            if '计划' in target_text or '课程' in target_text:
                if '创建' in context:
                    return 'creates'
                if '使用' in context:
                    return 'uses'
        
        # 设备相关关系
        if '设备' in source_text or 'Device' in source_type:
            if '手环' in target_text or '手表' in target_text or 'APP' in target_text:
                return 'associates_with'
            
            if '属性' in target_text or '版本' in target_text:
                return 'has_attribute'
        
        # APP相关关系
        if 'APP' in source_text or 'app' in context_lower:
            if '设备' in target_text:
                if '连接' in context:
                    return 'connects_to'
                if '控制' in context:
                    return 'controls'
        
        # 数据相关关系
        if '数据' in source_text or '记录' in source_text:
            if '第三方' in target_text or '服务' in target_text:
                return 'shares_with'
            
            if '计划' in target_text:
                return 'generates'
        
        return None
    
    def process_table_data(
        self,
        table_name: str,
        table_data: List[Dict[str, Any]],
        max_texts: int = 100
    ) -> Dict[str, Any]:
        """处理表数据，提取实体和关系"""
        if not self.available:
            return {
                "table_name": table_name,
                "entities": [],
                "relationships": [],
                "error": "HanLP未初始化"
            }
        
        # 提取文本
        texts = self.extract_text_from_table_data(table_data)
        texts = texts[:max_texts]  # 限制处理数量
        
        all_entities = []
        all_relationships = []
        entity_dict = {}  # 用于去重
        
        # 处理每个文本
        for text in texts:
            # 分词和NER
            ner_result = self.segment_and_ner(text)
            
            if 'error' in ner_result:
                continue
            
            entities = ner_result.get('entities', [])
            
            # 合并实体（去重）
            for entity in entities:
                entity_key = f"{entity['text']}_{entity['type']}"
                if entity_key not in entity_dict:
                    entity_dict[entity_key] = entity
                    all_entities.append(entity)
            
            # 抽取关系
            relationships = self.extract_relationships(text, entities)
            all_relationships.extend(relationships)
        
        return {
            "table_name": table_name,
            "entities": all_entities,
            "relationships": all_relationships,
            "total_texts_processed": len(texts)
        }


class KnowledgeGraphEnricher:
    """知识图谱丰富服务：将NER结果整合到知识图谱"""
    
    def __init__(self, db_service, metadata_service):
        self.db_service = db_service
        self.metadata_service = metadata_service
        self.ner_service = NERService()
    
    def enrich_from_table_data(
        self,
        engine,
        table_name: str,
        limit: int = 100,
        project_id: int = 1
    ) -> Dict[str, Any]:
        """从表数据中丰富知识图谱"""
        # 采样数据
        table_data = self.db_service.sample_data(engine, table_name, limit)
        
        if not table_data:
            return {
                "table_name": table_name,
                "entities": [],
                "relationships": [],
                "message": "表中没有数据"
            }
        
        # NER处理
        ner_result = self.ner_service.process_table_data(table_name, table_data, max_texts=100)
        
        # 构建实体和关系到Neo4j
        if ner_result.get('entities') or ner_result.get('relationships'):
            self._add_to_neo4j(
                table_name,
                ner_result.get('entities', []),
                ner_result.get('relationships', []),
                project_id
            )
        
        return ner_result
    
    def _add_to_neo4j(
        self,
        table_name: str,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        project_id: int
    ):
        """将实体和关系添加到Neo4j"""
        try:
            with self.db_service.neo4j_driver.session() as session:
                # 添加实体节点
                for entity in entities:
                    entity_text = entity.get('text', '')
                    entity_type = entity.get('type', 'Unknown')
                    
                    if not entity_text:
                        continue
                    
                    # 创建或更新实体节点
                    session.run("""
                        MERGE (e:Entity {
                            name: $name,
                            project_id: $project_id,
                            source_table: $source_table
                        })
                        SET e.type = $type,
                            e.updated_at = timestamp()
                    """,
                        name=entity_text,
                        project_id=project_id,
                        source_table=table_name,
                        type=entity_type
                    )
                    
                    # 建立实体与表的关联
                    session.run("""
                        MATCH (t:Table {name: $table_name, project_id: $project_id})
                        MATCH (e:Entity {name: $entity_name, project_id: $project_id})
                        MERGE (t)-[:CONTAINS_ENTITY]->(e)
                    """,
                        table_name=table_name,
                        project_id=project_id,
                        entity_name=entity_text
                    )
                
                # 添加关系
                for rel in relationships:
                    source = rel.get('source', '')
                    target = rel.get('target', '')
                    rel_type = rel.get('type', 'RELATED_TO')
                    
                    if not source or not target:
                        continue
                    
                    # 创建关系（如果实体存在）
                    # 动态构建关系类型（避免SQL注入）
                    rel_type_upper = rel_type.upper().replace(' ', '_')
                    safe_rel_types = [
                        'OWNS', 'BINDS_TO', 'CONNECTS_TO', 'ASSOCIATES_WITH', 'CONTROLS',
                        'CREATES', 'USES', 'CONTAINS', 'BELONGS_TO', 'GENERATES',
                        'SHARES_WITH', 'MANAGES', 'PARTICIPATES_IN', 'RELATED_TO'
                    ]
                    
                    if rel_type_upper not in safe_rel_types:
                        rel_type_upper = 'RELATED_TO'
                    
                    session.run(f"""
                        MATCH (e1:Entity {{
                            name: $source,
                            project_id: $project_id
                        }})
                        MATCH (e2:Entity {{
                            name: $target,
                            project_id: $project_id
                        }})
                        MERGE (e1)-[r:{rel_type_upper} {{
                            context: $context,
                            confidence: $confidence,
                            source: 'NER'
                        }}]->(e2)
                    """,
                        source=source,
                        target=target,
                        project_id=project_id,
                        context=rel.get('context', ''),
                        confidence=rel.get('confidence', 0.5)
                    )
        except Exception as e:
            print(f"添加实体和关系到Neo4j失败: {e}")
    
    def generate_cypher_for_entities(
        self,
        table_name: str,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        project_id: int
    ) -> str:
        """生成实体和关系的Cypher语句"""
        cypher_lines = [
            f"// 表 {table_name} 的实体和关系（通过NER抽取）",
            f"// 项目ID: {project_id}",
            ""
        ]
        
        # 创建实体节点
        cypher_lines.append("// 创建实体节点")
        for entity in entities:
            entity_text = entity.get('text', '').replace("'", "\\'")
            entity_type = entity.get('type', 'Unknown')
            
            if entity_text:
                cypher_lines.append(
                    f"MERGE (e:Entity {{name: '{entity_text}', project_id: {project_id}, "
                    f"source_table: '{table_name}', type: '{entity_type}'}});"
                )
        
        cypher_lines.append("")
        
        # 创建表与实体的关联
        cypher_lines.append("// 表与实体的关联")
        for entity in entities:
            entity_text = entity.get('text', '').replace("'", "\\'")
            if entity_text:
                # 使用双引号避免f-string内的单引号冲突
                table_name_escaped = table_name.replace("'", "\\'")
                entity_text_escaped = entity_text.replace("'", "\\'")
                cypher_lines.append(
                    f"MATCH (t:Table {{name: '{table_name_escaped}', project_id: {project_id}}})\n"
                    f"MATCH (e:Entity {{name: '{entity_text_escaped}', project_id: {project_id}}})\n"
                    f"MERGE (t)-[:CONTAINS_ENTITY]->(e);"
                )
        
        cypher_lines.append("")
        
        # 创建实体关系
        cypher_lines.append("// 实体之间的关系")
        for rel in relationships:
            source = rel.get('source', '').replace("'", "\\'")
            target = rel.get('target', '').replace("'", "\\'")
            rel_type = rel.get('type', 'RELATED_TO').upper()
            context = rel.get('context', '').replace("'", "\\'")
            confidence = rel.get('confidence', 0.5)
            
            if source and target:
                cypher_lines.append(
                    f"MATCH (e1:Entity {{name: '{source}', project_id: {project_id}}})\n"
                    f"MATCH (e2:Entity {{name: '{target}', project_id: {project_id}}})\n"
                    f"MERGE (e1)-[:{rel_type} {{context: '{context}', confidence: {confidence}, source: 'NER'}}]->(e2);"
                )
        
        return "\n".join(cypher_lines)

