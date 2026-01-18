"""
优化的接口依赖分析器：
1. 按接口标题、path、描述相似度分组（标题优先级最高）
2. 按CRUD逻辑排序
3. 基于相似度和类别自动分析依赖关系（不使用LLM）
4. 同类别接口之间建立连线关系
5. 严格区分版本（V0.1和V6分开）
6. 存储到Neo4j和Redis
"""
from typing import List, Dict, Any, Optional, Tuple, Callable
import json
import re
from collections import defaultdict
from sqlalchemy.orm import Session
import asyncio
from difflib import SequenceMatcher
from datetime import datetime

from app.config import settings
# 不再导入LLMService（接口依赖分析不使用LLM）
# from app.services.llm_service import LLMService
from app.services.db_service import DatabaseService
from app.services.vector_service import VectorService
import redis
from app.models import TestCaseSuite

# Redis连接
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    encoding='utf-8'
)


class OptimizedDependencyAnalyzer:
    """优化的接口依赖分析器"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        # 不再初始化LLM服务（接口依赖分析不使用LLM）
        # self.llm_service = LLMService()
        self.db_service = DatabaseService()
        self.vector_service = VectorService()
        self.progress_callback: Optional[Callable] = None
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调"""
        self.progress_callback = callback
    
    def _update_progress(self, progress: int, message: str):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(progress, message)
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度（0-1）"""
        if not text1 or not text2:
            return 0.0
        
        # 使用SequenceMatcher计算相似度
        similarity = SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
        return similarity
    
    def _get_interface_category(self, interface: Dict[str, Any]) -> str:
        """根据接口标题关键字识别接口类型（优先使用标题）"""
        # 优先使用标题，如果没有标题则使用name
        title = (interface.get('title', '') or interface.get('name', '') or '').strip().lower()
        name = (interface.get('name', '') or '').lower()
        description = (interface.get('description', '') or '').lower()
        path = (interface.get('path', '') or interface.get('url', '') or '').lower()
        
        # 优先检查标题，如果标题中没有找到，再检查其他字段
        # 标题优先级最高
        title_text = title
        # 如果标题为空，使用name作为主要检查文本
        if not title_text:
            title_text = name
        
        # 合并所有文本作为备用检查
        full_text = f"{title_text} {description} {path}"
        
        # 定义接口类型和关键词（根据用户提供的最新分类规则）
        categories = {
            'account': ['绑定', '解绑', '登录', '验证码', '登出', '密码', '账号', '小米', '微信', '微博', 'did', '邮箱', 'google', 'apple', 'token'],
            'personal': ['个人资料', '头像', '收藏', '积分', '打卡', '收货地址', '体重', '新手大礼包', '订单', '标签', '商品', '二维码', '年报', '语言包', '评分'],
            'sport_record': ['记录', '运动', '上传'],
            'device': ['绑定设备', '解绑设备', '按键', '连接设备', '查找设备', '设备列表', 'wifi', '蓝牙', '跑步机', '走步机', '划船机', '爬楼机', '手环', 'applewatch', '健身板'],
            'program': ['程序', '模板', '模版', '设置按键', '获取按键'],
            'course': ['课程', '视频', '动作'],
            'product': ['产品', '说明书', '百科'],
            'heart_rate': ['心率', '打点', 'point'],
            'family': ['家庭', '共享', '成员', '勋章', '邀请', '接受', '拒绝'],
            'xiaodu': ['小度'],
            'plan': ['计划', '定制', 'ai', '请假'],
            'after_sale': ['售后', '地址', '销售'],
            'message': ['消息', '置顶', '红点'],
            'advertisement': ['广告', '首屏', '轮播图'],
            'activity': ['活动', '海报'],
            'upgrade': ['固件', '升级', '模组', '下控'],
            'help_feedback': ['帮助', '反馈', '问卷'],
            'oauth': ['oauth'],
            'aliyun': ['阿里云', '支付宝', 'identity'],
            'ranking': ['排行榜', '上榜'],
            'dumbbell': ['哑铃'],
            'bicycle': ['单车']
        }
        
        # 优先检查标题（title_text），如果标题中有匹配，直接返回
        for category, keywords in categories.items():
            if any(keyword in title_text for keyword in keywords):
                return category
        
        # 如果标题中没有找到，再检查完整文本
        for category, keywords in categories.items():
            if any(keyword in full_text for keyword in keywords):
                return category
        
        return 'other'
    
    def _normalize_version(self, version: str) -> str:
        """标准化版本号，便于比较，严格区分V0.1和V6"""
        if not version:
            return ''
        version = version.strip().upper()
        # 处理 V0.1, v0.1, 0.1 等格式
        if version.startswith('V'):
            return version
        elif version.replace('.', '').isdigit() or version.replace('.', '').replace('-', '').isdigit():
            return f"V{version}"
        return version
    
    def _is_version_separated(self, version1: str, version2: str) -> bool:
        """检查两个版本是否需要分开（V0.1和V6必须分开）"""
        v1 = self._normalize_version(version1)
        v2 = self._normalize_version(version2)
        
        # 如果版本号不同，必须分开
        if v1 and v2:
            return v1 != v2
        
        # 如果只有一个有版本号，也要分开（严格版本区分）
        if (v1 and not v2) or (not v1 and v2):
            return True
        
        # 都没有版本号，可以在一起
        return False
    
    def _calculate_interface_similarity(self, interface1: Dict[str, Any], interface2: Dict[str, Any]) -> float:
        """计算两个接口的相似度（基于标题、path、描述），优先级最高是标题相似度"""
        # 检查版本号：如果版本号不同，直接返回0（不相似）
        version1 = self._normalize_version((interface1.get('version', '') or '').strip())
        version2 = self._normalize_version((interface2.get('version', '') or '').strip())
        
        # 严格区分版本：使用专门的版本检查方法
        # 特别处理：V0.1 和 V6 必须分开
        if self._is_version_separated(interface1.get('version', ''), interface2.get('version', '')):
                return 0.0  # 不同版本号的接口完全不相似
        
        # 提取标题、path、描述（标题优先级最高）
        title1 = (interface1.get('title', '') or interface1.get('name', '') or '').strip().lower()
        title2 = (interface2.get('title', '') or interface2.get('name', '') or '').strip().lower()
        
        path1 = (interface1.get('path', '') or interface1.get('url', '') or '').lower()
        path2 = (interface2.get('path', '') or interface2.get('url', '') or '').lower()
        
        desc1 = (interface1.get('description', '') or '').lower()
        desc2 = (interface2.get('description', '') or '').lower()
        
        # 计算标题相似度（优先级最高）
        title_sim = self._calculate_text_similarity(title1, title2)
        
        # 如果标题相似度很高，直接使用标题相似度作为主要指标
        if title_sim >= 0.6:
            # 标题相似度优先级最高，直接使用标题相似度
            similarity = title_sim
            # 如果path也相似，适当加权（但标题仍然占主导）
            path_sim = self._calculate_text_similarity(path1, path2)
            if path_sim >= 0.5:
                similarity = (title_sim * 0.85 + path_sim * 0.15)
        else:
            # 如果标题相似度不高，则综合考虑
            path_sim = self._calculate_text_similarity(path1, path2)
            desc_sim = self._calculate_text_similarity(desc1, desc2)
            # 标题权重最高（0.7），path其次（0.2），描述最低（0.1）
            similarity = (title_sim * 0.7 + path_sim * 0.2 + desc_sim * 0.1)
        
        # 检查接口类型是否相同
        category1 = self._get_interface_category(interface1)
        category2 = self._get_interface_category(interface2)
        same_category = category1 == category2 and category1 != 'other'
        
        # 如果接口类型相同，提高相似度（最多提升0.1）
        if same_category:
            similarity = min(1.0, similarity + 0.1)
        
        return similarity
    
    def _extract_crud_type(self, interface: Dict[str, Any]) -> str:
        """从接口信息推断CRUD类型，按照创建->修改->查询->删除的顺序"""
        name = (interface.get('name', '') or '').lower()
        description = (interface.get('description', '') or '').lower()
        method = (interface.get('method', '') or '').upper()
        path = (interface.get('path', '') or interface.get('url', '') or '').lower()
        title = (interface.get('title', '') or '').lower()
        
        # 合并所有文本（优先使用标题）
        full_text = f"{title} {name} {description} {path}"
        
        # Create操作（创建，开始，新建，新增）- 优先级最高
        create_keywords = ['创建', '开始', '新建', '新增', 'create', 'add', 'register', 'signup', 'insert', 'new', '新增']
        if any(keyword in full_text for keyword in create_keywords):
            return 'CREATE'
        # 如果没有关键词但方法是POST，也认为是CREATE
        if method == 'POST' and not any(kw in full_text for kw in ['update', '修改', '编辑', '更改']):
            return 'CREATE'
        
        # Update操作（修改，编辑，更改）- 第二优先级
        update_keywords = ['修改', '编辑', '更改', 'update', 'edit', 'modify', 'change', 'set', 'patch']
        if any(keyword in full_text for keyword in update_keywords):
            return 'UPDATE'
        if method in ['PUT', 'PATCH']:
            return 'UPDATE'
        
        # Read操作（查询，获取，列表，搜索）- 第三优先级
        read_keywords = ['查询', '获取', '列表', '搜索', 'get', '得到', 'fetch', 'list', 'query', 'search', 'find', 'read', 'detail', 'info', '查看']
        if any(keyword in full_text for keyword in read_keywords):
            return 'READ'
        if method == 'GET':
            return 'READ'
        
        # Delete操作（删除，清除，去掉，delete）- 最后
        delete_keywords = ['删除', '清除', '去掉', 'delete', 'remove', 'del', 'destroy', '取消', '移除']
        if any(keyword in full_text for keyword in delete_keywords):
            return 'DELETE'
        if method == 'DELETE':
            return 'DELETE'
        
        # 默认返回READ
        return 'READ'
    
    def _get_interface_category_by_name(self, interface: Dict[str, Any]) -> Optional[str]:
        """根据接口名称匹配到32个预定义类别（严格按照用户提供的分组列表）"""
        name = (interface.get('name', '') or interface.get('title', '') or '').strip()
        description = (interface.get('description', '') or '').strip()
        service = (interface.get('service', '') or '').strip()
        full_text = f"{name} {description} {service}"
        
        # 定义32个类别及其关键词（严格按照用户提供的分组列表）
        categories = {
            'phone_login': [
                '手机注册', '忘记密码', '验证用户登录密码是否正确', '查询用户是否在白名单中', '绑定手机号', 
                '校验验证码', '验证码登录', '手机密码登录', '修改密码', '刷新token', '用手机号码注册账号', 
                '用手机验证码登录', '获取手机验证码', '用手机号和密码登录', '查询手机号是否已经注册账号', 
                '忘记登录密码', '校验验证码', '手机用户名密码登录'
            ],
            'email': [
                'kschair发送邮件', '邮箱注册', '邮箱登录', '发送邮箱验证码', '验证邮箱验证码是否正确', 
                '更改绑定邮箱', '重置app端的邮箱账号密码', '绑定邮箱', '注册邮箱登录app的账号', 
                '注销账号', '检查邮箱是否已经注册app账号', '获取验证码', '注销账号', '校验密码'
            ],
            'weibo': [
                '绑定微博账号', '微博账号绑定手机号'
            ],
            'personal': [
                '删除体重', '获取体重', '保险验证', '运动杂谈', '文章分页', '设置新手引导', '获取新手引导', 
                '记录语言', '更新语言包', '获取语言包', '设置用户标签', '查看用户信息', '获取用户当天待领取的积分', 
                '本周积分', '获取用户总积分', '获取用户七天打卡进度', '获取用户积分任务列表', '获取积分收支明细列表', 
                '领取新手大礼包', '设置打卡提醒开关', '获取用户打卡提醒设置', '获取用户是否领取新手大礼包', 
                '获取单条标签记录', '获取用户设置的标签列表', '获取标签简要列表', '获取训练指导标签列表', 
                '获取动作标签列表筛选项', '缓存用户运动总距离百分比等分至多', '缓存用户的设备类型', '获取用户年报', 
                '设置用户头像', '获取是否首次对app评分', '提交问卷', '获取问卷详情', '获取问卷配置', 
                '查询用户问卷提交状态', '领取活动奖品', '编辑个人资料', '获取个人资料', '意见反馈', '体重记录', '体重图表'
            ],
            'sport_record': [
                '上传运动记录', '查看运动记录详情', '蓝牙跑步机上传运动记录', '体脂称记录数据', 
                '上传运动记录的pointlist', '获取运动记录的pointlist', '获取全部运动记录', '上传运动记录', 
                '删除运动记录', '共享运动记录列表', '共享运动记录点数据详情', '微信硬件ID上报运动数据', '分配记录'
            ],
            'target_sport': [
                '获取目标运动列表', '获取指定设备类型的目标运动列表', '获取目标运动详情', '获取跑步记录详情'
            ],
            'device': [
                '绑定设备', '获取设备名', '获取设备token', '查询设备是否绑定成功', '绑定did', '解绑did', 
                '获取设备盒子', '设备列表', '上报wifi设备列表', '获取设备列表', '查看设备的销售地区'
            ],
            'program': [
                '创建程序', '编辑程序', '删除程序', '获取程序列表', '设置按键', '获取按键', '获取程序详情'
            ],
            'product': [
                '商品列表', '商品详情', '添加收货地址', '获取收货地址列表', '修改收货地址', '获取收货地址详情', 
                '删除收货地址', '支付宝支付回调', '获取订单'
            ],
            'course': [
                '课程库', '用户课程详情', '获取课程详情', '添加课程', '删除课程', '评价课程', '课程埋点', 
                '获取课程列表', '获取课程详情', '开始课程', '完成课程', '课程评价', '获取完成课程次数', 
                '获取最近在练的课程', '删除最近在练的课程', '添加课程收藏', '取消课程收藏', '获取课程收藏列表', 
                '获取训练指导视频列表', '全局搜索课程', '获取课程榜单列表', '获取个性化推荐课程', 
                '获取课程动作列表', '获取课程动作详情', '获取课程榜单列表', '获取课程动作下的视频', 
                '获取课程筛选项标签列表', '课程音乐列表', '查询精选课程动作列表'
            ],
            'product_info': [
                '获取产品列表', '获取产品详情', '获取连接说明', '获取产品列表以及产品百科', '获取产品的指导视频'
            ],
            'heart_rate': [
                '心率数据上报', '获取心率数据统计'
            ],
            'family': [
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
            'xiaodu': [
                '小度发现设备', '小度打开设备', '小度速度快一点', '小度设置自动模式', '小度查询运动信息', 
                '小度查询速度', '小度上报属性', '小度查询设备属性'
            ],
            'plan': [
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
            'after_sale': [
                '批量创建售后单', '创建售后单', '查询售后单map数据'
            ],
            'message': [
                '获取消息红点', '获取消息列表', '置顶某类消息', '取消置顶某类消息', '删除用户某条消息', 
                '删除用户某类消息', '获取用户一级消息列表', '获取用户二级消息列表'
            ],
            'ad': [
                '开屏广告接口', '获取广告列表', '获取首页广告轮播图', '查看首页广告轮播图详情'
            ],
            'activity': [
                '运动页活动列表', '获取活动列表', '活动列表', '获取首页活动列表', '查询两周燃脂活动状态', 
                '更新两周燃脂排行榜', '查询两周燃脂排行榜信息'
            ],
            'firmware': [
                '固件升级', '固件fireware升级', '确认固件升级', '获取最近的蓝牙模组固件', '获取下控固件'
            ],
            'oauth': [
                'oauth_code', 'oauth_token', 'Oauth refresh token', 'Oauth userinfo', 'Oauth getscope'
            ],
            'ranking': [
                '获取排行榜榜单'
            ],
            'dumbbell': [
                '获取哑铃课程列表', '获取哑铃课程详情', '开始哑铃课程', '上传哑铃运动记录', '获取哑铃运动记录',
                '哑铃', 'dumbbell', '哑铃课程', '哑铃运动'
            ],
            'bike': [
                '获取单车活动列表', '开始单车课程', '完成单车课程', '完成单车课程打卡数',
                '单车', 'bike', '单车课程', '单车活动', '单车运动'
            ],
            'ai': [
                '获取AI 剩余生成次数和积分', '生成AI运动计划', '生成AI运动建议', 'openai翻译', 
                '把AI生成的数据融合到课程列表中'
            ],
            'wechat': [
                '微信登录', '微信绑定', '微信解绑', '微信登录绑定手机号'
            ],
            'xiaomi': [
                '解绑小米账号', '小米账号获取token', '小米账号刷新token', '绑定小米账号'
            ],
            'vivo': [
                'vivo 登录', 'vivo 绑定手机号'
            ],
            'qrcode': [
                '二维码登录手机扫描', '二维码登录-电视轮训', '二维码', 'qrcode', '二维码登录', '扫码'
            ],
            'app': [
                '应用内评分', 'App检查类型', 'app检查升级v2', '应用', 'app', '升级', '检查升级', '应用评分'
            ],
            'google': [
                '谷歌登录', '绑定谷歌账号', '解绑谷歌账号'
            ]
        }
        
        # 匹配接口名称到类别（严格按照用户提供的分组列表，精确匹配）
        # 按优先级顺序检查，确保精确匹配
        full_text_lower = full_text.lower()
        name_lower = name.lower()
        
        # 按顺序检查每个类别（精确匹配关键词）
        # 优先检查更具体的类别，避免误匹配
        # 1. 先检查特殊类别（单车、哑铃、二维码、应用等），避免被其他类别误匹配
        special_categories = {
            'bike': ['单车', 'bike', '单车课程', '单车活动'],
            'dumbbell': ['哑铃', 'dumbbell', '哑铃课程', '哑铃运动'],
            'qrcode': ['二维码', 'qrcode', '二维码登录', '扫码'],
            'app': ['应用内评分', 'App检查类型', 'app检查升级', '应用评分'],
            'ai': ['AI', '生成AI', 'openai'],
            'wechat': ['微信登录', '微信绑定', '微信解绑'],
            'xiaomi': ['小米账号', '小米'],
            'vivo': ['vivo', 'vivo 登录'],
            'google': ['谷歌登录', '绑定谷歌账号', '解绑谷歌账号'],
            'oauth': ['oauth', 'Oauth'],
            'device': ['绑定设备', '获取设备', '设备列表', '解绑did', '绑定did'],
            'program': ['创建程序', '编辑程序', '删除程序', '获取程序'],
            'product': ['商品列表', '商品详情', '收货地址', '订单', '支付'],
            'product_info': ['产品列表', '产品详情', '产品百科', '指导视频'],
            'heart_rate': ['心率', '心率数据'],
            'family': ['家庭', '家庭成员', '家庭活动', '家庭设备'],
            'xiaodu': ['小度'],
            'plan': ['计划', '训练计划', '定制计划'],
            'after_sale': ['售后单', '售后'],
            'message': ['消息', '消息列表', '消息红点'],
            'ad': ['广告', '广告列表', '广告轮播图'],
            'activity': ['活动列表', '活动', '燃脂活动'],
            'firmware': ['固件', '固件升级', 'fireware'],
            'ranking': ['排行榜'],
            'sport_record': ['运动记录', '上传运动记录', '删除运动记录', '运动数据'],
            'target_sport': ['目标运动', '跑步记录'],
            'course': ['课程', '课程列表', '课程详情', '课程收藏', '课程动作'],
            'personal': ['个人资料', '用户信息', '用户标签', '积分', '打卡', '体重', '问卷', '新手引导'],
            'email': ['邮箱注册', '邮箱登录', '邮箱验证码', '绑定邮箱', '邮箱账号'],
            'weibo': ['微博', '微博账号'],
            'phone_login': ['手机注册', '手机登录', '手机验证码', '手机号', '手机密码', '手机用户名密码登录']
        }
        
        # 先检查特殊类别（从具体到一般）
        for category, keywords in special_categories.items():
            for keyword in keywords:
                if keyword in name or keyword in description or keyword in service:
                    # 如果是phone_login，需要更精确的匹配（避免误匹配）
                    if category == 'phone_login':
                        # 确保包含登录相关的关键词
                        if any(kw in full_text_lower for kw in ['登录', '注册', '验证码', '密码', 'login', 'register', 'verify']):
                            return category
                    else:
                        return category
        
        # 2. 然后检查所有类别的精确关键词匹配
        for category, keywords in categories.items():
            for keyword in keywords:
                # 精确匹配：接口名称、描述或service中包含完整的关键词
                if keyword in name or keyword in description or keyword in service:
                    return category
        
        # 3. 如果都没有匹配到，返回None（会在调用处被设置为'other'）
        return None
    
    def _group_interfaces_by_similarity(self, interfaces: List[Dict[str, Any]], threshold: float = 0.3) -> List[List[Dict[str, Any]]]:
        """按预定义的32个类别分组接口，同一组内按版本再分组"""
        self._update_progress(10, '正在按预定义类别和版本号分组接口...')
        
        # 第一步：按类别分组
        category_groups = {}
        for interface in interfaces:
            category = self._get_interface_category_by_name(interface)
            if category is None:
                category = 'other'  # 未匹配到的接口归为other
            if category not in category_groups:
                category_groups[category] = []
            category_groups[category].append(interface)
        
        print(f"按类别分组完成，共 {len(category_groups)} 个类别")
        for cat, ifaces in category_groups.items():
            print(f"  {cat}: {len(ifaces)} 个接口")
        
        # 第二步：对每个类别组，按版本再分组（同一组内的接口如果属于不同版本，再新建一组）
        all_groups = []
        for category, category_interfaces in category_groups.items():
            # 先按版本分组
            version_groups = {}
            for interface in category_interfaces:
                version = self._normalize_version((interface.get('version', '') or '').strip())
                version_key = version if version else 'no_version'
                if version_key not in version_groups:
                    version_groups[version_key] = []
                version_groups[version_key].append(interface)
            
            # 如果同一类别内有多个版本，每个版本创建一个组
            if len(version_groups) > 1:
                print(f"  类别 {category} 包含 {len(version_groups)} 个版本，将分别创建组")
                for version_key, version_interfaces in version_groups.items():
                    if len(version_interfaces) > 0:
                        all_groups.append(version_interfaces)
            else:
                # 如果只有一个版本，直接作为一个组
                if len(category_interfaces) > 0:
                    all_groups.append(category_interfaces)
        
        print(f"最终分组完成，共 {len(all_groups)} 个组（考虑了版本差异）")
        self._update_progress(20, f'已将接口分为 {len(all_groups)} 个组（按预定义类别和版本号分组）')
        return all_groups
    
    def _sort_interfaces_by_crud(self, interfaces: List[Dict[str, Any]], include_login: bool = False, login_interface: Dict[str, Any] = None, project_id: int = None) -> List[Dict[str, Any]]:
        """按照相似度和CRUD逻辑排序接口：先按相似度分组，组内按CRUD顺序排序（登录接口作为第一个节点）"""
        if not interfaces:
            if include_login and login_interface:
                return [login_interface]
            return []
        
        # CRUD顺序映射：CREATE → UPDATE → READ → DELETE
        crud_order = {'CREATE': 1, 'UPDATE': 2, 'READ': 3, 'DELETE': 4}
        
        # 为每个接口添加CRUD类型
        for interface in interfaces:
            interface['_crud_type'] = self._extract_crud_type(interface)
        
        # 先按相似度分组（使用接口名称相似度）
        similarity_groups = []
        used_indices = set()
        
        for i, interface in enumerate(interfaces):
            if i in used_indices:
                continue
            
            # 创建新的相似度组
            similarity_group = [interface]
            used_indices.add(i)
            
            # 查找相似的接口
            interface_name = (interface.get('name', '') or interface.get('title', '') or '').lower()
            
            for j, other_interface in enumerate(interfaces):
                if j in used_indices or i == j:
                    continue
                
                other_name = (other_interface.get('name', '') or other_interface.get('title', '') or '').lower()
                
                # 计算相似度（使用简单的字符串相似度）
                similarity = self._calculate_interface_similarity(interface, other_interface)
                
                # 如果相似度较高（阈值0.3），添加到同一组
                if similarity >= 0.3:
                    similarity_group.append(other_interface)
                    used_indices.add(j)
            
            similarity_groups.append(similarity_group)
        
        # 在每个相似度组内，按照CRUD顺序和特殊规则排序
        def get_interface_sort_key(interface):
            """获取接口的排序键：先按CRUD，再按特殊规则（注册-登录-注销，绑定-解绑）"""
            crud_type = interface.get('_crud_type', 'READ')
            crud_priority = crud_order.get(crud_type, 5)
            
            # 获取接口文本用于匹配
            name = (interface.get('name', '') or '').lower()
            title = (interface.get('title', '') or '').lower()
            description = (interface.get('description', '') or '').lower()
            full_text = f"{title} {name} {description}".lower()
            
            # 特殊排序规则优先级（在CRUD类型相同的情况下）
            # 注册-登录-注销：注册(1) -> 登录(2) -> 注销(3)
            register_keywords = ['注册', 'register', 'signup', '注册账号']
            login_keywords = ['登录', 'login', 'signin']
            logout_keywords = ['注销', 'logout', '注销账号']
            
            special_priority = 0  # 默认优先级
            if any(kw in full_text for kw in register_keywords):
                special_priority = 1  # 注册优先级最高
            elif any(kw in full_text for kw in login_keywords):
                special_priority = 2  # 登录其次
            elif any(kw in full_text for kw in logout_keywords):
                special_priority = 3  # 注销最后
            
            # 绑定-解绑：绑定(1) -> 解绑(2)
            bind_keywords = ['绑定', 'bind']
            unbind_keywords = ['解绑', 'unbind', '解除绑定']
            
            if special_priority == 0:  # 如果还没有设置特殊优先级
                if any(kw in full_text for kw in bind_keywords):
                    special_priority = 1  # 绑定优先级高
                elif any(kw in full_text for kw in unbind_keywords):
                    special_priority = 2  # 解绑优先级低
            
            # 返回排序键：(CRUD优先级, 特殊规则优先级)
            return (crud_priority, special_priority)
        
        sorted_groups = []
        for group in similarity_groups:
            sorted_group = sorted(group, key=get_interface_sort_key)
            sorted_groups.append(sorted_group)
        
        # 合并所有组：先按相似度组顺序，然后在每个组内保持CRUD顺序（创建 -> 修改 -> 查询 -> 删除）
        sorted_interfaces = []
        for group in sorted_groups:
            # 组内已经按CRUD排序，直接添加
            sorted_interfaces.extend(group)
        
        # 如果需要包含登录接口，将其放在最前面
        if include_login and login_interface:
            # 确保登录接口有CRUD类型
            login_interface['_crud_type'] = 'LOGIN'
            # 将登录接口放在最前面
            sorted_interfaces = [login_interface] + sorted_interfaces
        
        return sorted_interfaces
    
    def _get_few_shot_example(self, project_id: int, environment_name: str = "国内测试环境") -> Optional[Dict[str, Any]]:
        """从Redis获取few-shot示例（支持多种key格式）"""
        try:
            # 方式1: 按document格式查找（few_shot:project:{project_id}:document:{document_id}）
            pattern = f"few_shot:project:{project_id}:document:*"
            keys = redis_client.keys(pattern)
            
            if keys:
                # 优先查找包含environment名称的文档
                for key in keys:
                    data = redis_client.get(key)
                    if data:
                        few_shot_info = json.loads(data)
                        # 检查environment是否匹配
                        if environment_name in few_shot_info.get('environment', '') or environment_name in few_shot_info.get('filename', ''):
                            interfaces = few_shot_info.get('interfaces', [])
                            if interfaces:
                                return {
                                    'interfaces': interfaces,
                                    'environment': few_shot_info.get('environment', environment_name),
                                    'document_id': few_shot_info.get('document_id'),
                                    'filename': few_shot_info.get('filename', '')
                                }
                
                # 如果没有匹配的，使用第一个找到的
                if keys:
                    data = redis_client.get(keys[0])
                    if data:
                        few_shot_info = json.loads(data)
                        interfaces = few_shot_info.get('interfaces', [])
                        if interfaces:
                            return {
                                'interfaces': interfaces,
                                'environment': few_shot_info.get('environment', environment_name),
                                'document_id': few_shot_info.get('document_id'),
                                'filename': few_shot_info.get('filename', '')
                            }
            
            # 方式2: 按旧格式查找（few_shot:project:{project_id}:environment:{environment_name}）
            few_shot_key = f"few_shot:project:{project_id}:environment:{environment_name}"
            data = redis_client.get(few_shot_key)
            if data:
                few_shot_info = json.loads(data)
                fileid = few_shot_info.get('fileid')
                if fileid:
                    # 获取接口信息
                    interfaces_key = f"file:{fileid}:interfaces"
                    interfaces_data = redis_client.get(interfaces_key)
                    if interfaces_data:
                        return {
                            'interfaces': json.loads(interfaces_data),
                            'environment': environment_name,
                            'fileid': fileid
                        }
        except Exception as e:
            print(f"获取few-shot示例失败: {e}")
            import traceback
            traceback.print_exc()
        return None
    
    async def _analyze_group_with_llm(self, group: List[Dict[str, Any]], group_index: int, total_groups: int, project_id: int = None) -> Dict[str, Any]:
        """已废弃：使用deepseek分析一个组的接口依赖关系（不再使用，已改为基于相似度的分析）"""
        # 此方法已不再使用，直接返回空结果
        if len(group) < 2:
            # 获取版本信息
            version = self._normalize_version((group[0].get('version', '') or '').strip()) if group else ''
            version_prefix = f"[{version}]" if version else ''
            category = self._get_interface_category(group[0]) if group else 'other'
            return {'dependencies': [], 'scenario_name': f'{version_prefix}场景_{group_index + 1}_{category}', 'call_order': [], 'analysis_summary': ''}
        
        # 检查版本一致性（确保所有接口在同一版本内）
        versions = set()
        for interface in group:
            version = self._normalize_version((interface.get('version', '') or '').strip())
            if version:
                versions.add(version)
        
        if len(versions) > 1:
            print(f"警告：组内接口版本不一致: {versions}，跳过分析")
            return {'dependencies': [], 'scenario_name': f'场景_{group_index + 1}_版本不一致', 'call_order': [], 'analysis_summary': '版本不一致，跳过分析'}
        
        # 获取版本和类别信息
        version = versions.pop() if versions else ''
        version_prefix = f"[{version}]" if version else ''
        category = self._get_interface_category(group[0])
        
        # 按CRUD排序
        sorted_group = self._sort_interfaces_by_crud(group)
        
        # 获取few-shot示例
        few_shot_example = None
        if project_id:
            few_shot_example = self._get_few_shot_example(project_id)
        
        # 构建接口信息字符串
        interfaces_info = []
        for idx, interface in enumerate(sorted_group):
            # 检查请求体中是否包含token/authorize字段
            request_body = interface.get('request_body', {})
            if isinstance(request_body, str):
                try:
                    request_body = json.loads(request_body)
                except:
                    request_body = {}
            has_token = False
            if isinstance(request_body, dict):
                has_token = any(key.lower() in ['token', 'authorize', 'authorization'] for key in request_body.keys())
            
            # 识别账号相关接口
            account_keywords = {
                'register': ['手机号注册', '邮箱注册', 'register', 'signup', '注册'],
                'login': ['手机号验证码登录', '手机号密码登录', '邮箱账号密码登录', 'login', 'signin', '登录'],
                'logout': ['注销账号', 'logout', '注销'],
                'bind_email': ['绑定邮箱', 'bind_email', 'bindEmail'],
                'change_email': ['更改绑定邮箱', 'change_email', 'changeEmail', '修改邮箱'],
                'forgot_password': ['忘记密码', 'forgot_password', 'forgotPassword', 'findPwd', '找回密码'],
                'third_party_login': ['小米账号登录', '微信登录', '微博登录', 'google登录', 'apple登录', 'wechat', 'weibo', 'xiaomi', 'google', 'apple', 'oauth']
            }
            
            account_type = None
            interface_name_lower = (interface.get('title', '') or interface.get('name', '') or '').lower()
            interface_desc_lower = (interface.get('description', '') or '').lower()
            interface_text = f"{interface_name_lower} {interface_desc_lower}"
            
            for acc_type, keywords in account_keywords.items():
                if any(kw.lower() in interface_text for kw in keywords):
                    account_type = acc_type
                    break
            
            interface_info = f"""
接口{idx + 1}:
- 标题: {interface.get('title', '')}
- 名称: {interface.get('name', '')}
- 方法: {interface.get('method', '')}
- URL: {interface.get('url', '')}
- 路径: {interface.get('path', '')}
- 服务: {interface.get('service', '')}
- 版本: {interface.get('version', '')}
- 描述: {interface.get('description', '')}
- CRUD类型: {interface.get('_crud_type', 'UNKNOWN')}
- 账号相关类型: {account_type or '否'}
- 请求体包含token/authorize: {'是' if has_token else '否'}
"""
            interfaces_info.append(interface_info)
        
        # 构建few-shot示例部分
        few_shot_prompt = ""
        if few_shot_example and few_shot_example.get('interfaces'):
            few_shot_interfaces = few_shot_example['interfaces'][:5]  # 使用前5个接口作为示例
            few_shot_prompt = f"""
## Few-Shot示例（来自{few_shot_example.get('environment', '国内测试环境')}）：
以下是参考示例，展示了如何分析接口依赖关系：

{json.dumps(few_shot_interfaces, ensure_ascii=False, indent=2)}

请参考以上示例的分析方式，分析下面的接口。

"""
        
        prompt = f"""{few_shot_prompt}请分析以下{len(sorted_group)}个相似接口之间的依赖关系。

这些接口属于同一个业务模块，请分析它们之间的调用顺序和依赖关系。

{''.join(interfaces_info)}

请遵循以下依赖规则进行分析：

1. **版本号规则**（最高优先级，绝对不可违反）：
   - **不同版本号的接口绝对不能放在一起**：如果接口的版本号（version字段）不同，它们绝对不能在同一组中分析
   - **特别强调**：V0.1和V6版本的接口必须严格分开，绝对不能分在一组
   - 只有相同版本号的接口才能进行依赖关系分析
   - 版本号相同的接口优先分组
   - 如果发现接口版本号不同，必须拒绝分析，返回空依赖关系

2. **账号相关接口识别和依赖规则**（优先级第二高）：
   - **注册接口**：手机号注册、邮箱注册（register/signup）
   - **登录接口**：手机号验证码登录、手机号密码登录、邮箱账号密码登录（login/signin）
   - **第三方登录接口**：小米账号登录、微信登录、微博登录、google登录、apple登录（oauth/third-party login）
   - **账号管理接口**：注销账号（logout）、绑定邮箱（bind_email）、更改绑定邮箱（change_email）、忘记密码（forgot_password）
   - **依赖关系**：
     * 所有登录接口（包括第三方登录）都依赖对应的注册接口（手机号登录依赖手机号注册，邮箱登录依赖邮箱注册）
     * 第三方登录接口（微信、微博、google、apple、小米）可以独立于注册接口（因为它们使用外部账号）
     * 注销账号、绑定邮箱、更改绑定邮箱、忘记密码等接口都依赖登录接口（必须先登录）
     * 请求体中包含token、authorize、authorization字段的接口都依赖登录接口

3. **设备连接依赖规则**：
   - **运动接口依赖登录和连接设备接口**：运动相关的接口（如运动数据上传、运动记录、运动计划等）同时依赖：
     * 登录接口（必须先登录）
     * 连接设备接口（如连接手环、连接设备、绑定设备等）
   - 显示心率、运动数据等接口依赖于设备连接接口

4. **CRUD逻辑顺序规则**（按照以下顺序组织接口依赖，严格按照顺序）：
   - **创建类（第一优先级）**：创建、新增、增加、建立 -> CREATE类型
   - **查询类（第二优先级）**：查询、get、获取、得到 -> READ类型
   - **修改类（第三优先级）**：修改、编辑、更改 -> UPDATE类型
   - **删除类（最后）**：删除、去掉、消除 -> DELETE类型
   - 在分析依赖关系时，必须遵循这个顺序：CREATE接口必须在READ之前，READ在UPDATE之前，UPDATE在DELETE之前

5. **相似度分组规则**：
   - 通过接口标题（title）、接口path、接口描述的相似度来判断
   - 相似度很高的接口组合在一起，构建小场景用例集
   - 优先使用接口标题进行相似度匹配，其次是path
   - **重要：只有相同版本号的接口才能分组**

请分析：
1. **接口调用顺序**（严格按照以下规则）：
   - **版本号检查**：确保所有接口的版本号相同，不同版本的接口不能放在一起
   - **同类型接口分组**：根据标题关键字识别的同类型接口（账号相关、个人相关、设备相关等）应该分在一组，它们之间应该有依赖关系（连线）
   - **账号相关接口顺序**：
     * 先调用注册接口（手机号注册、邮箱注册）- CREATE类型
     * 再调用登录接口（手机号验证码登录、手机号密码登录、邮箱账号密码登录、第三方登录）- 登录依赖注册（第三方登录除外）
     * 然后调用账号管理接口（绑定邮箱、更改绑定邮箱、忘记密码等）- 这些接口依赖登录
     * 注销账号接口依赖登录接口
   - **设备相关接口**：连接设备接口（如果需要）
   - **业务接口**：按照CRUD顺序（创建->查询->修改->删除）
   - 如果请求体中有token/authorize字段，该接口必须在登录接口之后
   - **重要**：同类型接口（根据标题关键字识别）之间应该建立依赖关系，形成调用链路

2. **接口数据依赖**：
   - 某个接口的请求参数来自哪个接口的响应
   - 例如：登录接口返回token，其他接口的请求体中使用这个token

3. **接口业务依赖**：
   - **版本依赖**（绝对规则）：不同版本的接口绝对不能有依赖关系，V0.1和V6版本的接口之间绝对不能建立依赖关系
   - **同类型接口依赖**（必须在同一版本内）：根据标题关键字识别的同类型接口之间应该有依赖关系（连线），但必须在同一版本内
     * 账号相关接口：绑定、解绑、登录、验证码、登出、密码、账号、小米、微信、微博、did、邮箱、google、apple、token 等接口之间应该有依赖关系（必须在同一版本内）
     * 个人相关接口：个人资料、头像、收藏、积分、打卡、收货地址、体重、订单、标签、商品、二维码、年报、语言包等接口之间应该有依赖关系（必须在同一版本内）
     * 设备相关接口：绑定设备、解绑设备、连接设备、查找设备、设备列表、wifi、蓝牙、跑步机、走步机、划船机、爬楼机、手环、applewatch、健身板、单车等接口之间应该有依赖关系（必须在同一版本内）
     * 运动记录相关接口：记录、运动、上传等接口之间应该有依赖关系（必须在同一版本内）
     * 程序相关接口：程序、模板、模版等接口之间应该有依赖关系（必须在同一版本内）
     * 课程相关接口：课程、视频、动作等接口之间应该有依赖关系（必须在同一版本内）
     * 产品相关接口：产品、说明书、百科等接口之间应该有依赖关系（必须在同一版本内）
     * 心率相关接口：心率、打点、point等接口之间应该有依赖关系（必须在同一版本内）
     * 家庭活动相关接口：家庭、共享、成员、勋章、邀请、接受、拒绝等接口之间应该有依赖关系（必须在同一版本内）
     * 小度相关接口：小度等接口之间应该有依赖关系（必须在同一版本内）
     * 计划相关接口：计划、定制、AI、请假等接口之间应该有依赖关系（必须在同一版本内）
     * 售后相关接口：售后、地址、销售等接口之间应该有依赖关系（必须在同一版本内）
     * 消息相关接口：消息、置顶、红点等接口之间应该有依赖关系（必须在同一版本内）
     * 广告相关接口：广告、首屏、轮播图等接口之间应该有依赖关系（必须在同一版本内）
     * 活动相关接口：活动、海报等接口之间应该有依赖关系（必须在同一版本内）
     * 升级相关接口：固件、升级、模组、下控等接口之间应该有依赖关系（必须在同一版本内）
     * 帮助与反馈相关接口：帮助、反馈、问卷等接口之间应该有依赖关系（必须在同一版本内）
     * oauth相关接口：oauth等接口之间应该有依赖关系（必须在同一版本内）
     * 阿里云相关接口：阿里云、支付宝、identity等接口之间应该有依赖关系（必须在同一版本内）
     * 排行榜相关接口：排行榜、上榜等接口之间应该有依赖关系（必须在同一版本内）
     * 哑铃相关接口：哑铃等接口之间应该有依赖关系（必须在同一版本内）
     * **重要**：所有同类型接口的依赖关系必须在同一版本内，不同版本的接口之间绝对不能建立依赖关系
   - **账号依赖**：
     * 手机号登录接口依赖手机号注册接口
     * 邮箱登录接口依赖邮箱注册接口
     * 第三方登录接口（微信、微博、google、apple、小米）可以独立（不依赖注册）
     * 账号管理接口（注销、绑定邮箱、更改绑定邮箱、忘记密码）依赖登录接口
   - **认证依赖**：有token/authorize的接口依赖登录接口
   - **设备依赖**：运动接口依赖登录接口和连接设备接口
   - **CRUD依赖**：按照创建->查询->修改->删除的顺序

4. **接口识别**（重点识别账号相关接口）：
   - **注册接口**：手机号注册、邮箱注册（register/signup）
   - **登录接口**：手机号验证码登录、手机号密码登录、邮箱账号密码登录（login/signin）
   - **第三方登录**：小米账号登录、微信登录、微博登录、google登录、apple登录
   - **账号管理**：注销账号、绑定邮箱、更改绑定邮箱、忘记密码
   - **需要token的接口**：请求体中有token/authorize/authorization字段
   - **运动相关接口**：运动、运动数据、运动记录等
   - **设备连接接口**：连接设备、绑定设备等

请以JSON格式返回分析结果：
{{
    "dependencies": [
        {{
            "source": "接口1的名称或索引",
            "target": "接口2的名称或索引",
            "type": "parameter/state/authentication/device_connection",
            "description": "依赖关系的详细说明",
            "dependency_path": "数据传递路径，如data.id -> request.id",
            "confidence": 0.0-1.0之间的置信度
        }}
    ],
    "call_order": ["接口1", "接口2", "接口3"],
    "scenario_name": "小场景用例集名称（基于相似接口组合）",
    "analysis_summary": "整体依赖关系分析总结"
}}

请确保返回的JSON格式正确："""

        try:
            # 不再使用LLM分析（已改为基于相似度的分析）
            # result = await self.llm_service.chat(prompt, temperature=0.3, max_tokens=2000)
            # 直接返回空结果，因为此方法已不再使用
            return {'dependencies': [], 'scenario_name': f'场景_{group_index + 1}', 'call_order': [], 'analysis_summary': '此方法已废弃，不再使用LLM分析'}
            
            # 解析JSON结果
            try:
                # 提取JSON部分
                if "```json" in result:
                    result = result.split("```json")[1].split("```")[0].strip()
                elif "```" in result:
                    result = result.split("```")[1].split("```")[0].strip()
                
                analysis = json.loads(result)
                
                # 转换为标准格式
                dependencies = []
                # 场景名称包含版本和类别信息
                default_scenario_name = f'{version_prefix}场景_{group_index + 1}_{category}'
                scenario_name = analysis.get('scenario_name', default_scenario_name)
                # 如果场景名称中没有版本信息，添加版本前缀
                if version_prefix and version_prefix not in scenario_name:
                    scenario_name = f'{version_prefix}{scenario_name}'
                
                # 构建映射：接口名称 -> 索引，接口索引 -> 索引
                source_map = {}
                for i, iface in enumerate(sorted_group):
                    name = iface.get('name', '')
                    if name:
                        source_map[name] = i
                    source_map[str(i + 1)] = i  # 接口1对应索引0
                    source_map[str(i)] = i
                    source_map[f"接口{i + 1}"] = i
                    source_map[f"接口{name}"] = i
                
                for dep in analysis.get('dependencies', []):
                    source_name = dep.get('source', '')
                    target_name = dep.get('target', '')
                    
                    # 尝试匹配接口名称或索引
                    source_idx = source_map.get(source_name, -1)
                    if source_idx == -1:
                        # 尝试从接口名称中提取数字
                        import re
                        match = re.search(r'(\d+)', source_name)
                        if match:
                            source_idx = int(match.group(1)) - 1
                    
                    target_idx = source_map.get(target_name, -1)
                    if target_idx == -1:
                        # 尝试从接口名称中提取数字
                        import re
                        match = re.search(r'(\d+)', target_name)
                        if match:
                            target_idx = int(match.group(1)) - 1
                    
                    if source_idx >= 0 and target_idx >= 0 and source_idx < len(sorted_group) and target_idx < len(sorted_group) and source_idx != target_idx:
                        source_interface = sorted_group[source_idx]
                        target_interface = sorted_group[target_idx]
                        
                        # 获取接口ID，优先使用id字段，如果没有则使用interface_id，最后使用生成的ID
                        source_id = source_interface.get('id') or source_interface.get('interface_id') or self._get_interface_id(source_interface)
                        target_id = target_interface.get('id') or target_interface.get('interface_id') or self._get_interface_id(target_interface)
                        
                        dependencies.append({
                            'source': str(source_id),  # 确保是字符串
                            'target': str(target_id),   # 确保是字符串
                            'source_interface': source_interface,
                            'target_interface': target_interface,
                            'type': dep.get('type', 'unknown'),
                            'description': dep.get('description', ''),
                            'dependency_path': dep.get('dependency_path', ''),
                            'confidence': float(dep.get('confidence', 0.5)),
                            'scenario_name': scenario_name  # 添加场景名称
                        })
                
                return {
                    'dependencies': dependencies,
                    'scenario_name': scenario_name,
                    'call_order': analysis.get('call_order', []),
                    'analysis_summary': analysis.get('analysis_summary', '')
                }
            except json.JSONDecodeError as e:
                print(f"LLM返回结果解析失败: {e}, 原始结果: {result[:500]}")
                return {'dependencies': [], 'scenario_name': f'场景_{group_index + 1}', 'call_order': [], 'analysis_summary': ''}
        except Exception as e:
            print(f"LLM分析失败: {e}")
            return {'dependencies': [], 'scenario_name': f'场景_{group_index + 1}', 'call_order': [], 'analysis_summary': ''}
    
    def _analyze_group_fast(self, group: List[Dict[str, Any]], group_index: int, total_groups: int, project_id: int = None) -> Dict[str, Any]:
        """快速分析接口依赖关系（已按预定义规则分组，直接按CRUD顺序连接，无需复杂计算）"""
        # 获取登录接口
        login_interface = self._get_login_interface(project_id)
        login_interface['_crud_type'] = 'LOGIN'
        login_id = self._get_interface_id(login_interface)
        
        # 快速处理：直接按CRUD类型排序，无需相似度计算
        if len(group) == 0:
            return {
                'dependencies': [],
                'scenario_name': f'场景_{group_index + 1}_空组',
                'call_order': [login_id],
                'analysis_summary': '组为空，只包含登录接口'
            }
        
        # 为每个接口快速提取CRUD类型（无需相似度计算）
        for interface in group:
            interface['_crud_type'] = self._extract_crud_type(interface)
        
        # 快速排序：直接按CRUD顺序（LOGIN -> CREATE -> UPDATE -> READ -> DELETE）
        crud_order = {'LOGIN': 0, 'CREATE': 1, 'UPDATE': 2, 'READ': 3, 'DELETE': 4}
        sorted_group = sorted(group, key=lambda x: crud_order.get(x.get('_crud_type', 'READ'), 5))
        
        # 确保登录接口在第一位
        if sorted_group and sorted_group[0].get('_crud_type') != 'LOGIN':
            sorted_group.insert(0, login_interface)
        elif not sorted_group:
            sorted_group = [login_interface]
        
        # 快速构建依赖链：直接按顺序连接
        dependencies = []
        call_order = [login_id]
        
        version = self._normalize_version((group[0].get('version', '') or '').strip()) if group else ''
        version_prefix = f"[{version}]" if version else ''
        category = self._get_interface_category_by_name(group[0]) if group else 'other'
        
        # 构建依赖关系（链式连接）
        prev_interface = login_interface
        prev_id = login_id
        
        for interface in sorted_group:
            if self._get_interface_id(interface) == login_id:
                continue  # 跳过登录接口（已在call_order中）
            
            interface_id = self._get_interface_id(interface)
            call_order.append(interface_id)
            
            # 建立依赖关系
            dependencies.append({
                'source': str(prev_id),
                'target': str(interface_id),
                'source_interface': prev_interface,
                'target_interface': interface,
                'type': 'dependency_chain',
                'description': f'{prev_interface.get("name", "")} -> {interface.get("name", "")}',
                'dependency_path': f'{prev_interface.get("_crud_type", "READ")} -> {interface.get("_crud_type", "READ")}',
                'confidence': 0.9,  # 预定义规则分组，置信度高
                'scenario_name': f'{version_prefix}场景_{group_index + 1}_{category}'
            })
            
            prev_interface = interface
            prev_id = interface_id
        
        scenario_name = f'{version_prefix}场景_{group_index + 1}_{category}'
        analysis_summary = f'基于预定义规则快速分析：{len(sorted_group)}个{category}相关接口，建立{len(dependencies)}个依赖关系'
        
        return {
            'dependencies': dependencies,
            'scenario_name': scenario_name,
            'call_order': call_order,
            'analysis_summary': analysis_summary
        }
    
    def _analyze_group_without_llm(self, group: List[Dict[str, Any]], group_index: int, total_groups: int, project_id: int = None) -> Dict[str, Any]:
        """基于相似度和类别自动分析接口依赖关系（不使用LLM），每条链的第一个节点都是登录接口（保留作为备用）"""
        # 获取登录接口
        login_interface = self._get_login_interface(project_id)
        login_interface['_crud_type'] = 'LOGIN'
        login_id = self._get_interface_id(login_interface)
        
        if len(group) < 1:
            print(f"警告：组 {group_index + 1} 为空，只包含登录接口")
            version = ''
            version_prefix = ''
            category = 'other'
            sorted_group = [login_interface]
        elif len(group) == 1:
            version = self._normalize_version((group[0].get('version', '') or '').strip())
            version_prefix = f"[{version}]" if version else ''
            category = self._get_interface_category(group[0]) if group else 'other'
            # 单接口场景也需要包含登录接口
            sorted_group = self._sort_interfaces_by_crud(group, include_login=True, login_interface=login_interface, project_id=project_id)
        else:
            # 检查版本一致性
            versions = set()
            for interface in group:
                version = self._normalize_version((interface.get('version', '') or '').strip())
                if version:
                    versions.add(version)
            
            if len(versions) > 1:
                print(f"警告：组内接口版本不一致: {versions}，跳过分析")
                return {
                    'dependencies': [],
                    'scenario_name': f'场景_{group_index + 1}_版本不一致',
                    'call_order': [],
                    'analysis_summary': '版本不一致，跳过分析'
                }
            
            # 获取版本和类别信息
            version = versions.pop() if versions else ''
            version_prefix = f"[{version}]" if version else ''
            category = self._get_interface_category(group[0])
            
            # 按CRUD排序（包含登录接口作为第一个节点）
            sorted_group = self._sort_interfaces_by_crud(group, include_login=True, login_interface=login_interface, project_id=project_id)
        
        # 构建依赖关系：构建完整的依赖链拓扑图
        # 第一条链的第一个节点是登录接口，后续接口按 CREATE → UPDATE → READ → DELETE 顺序
        dependencies = []
        call_order = []
        
        # 确保登录接口在第一个位置
        if sorted_group and sorted_group[0].get('_crud_type') != 'LOGIN':
            # 如果第一个不是登录接口，查找登录接口并移到最前面
            login_idx = None
            for idx, iface in enumerate(sorted_group):
                if self._get_interface_id(iface) == login_id or iface.get('_crud_type') == 'LOGIN':
                    login_idx = idx
                    break
            
            if login_idx is not None and login_idx > 0:
                sorted_group.insert(0, sorted_group.pop(login_idx))
            elif login_idx is None:
                # 如果没有找到登录接口，在开头插入
                sorted_group.insert(0, login_interface)
        
        # 构建依赖链：每个接口依赖前一个接口（形成链式结构）
        print(f"调试：组 {group_index + 1} sorted_group包含 {len(sorted_group)} 个接口")
        if len(sorted_group) == 0:
            print(f"警告：组 {group_index + 1} sorted_group为空，无法构建依赖链")
            return {
                'dependencies': [],
                'scenario_name': f'场景_{group_index + 1}_空组',
                'call_order': [],
                'analysis_summary': '组为空，无法构建依赖链'
            }
        
        # 确保call_order至少包含sorted_group中的所有接口ID（即使只有一个接口也要添加）
        for i in range(len(sorted_group)):
            source_interface = sorted_group[i]
            # 统一使用_get_interface_id方法生成ID，确保与Neo4j存储时一致
            source_id = self._get_interface_id(source_interface)
            # call_order中存储接口ID，而不是接口名称
            call_order.append(source_id)
            print(f"调试：组 {group_index + 1} 添加接口 {i+1}/{len(sorted_group)}: {source_interface.get('name', 'N/A')} (ID: {source_id})")
            
            # 如果不是最后一个接口，建立到下一个接口的依赖关系
            if i < len(sorted_group) - 1:
                target_interface = sorted_group[i + 1]
                # 统一使用_get_interface_id方法生成ID，确保与Neo4j存储时一致
                target_id = self._get_interface_id(target_interface)
                
                # 获取接口的CRUD类型
                source_crud = source_interface.get('_crud_type', self._extract_crud_type(source_interface))
                target_crud = target_interface.get('_crud_type', self._extract_crud_type(target_interface))
                
                # 计算相似度用于置信度
                similarity = self._calculate_interface_similarity(source_interface, target_interface) if source_interface.get('_crud_type') != 'LOGIN' else 0.8
                confidence = min(0.9, similarity + 0.3) if source_interface.get('_crud_type') != 'LOGIN' else 0.9
                
                dependencies.append({
                    'source': str(source_id),
                    'target': str(target_id),
                    'source_interface': source_interface,
                    'target_interface': target_interface,
                    'type': 'dependency_chain',  # 依赖链
                    'description': f'{source_interface.get("title", source_interface.get("name", ""))} -> {target_interface.get("title", target_interface.get("name", ""))}',
                    'dependency_path': f'{source_crud} -> {target_crud}',
                    'confidence': confidence,
                    'scenario_name': f'{version_prefix}场景_{group_index + 1}_{category}'
                })
        
        # 确保call_order不为空（至少包含登录接口或其他接口）
        if not call_order and len(sorted_group) > 0:
            print(f"警告：组 {group_index + 1} call_order为空但sorted_group不为空，强制添加接口")
            for iface in sorted_group:
                source_id = self._get_interface_id(iface)
                call_order.append(source_id)
        
        # 生成场景名称和分析摘要
        scenario_name = f'{version_prefix}场景_{group_index + 1}_{category}'
        analysis_summary = f'基于相似度和类别自动分析：{len(sorted_group)}个{category}相关接口，建立{len(dependencies)}个依赖关系'
        
        print(f"组 {group_index + 1} ({category}): {len(sorted_group)} 个接口，call_order包含 {len(call_order)} 个接口ID，生成 {len(dependencies)} 个依赖关系")
        if len(dependencies) > 0:
            for i, dep in enumerate(dependencies[:5], 1):  # 打印前5个
                source_name = dep.get('source_interface', {}).get('name', 'N/A')
                target_name = dep.get('target_interface', {}).get('name', 'N/A')
                print(f"  依赖关系 {i}: {source_name} ({dep.get('source', 'N/A')}) -> {target_name} ({dep.get('target', 'N/A')})")
        else:
            if len(sorted_group) <= 1:
                print(f"  警告：组内只有 {len(sorted_group)} 个接口，无法生成依赖关系，但call_order应包含接口ID")
                if call_order:
                    print(f"  call_order包含: {call_order}")
                else:
                    print(f"  错误：call_order为空！")
            else:
                print(f"  警告：组内有 {len(sorted_group)} 个接口，但未生成依赖关系，请检查逻辑")
        
        # 最终验证：确保call_order不为空
        if not call_order:
            print(f"严重错误：组 {group_index + 1} call_order为空，但sorted_group有 {len(sorted_group)} 个接口")
            # 强制从sorted_group中获取接口ID
            for iface in sorted_group:
                source_id = self._get_interface_id(iface)
                call_order.append(source_id)
            print(f"强制添加后，call_order包含 {len(call_order)} 个接口ID")
        
        return {
            'dependencies': dependencies,
            'scenario_name': scenario_name,
            'call_order': call_order,
            'analysis_summary': analysis_summary
        }
    
    def _get_interface_id(self, interface: Dict[str, Any]) -> str:
        """获取接口唯一标识"""
        interface_id = interface.get("interface_id")
        if interface_id:
            return f"api_{interface_id}"
        
        method = interface.get("method", "GET")
        path = interface.get("path", interface.get("url", ""))
        name = interface.get("name", "")
        
        # 使用method+path+name组合
        return f"{method}_{path}_{name}".replace("/", "_").replace(":", "")[:100]
    
    def analyze_interfaces(self, interfaces: List[Dict[str, Any]], connection_id: int, project_id: int, resume: bool = False) -> Dict[str, Any]:
        """分析指定接口的依赖关系（同步版本，供API调用，不使用LLM）"""
        # 直接调用同步方法（不再使用异步）
        return self._analyze_interfaces_async(interfaces, connection_id, project_id, resume=resume)
    
    def _analyze_interfaces_async(self, interfaces: List[Dict[str, Any]], connection_id: int, project_id: int, resume: bool = False) -> Dict[str, Any]:
        """分析指定接口的依赖关系（同步版本，不使用LLM）"""
        return self._analyze_all_interfaces_async(interfaces, project_id, resume=resume)
    
    def _is_response_body_valid(self, interface: Dict[str, Any]) -> bool:
        """检查接口的响应体是否有效（不为空且不是空JSON）
        如果response_body为空，会检查response_schema作为替代
        """
        response_body = interface.get('response_body')
        response_schema = interface.get('response_schema', {})
        
        # 首先检查response_body
        if response_body:
            # 如果是字符串，尝试解析JSON
            if isinstance(response_body, str):
                try:
                    parsed = json.loads(response_body)
                    # 如果是空字典或空字符串，认为无效
                    if isinstance(parsed, dict):
                        if len(parsed) > 0:
                            return True
                    elif isinstance(parsed, str):
                        if len(parsed.strip()) > 0:
                            return True
                    else:
                        if parsed is not None:
                            return True
                except:
                    # 如果不是JSON，检查是否是空字符串
                    if len(response_body.strip()) > 0:
                        return True
            
            # 如果是字典，检查是否为空
            elif isinstance(response_body, dict):
                if len(response_body) > 0:
                    return True
            
            # 其他类型认为有效
            else:
                return True
        
        # 如果response_body为空或无效，检查response_schema作为替代
        if response_schema:
            if isinstance(response_schema, dict):
                if len(response_schema) > 0:
                    return True
            elif isinstance(response_schema, str):
                try:
                    parsed = json.loads(response_schema)
                    if isinstance(parsed, dict) and len(parsed) > 0:
                        return True
                except:
                    if len(response_schema.strip()) > 0:
                        return True
        
        # 如果既没有有效的response_body也没有有效的response_schema
        # 检查是否有其他可用的响应信息（如status_code、description等）
        # 至少要有method和path，说明这是一个有效的接口
        if interface.get('method') and (interface.get('path') or interface.get('url')):
            # 对于某些接口（如DELETE），可能没有响应体，但仍然有效
            # 允许这些接口通过，但优先级较低
            return True
        
        return False
    
    def _save_analysis_progress(self, project_id: int, progress_data: Dict[str, Any]):
        """保存分析进度到Redis（支持断点续传）"""
        try:
            progress_key = f"analysis:progress:{project_id}"
            redis_client.set(progress_key, json.dumps(progress_data, ensure_ascii=False), ex=86400 * 7)  # 7天过期
        except Exception as e:
            print(f"保存分析进度失败: {e}")
    
    def _load_analysis_progress(self, project_id: int) -> Optional[Dict[str, Any]]:
        """从Redis加载分析进度（支持断点续传）"""
        try:
            progress_key = f"analysis:progress:{project_id}"
            progress_data = redis_client.get(progress_key)
            if progress_data:
                return json.loads(progress_data)
        except Exception as e:
            print(f"加载分析进度失败: {e}")
        return None
    
    def _clear_analysis_progress(self, project_id: int):
        """清除分析进度"""
        try:
            progress_key = f"analysis:progress:{project_id}"
            redis_client.delete(progress_key)
        except Exception as e:
            print(f"清除分析进度失败: {e}")
    
    def _store_dependency_graph_to_redis(self, interfaces: List[Dict[str, Any]], dependencies: List[Dict[str, Any]], project_id: int):
        """将依赖关系图数据保存到Redis作为备份（格式与Neo4j返回格式一致）"""
        try:
            # 生成依赖图数据（与Neo4j返回格式一致）
            nodes = []
            seen_node_ids = set()
            
            for iface in interfaces:
                interface_id = iface.get('id') or iface.get('interface_id') or self._get_interface_id(iface)
                node_id = str(interface_id)
                
                if node_id in seen_node_ids:
                    node_id = f"{node_id}_{len(seen_node_ids)}"
                
                seen_node_ids.add(node_id)
                
                node_name = iface.get('name', '') or iface.get('title', '') or ''
                node_url = iface.get('url', '') or iface.get('path', '')
                # 节点标签显示：接口名称 + URL
                label = f"{node_name}\n{node_url}" if node_url else node_name
                
                nodes.append({
                    'id': node_id,
                    'name': node_name,  # 显示接口名称
                    'url': node_url,
                    'method': iface.get('method', 'GET'),
                    'type': iface.get('_crud_type', 'UNKNOWN'),
                    'label': node_name  # 标签只显示接口名称，不显示"接口_123"格式
                })
            
            edges = []
            for dep in dependencies:
                source_id = str(dep.get('source', ''))
                target_id = str(dep.get('target', ''))
                
                # 验证source和target是否存在于nodes中
                source_exists = any(str(node['id']) == source_id for node in nodes)
                target_exists = any(str(node['id']) == target_id for node in nodes)
                
                if source_exists and target_exists:
                    edges.append({
                        'source': source_id,
                        'target': target_id,
                        'type': dep.get('type', 'unknown'),
                        'description': dep.get('description', ''),
                        'dependency_path': dep.get('dependency_path', ''),
                        'confidence': dep.get('confidence', 0.5)
                    })
            
            # 保存到Redis（格式与Neo4j返回格式一致）
            dependency_graph_data = {
                'nodes': nodes,
                'edges': edges
            }
            
            redis_key = f"dependency_graph:{project_id}"
            redis_client.set(
                redis_key,
                json.dumps(dependency_graph_data, ensure_ascii=False),
                ex=86400 * 7  # 7天过期
            )
            
            print(f"已保存依赖关系图到Redis备份：{len(nodes)} 个节点，{len(edges)} 条边")
        except Exception as e:
            print(f"保存依赖关系图到Redis失败: {e}")
            import traceback
            traceback.print_exc()
            # 不抛出异常，避免影响主流程
    
    def _load_dependency_graph_from_redis(self, project_id: int) -> Optional[Dict[str, Any]]:
        """从Redis加载依赖关系图数据（备份）"""
        try:
            redis_key = f"dependency_graph:{project_id}"
            data = redis_client.get(redis_key)
            if data:
                graph_data = json.loads(data)
                # 确保所有节点都有label字段（兼容旧数据）
                if 'nodes' in graph_data:
                    for node in graph_data['nodes']:
                        if 'label' not in node:
                            node_name = node.get('name', '')
                            node_url = node.get('url', '')
                            label = f"{node_name}\n{node_url}" if node_url else node_name
                            node['label'] = label
                return graph_data
        except Exception as e:
            print(f"从Redis加载依赖关系图失败: {e}")
        return None
    
    def _update_dependency_graph_in_redis_incremental(self, interfaces: List[Dict[str, Any]], dependencies: List[Dict[str, Any]], project_id: int):
        """增量更新Redis中的依赖关系图数据"""
        try:
            # 从Redis加载现有数据
            existing_data = self._load_dependency_graph_from_redis(project_id)
            if not existing_data:
                existing_data = {'nodes': [], 'edges': []}
            
            # 添加新节点（去重）
            existing_node_ids = {node['id'] for node in existing_data['nodes']}
            for iface in interfaces:
                interface_id = iface.get('id') or iface.get('interface_id') or self._get_interface_id(iface)
                node_id = str(interface_id)
                
                if node_id not in existing_node_ids:
                    existing_node_ids.add(node_id)
                    node_name = iface.get('name', '') or iface.get('title', '') or ''
                    node_url = iface.get('url', '') or iface.get('path', '')
                    # 节点标签显示：接口名称 + URL
                    label = f"{node_name}\n{node_url}" if node_url else node_name
                    
                    existing_data['nodes'].append({
                        'id': node_id,
                        'name': node_name,
                        'url': node_url,
                        'method': iface.get('method', 'GET'),
                        'type': iface.get('_crud_type', 'UNKNOWN'),
                        'label': label  # 添加label字段用于显示
                    })
            
            # 添加新边（去重）
            existing_edge_keys = {(edge['source'], edge['target']) for edge in existing_data['edges']}
            for dep in dependencies:
                source_id = str(dep.get('source', ''))
                target_id = str(dep.get('target', ''))
                edge_key = (source_id, target_id)
                
                if edge_key not in existing_edge_keys:
                    existing_edge_keys.add(edge_key)
                    existing_data['edges'].append({
                        'source': source_id,
                        'target': target_id,
                        'type': dep.get('type', 'unknown'),
                        'description': dep.get('description', ''),
                        'dependency_path': dep.get('dependency_path', ''),
                        'confidence': dep.get('confidence', 0.5)
                    })
            
            # 保存回Redis
            redis_key = f"dependency_graph:{project_id}"
            redis_client.set(
                redis_key,
                json.dumps(existing_data, ensure_ascii=False),
                ex=86400 * 7  # 7天过期
            )
            
        except Exception as e:
            print(f"增量更新Redis依赖关系图失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _analyze_all_interfaces_async(self, interfaces: List[Dict[str, Any]], project_id: int, resume: bool = False) -> Dict[str, Any]:
        """分析所有接口的依赖关系（基于相似度，不使用LLM）"""
        # 不再过滤响应体为空的接口，允许它们用于生成测试用例
        filtered_interfaces = interfaces
        filtered_count = 0  # 不再过滤接口，所以过滤数量为0
        
        self._update_progress(5, f'开始分析 {len(filtered_interfaces)} 个接口的依赖关系（已过滤 {filtered_count} 个无效接口）...')
        
        # 1. 按预定义32个类别快速分组（使用过滤后的接口）
        groups = self._group_interfaces_by_similarity(filtered_interfaces, threshold=0.3)
        
        self._update_progress(25, f'已按预定义规则快速分组完成，共 {len(groups)} 个组，开始分析依赖关系...')
        
        # 2. 对每组使用简化的快速分析（直接按CRUD顺序连接，无需复杂计算）
        all_dependencies = []
        
        def analyze_group_sync(group, idx, total, interface_id_map, login_interface, login_id):
            # 使用快速分析（直接按CRUD顺序连接，无需相似度计算）
            deps = self._analyze_group_fast(group, idx, total, project_id)
            return deps
        
        # 预先建立接口ID到接口对象的映射，避免嵌套查找（性能优化）
        interface_id_map = {}
        for iface in filtered_interfaces:
            interface_id = self._get_interface_id(iface)
            interface_id_map[interface_id] = iface
        
        # 预先获取登录接口（避免每次都调用）
        login_interface = self._get_login_interface(project_id)
        login_id = self._get_interface_id(login_interface)
        interface_id_map[login_id] = login_interface
        
        # 使用线程池并发处理多个组（提高性能）
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        results = []
        results_lock = threading.Lock()
        
        # 创建线程池（增加并发数以提高速度，最多10个并发）
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 提交所有任务
            future_to_group = {}
            for i, group in enumerate(groups):
                future = executor.submit(analyze_group_sync, group, i, len(groups), interface_id_map, login_interface, login_id)
                future_to_group[future] = i
            
            # 收集结果（按组索引排序，确保顺序正确）
            results_dict = {}
            for future in as_completed(future_to_group):
                try:
                    result = future.result()
                    group_idx = future_to_group[future]
                    if isinstance(result, dict):
                        deps_count = len(result.get('dependencies', []))
                        scenario = result.get('scenario_name', 'N/A')
                        print(f"✓ 第 {group_idx + 1} 组分析完成: {deps_count} 个依赖关系, 场景: {scenario}")
                    else:
                        print(f"⚠️ 第 {group_idx + 1} 组分析结果格式异常: {type(result)}")
                    with results_lock:
                        results_dict[group_idx] = result
                except Exception as e:
                    group_idx = future_to_group[future]
                    print(f"✗ 处理第 {group_idx + 1} 组时出错: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 按组索引排序结果
            results = [results_dict[i] for i in sorted(results_dict.keys()) if i in results_dict]
        
        # 批量写入所有组的接口和依赖关系到Neo4j和Redis（性能优化：避免每个组都单独写入）
        self._update_progress(65, '正在批量保存所有组到Neo4j和Redis...')
        try:
            # 收集所有新分析的接口和依赖关系
            all_new_interfaces = {}
            all_new_dependencies = []
            
            for result in results:
                if isinstance(result, dict):
                    deps = result.get('dependencies', [])
                    print(f"收集到 {len(deps)} 个依赖关系（来自result: {result.get('scenario_name', 'N/A')}）")
                    all_new_dependencies.extend(deps)
                    
                    # 收集所有涉及的接口
                    for dep in deps:
                        source_interface = dep.get('source_interface', {})
                        target_interface = dep.get('target_interface', {})
                        
                        if source_interface:
                            source_id = self._get_interface_id(source_interface)
                            if source_id not in all_new_interfaces:
                                iface = interface_id_map.get(source_id, source_interface)
                                all_new_interfaces[source_id] = iface
                        
                        if target_interface:
                            target_id = self._get_interface_id(target_interface)
                            if target_id not in all_new_interfaces:
                                iface = interface_id_map.get(target_id, target_interface)
                                all_new_interfaces[target_id] = iface
            
            print(f"总共收集到 {len(all_new_dependencies)} 个依赖关系，涉及 {len(all_new_interfaces)} 个接口")
            print(f"results数量: {len(results)}, 其中有效结果: {sum(1 for r in results if isinstance(r, dict))}")
            if len(all_new_dependencies) == 0:
                print(f"⚠️  关键警告：没有收集到任何依赖关系！")
                print(f"   results详情:")
                for i, result in enumerate(results[:10], 1):
                    if isinstance(result, dict):
                        deps = result.get('dependencies', [])
                        scenario = result.get('scenario_name', 'N/A')
                        print(f"     result {i}: {len(deps)} 个依赖关系, 场景: {scenario}")
                    else:
                        print(f"     result {i}: 类型异常 - {type(result)}")
            
            # 批量写入到Neo4j
            if all_new_interfaces and all_new_dependencies:
                try:
                    interfaces_list = list(all_new_interfaces.values())
                    print(f"准备保存 {len(interfaces_list)} 个接口和 {len(all_new_dependencies)} 个依赖关系到Neo4j")
                    
                    # 打印前5个依赖关系的详细信息
                    print(f"前5个依赖关系示例:")
                    for i, dep in enumerate(all_new_dependencies[:5], 1):
                        source_id = dep.get('source', 'N/A')
                        target_id = dep.get('target', 'N/A')
                        source_name = dep.get('source_interface', {}).get('name', 'N/A')
                        target_name = dep.get('target_interface', {}).get('name', 'N/A')
                        print(f"  {i}. {source_name} ({source_id}) -> {target_name} ({target_id})")
                    
                    self._store_to_neo4j_incremental(interfaces_list, all_new_dependencies, project_id)
                    print(f"批量保存完成：{len(interfaces_list)} 个接口和 {len(all_new_dependencies)} 个依赖关系")
                except Exception as e:
                    print(f"批量保存到Neo4j失败: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                if not all_new_interfaces:
                    print(f"⚠️  警告：没有收集到接口数据（all_new_interfaces为空）")
                if not all_new_dependencies:
                    print(f"⚠️  警告：没有收集到依赖关系数据（all_new_dependencies为空）")
                    print(f"   results数量: {len(results)}")
                    for i, result in enumerate(results[:5], 1):
                        if isinstance(result, dict):
                            deps_count = len(result.get('dependencies', []))
                            scenario = result.get('scenario_name', 'N/A')
                            print(f"   result {i}: {deps_count} 个依赖关系, 场景: {scenario}")
            
            # 批量更新Redis备份（无论是否有依赖关系，都要更新接口）
            if all_new_interfaces:
                try:
                    interfaces_list = list(all_new_interfaces.values())
                    if all_new_dependencies:
                        # 如果有依赖关系，一起更新
                        self._update_dependency_graph_in_redis_incremental(interfaces_list, all_new_dependencies, project_id)
                        print(f"批量更新了 {len(interfaces_list)} 个接口的依赖关系到Redis备份")
                    else:
                        # 如果没有依赖关系，只更新接口
                        self._update_dependency_graph_in_redis_incremental(interfaces_list, [], project_id)
                        print(f"批量更新了 {len(interfaces_list)} 个接口到Redis备份（无依赖关系）")
                except Exception as e:
                    print(f"批量更新Redis备份失败: {e}")
        except Exception as e:
            print(f"批量保存失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 收集所有依赖关系和场景信息
        all_scenarios = []
        
        # 从results中获取场景信息，基于分组、依赖关系和依赖链构建场景用例集
        for group_idx, group in enumerate(groups):
            if group_idx < len(results):
                result = results[group_idx]
                if isinstance(result, dict):
                    dependencies = result.get('dependencies', [])
                    call_order = result.get('call_order', [])  # 接口ID列表，按CRUD顺序
                    
                    # 基于依赖关系构建依赖链拓扑结构
                    # 构建邻接表：source -> [targets]
                    adjacency_map = {}
                    interface_set = set()
                    
                    for dep in dependencies:
                        source_id = dep.get('source')
                        target_id = dep.get('target')
                        source_interface = dep.get('source_interface', {})
                        target_interface = dep.get('target_interface', {})
                        
                        if source_id and target_id:
                            interface_set.add(str(source_id))
                            interface_set.add(str(target_id))
                            
                            if source_id not in adjacency_map:
                                adjacency_map[source_id] = []
                            adjacency_map[source_id].append({
                                'target': target_id,
                                'target_interface': target_interface
                            })
                    
                    # 构建依赖链：从登录接口开始，按照拓扑排序
                    dependency_chain = []
                    login_interface = self._get_login_interface(project_id)
                    login_id = self._get_interface_id(login_interface)
                    
                    # 如果call_order存在，使用它作为基础顺序（已经按CRUD排序：登录 -> 创建 -> 修改 -> 查询 -> 删除）
                    if call_order and len(call_order) > 0:
                        print(f"调试：场景 {result.get('scenario_name', '')} call_order包含 {len(call_order)} 个接口ID")
                        # 确保登录接口在第一位
                        ordered_ids = []
                        login_id_str = str(login_id)
                        # 检查call_order中是否包含登录接口
                        login_in_order = False
                        for id in call_order:
                            if str(id) == login_id_str:
                                login_in_order = True
                                break
                        
                        if login_in_order:
                            # 如果登录接口在call_order中，确保它在第一位
                            ordered_ids.append(login_id)
                            for id in call_order:
                                if str(id) != login_id_str:
                                    ordered_ids.append(id)
                        else:
                            # 如果不在，添加到第一位
                            ordered_ids = [login_id] + call_order
                        
                        print(f"调试：ordered_ids包含 {len(ordered_ids)} 个接口ID，group包含 {len(group)} 个接口，filtered_interfaces包含 {len(filtered_interfaces)} 个接口")
                        
                        # 转换为数据库ID
                        # 优先从group中查找（因为group是当前场景的接口），如果找不到再从filtered_interfaces中查找
                        matched_count = 0
                        for interface_id in ordered_ids:
                            matched = False
                            # 先从group中查找（当前场景的接口）
                            for iface in group:
                                iface_id = self._get_interface_id(iface)
                                if str(iface_id) == str(interface_id):
                                    db_id = iface.get('interface_id') or iface.get('id')
                                    if db_id:
                                        dependency_chain.append(str(db_id))
                                        matched = True
                                        matched_count += 1
                                        break
                            
                            # 如果group中找不到，再从filtered_interfaces中查找
                            if not matched:
                                for iface in filtered_interfaces:
                                    iface_id = self._get_interface_id(iface)
                                    if str(iface_id) == str(interface_id):
                                        db_id = iface.get('interface_id') or iface.get('id')
                                        if db_id:
                                            dependency_chain.append(str(db_id))
                                            matched = True
                                            matched_count += 1
                                        break
                            
                            if not matched:
                                print(f"警告：场景 {result.get('scenario_name', '')} 中无法找到接口ID {interface_id} 对应的接口")
                        
                        print(f"调试：场景 {result.get('scenario_name', '')} 匹配到 {matched_count}/{len(ordered_ids)} 个接口，依赖链长度: {len(dependency_chain)}")
                    else:
                        # 如果没有call_order，从依赖关系中构建拓扑排序
                        # 找到入口节点（登录接口或没有入边的节点）
                        in_degree = {}
                        for source_id in adjacency_map:
                            for target_info in adjacency_map[source_id]:
                                target_id = target_info['target']
                                in_degree[str(target_id)] = in_degree.get(str(target_id), 0) + 1
                        
                        # 拓扑排序：从登录接口开始
                        visited = set()
                        queue = [str(login_id)] if str(login_id) in interface_set else []
                        
                        # 添加其他没有入边的节点
                        for interface_id in interface_set:
                            if str(interface_id) not in in_degree and str(interface_id) not in queue:
                                queue.append(str(interface_id))
                        
                        while queue:
                            current_id = queue.pop(0)
                            if current_id in visited:
                                continue
                            
                            visited.add(current_id)
                            # 转换为数据库ID
                            # 优先从group中查找
                            matched = False
                            for iface in group:
                                iface_id = self._get_interface_id(iface)
                                if str(iface_id) == str(current_id):
                                    db_id = iface.get('interface_id') or iface.get('id')
                                    if db_id:
                                        dependency_chain.append(str(db_id))
                                        matched = True
                                        break
                            
                            # 如果group中找不到，再从filtered_interfaces中查找
                            if not matched:
                                for iface in filtered_interfaces:
                                    iface_id = self._get_interface_id(iface)
                                    if str(iface_id) == str(current_id):
                                        db_id = iface.get('interface_id') or iface.get('id')
                                        if db_id:
                                            dependency_chain.append(str(db_id))
                                        break
                            
                            # 添加依赖的节点
                            if current_id in adjacency_map:
                                for target_info in adjacency_map[current_id]:
                                    target_id = str(target_info['target'])
                                    if target_id not in visited:
                                        in_degree[target_id] = in_degree.get(target_id, 0) - 1
                                        if in_degree[target_id] == 0:
                                            queue.append(target_id)
                    
                    # 如果依赖链为空，尝试从call_order或group中获取
                    if not dependency_chain and call_order:
                        print(f"警告：场景 {result.get('scenario_name', f'场景_{group_idx + 1}')} 依赖链为空，尝试从call_order重新构建")
                        for interface_id in call_order:
                            # 先在filtered_interfaces中查找
                            found = False
                            for iface in filtered_interfaces:
                                iface_id = self._get_interface_id(iface)
                                if str(iface_id) == str(interface_id):
                                    db_id = iface.get('interface_id') or iface.get('id')
                                    if db_id:
                                        dependency_chain.append(str(db_id))
                                        found = True
                                        break
                            
                            # 如果在filtered_interfaces中找不到，尝试从group中查找
                            if not found:
                                for iface in group:
                                    iface_id = self._get_interface_id(iface)
                                    if str(iface_id) == str(interface_id):
                                        db_id = iface.get('interface_id') or iface.get('id')
                                        if db_id:
                                            dependency_chain.append(str(db_id))
                                            break
                    
                    # 如果还是没有，从group中获取接口ID（按CRUD顺序）
                    if not dependency_chain:
                        print(f"警告：场景 {result.get('scenario_name', f'场景_{group_idx + 1}')} 依赖链为空，尝试从group中获取")
                        # 按CRUD顺序排序group中的接口
                        sorted_group = self._sort_interfaces_by_crud(group, include_login=False, login_interface=None, project_id=project_id)
                        for iface in sorted_group:
                            db_id = iface.get('interface_id') or iface.get('id')
                            if db_id:
                                dependency_chain.append(str(db_id))
                        print(f"从group中获取到 {len(dependency_chain)} 个接口ID")
                    
                    # 确保至少有一个接口（登录接口或其他接口）
                    if not dependency_chain:
                        print(f"警告：场景 {result.get('scenario_name', f'场景_{group_idx + 1}')} 完全没有接口，跳过")
                        continue
                    
                    scenario_info = {
                        'scenario_name': result.get('scenario_name', f'场景_{group_idx + 1}'),
                        'call_order': call_order,
                        'dependency_chain': dependency_chain,
                        'dependencies': dependencies,  # 保存完整的依赖关系信息
                        'analysis_summary': result.get('analysis_summary', ''),
                        'dependencies_count': len(dependencies),
                        'interfaces_in_chain': len(dependency_chain)
                    }
                    all_scenarios.append(scenario_info)
                    print(f"✓ 场景 {scenario_info['scenario_name']}: 依赖链包含 {len(dependency_chain)} 个接口")
        
        # 为同类型接口建立连接关系（基于标题关键字）
        self._update_progress(70, '正在为同类型接口建立连接关系...')
        category_dependencies = self._build_category_dependencies(filtered_interfaces)
        all_dependencies.extend(category_dependencies)
        print(f"为同类型接口建立了 {len(category_dependencies)} 个连接关系")
        
        self._update_progress(75, f'依赖分析完成，找到 {len(all_dependencies)} 个依赖关系（包含同类型连接），{len(all_scenarios)} 个场景用例集，正在存储...')
        
        # 3. 存储场景用例集到数据库和Redis（使用过滤后的接口）
        if all_scenarios:
            print(f"准备存储 {len(all_scenarios)} 个场景用例集到数据库和Redis...")
            self._store_scenarios_to_db_and_redis(project_id, all_scenarios, filtered_interfaces)
        else:
            print(f"警告：没有场景用例集需要存储（all_scenarios为空）")
            print(f"分组数: {len(groups)}, 结果数: {len(results)}")
        
        # 4. 最终存储到Neo4j（使用过滤后的接口，确保所有数据都同步，包含登录接口）
        # 注意：由于已在分析过程中增量更新，这里主要是确保数据完整性
        neo4j_success = False
        try:
            # 确保登录接口包含在接口列表中
            login_interface = self._get_login_interface(project_id)
            login_id = self._get_interface_id(login_interface)
            
            # 检查登录接口是否已经在接口列表中
            login_exists = any(self._get_interface_id(iface) == login_id for iface in filtered_interfaces)
            if not login_exists:
                # 如果不存在，添加到列表开头
                filtered_interfaces.insert(0, login_interface)
            
            self._store_to_neo4j(filtered_interfaces, all_dependencies, project_id)
            neo4j_success = True
            print("Neo4j存储成功")
        except Exception as e:
            print(f"Neo4j存储失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 4.5. 保存依赖关系数据到Redis作为备份（即使Neo4j失败也能从Redis获取）
        self._update_progress(90, '正在保存依赖关系数据到Redis备份...')
        try:
            # 确保登录接口包含在接口列表中
            login_interface = self._get_login_interface(project_id)
            login_id = self._get_interface_id(login_interface)
            
            # 检查登录接口是否已经在接口列表中
            login_exists = any(self._get_interface_id(iface) == login_id for iface in filtered_interfaces)
            if not login_exists:
                # 如果不存在，添加到列表开头
                filtered_interfaces.insert(0, login_interface)
            
            self._store_dependency_graph_to_redis(filtered_interfaces, all_dependencies, project_id)
            print("Redis备份存储成功")
        except Exception as e:
            print(f"Redis备份存储失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 5. 同步到ChromaDB（使用过滤后的接口和依赖关系）
        self._update_progress(95, '正在同步依赖分析结果到ChromaDB...')
        try:
            # 使用异步方式存储到ChromaDB
            # 在 Celery worker 中，事件循环可能已关闭或不存在，需要创建新的事件循环
            # 使用辅助函数来安全地运行异步代码
            self._run_async_in_sync_context(
                self._store_to_chromadb(filtered_interfaces, all_dependencies, project_id)
            )
        except Exception as e:
            print(f"同步到ChromaDB失败: {e}")
            import traceback
            traceback.print_exc()
        
        self._update_progress(100, '接口依赖分析完成')
        
        # 清除分析进度（分析完成）
        self._clear_analysis_progress(project_id)
        
        # 4. 生成依赖图数据（使用过滤后的接口）
        nodes = []
        seen_node_ids = set()  # 用于去重
        node_id_map = {}  # 映射：接口对象 -> 节点ID（用于边的匹配）
        
        for iface in filtered_interfaces:
            # 统一使用_get_interface_id生成ID，确保与边的source/target ID格式一致
            interface_id = self._get_interface_id(iface)
            node_id = str(interface_id)
            
            # 去重：如果ID已存在，跳过（不应该发生，但为了安全）
            if node_id in seen_node_ids:
                print(f"警告：发现重复的接口ID: {node_id}, 接口名称: {iface.get('name', '')}")
                continue
            
            seen_node_ids.add(node_id)
            
            # 建立接口对象到节点ID的映射（用于边的匹配）
            # 使用内置函数id()获取对象内存地址（避免被覆盖）
            import builtins
            iface_key = builtins.id(iface)  # 使用对象内存地址作为键
            node_id_map[iface_key] = node_id
            
            node_name = iface.get('name', '') or iface.get('title', '') or ''
            node_url = iface.get('url', '') or iface.get('path', '')
            # 节点标签显示：接口名称 + URL
            label = f"{node_name}\n{node_url}" if node_url else node_name
            
            nodes.append({
                'id': node_id,  # 确保ID是字符串且唯一（使用接口ID，不显示"接口_123"）
                'name': node_name,  # 显示接口名称
                'url': node_url,
                'method': iface.get('method', 'GET'),
                'path': iface.get('path', ''),
                'type': iface.get('_crud_type', 'UNKNOWN'),
                'label': node_name  # 标签只显示接口名称，不显示"接口_123"格式
            })
        
        # 创建节点ID到接口对象的映射（用于从依赖关系中查找接口）
        interface_by_id = {}
        for iface in filtered_interfaces:
            interface_id = self._get_interface_id(iface)
            interface_by_id[str(interface_id)] = iface
        
        edges = []
        for dep in all_dependencies:
            # 获取source和target ID，优先从依赖关系对象中获取
            source_id = dep.get('source')
            target_id = dep.get('target')
            
            # 如果依赖关系中没有source/target，尝试从source_interface/target_interface中获取
            if not source_id:
                source_interface = dep.get('source_interface', {})
                if source_interface:
                    source_id = self._get_interface_id(source_interface)
            
            if not target_id:
                target_interface = dep.get('target_interface', {})
                if target_interface:
                    target_id = self._get_interface_id(target_interface)
            
            # 确保ID是字符串格式
            if source_id:
                source_id = str(source_id)
            if target_id:
                target_id = str(target_id)
            
            # 验证source和target是否存在于nodes中
            source_exists = source_id in seen_node_ids
            target_exists = target_id in seen_node_ids
            
            if source_exists and target_exists:
                edges.append({
                    'source': source_id,
                    'target': target_id,
                    'type': dep.get('type', 'unknown'),
                    'description': dep.get('description', ''),
                    'dependency_path': dep.get('dependency_path', ''),
                    'confidence': dep.get('confidence', 0.5)
                })
            else:
                if not source_exists:
                    print(f"警告：边的source节点不存在: {source_id}, 依赖关系: {dep.get('type', 'unknown')}")
                if not target_exists:
                    print(f"警告：边的target节点不存在: {target_id}, 依赖关系: {dep.get('type', 'unknown')}")
        
        return {
            'nodes': nodes,
            'edges': edges,
            'total_interfaces': len(filtered_interfaces),
            'total_dependencies': len(all_dependencies),
            'groups_count': len(groups),
            'filtered_count': filtered_count  # 返回过滤掉的接口数量
        }
    
    def _build_category_dependencies(self, interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为同类型接口建立连接关系（基于标题关键字）"""
        category_dependencies = []
        
        # 按版本号分组（严格区分版本，V0.1和V6必须分开）
        version_groups = {}
        for interface in interfaces:
            version = self._normalize_version((interface.get('version', '') or '').strip())
            version_key = version if version else 'no_version'
            if version_key not in version_groups:
                version_groups[version_key] = []
            version_groups[version_key].append(interface)
        
        # 确保V0.1和V6严格分开（再次检查）
        if 'V0.1' in version_groups and 'V6' in version_groups:
            print(f"为同类型接口建立连接：已严格分开V0.1版本（{len(version_groups['V0.1'])}个接口）和V6版本（{len(version_groups['V6'])}个接口）")
        
        # 在每个版本组内，按类型分组
        for version_key, version_interfaces in version_groups.items():
            type_groups = {}
            for interface in version_interfaces:
                category = self._get_interface_category(interface)
                if category not in type_groups:
                    type_groups[category] = []
                type_groups[category].append(interface)
            
            # 为同类型接口建立连接关系
            for category, type_interfaces in type_groups.items():
                if category == 'other' or len(type_interfaces) < 2:
                    continue  # 跳过other类型和少于2个接口的类型
                
                # 为同类型接口建立连接（按CRUD顺序或接口名称排序）
                sorted_interfaces = sorted(type_interfaces, key=lambda x: (
                    self._extract_crud_type(x),
                    x.get('name', '') or x.get('title', '')
                ))
                
                # 建立链式连接：每个接口连接到下一个接口
                for i in range(len(sorted_interfaces) - 1):
                    source_interface = sorted_interfaces[i]
                    target_interface = sorted_interfaces[i + 1]
                    
                    source_id = source_interface.get('id') or source_interface.get('interface_id') or self._get_interface_id(source_interface)
                    target_id = target_interface.get('id') or target_interface.get('interface_id') or self._get_interface_id(target_interface)
                    
                    category_dependencies.append({
                        'source': str(source_id),
                        'target': str(target_id),
                        'source_interface': source_interface,
                        'target_interface': target_interface,
                        'type': 'category_related',  # 标记为同类型连接
                        'description': f'同类型接口连接（{category}）',
                        'dependency_path': '',
                        'confidence': 0.8  # 同类型连接置信度较高
                    })
        
        return category_dependencies
    
    def _generate_cypher_file(self, interfaces: List[Dict[str, Any]], dependencies: List[Dict[str, Any]], project_id: int) -> str:
        """生成Cypher文件内容"""
        cypher_lines = []
        cypher_lines.append(f"// 项目ID: {project_id}")
        cypher_lines.append(f"// 生成时间: {self._get_current_timestamp()}")
        cypher_lines.append(f"// 接口数量: {len(interfaces)}")
        cypher_lines.append(f"// 依赖关系数量: {len(dependencies)}")
        cypher_lines.append("")
        cypher_lines.append("// 清空旧数据")
        cypher_lines.append(f"MATCH (n:APIInterface) WHERE n.project_id = {project_id} DETACH DELETE n;")
        cypher_lines.append("")
        cypher_lines.append("// 创建接口节点")
        
        # 按版本分组输出节点（便于查看）
        version_groups = {}
        for interface in interfaces:
            version = self._normalize_version((interface.get('version', '') or '').strip())
            version_key = version if version else 'no_version'
            if version_key not in version_groups:
                version_groups[version_key] = []
            version_groups[version_key].append(interface)
        
        for version_key, version_interfaces in version_groups.items():
            cypher_lines.append(f"// 版本: {version_key} (共 {len(version_interfaces)} 个接口)")
            
            for interface in version_interfaces:
                interface_id = self._get_interface_id(interface)
                crud_type = interface.get('_crud_type', self._extract_crud_type(interface))
                category = self._get_interface_category(interface)
                
                # 转义特殊字符
                name = interface.get('name', '').replace('"', '\\"').replace("'", "\\'")
                url = interface.get('url', '').replace('"', '\\"').replace("'", "\\'")
                path = (interface.get('path', '') or '').replace('"', '\\"').replace("'", "\\'")
                service = (interface.get('service', '') or '').replace('"', '\\"').replace("'", "\\'")
                description = (interface.get('description', '') or '').replace('"', '\\"').replace("'", "\\'")
                version_str = (interface.get('version', '') or '').replace('"', '\\"').replace("'", "\\'")
                
                cypher_lines.append(f"""MERGE (api{interface_id}:APIInterface {{
    id: "{interface_id}",
    project_id: {project_id}
}})
SET api{interface_id}.name = "{name}",
    api{interface_id}.method = "{interface.get('method', '')}",
    api{interface_id}.url = "{url}",
    api{interface_id}.path = "{path}",
    api{interface_id}.service = "{service}",
    api{interface_id}.description = "{description}",
    api{interface_id}.crud_type = "{crud_type}",
    api{interface_id}.version = "{version_str}",
    api{interface_id}.category = "{category}";""")
            
            cypher_lines.append("")
        
        cypher_lines.append("// 创建依赖关系边")
        cypher_lines.append("// 包括：业务依赖、同类型接口连接等（按版本和类别分组）")
        
        # 按版本分组依赖关系
        version_dep_groups = {}
        for dep in dependencies:
            # 获取source和target接口的版本信息
            source_interface = dep.get('source_interface', {})
            target_interface = dep.get('target_interface', {})
            source_version = self._normalize_version((source_interface.get('version', '') or '').strip())
            target_version = self._normalize_version((target_interface.get('version', '') or '').strip())
            
            # 确保依赖关系在同一版本内（不同版本的接口不能有依赖关系）
            if source_version and target_version and source_version != target_version:
                print(f"警告：跳过跨版本依赖关系: {source_version} -> {target_version}")
                continue
            
            version_key = source_version or target_version or 'no_version'
            if version_key not in version_dep_groups:
                version_dep_groups[version_key] = []
            version_dep_groups[version_key].append(dep)
        
        # 按版本分组输出依赖关系
        for version_key, version_deps in version_dep_groups.items():
            cypher_lines.append(f"// 版本: {version_key} 的依赖关系 (共 {len(version_deps)} 个)")
            
            # 按依赖类型分组输出（便于查看）
            dep_type_groups = {}
            for dep in version_deps:
                dep_type = dep.get('type', 'unknown')
                if dep_type not in dep_type_groups:
                    dep_type_groups[dep_type] = []
                dep_type_groups[dep_type].append(dep)
            
            for dep_type, deps in dep_type_groups.items():
                cypher_lines.append(f"//  依赖类型: {dep_type} (共 {len(deps)} 个)")
                
                for dep in deps:
                    source_id = dep['source']
                    target_id = dep['target']
                    description = (dep.get('description', '') or '').replace('"', '\\"').replace("'", "\\'")
                    dependency_path = (dep.get('dependency_path', '') or '').replace('"', '\\"').replace("'", "\\'")
                    confidence = dep.get('confidence', 0.5)
                    
                    cypher_lines.append(f"""MATCH (source{source_id}:APIInterface {{id: "{source_id}", project_id: {project_id}}})
MATCH (target{target_id}:APIInterface {{id: "{target_id}", project_id: {project_id}}})
MERGE (source{source_id})-[r:DEPENDS_ON {{
    type: "{dep_type}",
    description: "{description}",
    dependency_path: "{dependency_path}",
    confidence: {confidence}
}}]->(target{target_id});""")
                    
                    cypher_lines.append("")
                
                cypher_lines.append("")
        
        return "\n".join(cypher_lines)
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _store_to_neo4j_incremental(self, interfaces: List[Dict[str, Any]], dependencies: List[Dict[str, Any]], project_id: int):
        """增量存储接口和依赖关系到Neo4j（用于实时更新）"""
        print(f"开始存储到Neo4j: {len(interfaces)} 个接口，{len(dependencies)} 个依赖关系")
        try:
            session = self.db_service._get_neo4j_session()
            if not session:
                print(f"✗ 错误：无法获取Neo4j会话")
                return
            
            with session as neo4j_session:
                if not neo4j_session:
                    print(f"✗ 错误：Neo4j会话无效")
                    return
                # 创建接口节点（如果不存在则创建，存在则更新）
                for interface in interfaces:
                    interface_id = self._get_interface_id(interface)
                    crud_type = interface.get('_crud_type', self._extract_crud_type(interface))
                    category = self._get_interface_category(interface)
                    
                    neo4j_session.run("""
                        MERGE (api:APIInterface {
                            id: $id,
                            project_id: $project_id
                        })
                        SET api.name = $name,
                            api.method = $method,
                            api.url = $url,
                            api.path = $path,
                            api.service = $service,
                            api.description = $description,
                            api.crud_type = $crud_type,
                            api.version = $version,
                            api.category = $category
                    """,
                        id=interface_id,
                        project_id=project_id,
                        name=interface.get('name', ''),
                        method=interface.get('method', ''),
                        url=interface.get('url', ''),
                        path=interface.get('path', '') or '',
                        service=interface.get('service', ''),
                        description=interface.get('description', ''),
                        crud_type=crud_type,
                        version=interface.get('version', ''),
                        category=category
                    )
                
                # 创建依赖关系边（确保所有涉及的接口节点都已创建）
                edges_created = 0
                edges_failed = 0
                
                # 首先，确保所有依赖关系中的接口节点都已创建
                interface_ids_in_deps = set()
                for dep in dependencies:
                    source_interface = dep.get('source_interface', {})
                    target_interface = dep.get('target_interface', {})
                    
                    # 从依赖关系中获取source和target ID
                    source_id = dep.get('source')
                    target_id = dep.get('target')
                    
                    if source_id:
                        interface_ids_in_deps.add(str(source_id))
                    if target_id:
                        interface_ids_in_deps.add(str(target_id))
                    
                    # 如果source_id或target_id不存在，尝试从接口对象中生成
                    if not source_id and source_interface:
                        source_id = self._get_interface_id(source_interface)
                        dep['source'] = source_id
                        interface_ids_in_deps.add(str(source_id))
                    if not target_id and target_interface:
                        target_id = self._get_interface_id(target_interface)
                        dep['target'] = target_id
                        interface_ids_in_deps.add(str(target_id))
                    
                    # 确保source_interface和target_interface也在interfaces列表中（如果不在，需要创建节点）
                    if source_interface:
                        source_id_from_iface = self._get_interface_id(source_interface)
                        if source_id_from_iface not in [self._get_interface_id(iface) for iface in interfaces]:
                            # 如果source_interface不在interfaces列表中，添加它
                            interfaces.append(source_interface)
                    if target_interface:
                        target_id_from_iface = self._get_interface_id(target_interface)
                        if target_id_from_iface not in [self._get_interface_id(iface) for iface in interfaces]:
                            # 如果target_interface不在interfaces列表中，添加它
                            interfaces.append(target_interface)
                
                # 再次确保所有涉及的接口节点都已创建
                for interface in interfaces:
                    interface_id = self._get_interface_id(interface)
                    crud_type = interface.get('_crud_type', self._extract_crud_type(interface))
                    category = self._get_interface_category(interface)
                    
                    neo4j_session.run("""
                        MERGE (api:APIInterface {
                            id: $id,
                            project_id: $project_id
                        })
                        SET api.name = $name,
                            api.method = $method,
                            api.url = $url,
                            api.path = $path,
                            api.service = $service,
                            api.description = $description,
                            api.crud_type = $crud_type,
                            api.version = $version,
                            api.category = $category
                    """,
                        id=interface_id,
                        project_id=project_id,
                        name=interface.get('name', ''),
                        method=interface.get('method', ''),
                        url=interface.get('url', ''),
                        path=interface.get('path', '') or '',
                        service=interface.get('service', ''),
                        description=interface.get('description', ''),
                        crud_type=crud_type,
                        version=interface.get('version', ''),
                        category=category
                    )
                
                # 现在创建依赖关系边
                for dep in dependencies:
                    try:
                        source_interface = dep.get('source_interface', {})
                        target_interface = dep.get('target_interface', {})
                        source_version = self._normalize_version((source_interface.get('version', '') or '').strip())
                        target_version = self._normalize_version((target_interface.get('version', '') or '').strip())
                        
                        # 确保依赖关系在同一版本内
                        if source_version and target_version and source_version != target_version:
                            print(f"跳过跨版本依赖关系: {source_version} -> {target_version}")
                            edges_failed += 1
                            continue
                        
                        # 统一使用_get_interface_id方法生成ID，确保格式一致
                        source_id = dep.get('source')
                        target_id = dep.get('target')
                        
                        # 如果依赖关系中的source/target ID不存在，从接口对象中生成
                        if not source_id and source_interface:
                            source_id = self._get_interface_id(source_interface)
                        if not target_id and target_interface:
                            target_id = self._get_interface_id(target_interface)
                        
                        if not source_id or not target_id:
                            print(f"警告：依赖关系缺少source或target ID: source={source_id}, target={target_id}, dep={dep}")
                            edges_failed += 1
                            continue
                        
                        # 确保ID格式一致（转换为字符串）
                        source_id = str(source_id)
                        target_id = str(target_id)
                        
                        print(f"创建依赖关系边: {source_id} -> {target_id}")
                        
                        # 使用MERGE确保节点存在，然后创建边
                        # 注意：使用ON CREATE和ON MATCH来确保边被创建
                        result = neo4j_session.run("""
                            MERGE (source:APIInterface {id: $source_id, project_id: $project_id})
                            MERGE (target:APIInterface {id: $target_id, project_id: $project_id})
                            MERGE (source)-[r:DEPENDS_ON]->(target)
                            ON CREATE SET r.type = $dep_type,
                                         r.description = $description,
                                         r.dependency_path = $dependency_path,
                                         r.confidence = $confidence
                            ON MATCH SET r.type = $dep_type,
                                        r.description = $description,
                                        r.dependency_path = $dependency_path,
                                        r.confidence = $confidence
                            RETURN r
                        """,
                            source_id=source_id,
                            target_id=target_id,
                            project_id=project_id,
                            dep_type=dep.get('type', 'unknown'),
                            description=dep.get('description', ''),
                            dependency_path=dep.get('dependency_path', ''),
                            confidence=dep.get('confidence', 0.5)
                        )
                        
                        # 检查是否成功创建
                        record = result.single()
                        if record:
                            edges_created += 1
                            print(f"✓ 成功创建依赖关系边: {source_id} -> {target_id}")
                        else:
                            edges_failed += 1
                            print(f"✗ 警告：未能创建依赖关系边: {source_id} -> {target_id} (查询返回空结果)")
                            # 尝试检查节点是否存在
                            check_result = neo4j_session.run("""
                                MATCH (source:APIInterface {id: $source_id, project_id: $project_id})
                                MATCH (target:APIInterface {id: $target_id, project_id: $project_id})
                                RETURN source.id as source_id, target.id as target_id
                            """, source_id=source_id, target_id=target_id, project_id=project_id)
                            check_record = check_result.single()
                            if check_record:
                                print(f"   节点存在但边创建失败，source_id={source_id}, target_id={target_id}")
                            else:
                                print(f"   节点不存在，source_id={source_id}, target_id={target_id}")
                    except Exception as e:
                        edges_failed += 1
                        print(f"✗ 创建依赖关系边失败: {e}, source_id={source_id if 'source_id' in locals() else 'N/A'}, target_id={target_id if 'target_id' in locals() else 'N/A'}")
                        import traceback
                        traceback.print_exc()
                
                print(f"依赖关系边创建完成: 成功 {edges_created} 个，失败 {edges_failed} 个")
                if edges_created > 0:
                    print(f"✓ 成功创建 {edges_created} 个依赖关系边")
                if edges_failed > 0:
                    print(f"✗ 失败 {edges_failed} 个依赖关系边")
        except Exception as e:
            print(f"增量存储到Neo4j失败: {e}")
            # 不抛出异常，避免影响主流程
    
    def _store_to_neo4j(self, interfaces: List[Dict[str, Any]], dependencies: List[Dict[str, Any]], project_id: int):
        """存储接口和依赖关系到Neo4j，并生成Cypher文件"""
        try:
            # 生成Cypher文件
            cypher_content = self._generate_cypher_file(interfaces, dependencies, project_id)
            
            # 保存Cypher文件到本地（可选）
            import os
            # 获取项目根目录（backend目录）
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cypher_dir = os.path.join(backend_dir, "cypher_files")
            os.makedirs(cypher_dir, exist_ok=True)
            cypher_file_path = os.path.join(cypher_dir, f"project_{project_id}_dependencies.cypher")
            
            try:
                with open(cypher_file_path, 'w', encoding='utf-8') as f:
                    f.write(cypher_content)
                print(f"Cypher文件已保存到: {cypher_file_path}")
            except Exception as e:
                print(f"保存Cypher文件失败: {e}")
            
            # 执行Cypher语句存储到Neo4j
            session = self.db_service._get_neo4j_session()
            
            with session as neo4j_session:
                # 清空旧数据
                neo4j_session.run(
                    "MATCH (n:APIInterface) WHERE n.project_id = $project_id DETACH DELETE n",
                    project_id=project_id
                )
                
                # 收集所有需要创建的接口（包括依赖关系中的接口）
                all_interfaces_to_create = {}
                seen_interface_ids = set()
                
                # 首先添加传入的interfaces列表中的接口
                for interface in interfaces:
                    interface_id = self._get_interface_id(interface)
                    if interface_id not in seen_interface_ids:
                        seen_interface_ids.add(interface_id)
                        all_interfaces_to_create[interface_id] = interface
                
                # 从依赖关系中添加source和target接口
                for dep in dependencies:
                    source_interface = dep.get('source_interface', {})
                    target_interface = dep.get('target_interface', {})
                    
                    if source_interface:
                        source_id = self._get_interface_id(source_interface)
                        if source_id not in seen_interface_ids:
                            seen_interface_ids.add(source_id)
                            all_interfaces_to_create[source_id] = source_interface
                    
                    if target_interface:
                        target_id = self._get_interface_id(target_interface)
                        if target_id not in seen_interface_ids:
                            seen_interface_ids.add(target_id)
                            all_interfaces_to_create[target_id] = target_interface
                
                # 创建所有去重后的接口节点（只创建一次）
                print(f"准备创建 {len(all_interfaces_to_create)} 个去重后的接口节点到Neo4j")
                for interface_id, interface in all_interfaces_to_create.items():
                    crud_type = interface.get('_crud_type', self._extract_crud_type(interface))
                    category = self._get_interface_category(interface)
                    
                    neo4j_session.run("""
                        MERGE (api:APIInterface {
                            id: $id,
                            project_id: $project_id
                        })
                        SET api.name = $name,
                            api.method = $method,
                            api.url = $url,
                            api.path = $path,
                            api.service = $service,
                            api.description = $description,
                            api.crud_type = $crud_type,
                            api.version = $version,
                            api.category = $category
                    """,
                        id=interface_id,
                        project_id=project_id,
                        name=interface.get('name', ''),
                        method=interface.get('method', ''),
                        url=interface.get('url', ''),
                        path=interface.get('path', '') or '',
                        service=interface.get('service', ''),
                        description=interface.get('description', ''),
                        crud_type=crud_type,
                        version=interface.get('version', ''),
                        category=category
                    )
                
                # 创建依赖关系边（确保只在同一版本内建立依赖关系）
                edges_created = 0
                edges_failed = 0
                
                # 现在创建依赖关系边
                for dep in dependencies:
                    try:
                        # 获取source和target接口的版本信息
                        source_interface = dep.get('source_interface', {})
                        target_interface = dep.get('target_interface', {})
                        source_version = self._normalize_version((source_interface.get('version', '') or '').strip())
                        target_version = self._normalize_version((target_interface.get('version', '') or '').strip())
                        
                        # 确保依赖关系在同一版本内（不同版本的接口不能有依赖关系）
                        if source_version and target_version and source_version != target_version:
                            print(f"警告：跳过跨版本依赖关系存储到Neo4j: {source_version} -> {target_version}")
                            edges_failed += 1
                            continue
                        
                        # 统一使用_get_interface_id方法生成ID，确保格式一致
                        source_id = dep.get('source')
                        target_id = dep.get('target')
                        
                        # 如果依赖关系中的source/target ID不存在，从接口对象中生成
                        if not source_id and source_interface:
                            source_id = self._get_interface_id(source_interface)
                        if not target_id and target_interface:
                            target_id = self._get_interface_id(target_interface)
                        
                        if not source_id or not target_id:
                            print(f"警告：依赖关系缺少source或target ID: source={source_id}, target={target_id}, dep={dep}")
                            edges_failed += 1
                            continue
                        
                        # 确保ID格式一致（转换为字符串）
                        source_id = str(source_id)
                        target_id = str(target_id)
                        
                        # 使用MERGE确保节点存在，然后创建边
                        result = neo4j_session.run("""
                            MERGE (source:APIInterface {id: $source_id, project_id: $project_id})
                            MERGE (target:APIInterface {id: $target_id, project_id: $project_id})
                        MERGE (source)-[r:DEPENDS_ON {
                            type: $dep_type,
                            description: $description,
                            dependency_path: $dependency_path,
                            confidence: $confidence
                        }]->(target)
                            RETURN r
                    """,
                            source_id=source_id,
                            target_id=target_id,
                        project_id=project_id,
                            dep_type=dep.get('type', 'unknown'),
                            description=dep.get('description', ''),
                        dependency_path=dep.get('dependency_path', ''),
                        confidence=dep.get('confidence', 0.5)
                    )
                
                        # 检查是否成功创建
                        record = result.single()
                        if record:
                            edges_created += 1
                            print(f"✓ 成功创建依赖关系边: {source_id} -> {target_id}")
                        else:
                            edges_failed += 1
                            print(f"✗ 警告：未能创建依赖关系边: {source_id} -> {target_id} (查询返回空结果)")
                    except Exception as e:
                        edges_failed += 1
                        print(f"✗ 创建依赖关系边失败: {e}, source_id={source_id if 'source_id' in locals() else 'N/A'}, target_id={target_id if 'target_id' in locals() else 'N/A'}")
                        import traceback
                        traceback.print_exc()
                
                print(f"依赖关系边创建完成: 成功 {edges_created} 个，失败 {edges_failed} 个")
                if edges_created > 0:
                    print(f"✓ 成功创建 {edges_created} 个依赖关系边")
                if edges_failed > 0:
                    print(f"✗ 失败 {edges_failed} 个依赖关系边")
            
            print(f"已成功存储 {len(interfaces)} 个接口节点和 {edges_created} 个依赖关系到Neo4j")
            
        except Exception as e:
            print(f"存储到Neo4j失败: {e}")
            import traceback
            traceback.print_exc()
            # 不抛出异常，继续执行
    
    def get_dependencies_from_neo4j(self, project_id: int) -> Dict[str, Any]:
        """从Neo4j获取接口依赖关系"""
        try:
            session = self.db_service._get_neo4j_session()
            
            with session as neo4j_session:
                # 获取所有接口节点
                nodes_result = neo4j_session.run("""
                    MATCH (api:APIInterface {project_id: $project_id})
                    RETURN api.id as id, api.name as name, api.method as method, 
                           api.url as url, api.crud_type as crud_type
                """, project_id=project_id)
                
                nodes = []
                seen_node_ids = set()  # 用于去重，确保每个接口ID只出现一次
                for record in nodes_result:
                    # 确保ID格式为字符串，与边的source/target格式一致
                    node_id = str(record['id']) if record['id'] else None
                    if node_id and node_id not in seen_node_ids:
                        seen_node_ids.add(node_id)
                        node_name = record.get('name', '')
                        node_url = record.get('url', '')
                        # 节点标签显示：接口名称 + URL
                        label = f"{node_name}\n{node_url}" if node_url else node_name
                        nodes.append({
                            'id': node_id,
                            'name': node_name,
                            'url': node_url,
                            'method': record.get('method', ''),
                            'type': record.get('crud_type', 'UNKNOWN'),
                            'label': label  # 添加label字段用于显示
                        })
                
                # 获取所有依赖关系
                edges_result = neo4j_session.run("""
                    MATCH (source:APIInterface {project_id: $project_id})-[r:DEPENDS_ON]->(target:APIInterface {project_id: $project_id})
                    RETURN source.id as source, target.id as target, 
                           r.type as type, r.description as description,
                           r.dependency_path as dependency_path, r.confidence as confidence
                """, project_id=project_id)
                
                edges = []
                for record in edges_result:
                    source_id = str(record['source']) if record['source'] else None
                    target_id = str(record['target']) if record['target'] else None
                    
                    if source_id and target_id:
                        edges.append({
                            'source': source_id,
                            'target': target_id,
                            'type': record.get('type', 'unknown'),
                            'description': record.get('description', ''),
                            'dependency_path': record.get('dependency_path', ''),
                            'confidence': float(record.get('confidence', 0.5))
                        })
                
                # 验证边的source和target是否都在nodes中
                node_ids_set = {node['id'] for node in nodes}
                valid_edges = []
                invalid_edges = []
                
                for edge in edges:
                    source_id = edge.get('source')
                    target_id = edge.get('target')
                    if source_id in node_ids_set and target_id in node_ids_set:
                        valid_edges.append(edge)
                    else:
                        invalid_edges.append(edge)
                        if source_id not in node_ids_set:
                            print(f"警告：边的source节点不存在于nodes中: {source_id}")
                        if target_id not in node_ids_set:
                            print(f"警告：边的target节点不存在于nodes中: {target_id}")
                
                # 只返回有效的边
                edges = valid_edges
                
                print(f"从Neo4j获取到 {len(nodes)} 个节点和 {len(edges)} 条有效边（过滤掉 {len(invalid_edges)} 条无效边）")
                if len(edges) > 0:
                    print(f"前5条边示例:")
                    for i, edge in enumerate(edges[:5], 1):
                        print(f"  {i}. {edge.get('source', 'N/A')} -> {edge.get('target', 'N/A')} (类型: {edge.get('type', 'N/A')})")
                elif len(nodes) > 0:
                    print(f"⚠️  警告：有 {len(nodes)} 个节点，但没有有效边，可能依赖关系未正确存储或ID不匹配")
                    print(f"节点ID示例（前5个）: {list(node_ids_set)[:5]}")
                    if invalid_edges:
                        print(f"无效边示例（前3个）:")
                        for i, edge in enumerate(invalid_edges[:3], 1):
                            print(f"  {i}. {edge.get('source', 'N/A')} -> {edge.get('target', 'N/A')}")
                
                # 构建依赖链（从edges构建）
                dependency_chains = []
                if edges and len(edges) > 0:
                    # 构建邻接表
                    graph = {}
                    for edge in edges:
                        source = edge['source']
                        target = edge['target']
                        if source not in graph:
                            graph[source] = []
                        graph[source].append(target)
                    
                    # 查找所有路径（深度优先搜索）
                    def dfs(current_node, path, visited, max_depth=10):
                        """深度优先搜索查找路径"""
                        if len(path) > max_depth:
                            return
                        
                        # 如果路径长度>=2，保存为一条调用链
                        if len(path) >= 2:
                            chain = path.copy()
                            dependency_chains.append(chain)
                        
                        # 继续搜索
                        if current_node in graph:
                            for next_node in graph[current_node]:
                                if next_node not in visited:
                                    visited.add(next_node)
                                    path.append(next_node)
                                    dfs(next_node, path, visited, max_depth)
                                    path.pop()
                                    visited.remove(next_node)
                    
                    # 从每个节点开始搜索
                    for node in nodes:
                        node_id = node['id']
                        if node_id in graph:
                            visited = {node_id}
                            dfs(node_id, [node_id], visited)
                    
                    # 去重（保留最长的链）
                    unique_chains = []
                    seen_chains = set()
                    for chain in dependency_chains:
                        chain_str = '->'.join(chain)
                        if chain_str not in seen_chains:
                            seen_chains.add(chain_str)
                            unique_chains.append(chain)
                    
                    dependency_chains = unique_chains
                    print(f"构建了 {len(dependency_chains)} 条依赖链")
                
                return {
                    'nodes': nodes,
                    'edges': edges,
                    'dependency_chains': dependency_chains
                }
        except Exception as e:
            print(f"从Neo4j获取依赖关系失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'nodes': [],
                'edges': [],
                'dependency_chains': []
            }
    
    def _get_login_interface(self, project_id: int = None) -> Dict[str, Any]:
        """获取登录接口配置（不再从测试环境配置中获取手机号和密码）"""
        
        # 默认值
        phone = "{{PHONE}}"
        password = "{{PWD}}"
        base_url = "https://test-xj.kingsmith.com.cn"
        
        login_interface = {
            "title": "用手机号和密码登录",
            "base_url": base_url,
            "version": "V0.1",
            "path": "/V0.1/index.php",
            "url": f"{base_url}/V0.1/index.php",
            "method": "POST",
            "headers": {
                "language": "zh_CN",
                "appver": "5.9.11",
                "country": "AE",
                "timeZoneName": "CST",
                "timeZoneOffset": "8",
                "content-type": "application/json"
            },
            "request_body": {
                "service": "user.login",
                "pwd": password,
                "phone": phone,
                "lng": "-7946048961065881",
                "lat": "-8368059298647897",
                "brand": "",
                "IMEI": ""
            },
            "body": {
                "service": "user.login",
                "pwd": password,
                "phone": phone,
                "lng": "-7946048961065881",
                "lat": "-8368059298647897",
                "brand": "",
                "IMEI": ""
            },
            "response_extract": {
                "token": "token"  # 从响应体中提取token字段
            },
            "_crud_type": "LOGIN"
        }
        
        # 确保登录接口有唯一的ID
        login_interface['id'] = self._get_interface_id(login_interface)
        login_interface['interface_id'] = login_interface['id']
        
        return login_interface
    
    def _should_exclude_interface(self, interface: Dict[str, Any]) -> bool:
        """判断是否应该排除该接口（账号、oauth、小度、阿里云相关）"""
        category = self._get_interface_category(interface)
        exclude_categories = ['account', 'oauth', 'xiaodu', 'aliyun']
        return category in exclude_categories
    
    def _extract_token_from_response(self, response_body: Any) -> Optional[str]:
        """从响应体中提取token字段的值（支持多种路径：data.info.token, data.token, token等）"""
        if not response_body:
            return None
        
        try:
            if isinstance(response_body, str):
                response_data = json.loads(response_body)
            else:
                response_data = response_body
            
            # 尝试从不同路径提取token
            if isinstance(response_data, dict):
                # 1. 查找data.info.token（最常用路径）
                if 'data' in response_data and isinstance(response_data['data'], dict):
                    if 'info' in response_data['data'] and isinstance(response_data['data']['info'], dict):
                        if 'token' in response_data['data']['info']:
                            return str(response_data['data']['info']['token'])
                    # 2. 查找data.token
                    if 'token' in response_data['data']:
                        return str(response_data['data']['token'])
                # 3. 直接查找token字段
                if 'token' in response_data:
                    return str(response_data['token'])
                # 4. 查找result.token
                if 'result' in response_data and isinstance(response_data['result'], dict):
                    if 'token' in response_data['result']:
                        return str(response_data['result']['token'])
        except Exception as e:
            print(f"提取token失败: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def _add_token_to_headers(self, interface: Dict[str, Any], token: str) -> Dict[str, Any]:
        """将token添加到接口的请求头中（token或authorized字段）"""
        # 创建接口的副本
        interface_copy = interface.copy()
        
        # 获取headers
        headers = interface_copy.get('headers', {})
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except:
                headers = {}
        
        # 添加token到headers（优先使用token字段，如果没有则使用authorized）
        if 'token' not in headers:
            headers['token'] = f"{{{{TOKEN}}}}"
        if 'authorized' not in headers:
            headers['authorized'] = f"{{{{TOKEN}}}}"
        
        interface_copy['headers'] = headers
        return interface_copy
    
    def _store_scenarios_to_db_and_redis(self, project_id: int, scenarios: List[Dict[str, Any]], interfaces: List[Dict[str, Any]]):
        """存储场景用例集到数据库和Redis，包含依赖链中的接口列表
        每个场景用例集的第一个用例是登录接口，后续接口会排除账号、oauth、小度、阿里云相关接口
        """
        try:
            # 获取登录接口配置（从测试环境配置中获取手机号和密码）
            login_interface = self._get_login_interface(project_id)
            
            print(f"开始存储 {len(scenarios)} 个场景用例集...")
            
            # 存储到数据库
            stored_count = 0
            skipped_count = 0
            for scenario in scenarios:
                scenario_name = scenario.get('scenario_name', '')
                if not scenario_name:
                    print(f"跳过场景（名称为空）")
                    skipped_count += 1
                    continue
                
                # 将依赖链中的接口ID转换为实际的接口信息
                # dependency_chain中存储的是数据库ID（字符串格式）
                dependency_chain = scenario.get('dependency_chain', [])
                
                # 过滤掉账号、oauth、小度、阿里云相关的接口，以及响应体为空或空{}的接口
                filtered_interfaces = []
                for interface_db_id in dependency_chain:
                    # 通过数据库ID匹配接口
                    matched = False
                    for iface in interfaces:
                        db_id = iface.get('interface_id') or iface.get('id')
                        if db_id and str(db_id) == str(interface_db_id):
                            # 检查是否应该排除（账号相关等）
                            if self._should_exclude_interface(iface):
                                continue
                            # 不再检查响应体是否有效，允许响应体为空的接口
                            # 响应体为空时，后续会使用默认值
                            filtered_interfaces.append(iface)
                            matched = True
                            break
                
                    if not matched:
                        # 如果通过数据库ID匹配失败，尝试通过接口ID匹配（兼容旧数据）
                        for iface in interfaces:
                            iface_id = self._get_interface_id(iface)
                            if str(iface_id) == str(interface_db_id):
                                if self._should_exclude_interface(iface):
                                    continue
                                # 不再检查响应体是否有效，允许响应体为空的接口
                                filtered_interfaces.append(iface)
                                break
                
                # 如果过滤后没有接口，尝试从dependency_chain中直接使用（可能包含被过滤的接口）
                if not filtered_interfaces:
                    print(f"场景 {scenario_name} 过滤后没有接口，尝试使用dependency_chain中的接口")
                    # 如果dependency_chain不为空，直接使用它（不进行过滤）
                    if dependency_chain:
                        print(f"场景 {scenario_name} 使用dependency_chain中的 {len(dependency_chain)} 个接口（不过滤）")
                        # 直接从interfaces中查找这些接口，不过滤
                        for interface_db_id in dependency_chain:
                            for iface in interfaces:
                                db_id = iface.get('interface_id') or iface.get('id')
                                if db_id and str(db_id) == str(interface_db_id):
                                    filtered_interfaces.append(iface)
                                    break
                    
                    # 如果还是没有接口，跳过
                    if not filtered_interfaces:
                        print(f"场景 {scenario_name} 完全没有接口，跳过")
                        skipped_count += 1
                    continue
                
                # 构建最终的依赖链：登录接口 + 过滤后的接口（按依赖链顺序）
                # 登录接口使用特殊标识
                final_dependency_chain = ['__LOGIN_INTERFACE__']
                
                # 如果dependency_chain不为空，按照dependency_chain中的顺序添加接口（保持CRUD顺序）
                if dependency_chain:
                    for interface_db_id in dependency_chain:
                        # 检查这个接口是否在过滤后的接口列表中
                        found = False
                        for iface in filtered_interfaces:
                            db_id = iface.get('interface_id') or iface.get('id')
                            if db_id and str(db_id) == str(interface_db_id):
                                final_dependency_chain.append(str(db_id))
                                found = True
                                break
                        if not found:
                            print(f"警告：场景 {scenario_name} 中dependency_chain的接口ID {interface_db_id} 不在过滤后的接口列表中")
                else:
                    # 如果dependency_chain为空，直接使用filtered_interfaces中的所有接口
                    print(f"警告：场景 {scenario_name} dependency_chain为空，使用filtered_interfaces中的所有接口")
                    for iface in filtered_interfaces:
                        db_id = iface.get('interface_id') or iface.get('id')
                        if db_id:
                            final_dependency_chain.append(str(db_id))
                
                # 检查是否已存在
                existing_suite = self.db.query(TestCaseSuite).filter(
                    TestCaseSuite.project_id == project_id,
                    TestCaseSuite.name == scenario_name
                ).first()
                
                if existing_suite:
                    # 更新现有记录
                    existing_suite.description = scenario.get('analysis_summary', '')
                    # 使用test_case_ids字段存储依赖链中的接口ID列表（JSON格式）
                    existing_suite.test_case_ids = json.dumps(final_dependency_chain, ensure_ascii=False)
                    print(f"更新场景: {scenario_name} (接口数: {len(final_dependency_chain)})")
                else:
                    # 创建新记录
                    new_suite = TestCaseSuite(
                        project_id=project_id,
                        name=scenario_name,
                        description=scenario.get('analysis_summary', ''),
                        test_case_ids=json.dumps(final_dependency_chain, ensure_ascii=False)  # 存储依赖链中的接口ID
                    )
                    self.db.add(new_suite)
                    print(f"创建场景: {scenario_name} (接口数: {len(final_dependency_chain)})")
                    stored_count += 1
            
            self.db.commit()
            print(f"数据库存储完成: 创建 {stored_count} 个，跳过 {skipped_count} 个")
            
            # 存储到Redis（包含登录接口信息）
            redis_key = f"project:{project_id}:scenarios"
            scenarios_data = {
                'scenarios': scenarios,
                'total_count': len(scenarios),
                'interfaces_count': len(interfaces),
                'login_interface': login_interface  # 存储登录接口配置
            }
            redis_client.set(redis_key, json.dumps(scenarios_data, ensure_ascii=False), ex=86400 * 30)  # 30天过期
            
            print(f"已存储 {len(scenarios)} 个场景用例集到数据库和Redis（已添加登录接口并排除账号相关接口）")
            
        except Exception as e:
            print(f"存储场景用例集失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _run_async_in_sync_context(self, coro):
        """
        在同步上下文中安全地运行异步协程
        适用于 Celery worker 等没有事件循环或事件循环已关闭的环境
        """
        loop = None
        try:
            # 尝试获取当前事件循环
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed() or loop.is_running():
                    # 如果事件循环已关闭或正在运行，创建新的事件循环
                    loop = None
            except RuntimeError:
                # 如果没有事件循环，继续创建新的
                pass
            
            # 如果没有可用的事件循环，创建新的
            if loop is None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(coro)
                finally:
                    # 关闭我们创建的事件循环
                    try:
                        # 取消所有待处理的任务
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()
                        # 等待所有任务完成或取消
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception:
                        pass
                    finally:
                        if not loop.is_closed():
                            loop.close()
            else:
                # 使用现有的事件循环
                return loop.run_until_complete(coro)
        except Exception as e:
            print(f"运行异步函数时出错: {e}")
            raise
    
    async def _store_to_chromadb(self, interfaces: List[Dict[str, Any]], dependencies: List[Dict[str, Any]], project_id: int):
        """将依赖分析结果同步到ChromaDB向量数据库"""
        try:
            # 准备要存储到ChromaDB的数据
            chunks = []
            metadata_list = []
            
            # 为每个接口创建向量化文本
            for interface in interfaces:
                interface_id = interface.get('id') or interface.get('interface_id') or self._get_interface_id(interface)
                name = interface.get('name', '') or interface.get('title', '')
                method = interface.get('method', 'GET')
                path = interface.get('path', '') or interface.get('url', '')
                description = interface.get('description', '')
                version = interface.get('version', '')
                category = self._get_interface_category(interface)
                
                # 构建接口的文本描述（用于向量化）
                interface_text = f"""
接口名称: {name}
请求方法: {method}
接口路径: {path}
接口描述: {description}
接口版本: {version}
接口分类: {category}
                """.strip()
                
                chunks.append(interface_text)
                
                # 构建元数据
                metadata = {
                    'type': 'api_interface',
                    'project_id': project_id,
                    'interface_id': str(interface_id),
                    'name': name,
                    'method': method,
                    'path': path,
                    'version': version,
                    'category': category
                }
                metadata_list.append(metadata)
            
            # 为每个依赖关系创建向量化文本
            for dep in dependencies:
                source_id = dep.get('source', '')
                target_id = dep.get('target', '')
                dep_type = dep.get('type', 'unknown')
                description = dep.get('description', '')
                dependency_path = dep.get('dependency_path', '')
                confidence = dep.get('confidence', 0.5)
                
                # 构建依赖关系的文本描述
                dependency_text = f"""
依赖关系类型: {dep_type}
源接口ID: {source_id}
目标接口ID: {target_id}
依赖描述: {description}
依赖路径: {dependency_path}
置信度: {confidence}
                """.strip()
                
                chunks.append(dependency_text)
                
                # 构建元数据
                metadata = {
                    'type': 'api_dependency',
                    'project_id': project_id,
                    'source_id': str(source_id),
                    'target_id': str(target_id),
                    'dep_type': dep_type,
                    'confidence': float(confidence)
                }
                metadata_list.append(metadata)
            
            if chunks:
                # 使用VectorService存储到ChromaDB
                # 注意：ChromaDB使用document_id来标识，这里使用project_id作为document_id
                await self.vector_service.add_documents(
                    document_id=project_id,
                    chunks=chunks,
                    metadata_list=metadata_list
                )
                print(f"已同步 {len(chunks)} 条依赖分析数据到ChromaDB（包含 {len(interfaces)} 个接口和 {len(dependencies)} 个依赖关系）")
            else:
                print("没有数据需要同步到ChromaDB")
                
        except Exception as e:
            print(f"同步到ChromaDB失败: {e}")
            import traceback
            traceback.print_exc()
            # 不抛出异常，避免影响主流程

