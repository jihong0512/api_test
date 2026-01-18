"""
接口分组和依赖链服务
1. 按照30个分组规则对接口进行分组
2. 如果没有匹配的分组规则，按照接口名称、接口path的相似度分组
3. 构建依赖链：登录接口 -> 创建 -> 修改 -> 查询 -> 删除
4. 生成Cypher文件并存储到Neo4j、ChromaDB和Redis
"""
from typing import List, Dict, Any, Optional, Tuple
import json
import re
from collections import defaultdict
from sqlalchemy.orm import Session
from difflib import SequenceMatcher
from datetime import datetime
import os

from app.config import settings
from app.services.db_service import DatabaseService
from app.services.vector_service import VectorService
from app.models import DocumentAPIInterface
import redis

# Redis连接
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    encoding='utf-8'
)


class InterfaceGroupingService:
    """接口分组和依赖链服务"""
    
    # 32个分组规则（关键词映射，严格按照用户提供的分组列表）
    GROUPING_RULES = {
        'phone_login': {
            'keywords': [
                '手机注册', '忘记密码', '验证用户登录密码是否正确', '查询用户是否在白名单中', '绑定手机号', 
                '校验验证码', '验证码登录', '手机密码登录', '修改密码', '刷新token', '用手机号码注册账号', 
                '用手机验证码登录', '获取手机验证码', '用手机号和密码登录', '查询手机号是否已经注册账号', 
                '忘记登录密码', '校验验证码', '手机用户名密码登录'
            ],
            'name': '手机号登录相关的接口'
        },
        'email': {
            'keywords': [
                'kschair发送邮件', '邮箱注册', '邮箱登录', '发送邮箱验证码', '验证邮箱验证码是否正确', 
                '更改绑定邮箱', '重置app端的邮箱账号密码', '绑定邮箱', '注册邮箱登录app的账号', 
                '注销账号', '检查邮箱是否已经注册app账号', '获取验证码', '注销账号', '校验密码'
            ],
            'name': '邮箱相关的接口'
        },
        'weibo': {
            'keywords': ['绑定微博账号', '微博账号绑定手机号'],
            'name': '微博相关的接口'
        },
        'personal': {
            'keywords': [
                '删除体重', '获取体重', '保险验证', '运动杂谈', '文章分页', '设置新手引导', '获取新手引导', 
                '记录语言', '更新语言包', '获取语言包', '设置用户标签', '查看用户信息', '获取用户当天待领取的积分', 
                '本周积分', '获取用户总积分', '获取用户七天打卡进度', '获取用户积分任务列表', '获取积分收支明细列表', 
                '领取新手大礼包', '设置打卡提醒开关', '获取用户打卡提醒设置', '获取用户是否领取新手大礼包', 
                '获取单条标签记录', '获取用户设置的标签列表', '获取标签简要列表', '获取训练指导标签列表', 
                '获取动作标签列表筛选项', '缓存用户运动总距离百分比等分至多', '缓存用户的设备类型', '获取用户年报', 
                '设置用户头像', '获取是否首次对app评分', '提交问卷', '获取问卷详情', '获取问卷配置', 
                '查询用户问卷提交状态', '领取活动奖品', '编辑个人资料', '获取个人资料', '意见反馈', '体重记录', '体重图表'
            ],
            'name': '个人相关的接口'
        },
        'sport_record': {
            'keywords': [
                '上传运动记录', '查看运动记录详情', '蓝牙跑步机上传运动记录', '体脂称记录数据', 
                '上传运动记录的pointlist', '获取运动记录的pointlist', '获取全部运动记录', '上传运动记录', 
                '删除运动记录', '共享运动记录列表', '共享运动记录点数据详情', '微信硬件ID上报运动数据', '分配记录'
            ],
            'name': '运动记录相关的接口'
        },
        'target_sport': {
            'keywords': [
                '获取目标运动列表', '获取指定设备类型的目标运动列表', '获取目标运动详情', '获取跑步记录详情'
            ],
            'name': '目标运动相关的接口'
        },
        'device': {
            'keywords': [
                '绑定设备', '获取设备名', '获取设备token', '查询设备是否绑定成功', '绑定did', '解绑did', 
                '获取设备盒子', '设备列表', '上报wifi设备列表', '获取设备列表', '查看设备的销售地区'
            ],
            'name': '设备相关的接口'
        },
        'program': {
            'keywords': [
                '创建程序', '编辑程序', '删除程序', '获取程序列表', '设置按键', '获取按键', '获取程序详情'
            ],
            'name': '程序相关的接口'
        },
        'product': {
            'keywords': [
                '商品列表', '商品详情', '添加收货地址', '获取收货地址列表', '修改收货地址', '获取收货地址详情', 
                '删除收货地址', '支付宝支付回调', '获取订单'
            ],
            'name': '商品相关的接口'
        },
        'course': {
            'keywords': [
                '课程库', '用户课程详情', '获取课程详情', '添加课程', '删除课程', '评价课程', '课程埋点', 
                '获取课程列表', '获取课程详情', '开始课程', '完成课程', '课程评价', '获取完成课程次数', 
                '获取最近在练的课程', '删除最近在练的课程', '添加课程收藏', '取消课程收藏', '获取课程收藏列表', 
                '获取训练指导视频列表', '全局搜索课程', '获取课程榜单列表', '获取个性化推荐课程', 
                '获取课程动作列表', '获取课程动作详情', '获取课程榜单列表', '获取课程动作下的视频', 
                '获取课程筛选项标签列表', '课程音乐列表', '查询精选课程动作列表'
            ],
            'name': '课程相关的接口'
        },
        'product_info': {
            'keywords': [
                '获取产品列表', '获取产品详情', '获取连接说明', '获取产品列表以及产品百科', '获取产品的指导视频'
            ],
            'name': '产品相关的接口'
        },
        'heart_rate': {
            'keywords': ['心率数据上报', '获取心率数据统计'],
            'name': '心率相关的接口'
        },
        'family': {
            'keywords': [
                '获取家庭每日详情', '获取家庭活动列表', '删除家庭活动', '修改家庭活动', '查看家庭活动详情', 
                '退出家庭活动', '获取家庭活动勋章列表', '加入家庭', '删除子成员', '获取已删除的子成员', 
                '共享设备成员列表', '共享设备设备列表', '共享设备修改状态', '创建家庭', '编辑家庭', 
                '获取家庭列表', '获取家庭详情', '获取家庭成员列表', '获取家庭成员详情', '设置家庭成员备注', 
                '退出家庭', '删除家庭成员', '批量添加家庭设备', '删除家庭设备', '获取家庭设备列表', 
                '邀请人展示邀请码', '被邀请人扫码', '邀请人展示链接', '发送加入家庭邀请', 
                '家庭邀请根据邮箱搜索用户', '家庭邀请根据手机号搜索用户', '接受加入家庭邀请', 
                '拒绝加入家庭邀请', '撤销加入家庭邀请', '家庭活动更改设备名称', '上报家庭阿里云identityid', 
                '获取家庭用户阿里云identityid', '添加成员', '编辑成员', '成员列表', '设置子用户头像', '获取子成员信息'
            ],
            'name': '家庭活动相关的接口'
        },
        'xiaodu': {
            'keywords': [
                '小度发现设备', '小度打开设备', '小度速度快一点', '小度设置自动模式', '小度查询运动信息', 
                '小度查询速度', '小度上报属性', '小度查询设备属性'
            ],
            'name': '小度相关的接口'
        },
        'plan': {
            'keywords': [
                '报名训练计划', '获取当前训练计划', '取消训练计划', '计划请假', '结束计划', '删除计划', 
                '获取计划详情', '上传计划内容开始运动记录', '上传运动计划结束运动记录', '上传运动计划内容', 
                '删除计划内容运动记录', '获取指定日期的运动计划和运动记录', '获取指定日期区间的运动目标', 
                '计划请假预览', '获取运动计划关联的运动记录', '计划定时通知提醒', '添加自定义计划', 
                '修改自定义计划', '获取指定日期区间的运动计划内容', '获取推荐计划列表', 
                '获取个性化推荐的计划列表', '获取推荐计划详情', '生成推荐计划', '删除推荐计划', 
                '获取定制计划', '获取定制计划详情', '生成用户定制计划', '删除定制计划', '课程加入日期', 
                '调整课程日程训练日', '删除课程日程', '删除此课程日程以及后续安排', '获取用户定制计划状态', 
                '获取定制计划标签列表', '本周计划', '完成计划'
            ],
            'name': '计划相关的接口'
        },
        'after_sale': {
            'keywords': ['批量创建售后单', '创建售后单', '查询售后单map数据'],
            'name': '售后相关单接口'
        },
        'message': {
            'keywords': [
                '获取消息红点', '获取消息列表', '置顶某类消息', '取消置顶某类消息', '删除用户某条消息', 
                '删除用户某类消息', '获取用户一级消息列表', '获取用户二级消息列表'
            ],
            'name': '消息相关的接口'
        },
        'ad': {
            'keywords': ['开屏广告接口', '获取广告列表', '获取首页广告轮播图', '查看首页广告轮播图详情'],
            'name': '广告相关的接口'
        },
        'activity': {
            'keywords': [
                '运动页活动列表', '获取活动列表', '活动列表', '获取首页活动列表', '查询两周燃脂活动状态', 
                '更新两周燃脂活动排行榜', '查询两周燃脂排行榜信息'
            ],
            'name': '活动相关的接口'
        },
        'firmware': {
            'keywords': [
                '固件升级', '固件fireware升级', '确认固件升级', '获取最近的蓝牙模组固件', '获取下控固件'
            ],
            'name': '固件相关的接口'
        },
        'oauth': {
            'keywords': ['oauth_code', 'oauth_token', 'Oauth refresh token', 'Oauth userinfo', 'Oauth getscope'],
            'name': 'oauth相关的接口'
        },
        'ranking': {
            'keywords': ['获取排行榜榜单'],
            'name': '排行榜相关的接口'
        },
        'dumbbell': {
            'keywords': [
                '获取哑铃课程列表', '获取哑铃课程详情', '开始哑铃课程', '上传哑铃运动记录', '获取哑铃运动记录'
            ],
            'name': '哑铃相关的接口'
        },
        'bike': {
            'keywords': [
                '获取单车活动列表', '开始单车课程', '完成单车课程', '完成单车课程打卡数'
            ],
            'name': '单车相关的接口'
        },
        'ai': {
            'keywords': [
                '获取AI 剩余生成次数和积分', '生成AI运动计划', '生成AI运动建议', 'openai翻译', 
                '把AI生成的数据融合到课程列表中'
            ],
            'name': 'AI相关的接口'
        },
        'wechat': {
            'keywords': ['微信登录', '微信绑定', '微信解绑', '微信登录绑定手机号'],
            'name': '微信相关的接口'
        },
        'xiaomi': {
            'keywords': ['解绑小米账号', '小米账号获取token', '小米账号刷新token', '绑定小米账号'],
            'name': '小米相关的接口'
        },
        'vivo': {
            'keywords': ['vivo 登录', 'vivo 绑定手机号'],
            'name': 'vivo相关的接口'
        },
        'qrcode': {
            'keywords': ['二维码登录手机扫描', '二维码登录-电视轮训'],
            'name': '二维码相关的接口'
        },
        'app': {
            'keywords': ['应用内评分', 'App检查类型', 'app检查升级v2'],
            'name': 'app相关的接口'
        },
        'google': {
            'keywords': ['谷歌登录', '绑定谷歌账号', '解绑谷歌账号'],
            'name': '谷歌相关的接口'
        }
    }
    
    # 登录接口标识
    LOGIN_INTERFACE = {
        "url": "https://test-xj.kingsmith.com.cn/V0.1/index.php",
        "service": "user.login"
    }
    
    # CRUD操作关键词
    CREATE_KEYWORDS = ['增加', '创建', '新建', 'add', '新增', '添加', '注册', '报名', '加入', '绑定']
    UPDATE_KEYWORDS = ['修改', '编辑', 'change', '更改', '更新', '设置', '重置', '调整']
    READ_KEYWORDS = ['查询', '获取', 'get', '查看', '列表', '详情', '搜索', '检查', '验证', '校验']
    DELETE_KEYWORDS = ['删除', '去掉', '消除', 'del', '取消', '解绑', '退出', '注销']
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.db_service = DatabaseService()
        self.vector_service = VectorService()
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度（0-1）"""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    def _match_interface_to_group(self, interface: Dict[str, Any]) -> Optional[str]:
        """将接口匹配到分组规则"""
        name = (interface.get('name', '') or '').lower()
        description = (interface.get('description', '') or '').lower()
        path = (interface.get('path', '') or interface.get('url', '') or '').lower()
        service = (interface.get('service', '') or '').lower()
        
        full_text = f"{name} {description} {path} {service}"
        
        # 遍历所有分组规则
        for group_id, group_info in self.GROUPING_RULES.items():
            keywords = group_info['keywords']
            for keyword in keywords:
                if keyword.lower() in full_text:
                    return group_id
        
        return None
    
    def _calculate_interface_similarity(self, interface1: Dict[str, Any], interface2: Dict[str, Any]) -> float:
        """计算两个接口的相似度（基于名称、path、描述）"""
        name1 = (interface1.get('name', '') or '').lower()
        name2 = (interface2.get('name', '') or '').lower()
        path1 = (interface1.get('path', '') or interface1.get('url', '') or '').lower()
        path2 = (interface2.get('path', '') or interface2.get('url', '') or '').lower()
        desc1 = (interface1.get('description', '') or '').lower()
        desc2 = (interface2.get('description', '') or '').lower()
        
        name_sim = self._calculate_text_similarity(name1, name2)
        path_sim = self._calculate_text_similarity(path1, path2)
        desc_sim = self._calculate_text_similarity(desc1, desc2)
        
        # 名称权重0.5，path权重0.3，描述权重0.2
        similarity = (name_sim * 0.5 + path_sim * 0.3 + desc_sim * 0.2)
        
        return similarity
    
    def _extract_crud_type(self, interface: Dict[str, Any]) -> str:
        """提取接口的CRUD类型"""
        name = (interface.get('name', '') or '').lower()
        description = (interface.get('description', '') or '').lower()
        path = (interface.get('path', '') or interface.get('url', '') or '').lower()
        method = (interface.get('method', '') or '').upper()
        
        full_text = f"{name} {description} {path}"
        
        # 检查创建操作
        if any(keyword in full_text for keyword in self.CREATE_KEYWORDS):
            return 'CREATE'
        
        # 检查更新操作
        if any(keyword in full_text for keyword in self.UPDATE_KEYWORDS):
            return 'UPDATE'
        
        # 检查删除操作
        if any(keyword in full_text for keyword in self.DELETE_KEYWORDS):
            return 'DELETE'
        
        # 检查查询操作
        if any(keyword in full_text for keyword in self.READ_KEYWORDS):
            return 'READ'
        
        # 根据HTTP方法推断
        if method == 'POST':
            return 'CREATE'
        elif method == 'PUT' or method == 'PATCH':
            return 'UPDATE'
        elif method == 'DELETE':
            return 'DELETE'
        else:
            return 'READ'
    
    def _is_login_interface(self, interface: Dict[str, Any]) -> bool:
        """判断是否是登录接口"""
        url = interface.get('url', '') or ''
        service = interface.get('service', '') or ''
        
        # 检查URL和service是否匹配登录接口
        if self.LOGIN_INTERFACE['service'].lower() in service.lower():
            return True
        
        if 'login' in service.lower() or '登录' in (interface.get('name', '') or '').lower():
            return True
        
        return False
    
    def group_interfaces(self, interfaces: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """对接口进行分组"""
        groups = defaultdict(list)
        ungrouped = []
        
        # 第一遍：按照分组规则匹配
        for interface in interfaces:
            group_id = self._match_interface_to_group(interface)
            if group_id:
                groups[group_id].append(interface)
            else:
                ungrouped.append(interface)
        
        # 第二遍：对未分组的接口按照相似度分组
        if ungrouped:
            similarity_groups = []
            for interface in ungrouped:
                matched = False
                for group in similarity_groups:
                    # 检查与组内第一个接口的相似度
                    if self._calculate_interface_similarity(interface, group[0]) >= 0.6:
                        group.append(interface)
                        matched = True
                        break
                
                if not matched:
                    similarity_groups.append([interface])
            
            # 将相似度分组添加到groups中
            for idx, group in enumerate(similarity_groups):
                group_id = f'similarity_group_{idx}'
                groups[group_id] = group
        
        return dict(groups)
    
    def build_dependency_chains(self, interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建依赖链：登录接口 -> 创建 -> 修改 -> 查询 -> 删除"""
        # 分离登录接口和业务接口
        login_interfaces = []
        business_interfaces = []
        
        for interface in interfaces:
            if self._is_login_interface(interface):
                login_interfaces.append(interface)
            else:
                business_interfaces.append(interface)
        
        chains = []
        
        # 如果没有登录接口，创建一个虚拟的登录接口节点
        if not login_interfaces:
            login_node = {
                'id': '__LOGIN_INTERFACE__',
                'name': '用户登录',
                'url': self.LOGIN_INTERFACE['url'],
                'service': self.LOGIN_INTERFACE['service'],
                'method': 'POST',
                'type': 'LOGIN'
            }
        else:
            login_node = login_interfaces[0]
            login_node['type'] = 'LOGIN'
        
        # 对业务接口按CRUD类型分组
        crud_groups = defaultdict(list)
        for interface in business_interfaces:
            crud_type = self._extract_crud_type(interface)
            interface['crud_type'] = crud_type
            crud_groups[crud_type].append(interface)
        
        # 按照CRUD顺序构建链：CREATE -> UPDATE -> READ -> DELETE
        ordered_interfaces = []
        for crud_type in ['CREATE', 'UPDATE', 'READ', 'DELETE']:
            ordered_interfaces.extend(crud_groups[crud_type])
        
        # 构建依赖链
        chain = {
            'nodes': [login_node] + ordered_interfaces,
            'edges': []
        }
        
        # 创建边：从登录接口到第一个业务接口
        if ordered_interfaces:
            chain['edges'].append({
                'source': login_node.get('id', str(login_node.get('id', '__LOGIN_INTERFACE__'))),
                'target': ordered_interfaces[0].get('id', str(ordered_interfaces[0].get('id', ''))),
                'type': 'DEPENDS_ON',
                'description': '登录后执行'
            })
        
        # 创建边：业务接口之间的依赖关系
        for i in range(len(ordered_interfaces) - 1):
            chain['edges'].append({
                'source': ordered_interfaces[i].get('id', str(ordered_interfaces[i].get('id', ''))),
                'target': ordered_interfaces[i + 1].get('id', str(ordered_interfaces[i + 1].get('id', ''))),
                'type': 'DEPENDS_ON',
                'description': f"{ordered_interfaces[i].get('crud_type', '')} -> {ordered_interfaces[i + 1].get('crud_type', '')}"
            })
        
        chains.append(chain)
        
        return chains
    
    def generate_cypher(self, groups: Dict[str, List[Dict[str, Any]]], chains: List[Dict[str, Any]], project_id: int) -> str:
        """生成Cypher查询语句"""
        cypher_lines = [
            f"// 接口分组和依赖链Cypher文件",
            f"// 项目ID: {project_id}",
            f"// 生成时间: {datetime.now().isoformat()}",
            ""
        ]
        
        # 创建接口节点
        cypher_lines.append("// 创建接口节点")
        all_interfaces = []
        for group_id, interfaces in groups.items():
            for interface in interfaces:
                if interface not in all_interfaces:
                    all_interfaces.append(interface)
        
        for interface in all_interfaces:
            interface_id = str(interface.get('id', ''))
            name = interface.get('name', '').replace("'", "\\'")
            url = interface.get('url', '').replace("'", "\\'")
            method = interface.get('method', 'GET')
            service = interface.get('service', '').replace("'", "\\'")
            description = (interface.get('description', '') or '').replace("'", "\\'")
            
            cypher_lines.append(
                f"MERGE (i:APIInterface {{id: '{interface_id}', project_id: {project_id}}})\n"
                f"SET i.name = '{name}',\n"
                f"    i.url = '{url}',\n"
                f"    i.method = '{method}',\n"
                f"    i.service = '{service}',\n"
                f"    i.description = '{description}',\n"
                f"    i.crud_type = '{interface.get('crud_type', '')}',\n"
                f"    i.type = '{interface.get('type', '')}';"
            )
        
        cypher_lines.append("")
        
        # 创建分组节点和关系
        cypher_lines.append("// 创建分组节点和关系")
        for group_id, interfaces in groups.items():
            group_name = self.GROUPING_RULES.get(group_id, {}).get('name', f'分组_{group_id}')
            group_name_escaped = group_name.replace("'", "\\'")
            
            cypher_lines.append(
                f"MERGE (g:InterfaceGroup {{id: '{group_id}', project_id: {project_id}}})\n"
                f"SET g.name = '{group_name_escaped}';"
            )
            
            for interface in interfaces:
                interface_id = str(interface.get('id', ''))
                cypher_lines.append(
                    f"MATCH (i:APIInterface {{id: '{interface_id}', project_id: {project_id}}})\n"
                    f"MATCH (g:InterfaceGroup {{id: '{group_id}', project_id: {project_id}}})\n"
                    f"MERGE (g)-[:CONTAINS]->(i);"
                )
        
        cypher_lines.append("")
        
        # 创建依赖链关系
        cypher_lines.append("// 创建依赖链关系")
        for chain in chains:
            for edge in chain.get('edges', []):
                source_id = str(edge['source']).replace("'", "\\'")
                target_id = str(edge['target']).replace("'", "\\'")
                edge_type = edge.get('type', 'DEPENDS_ON')
                description = edge.get('description', '').replace("'", "\\'")
                
                # 如果是登录接口，需要特殊处理
                if source_id == '__LOGIN_INTERFACE__':
                    cypher_lines.append(
                        f"MERGE (login:LoginInterface {{id: '{source_id}', project_id: {project_id}}})\n"
                        f"SET login.name = '用户登录',\n"
                        f"    login.url = '{self.LOGIN_INTERFACE['url']}',\n"
                        f"    login.service = '{self.LOGIN_INTERFACE['service']}';"
                    )
                    cypher_lines.append(
                        f"MATCH (login:LoginInterface {{id: '{source_id}', project_id: {project_id}}})\n"
                        f"MATCH (target:APIInterface {{id: '{target_id}', project_id: {project_id}}})\n"
                        f"MERGE (login)-[r:{edge_type}]->(target)\n"
                        f"SET r.description = '{description}';"
                    )
                else:
                    cypher_lines.append(
                        f"MATCH (source:APIInterface {{id: '{source_id}', project_id: {project_id}}})\n"
                        f"MATCH (target:APIInterface {{id: '{target_id}', project_id: {project_id}}})\n"
                        f"MERGE (source)-[r:{edge_type}]->(target)\n"
                        f"SET r.description = '{description}';"
                    )
        
        return "\n".join(cypher_lines)
    
    def store_to_neo4j(self, cypher_content: str, project_id: int):
        """将Cypher内容存储到Neo4j"""
        try:
            with self.db_service._get_neo4j_session() as session:
                # 执行Cypher语句
                statements = cypher_content.split(';')
                for statement in statements:
                    statement = statement.strip()
                    if statement and not statement.startswith('//'):
                        try:
                            session.run(statement)
                        except Exception as e:
                            print(f"执行Cypher语句失败: {e}")
                            print(f"语句: {statement[:200]}...")
        except Exception as e:
            print(f"Neo4j存储失败: {e}")
    
    def store_to_redis(self, groups: Dict[str, List[Dict[str, Any]]], chains: List[Dict[str, Any]], project_id: int):
        """将分组和依赖链数据存储到Redis"""
        try:
            # 存储分组数据
            groups_key = f"interface_groups:{project_id}"
            groups_data = {}
            for group_id, interfaces in groups.items():
                groups_data[group_id] = {
                    'name': self.GROUPING_RULES.get(group_id, {}).get('name', f'分组_{group_id}'),
                    'interfaces': [{'id': str(iface.get('id', '')), 'name': iface.get('name', '')} for iface in interfaces]
                }
            redis_client.setex(groups_key, 86400 * 7, json.dumps(groups_data, ensure_ascii=False))
            
            # 存储依赖链数据
            chains_key = f"interface_chains:{project_id}"
            chains_data = []
            for chain in chains:
                chains_data.append({
                    'nodes': [{'id': str(node.get('id', '')), 'name': node.get('name', '')} for node in chain.get('nodes', [])],
                    'edges': chain.get('edges', [])
                })
            redis_client.setex(chains_key, 86400 * 7, json.dumps(chains_data, ensure_ascii=False))
            
            print(f"已存储接口分组和依赖链数据到Redis (project_id: {project_id})")
        except Exception as e:
            print(f"Redis存储失败: {e}")
    
    async def store_to_chromadb(self, interfaces: List[Dict[str, Any]], groups: Dict[str, List[Dict[str, Any]]], project_id: int):
        """将接口数据存储到ChromaDB"""
        try:
            chunks = []
            metadata_list = []
            
            for interface in interfaces:
                interface_id = str(interface.get('id', ''))
                name = interface.get('name', '')
                method = interface.get('method', 'GET')
                path = interface.get('path', '') or interface.get('url', '')
                description = interface.get('description', '')
                
                # 构建接口的文本描述
                interface_text = f"""
接口名称: {name}
请求方法: {method}
接口路径: {path}
接口描述: {description}
                """.strip()
                
                chunks.append(interface_text)
                
                # 查找接口所属的分组
                group_id = None
                for gid, group_interfaces in groups.items():
                    if interface in group_interfaces:
                        group_id = gid
                        break
                
                metadata = {
                    'type': 'api_interface',
                    'project_id': project_id,
                    'interface_id': interface_id,
                    'name': name,
                    'method': method,
                    'path': path,
                    'group_id': group_id or 'ungrouped'
                }
                metadata_list.append(metadata)
            
            if chunks:
                await self.vector_service.add_documents(project_id, chunks, metadata_list)
                print(f"已存储 {len(chunks)} 个接口到ChromaDB (project_id: {project_id})")
        except Exception as e:
            print(f"ChromaDB存储失败: {e}")
    
    def save_cypher_file(self, cypher_content: str, project_id: int) -> str:
        """保存Cypher文件到本地"""
        try:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cypher_dir = os.path.join(backend_dir, "cypher_files")
            os.makedirs(cypher_dir, exist_ok=True)
            
            filename = f"interface_groups_chains_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.cypher"
            filepath = os.path.join(cypher_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cypher_content)
            
            print(f"Cypher文件已保存: {filepath}")
            return filepath
        except Exception as e:
            print(f"保存Cypher文件失败: {e}")
            return ""
    
    async def process_interfaces(
        self,
        project_id: int,
        interfaces: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """处理接口分组和依赖链构建的主方法"""
        # 如果没有提供接口列表，从数据库获取
        if interfaces is None:
            db_interfaces = self.db.query(DocumentAPIInterface).filter(
                DocumentAPIInterface.project_id == project_id
            ).all()
            
            interfaces = []
            for iface in db_interfaces:
                try:
                    interface_dict = {
                        'id': iface.id,
                        'name': iface.name,
                        'method': iface.method,
                        'url': iface.url,
                        'path': iface.path,
                        'service': iface.service,
                        'description': iface.description,
                        'version': iface.version
                    }
                    interfaces.append(interface_dict)
                except Exception as e:
                    print(f"解析接口 {iface.id} 失败: {e}")
                    continue
        
        # 1. 接口分组
        groups = self.group_interfaces(interfaces)
        
        # 2. 构建依赖链（对每个分组构建依赖链）
        all_chains = []
        for group_id, group_interfaces in groups.items():
            chains = self.build_dependency_chains(group_interfaces)
            all_chains.extend(chains)
        
        # 3. 生成Cypher文件
        cypher_content = self.generate_cypher(groups, all_chains, project_id)
        
        # 4. 存储到Neo4j
        try:
            self.store_to_neo4j(cypher_content, project_id)
        except Exception as e:
            print(f"Neo4j存储失败（继续执行）: {e}")
        
        # 5. 存储到Redis
        self.store_to_redis(groups, all_chains, project_id)
        
        # 6. 存储到ChromaDB
        await self.store_to_chromadb(interfaces, groups, project_id)
        
        # 7. 保存Cypher文件
        cypher_filepath = self.save_cypher_file(cypher_content, project_id)
        
        return {
            'groups': {gid: {'name': self.GROUPING_RULES.get(gid, {}).get('name', f'分组_{gid}'), 'count': len(group_interfaces)} for gid, group_interfaces in groups.items()},
            'chains_count': len(all_chains),
            'total_interfaces': len(interfaces),
            'cypher_file': cypher_filepath
        }

