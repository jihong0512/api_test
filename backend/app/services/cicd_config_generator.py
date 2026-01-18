"""
CI/CD配置文件生成器
自动生成Jenkinsfile、GitHub Actions、GitLab CI/CD等配置文件
"""
from typing import Dict, Any, Optional, List
import yaml


class CICDConfigGenerator:
    """CI/CD配置生成器"""
    
    def __init__(self):
        self.supported_platforms = ["jenkins", "github_actions", "gitlab_ci"]
    
    def generate_config(
        self,
        platform: str,
        project_name: str,
        test_command_config: Dict[str, Any],
        python_version: str = "3.9",
        node_version: str = "18",
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成CI/CD配置文件
        
        Args:
            platform: 平台（jenkins, github_actions, gitlab_ci）
            project_name: 项目名称
            test_command_config: 测试命令配置（来自TestCommandBuilder）
            python_version: Python版本
            node_version: Node.js版本（如果需要）
            **kwargs: 其他配置参数
        
        Returns:
            包含配置内容和文件名的字典
        """
        if platform == "jenkins":
            return self._generate_jenkinsfile(project_name, test_command_config, python_version, **kwargs)
        elif platform == "github_actions":
            return self._generate_github_actions(project_name, test_command_config, python_version, **kwargs)
        elif platform == "gitlab_ci":
            return self._generate_gitlab_ci(project_name, test_command_config, python_version, **kwargs)
        else:
            raise ValueError(f"不支持的CI/CD平台: {platform}")
    
    def _generate_jenkinsfile(
        self,
        project_name: str,
        test_command_config: Dict[str, Any],
        python_version: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成Jenkinsfile (Groovy)"""
        framework = test_command_config.get("framework", "httprunner")
        environment = test_command_config.get("environment_vars", {}).get("ENV", "test")
        report_format = test_command_config.get("report_config", {}).get("format", "allure")
        parallel = test_command_config.get("parallel", False)
        workers = test_command_config.get("workers", 4)
        
        stages = []
        
        # Checkout stage
        stages.append("""            stage('Checkout') {
                steps {
                    checkout scm
                }
            }""")
        
        # Setup Python environment
        stages.append(f"""            stage('Setup Python Environment') {{
                steps {{
                    sh '''
                        python{python_version.replace(".", "")} -m venv venv
                        source venv/bin/activate
                        pip install --upgrade pip
                        pip install -r requirements.txt
                    '''
                }}
            }}""")
        
        # Install test dependencies
        if framework == "httprunner":
            stages.append("""            stage('Install Test Dependencies') {
                steps {
                    sh '''
                        source venv/bin/activate
                        pip install httprunner allure-pytest
                    '''
                }
            }""")
        elif framework == "pytest":
            stages.append("""            stage('Install Test Dependencies') {
                steps {
                    sh '''
                        source venv/bin/activate
                        pip install pytest pytest-html pytest-xdist allure-pytest
                    '''
                }
            }""")
        elif framework == "jmeter":
            stages.append("""            stage('Install Test Dependencies') {
                steps {
                    sh '''
                        source venv/bin/activate
                        # Install JMeter if needed
                        # wget https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-5.5.tgz
                    '''
                }
            }""")
        
        # Run tests stage
        test_command = test_command_config.get("command", "")
        stages.append(f"""            stage('Run Tests') {{
                steps {{
                    sh '''
                        source venv/bin/activate
                        export ENV={environment}
                        {test_command}
                    '''
                }}
            }}""")
        
        # Generate reports stage
        if report_format == "allure":
            stages.append("""            stage('Generate Allure Report') {
                steps {
                    sh '''
                        source venv/bin/activate
                        allure generate reports/allure-results -o reports/allure-report --clean
                    '''
                }
            }
            stage('Publish Allure Report') {
                steps {
                    allure([
                        includeProperties: false,
                        jdk: '',
                        properties: [],
                        reportBuildPolicy: 'ALWAYS',
                        results: [[path: 'reports/allure-results']]
                    ])
                }
            }""")
        elif report_format == "junit":
            stages.append("""            stage('Publish Test Results') {
                steps {
                    junit 'reports/junit.xml'
                }
            }""")
        
        # Archive artifacts
        stages.append("""            stage('Archive Test Results') {
                steps {
                    archiveArtifacts artifacts: 'reports/**/*', fingerprint: true
                    archiveArtifacts artifacts: 'logs/**/*', fingerprint: true
                }
            }""")
        
        # Build Jenkinsfile content
        jenkinsfile_content = f"""pipeline {{
    agent any
    
    options {{
        timeout(time: 1, unit: 'HOURS')
        ansiColor('xterm')
    }}
    
    environment {{
        PYTHON_VERSION = '{python_version}'
        ENV = '{environment}'
        PROJECT_NAME = '{project_name}'
    }}
    
    stages {{
{chr(10).join(stages)}
    }}
    
    post {{
        always {{
            script {{
                // Clean up
                sh 'rm -rf venv __pycache__ .pytest_cache || true'
            }}
        }}
        success {{
            echo 'Tests completed successfully!'
        }}
        failure {{
            echo 'Tests failed!'
        }}
    }}
}}"""
        
        return {
            "platform": "jenkins",
            "filename": "Jenkinsfile",
            "content": jenkinsfile_content,
            "language": "groovy"
        }
    
    def _generate_github_actions(
        self,
        project_name: str,
        test_command_config: Dict[str, Any],
        python_version: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成GitHub Actions workflow配置"""
        framework = test_command_config.get("framework", "httprunner")
        environment = test_command_config.get("environment_vars", {}).get("ENV", "test")
        report_format = test_command_config.get("report_config", {}).get("format", "allure")
        parallel = test_command_config.get("parallel", False)
        workers = test_command_config.get("workers", 4)
        
        workflow_name = kwargs.get("workflow_name", "API Tests")
        trigger_branches = kwargs.get("trigger_branches", ["main", "develop"])
        test_command = test_command_config.get("command", "")
        
        workflow = {
            "name": workflow_name,
            "on": {
                "push": {
                    "branches": trigger_branches
                },
                "pull_request": {
                    "branches": trigger_branches
                },
                "workflow_dispatch": {}  # 允许手动触发
            },
            "jobs": {
                "test": {
                    "runs-on": "ubuntu-latest",
                    "strategy": {
                        "matrix": {
                            "python-version": [python_version]
                        }
                    },
                    "steps": [
                        {
                            "name": "Checkout code",
                            "uses": "actions/checkout@v3"
                        },
                        {
                            "name": "Set up Python",
                            "uses": "actions/setup-python@v4",
                            "with": {
                                "python-version": python_version
                            }
                        },
                        {
                            "name": "Install dependencies",
                            "run": "pip install --upgrade pip && pip install -r requirements.txt"
                        }
                    ]
                }
            }
        }
        
        # Add framework-specific dependencies
        if framework == "httprunner":
            workflow["jobs"]["test"]["steps"].append({
                "name": "Install HttpRunner",
                "run": "pip install httprunner allure-pytest"
            })
        elif framework == "pytest":
            workflow["jobs"]["test"]["steps"].append({
                "name": "Install pytest",
                "run": "pip install pytest pytest-html pytest-xdist allure-pytest"
            })
        
        # Add test execution step
        workflow["jobs"]["test"]["steps"].extend([
            {
                "name": "Run tests",
                "env": {
                    "ENV": environment
                },
                "run": test_command
            }
        ])
        
        # Add report generation and upload
        if report_format == "allure":
            workflow["jobs"]["test"]["steps"].extend([
                {
                    "name": "Generate Allure Report",
                    "if": "always()",
                    "run": "allure generate reports/allure-results -o reports/allure-report --clean || true"
                },
                {
                    "name": "Publish Allure Report",
                    "if": "always()",
                    "uses": "simple-elf/allure-report-action@master",
                    "with": {
                        "allure_results": "reports/allure-results",
                        "allure_report": "reports/allure-report"
                    }
                }
            ])
        elif report_format == "junit":
            workflow["jobs"]["test"]["steps"].append({
                "name": "Publish Test Results",
                "if": "always()",
                "uses": "EnricoMi/publish-unit-test-result-action@v2",
                "with": {
                    "files": "reports/junit.xml"
                }
            })
        
        # Add artifact upload
        workflow["jobs"]["test"]["steps"].append({
            "name": "Upload test artifacts",
            "if": "always()",
            "uses": "actions/upload-artifact@v3",
            "with": {
                "name": "test-results",
                "path": "reports/"
            }
        })
        
        return {
            "platform": "github_actions",
            "filename": ".github/workflows/api-tests.yml",
            "content": yaml.dump(workflow, default_flow_style=False, allow_unicode=True),
            "language": "yaml"
        }
    
    def _generate_gitlab_ci(
        self,
        project_name: str,
        test_command_config: Dict[str, Any],
        python_version: str,
        **kwargs
    ) -> Dict[str, Any]:
        """生成GitLab CI/CD配置"""
        framework = test_command_config.get("framework", "httprunner")
        environment = test_command_config.get("environment_vars", {}).get("ENV", "test")
        report_format = test_command_config.get("report_config", {}).get("format", "allure")
        test_command = test_command_config.get("command", "")
        
        config = {
            "image": f"python:{python_version}",
            "variables": {
                "ENV": environment,
                "PROJECT_NAME": project_name
            },
            "stages": ["test", "report"],
            "before_script": [
                "pip install --upgrade pip",
                "pip install -r requirements.txt"
            ],
            "test": {
                "stage": "test",
                "script": [
                    f"export ENV={environment}",
                    test_command
                ],
                "artifacts": {
                    "when": "always",
                    "paths": [
                        "reports/",
                        "logs/"
                    ],
                    "expire_in": "7 days"
                }
            }
        }
        
        # Add framework-specific installation
        if framework == "httprunner":
            config["before_script"].append("pip install httprunner allure-pytest")
        elif framework == "pytest":
            config["before_script"].append("pip install pytest pytest-html pytest-xdist allure-pytest")
        
        # Add report generation
        if report_format == "allure":
            config["stages"].append("report")
            config["generate_report"] = {
                "stage": "report",
                "image": "frankescobar/allure-docker-service",
                "script": [
                    "allure generate reports/allure-results -o reports/allure-report --clean || true"
                ],
                "artifacts": {
                    "paths": ["reports/allure-report"],
                    "expire_in": "30 days"
                },
                "only": ["main", "develop"]  # 只在主要分支生成报告
            }
        elif report_format == "junit":
            config["test"]["artifacts"]["reports"] = {
                "junit": "reports/junit.xml"
            }
        
        return {
            "platform": "gitlab_ci",
            "filename": ".gitlab-ci.yml",
            "content": yaml.dump(config, default_flow_style=False, allow_unicode=True),
            "language": "yaml"
        }
    
    def generate_multiple_configs(
        self,
        project_name: str,
        test_command_config: Dict[str, Any],
        platforms: List[str] = None,
        **kwargs
    ) -> Dict[str, Dict[str, Any]]:
        """
        生成多个平台的CI/CD配置
        
        Args:
            project_name: 项目名称
            test_command_config: 测试命令配置
            platforms: 平台列表，如果为None则生成所有支持的平台
            **kwargs: 其他参数
        
        Returns:
            平台名称到配置的映射
        """
        if platforms is None:
            platforms = self.supported_platforms
        
        configs = {}
        for platform in platforms:
            try:
                configs[platform] = self.generate_config(
                    platform=platform,
                    project_name=project_name,
                    test_command_config=test_command_config,
                    **kwargs
                )
            except Exception as e:
                configs[platform] = {
                    "error": str(e)
                }
        
        return configs








































