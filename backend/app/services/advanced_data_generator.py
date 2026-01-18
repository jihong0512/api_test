from typing import Dict, Any, List, Optional, Union
from faker import Faker
import json
import random
import re
from datetime import datetime, timedelta
from enum import Enum

from app.services.smart_test_data_generator import SmartTestDataGenerator


class DataType(Enum):
    """数据类型枚举"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


class TestDataCaseType(Enum):
    """测试数据类型"""
    POSITIVE = "positive"  # 正向用例
    NEGATIVE = "negative"  # 负向用例
    BOUNDARY = "boundary"  # 边界值
    INVALID = "invalid"  # 无效数据


class AdvancedDataGenerator(SmartTestDataGenerator):
    """高级数据生成器：支持类型约束、参数化驱动、依赖处理"""
    
    def __init__(self):
        super().__init__()
        self.case_types = {
            TestDataCaseType.POSITIVE: self._generate_positive_data,
            TestDataCaseType.NEGATIVE: self._generate_negative_data,
            TestDataCaseType.BOUNDARY: self._generate_boundary_data,
            TestDataCaseType.INVALID: self._generate_invalid_data
        }
    
    def generate_by_schema(
        self,
        schema: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        case_type: TestDataCaseType = TestDataCaseType.POSITIVE
    ) -> Any:
        """
        根据JSON Schema生成数据
        
        Args:
            schema: JSON Schema定义
            constraints: 额外约束（format, pattern, min/max length等）
            case_type: 测试数据类型
        
        Returns:
            生成的数据
        """
        data_type = schema.get("type", "string")
        constraints = constraints or {}
        
        # 合并schema中的约束
        constraints.update({
            "format": schema.get("format"),
            "pattern": schema.get("pattern"),
            "minLength": schema.get("minLength"),
            "maxLength": schema.get("maxLength"),
            "minimum": schema.get("minimum"),
            "maximum": schema.get("maximum"),
            "enum": schema.get("enum"),
            "default": schema.get("default")
        })
        
        # 根据类型生成
        if data_type == DataType.STRING.value:
            return self._generate_string_value(constraints, case_type)
        elif data_type == DataType.INTEGER.value or data_type == DataType.NUMBER.value:
            return self._generate_number_value(constraints, case_type, data_type == DataType.INTEGER.value)
        elif data_type == DataType.BOOLEAN.value:
            return self._generate_boolean_value(constraints, case_type)
        elif data_type == DataType.ARRAY.value:
            return self._generate_array_value(schema, constraints, case_type)
        elif data_type == DataType.OBJECT.value:
            return self._generate_object_value(schema, constraints, case_type)
        else:
            return None
    
    def _generate_string_value(
        self,
        constraints: Dict[str, Any],
        case_type: TestDataCaseType
    ) -> str:
        """生成字符串值"""
        min_length = constraints.get("minLength", 1)
        max_length = constraints.get("maxLength", 100)
        pattern = constraints.get("pattern")
        format_type = constraints.get("format")
        enum_values = constraints.get("enum")
        default = constraints.get("default")
        
        if case_type == TestDataCaseType.POSITIVE:
            # 正向用例：生成有效数据
            if default is not None:
                return default
            if enum_values:
                return random.choice(enum_values)
            if format_type:
                return self._generate_by_format(format_type)
            if pattern:
                return self._generate_by_pattern(pattern, min_length, max_length)
            return self.faker.text(max_nb_chars=max_length)[:max_length]
        
        elif case_type == TestDataCaseType.NEGATIVE:
            # 负向用例：生成无效数据
            if enum_values:
                # 返回不在枚举中的值
                invalid = "invalid_enum_value"
                while invalid in enum_values:
                    invalid = self.faker.word()
                return invalid
            if format_type:
                # 格式错误
                return self.faker.text(max_nb_chars=10)
            if pattern:
                # 不匹配模式
                return "invalid_pattern_123"
            # 长度不符合要求
            if min_length > 1:
                return ""  # 太短
            else:
                return "x" * (max_length + 1)  # 太长
        
        elif case_type == TestDataCaseType.BOUNDARY:
            # 边界值
            if min_length > 0:
                # 最小长度
                return "x" * min_length
            elif max_length < float('inf'):
                # 最大长度
                return "x" * max_length
            else:
                return "x" * 50
        
        else:  # INVALID
            return None  # null值（如果允许）
    
    def _generate_number_value(
        self,
        constraints: Dict[str, Any],
        case_type: TestDataCaseType,
        is_integer: bool = False
    ) -> Union[int, float]:
        """生成数值"""
        minimum = constraints.get("minimum")
        maximum = constraints.get("maximum")
        default = constraints.get("default")
        enum_values = constraints.get("enum")
        
        if case_type == TestDataCaseType.POSITIVE:
            if default is not None:
                return default
            if enum_values:
                return random.choice(enum_values)
            
            min_val = minimum if minimum is not None else (0 if is_integer else 0.0)
            max_val = maximum if maximum is not None else (100 if is_integer else 100.0)
            
            if is_integer:
                return random.randint(int(min_val), int(max_val))
            else:
                return round(random.uniform(float(min_val), float(max_val)), 2)
        
        elif case_type == TestDataCaseType.NEGATIVE:
            # 超出范围
            if minimum is not None:
                return minimum - 1
            elif maximum is not None:
                return maximum + 1
            else:
                return -1  # 负数（如果要求正数）
        
        elif case_type == TestDataCaseType.BOUNDARY:
            # 边界值
            if minimum is not None:
                return minimum
            elif maximum is not None:
                return maximum
            else:
                return 0
        
        else:
            return None
    
    def _generate_boolean_value(
        self,
        constraints: Dict[str, Any],
        case_type: TestDataCaseType
    ) -> bool:
        """生成布尔值"""
        default = constraints.get("default")
        
        if default is not None:
            return default
        
        if case_type == TestDataCaseType.POSITIVE:
            return random.choice([True, False])
        elif case_type == TestDataCaseType.NEGATIVE:
            # 对于布尔值，负向用例可能是None（如果允许）
            return None
        else:
            return random.choice([True, False])
    
    def _generate_array_value(
        self,
        schema: Dict[str, Any],
        constraints: Dict[str, Any],
        case_type: TestDataCaseType
    ) -> List[Any]:
        """生成数组值"""
        items_schema = schema.get("items", {})
        min_items = constraints.get("minItems", schema.get("minItems", 1))
        max_items = constraints.get("maxItems", schema.get("maxItems", 10))
        unique_items = schema.get("uniqueItems", False)
        
        if case_type == TestDataCaseType.POSITIVE:
            count = random.randint(min_items, max_items)
            result = []
            for _ in range(count):
                item = self.generate_by_schema(items_schema, case_type=case_type)
                if unique_items and item in result:
                    # 确保唯一性
                    while item in result:
                        item = self.generate_by_schema(items_schema, case_type=case_type)
                result.append(item)
            return result
        
        elif case_type == TestDataCaseType.NEGATIVE:
            # 数量不符合要求
            if min_items > 0:
                return []  # 空数组（如果要求至少1个）
            else:
                return [None] * (max_items + 1)  # 超出最大数量
        
        elif case_type == TestDataCaseType.BOUNDARY:
            # 边界值
            if min_items > 0:
                return [self.generate_by_schema(items_schema, case_type=TestDataCaseType.POSITIVE)] * min_items
            else:
                return [self.generate_by_schema(items_schema, case_type=TestDataCaseType.POSITIVE)] * max_items
        
        else:
            return []
    
    def _generate_object_value(
        self,
        schema: Dict[str, Any],
        constraints: Dict[str, Any],
        case_type: TestDataCaseType
    ) -> Dict[str, Any]:
        """生成对象值"""
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        
        result = {}
        
        if case_type == TestDataCaseType.POSITIVE:
            # 正向用例：生成所有必需字段，可选字段随机包含
            for prop_name, prop_schema in properties.items():
                if prop_name in required or random.random() > 0.3:  # 70%概率包含可选字段
                    result[prop_name] = self.generate_by_schema(
                        prop_schema,
                        case_type=case_type
                    )
        
        elif case_type == TestDataCaseType.NEGATIVE:
            # 负向用例：缺少必需字段或字段类型错误
            for prop_name, prop_schema in properties.items():
                if prop_name in required:
                    # 缺少必需字段（只包含部分必需字段）
                    if random.random() > 0.5:
                        continue
                # 类型错误
                if prop_schema.get("type") == "string":
                    result[prop_name] = 123  # 应该是字符串，但给数字
                elif prop_schema.get("type") == "number":
                    result[prop_name] = "invalid_number"  # 应该是数字，但给字符串
                else:
                    result[prop_name] = self.generate_by_schema(
                        prop_schema,
                        case_type=TestDataCaseType.POSITIVE
                    )
        
        elif case_type == TestDataCaseType.BOUNDARY:
            # 边界值：只包含必需字段
            for prop_name, prop_schema in properties.items():
                if prop_name in required:
                    result[prop_name] = self.generate_by_schema(
                        prop_schema,
                        case_type=TestDataCaseType.BOUNDARY
                    )
        
        else:
            return {}
        
        return result
    
    def _generate_by_format(self, format_type: str) -> str:
        """根据format生成数据"""
        format_map = {
            "email": self.faker.email,
            "uri": self.faker.url,
            "url": self.faker.url,
            "date-time": lambda: datetime.now().isoformat(),
            "date": lambda: datetime.now().strftime("%Y-%m-%d"),
            "time": lambda: datetime.now().strftime("%H:%M:%S"),
            "ipv4": self.faker.ipv4,
            "ipv6": self.faker.ipv6,
            "uuid": lambda: str(self.faker.uuid4()),
            "phone": self.faker.phone_number,
            "mobile": self.faker.phone_number
        }
        
        generator = format_map.get(format_type.lower())
        if generator:
            return generator()
        return self.faker.word()
    
    def _generate_by_pattern(self, pattern: str, min_length: int, max_length: int) -> str:
        """根据正则表达式模式生成数据"""
        # 简化处理：识别常见的模式
        if "^[0-9]+$" in pattern or r"\d+" in pattern:
            # 纯数字
            return str(random.randint(10 ** (min_length - 1), 10 ** min_length - 1))
        elif "^[a-zA-Z]+$" in pattern or r"[a-zA-Z]+" in pattern:
            # 纯字母
            return self.faker.word()[:max_length]
        elif r"^\+?[1-9]\d{1,14}$" in pattern:
            # 电话号码格式
            return self.faker.phone_number()
        else:
            # 通用：生成随机字符串
            return self.faker.text(max_nb_chars=max_length)[:max_length]
    
    def generate_parametrized_cases(
        self,
        api_schema: Dict[str, Any],
        variable_params: List[str],
        case_types: List[TestDataCaseType] = None
    ) -> List[Dict[str, Any]]:
        """
        生成参数化测试用例（数据驱动）
        
        Args:
            api_schema: API Schema定义
            variable_params: 可变参数列表
            case_types: 测试用例类型列表
        
        Returns:
            参数化测试用例列表
        """
        if case_types is None:
            case_types = [
                TestDataCaseType.POSITIVE,
                TestDataCaseType.NEGATIVE,
                TestDataCaseType.BOUNDARY
            ]
        
        test_cases = []
        
        for case_type in case_types:
            case_data = {}
            
            # 为每个可变参数生成数据
            for param in variable_params:
                param_schema = api_schema.get("properties", {}).get(param, {"type": "string"})
                case_data[param] = self.generate_by_schema(param_schema, case_type=case_type)
            
            test_cases.append({
                "case_type": case_type.value,
                "data": case_data
            })
        
        return test_cases
    
    def generate_pytest_parametrize_code(
        self,
        variable_params: List[str],
        test_cases: List[Dict[str, Any]],
        test_function_name: str = "test_api"
    ) -> str:
        """
        生成pytest.mark.parametrize代码
        
        Args:
            variable_params: 可变参数列表
            test_cases: 测试用例列表
            test_function_name: 测试函数名
        
        Returns:
            Python代码
        """
        # 构建参数名列表
        param_names = ", ".join([f'"{p}"' for p in variable_params])
        
        # 构建测试数据列表
        test_data_values = []
        test_ids = []
        for i, case in enumerate(test_cases):
            values = []
            for param in variable_params:
                value = case["data"].get(param)
                values.append(repr(value))
            test_data_values.append(f"({', '.join(values)})")
            test_ids.append(f'"{case["case_type"]}_{i}"')
        
        # 生成代码
        code = f"""import pytest

@pytest.mark.parametrize({param_names}, [
"""
        
        for i, values in enumerate(test_data_values):
            code += f"    {values},  # {test_cases[i]['case_type']}\n"
        
        code += f"""], ids=[{', '.join(test_ids)}])
def {test_function_name}({', '.join(variable_params)}):
    \"\"\"参数化测试用例\"\"\"
    # 使用参数构建请求
    request_data = {{
"""
        
        for param in variable_params:
            code += f"        \"{param}\": {param},\n"
        
        code += """    }
    
    # 发送请求
    response = send_request(request_data)
    
    # 验证响应
    assert response.status_code == 200
"""
        
        return code









































