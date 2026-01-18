from typing import List, Dict, Any, Optional
import re
import asyncio

from app.services.llm_service import LLMService
from app.services.llm_sync_helper import LLMServiceSync


class RelationshipAnalyzer:
    """关系分析器：基于业务语义分析表关系"""
    
    def __init__(self):
        self.llm_service = LLMService()
        
        # 业务实体类型映射
        self.entity_types = {
            "用户": ["user", "用户", "member", "成员"],
            "群组": ["group", "群组", "team", "团队", "family", "家庭"],
            "设备": ["device", "设备", "equipment", "equipment", "设备"],
            "运动设备": ["treadmill", "跑步机", "walking", "走步机", "rower", "划船机", 
                        "dumbbell", "哑铃", "rope", "跳绳", "bike", "单车", "动感单车"],
            "手环": ["band", "手环", "bracelet"],
            "手表": ["watch", "手表", "applewatch"],
            "APP": ["app", "application", "应用"],
            "遥控器": ["remote", "遥控器", "controller"],
            "课程": ["course", "课程", "training"],
            "计划": ["plan", "计划", "program", "程序"],
            "记录": ["record", "记录", "log", "日志"],
            "数据": ["data", "数据"],
            "活动": ["activity", "活动", "event", "事件"],
            "属性": ["attribute", "属性", "property", "配置", "config"],
            "版本": ["version", "版本", "firmware", "固件"],
            "模式": ["mode", "模式", "program", "程序模式"],
        }
        
        # 关系模式定义
        self.relationship_patterns = {
            "is_a": {
                "keywords": ["admin", "super", "vip", "premium", "高级", "管理员"],
                "description": "继承关系"
            },
            "has_a": {
                "keywords": ["item", "detail", "info", "profile", "项", "详情", "信息"],
                "description": "包含关系"
            },
            "belongs_to": {
                "source": ["user", "用户", "member", "成员"],
                "target": ["group", "群组", "team", "team", "family", "家庭"],
                "description": "属于关系"
            },
            "contains": {
                "source": ["group", "群组", "team", "team", "family", "家庭"],
                "target": ["user", "用户", "member", "成员"],
                "description": "包含关系"
            },
            "binds_to": {
                "source": ["user", "用户"],
                "target": ["device", "设备", "email", "邮箱", "phone", "手机", "account", "账号",
                          "band", "手环", "watch", "wechat", "微信", "weibo", "微博"],
                "description": "绑定关系"
            },
            "owns": {
                "source": ["user", "用户"],
                "target": ["record", "记录", "data", "数据", "plan", "计划", "health", "健康数据"],
                "description": "拥有关系"
            },
            "associates_with": {
                "pairs": [
                    (["device", "设备"], ["band", "手环"]),
                    (["device", "设备"], ["watch", "手表"]),
                    (["device", "设备"], ["app", "应用"]),
                    (["device", "设备"], ["remote", "遥控器"]),
                ],
                "description": "关联关系"
            },
            "connects_to": {
                "source": ["app", "应用", "remote", "遥控器"],
                "target": ["device", "设备"],
                "description": "连接关系"
            },
            "controls": {
                "source": ["app", "应用", "remote", "遥控器"],
                "target": ["device", "设备"],
                "description": "控制关系"
            },
            "creates": {
                "source": ["user", "用户"],
                "target": ["plan", "计划", "activity", "活动", "program", "程序"],
                "description": "创建关系"
            },
            "uses": {
                "source": ["user", "用户"],
                "target": ["course", "课程", "plan", "计划", "program", "程序"],
                "description": "使用关系"
            },
            "collects": {
                "source": ["user", "用户"],
                "target": ["course", "课程", "收藏"],
                "description": "收藏关系"
            },
            "generates": {
                "source": ["record", "记录"],
                "target": ["plan", "计划"],
                "description": "生成关系"
            },
            "participates_in": {
                "source": ["user", "用户"],
                "target": ["activity", "活动", "event", "事件"],
                "description": "参与关系"
            },
            "manages": {
                "source": ["user", "用户"],
                "target": ["family", "家庭", "group", "群组"],
                "description": "管理关系"
            },
            "has_attribute": {
                "source": ["device", "设备"],
                "target": ["attribute", "属性", "property", "配置"],
                "description": "有属性"
            },
            "has_version": {
                "source": ["device", "设备"],
                "target": ["version", "版本", "firmware", "固件"],
                "description": "有版本"
            },
            "supports": {
                "source": ["device", "设备"],
                "target": ["mode", "模式", "program", "程序模式"],
                "description": "支持"
            },
            "upgrades": {
                "source": ["user", "用户"],
                "target": ["firmware", "固件", "version", "版本"],
                "description": "升级关系"
            },
            "shares_with": {
                "source": ["data", "数据", "record", "记录"],
                "target": ["third", "第三方", "fit", "health", "健康", "google", "huawei", "华为"],
                "description": "共享关系"
            }
        }
    
    def analyze_comprehensive_relationships(
        self,
        source_table: str,
        target_table: str,
        source_columns: List[str],
        target_columns: List[str],
        foreign_key_info: Dict[str, Any],
        schema_info: Dict[str, Any],
        business_context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """综合分析所有可能的关系"""
        relationships = []
        
        source_lower = source_table.lower()
        target_lower = target_table.lower()
        source_entity = self._identify_entity_type(source_table)
        target_entity = self._identify_entity_type(target_table)
        
        # 1. 基础关系（has_a, is_a, depend_on）
        base_rel = self._analyze_base_relationship(
            source_table, target_table, foreign_key_info
        )
        if base_rel:
            relationships.append(base_rel)
        
        # 2. 业务关系（基于实体类型）
        business_rels = self._analyze_business_relationships(
            source_entity, target_entity, source_table, target_table,
            source_columns, target_columns, foreign_key_info
        )
        relationships.extend(business_rels)
        
        # 3. 属性关系
        attr_rels = self._analyze_attribute_relationships(
            source_table, target_table, source_columns, target_columns
        )
        relationships.extend(attr_rels)
        
        # 4. 使用LLM进行深度分析
        llm_rels = self._analyze_with_llm(
            source_table, target_table, source_entity, target_entity,
            source_columns, target_columns, foreign_key_info, business_context
        )
        relationships.extend(llm_rels)
        
        return relationships
    
    def _identify_entity_type(self, table_name: str) -> str:
        """识别表的实体类型"""
        table_lower = table_name.lower()
        
        for entity_type, keywords in self.entity_types.items():
            if any(keyword in table_lower for keyword in keywords):
                return entity_type
        
        return "未知"
    
    def _analyze_base_relationship(
        self,
        source: str,
        target: str,
        foreign_key_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """分析基础关系"""
        source_lower = source.lower()
        target_lower = target.lower()
        
        # is_a关系
        if source_lower in target_lower or target_lower in source_lower:
            if any(keyword in target_lower for keyword in ['admin', 'super', 'vip', 'premium']):
                return {
                    "type": "is_a",
                    "description": f"{source}是{target}的一种类型",
                    "confidence": 0.8
                }
        
        # has_a关系
        if source_lower in target_lower:
            return {
                "type": "has_a",
                "description": f"{source}包含{target}",
                "confidence": 0.7
            }
        
        # depend_on关系（通过外键）
        if foreign_key_info:
            return {
                "type": "depend_on",
                "description": f"{source}依赖{target}",
                "confidence": 0.9
            }
        
        return None
    
    def _analyze_business_relationships(
        self,
        source_entity: str,
        target_entity: str,
        source_table: str,
        target_table: str,
        source_columns: List[str],
        target_columns: List[str],
        foreign_key_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """分析业务关系"""
        relationships = []
        
        # 根据实体类型匹配关系模式
        for rel_type, pattern in self.relationship_patterns.items():
            if rel_type in ["is_a", "has_a", "depend_on"]:
                continue  # 已在基础关系中处理
            
            # 检查source和target匹配
            if "source" in pattern and "target" in pattern:
                source_match = any(kw in source_entity.lower() or kw in source_table.lower() 
                                  for kw in pattern["source"])
                target_match = any(kw in target_entity.lower() or kw in target_table.lower() 
                                 for kw in pattern["target"])
                
                if source_match and target_match:
                    relationships.append({
                        "type": rel_type,
                        "description": pattern["description"] + f": {source_table} {rel_type} {target_table}",
                        "confidence": 0.8
                    })
            
            # 检查pairs模式（双向关系）
            if "pairs" in pattern:
                for pair in pattern["pairs"]:
                    source_keywords, target_keywords = pair
                    source_match = any(kw in source_table.lower() for kw in source_keywords)
                    target_match = any(kw in target_table.lower() for kw in target_keywords)
                    
                    if source_match and target_match:
                        relationships.append({
                            "type": rel_type,
                            "description": pattern["description"] + f": {source_table} {rel_type} {target_table}",
                            "confidence": 0.8
                        })
        
        return relationships
    
    def _analyze_attribute_relationships(
        self,
        source: str,
        target: str,
        source_columns: List[str],
        target_columns: List[str]
    ) -> List[Dict[str, Any]]:
        """分析属性关系"""
        relationships = []
        
        source_lower = source.lower()
        target_lower = target.lower()
        
        # 设备有属性
        if any(kw in source_lower for kw in ["device", "设备"]) and \
           any(kw in target_lower for kw in ["attribute", "属性", "property", "配置"]):
            relationships.append({
                "type": "has_attribute",
                "description": f"{source}具有属性{target}",
                "confidence": 0.9
            })
        
        # 设备有版本
        if any(kw in source_lower for kw in ["device", "设备"]) and \
           any(kw in target_lower for kw in ["version", "版本", "firmware", "固件"]):
            relationships.append({
                "type": "has_version",
                "description": f"{source}有版本信息{target}",
                "confidence": 0.9
            })
        
        # 用户有属性（profile、info等）
        if any(kw in source_lower for kw in ["user", "用户"]) and \
           any(kw in target_lower for kw in ["profile", "profile", "info", "信息"]):
            relationships.append({
                "type": "has_a",
                "description": f"{source}包含{target}信息",
                "confidence": 0.8
            })
        
        return relationships
    
    def _analyze_with_llm(
        self,
        source_table: str,
        target_table: str,
        source_entity: str,
        target_entity: str,
        source_columns: List[str],
        target_columns: List[str],
        foreign_key_info: Dict[str, Any],
        business_context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """使用LLM深度分析关系"""
        try:
            # 构建业务上下文提示
            context_part = ""
            if business_context:
                context_part = f"\n{business_context}\n"
            else:
                context_part = "\n请根据表名和字段名推断业务语义。\n"
            
            prompt = f"""
请分析以下两个数据库表之间的关系。{context_part}

源表：{source_table}（实体类型：{source_entity}）
源表字段：{', '.join(source_columns[:15])}

目标表：{target_table}（实体类型：{target_entity}）
目标表字段：{', '.join(target_columns[:15])}

外键信息：{foreign_key_info}

请根据以上信息和业务上下文，判断这两个表之间的所有可能关系类型（可以是多个）。输出JSON数组格式，每个关系包含：
- type: 关系类型（从has_a, is_a, belongs_to, contains, upload,update,delete, binds_to, owns, associates_with, connects_to, controls, shares_with, creates, uses, collects, generates, participates_in,play, manages, has_attribute, has_version, supports, upgrades, depend_on中选择）
- description: 关系描述
- confidence: 置信度(0-1)

只输出JSON数组，不要其他文字：
"""
            
            result = self.llm_service.chat(prompt, temperature=0.3, max_tokens=1000)
            
            if not result:
                return []
            
            # 解析JSON结果
            import json
            # 清理结果
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                try:
                    relationships = json.loads(json_match.group())
                    return relationships if isinstance(relationships, list) else []
                except:
                    pass
        except Exception as e:
            print(f"LLM关系分析失败: {e}")
        
        return []

