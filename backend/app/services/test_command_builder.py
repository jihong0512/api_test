"""
测试执行命令封装服务
生成运行测试套件的标准命令行指令
"""
from typing import List, Dict, Any, Optional
import json
import os


class TestCommandBuilder:
    """测试执行命令构建器"""
    
    def __init__(self):
        self.supported_frameworks = ["httprunner", "pytest", "jmeter"]
    
    def build_test_command(
        self,
        test_case_ids: List[int] = None,
        test_case_files: List[str] = None,
        test_suite_id: int = None,
        test_module: str = None,
        environment: str = None,
        framework: str = "httprunner",
        report_format: str = "allure",
        parallel: bool = False,
        workers: int = 4,
        verbose: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建测试执行命令
        
        Args:
            test_case_ids: 测试用例ID列表
            test_case_files: 测试用例文件路径列表
            test_suite_id: 测试套件ID
            test_module: 测试模块名称
            environment: 测试环境（如test_cn, test_overseas）
            framework: 测试框架（httprunner, pytest, jmeter）
            report_format: 报告格式（allure, junit, html）
            parallel: 是否并行执行
            workers: 并行worker数量
            verbose: 是否显示详细输出
            **kwargs: 其他参数
        
        Returns:
            包含命令和配置的字典
        """
        if framework == "httprunner":
            return self._build_httprunner_command(
                test_case_ids=test_case_ids,
                test_case_files=test_case_files,
                test_suite_id=test_suite_id,
                test_module=test_module,
                environment=environment,
                report_format=report_format,
                parallel=parallel,
                workers=workers,
                verbose=verbose,
                **kwargs
            )
        elif framework == "pytest":
            return self._build_pytest_command(
                test_case_ids=test_case_ids,
                test_case_files=test_case_files,
                test_suite_id=test_suite_id,
                test_module=test_module,
                environment=environment,
                report_format=report_format,
                parallel=parallel,
                workers=workers,
                verbose=verbose,
                **kwargs
            )
        elif framework == "jmeter":
            return self._build_jmeter_command(
                test_case_ids=test_case_ids,
                test_case_files=test_case_files,
                test_suite_id=test_suite_id,
                test_module=test_module,
                environment=environment,
                report_format=report_format,
                **kwargs
            )
        else:
            raise ValueError(f"不支持的测试框架: {framework}")
    
    def _build_httprunner_command(
        self,
        test_case_ids: List[int] = None,
        test_case_files: List[str] = None,
        test_suite_id: int = None,
        test_module: str = None,
        environment: str = None,
        report_format: str = "allure",
        parallel: bool = False,
        workers: int = 4,
        verbose: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """构建HttpRunner测试命令"""
        base_command = "hrun"
        commands = []
        
        # 添加测试文件或目录
        if test_case_files:
            commands.extend(test_case_files)
        elif test_module:
            commands.append(f"tests/{test_module}")
        elif test_case_ids:
            # 如果只有用例ID，需要先导出为文件
            commands.append("tests/")  # 假设用例已导出到tests目录
        else:
            commands.append("tests/")  # 默认运行所有测试
        
        # 环境变量设置
        env_vars = {}
        if environment:
            env_vars["ENV"] = environment
        
        # 报告配置
        if report_format == "allure":
            report_dir = kwargs.get("report_dir", "reports/allure-results")
            commands.extend(["--alluredir", report_dir])
        elif report_format == "html":
            report_dir = kwargs.get("report_dir", "reports/html")
            commands.extend(["--html", report_dir])
        elif report_format == "junit":
            report_file = kwargs.get("report_file", "reports/junit.xml")
            commands.extend(["--junit-xml", report_file])
        
        # 日志配置
        if verbose:
            commands.append("--log-level")
            commands.append("DEBUG")
        else:
            log_dir = kwargs.get("log_dir", "logs")
            commands.extend(["--log-dir", log_dir])
        
        # 并行执行
        if parallel:
            commands.extend(["-n", str(workers)])
        
        # 其他参数
        if kwargs.get("max_failures"):
            commands.extend(["--maxfail", str(kwargs["max_failures"])])
        
        if kwargs.get("markers"):
            commands.extend(["-m", kwargs["markers"]])
        
        # 构建完整命令
        full_command = " ".join([base_command] + commands)
        
        # 环境变量设置命令
        env_command_parts = []
        for key, value in env_vars.items():
            env_command_parts.append(f"{key}={value}")
        
        if env_command_parts:
            env_command = " ".join(env_command_parts) + " " + full_command
        else:
            env_command = full_command
        
        return {
            "framework": "httprunner",
            "base_command": base_command,
            "command": full_command,
            "command_with_env": env_command,
            "commands_array": [base_command] + commands,
            "environment_vars": env_vars,
            "report_config": {
                "format": report_format,
                "output": report_dir if report_format != "junit" else report_file
            },
            "parallel": parallel,
            "workers": workers if parallel else 1
        }
    
    def _build_pytest_command(
        self,
        test_case_ids: List[int] = None,
        test_case_files: List[str] = None,
        test_suite_id: int = None,
        test_module: str = None,
        environment: str = None,
        report_format: str = "allure",
        parallel: bool = False,
        workers: int = 4,
        verbose: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """构建pytest测试命令"""
        base_command = "pytest"
        commands = []
        
        # 添加测试文件或目录
        if test_case_files:
            commands.extend(test_case_files)
        elif test_module:
            commands.append(f"tests/{test_module}")
        else:
            commands.append("tests/")
        
        # 环境变量设置
        env_vars = {}
        if environment:
            env_vars["ENV"] = environment
        
        # 报告配置
        if report_format == "allure":
            report_dir = kwargs.get("report_dir", "reports/allure-results")
            commands.extend(["--alluredir", report_dir])
        elif report_format == "html":
            report_file = kwargs.get("report_file", "reports/report.html")
            commands.extend(["--html", report_file, "--self-contained-html"])
        elif report_format == "junit":
            report_file = kwargs.get("report_file", "reports/junit.xml")
            commands.extend(["--junit-xml", report_file])
        
        # 日志和详细输出
        if verbose:
            commands.append("-v")
            commands.append("-s")
        
        log_file = kwargs.get("log_file", "logs/pytest.log")
        commands.extend(["--log-file", log_file, "--log-file-level", "INFO"])
        
        # 并行执行
        if parallel:
            commands.extend(["-n", str(workers)])
        
        # 其他参数
        if kwargs.get("max_failures"):
            commands.extend(["--maxfail", str(kwargs["max_failures"])])
        
        if kwargs.get("markers"):
            commands.extend(["-m", kwargs["markers"]])
        
        if kwargs.get("coverage"):
            commands.extend(["--cov", kwargs.get("cov_module", "."), "--cov-report", "html"])
        
        # 构建完整命令
        full_command = " ".join([base_command] + commands)
        
        # 环境变量设置命令
        env_command_parts = []
        for key, value in env_vars.items():
            env_command_parts.append(f"{key}={value}")
        
        if env_command_parts:
            env_command = " ".join(env_command_parts) + " " + full_command
        else:
            env_command = full_command
        
        return {
            "framework": "pytest",
            "base_command": base_command,
            "command": full_command,
            "command_with_env": env_command,
            "commands_array": [base_command] + commands,
            "environment_vars": env_vars,
            "report_config": {
                "format": report_format,
                "output": report_dir if report_format != "junit" else report_file
            },
            "parallel": parallel,
            "workers": workers if parallel else 1
        }
    
    def _build_jmeter_command(
        self,
        test_case_ids: List[int] = None,
        test_case_files: List[str] = None,
        test_suite_id: int = None,
        test_module: str = None,
        environment: str = None,
        report_format: str = "html",
        **kwargs
    ) -> Dict[str, Any]:
        """构建JMeter测试命令"""
        base_command = "jmeter"
        commands = ["-n", "-t"]  # 非GUI模式，指定测试计划
        
        # 添加测试文件
        if test_case_files:
            commands.append(test_case_files[0])  # JMeter通常只接受一个文件
        else:
            commands.append("tests/test_plan.jmx")  # 默认文件
        
        # 环境变量设置
        env_vars = {}
        if environment:
            env_vars["ENV"] = environment
        
        # 报告配置
        if report_format == "html":
            report_dir = kwargs.get("report_dir", "reports/jmeter")
            commands.extend(["-l", f"{report_dir}/results.jtl"])
            commands.extend(["-e", "-o", report_dir])
        elif report_format == "junit":
            report_file = kwargs.get("report_file", "reports/jmeter-junit.xml")
            commands.extend(["-l", report_file])
        
        # 其他参数
        if kwargs.get("properties_file"):
            commands.extend(["-q", kwargs["properties_file"]])
        
        if kwargs.get("threads"):
            # 通过properties文件或命令行参数设置线程数
            pass
        
        # 构建完整命令
        full_command = " ".join([base_command] + commands)
        
        # 环境变量设置命令
        env_command_parts = []
        for key, value in env_vars.items():
            env_command_parts.append(f"{key}={value}")
        
        if env_command_parts:
            env_command = " ".join(env_command_parts) + " " + full_command
        else:
            env_command = full_command
        
        return {
            "framework": "jmeter",
            "base_command": base_command,
            "command": full_command,
            "command_with_env": env_command,
            "commands_array": [base_command] + commands,
            "environment_vars": env_vars,
            "report_config": {
                "format": report_format,
                "output": report_dir if report_format == "html" else report_file
            }
        }
    
    def build_test_suite_command(
        self,
        suite_name: str,
        framework: str = "httprunner",
        environment: str = None,
        report_format: str = "allure",
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建测试套件执行命令
        
        Args:
            suite_name: 测试套件名称或路径
            framework: 测试框架
            environment: 测试环境
            report_format: 报告格式
            **kwargs: 其他参数
        
        Returns:
            命令配置字典
        """
        return self.build_test_command(
            test_case_files=[suite_name],
            framework=framework,
            environment=environment,
            report_format=report_format,
            **kwargs
        )
    
    def generate_shell_script(
        self,
        command_config: Dict[str, Any],
        script_name: str = "run_tests.sh"
    ) -> str:
        """
        生成Shell脚本
        
        Args:
            command_config: 命令配置（来自build_test_command）
            script_name: 脚本文件名
        
        Returns:
            Shell脚本内容
        """
        framework = command_config.get("framework", "httprunner")
        env_vars = command_config.get("environment_vars", {})
        report_config = command_config.get("report_config", {})
        
        script_lines = [
            "#!/bin/bash",
            f"# Auto-generated test execution script for {framework}",
            "set -e  # Exit on error",
            "",
            "# Set environment variables"
        ]
        
        # 设置环境变量
        for key, value in env_vars.items():
            script_lines.append(f"export {key}={value}")
        
        script_lines.extend([
            "",
            "# Create directories",
            "mkdir -p reports logs",
            "",
            "# Install dependencies (if needed)",
            "if [ -f requirements.txt ]; then",
            "    pip install -r requirements.txt",
            "fi",
            "",
            "# Run tests"
        ])
        
        # 添加测试命令
        commands_array = command_config.get("commands_array", [])
        script_lines.append(" ".join(commands_array))
        
        script_lines.extend([
            "",
            "# Generate reports if needed"
        ])
        
        # 生成报告命令
        if report_config.get("format") == "allure":
            script_lines.append("allure generate reports/allure-results -o reports/allure-report --clean || true")
            script_lines.append("allure open reports/allure-report || true")
        
        script_lines.extend([
            "",
            "# Exit with test result code",
            "exit $?"
        ])
        
        return "\n".join(script_lines)








































