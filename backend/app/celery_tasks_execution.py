"""
测试任务执行相关的Celery任务
包括：接口场景用例执行、接口测试用例执行、性能测试执行
"""
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import TestTask, TestCase, TestEnvironment, TestCaseSuite
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import os
import subprocess
import tempfile
import shutil
import re
from pathlib import Path

from app.utils.redis_helper import get_redis_client


def parse_pytest_summary(output: str) -> Dict[str, int]:
    """
    解析pytest输出的统计信息
    例如: "========== 1 passed, 2 failed, 3 skipped in 0.5s =========="
    返回: {'passed': 1, 'failed': 2, 'skipped': 3}
    """
    result = {'passed': 0, 'failed': 0, 'skipped': 0}
    
    # 查找pytest的总结行（最后一行包含统计信息）
    # 格式：========== X passed, Y failed, Z skipped in ... ==========
    lines = output.split('\n')
    for line in reversed(lines):  # 从后往前查找，总结通常在最后
        if 'passed' in line.lower() or 'failed' in line.lower() or 'skipped' in line.lower():
            # 使用更简单的模式匹配每个数字
            passed_match = re.search(r'(\d+)\s+passed', line, re.IGNORECASE)
            failed_match = re.search(r'(\d+)\s+failed', line, re.IGNORECASE)
            skipped_match = re.search(r'(\d+)\s+skipped', line, re.IGNORECASE)
            error_match = re.search(r'(\d+)\s+error', line, re.IGNORECASE)
            
            if passed_match:
                result['passed'] = int(passed_match.group(1))
            if failed_match:
                result['failed'] = int(failed_match.group(1))
            if skipped_match:
                result['skipped'] = int(skipped_match.group(1))
            if error_match:
                result['failed'] += int(error_match.group(1))
            
            # 如果找到了统计行，就退出
            if any(result.values()):
                break
    
    # 如果正则匹配失败，使用简单的计数方法作为后备
    if not any(result.values()):
        # 计算测试函数数量（通过查找 :: PASSED/FAILED/SKIPPED 模式）
        # 注意：排除 "short test summary info" 行之后的内容，避免重复计数
        # 匹配格式：路径::test_function STATUS
        lines_before_summary = output.split('short test summary info')[0] if 'short test summary info' in output else output
        # 使用 \S+ 匹配非空白字符（包括中文字符），匹配到STATUS之前的测试函数名
        passed_count = len(re.findall(r'::[^\s]+\s+PASSED\b', lines_before_summary))
        failed_count = len(re.findall(r'::[^\s]+\s+FAILED\b', lines_before_summary))
        skipped_count = len(re.findall(r'::[^\s]+\s+SKIPPED\b', lines_before_summary))
        
        if passed_count > 0 or failed_count > 0 or skipped_count > 0:
            result = {
                'passed': passed_count,
                'failed': failed_count,
                'skipped': skipped_count
            }
        else:
            # 如果都没有找到，检查是否有 error
            error_match = re.search(r'(\d+)\s+error', output, re.IGNORECASE)
            if error_match:
                result['failed'] = int(error_match.group(1))
    
    return result


def safe_update_failure_state(task_self, error_msg: str):
    """安全地更新任务失败状态"""
    safe_error_msg = str(error_msg) if error_msg else "未知错误"
    if len(safe_error_msg) > 1000:
        safe_error_msg = safe_error_msg[:1000] + "..."
    
    try:
        task_self.update_state(
            # 仅更新进度/错误信息，不直接写入FAILURE状态
            state='PROGRESS',
            meta={
                'progress': 0,
                'message': safe_error_msg,
                'error': safe_error_msg,
                'status': 'failed'
            }
        )
    except Exception as update_error:
        print(f"更新任务状态失败: {update_error}")
    
    return safe_error_msg


@celery_app.task(bind=True, time_limit=3600, soft_time_limit=3500)
def execute_test_task_task(
    self,
    task_id: int
):
    """
    执行测试任务（根据execution_task_type分发到不同的执行器）
    
    Args:
        task_id: 测试任务ID
    """
    db = SessionLocal()
    task = None
    
    try:
        task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            raise Exception(f"测试任务不存在: {task_id}")
        
        # 更新任务状态（如果状态不是running，说明可能是在task_scheduler中已经更新了）
        # 这里确保execution_task_id和进度被正确设置
        if task.status != "running":
            task.status = "running"
        if not task.executed_at:
            task.executed_at = datetime.now()
        task.execution_task_id = self.request.id
        if task.progress != 0:
            task.progress = 0
        db.commit()
        print(f"[execute_test_task_task] 任务 {task_id} 状态已更新为 running，execution_task_id: {self.request.id}")
        
        # 在关闭会话之前，保存需要使用的属性值
        execution_task_type = task.execution_task_type
        environment_id = task.environment_id
        if execution_task_type in ("scenario", "interface", "performance") and not environment_id:
            raise Exception(f"测试环境不存在: {environment_id}")
        
        # 关闭当前会话，子函数会创建自己的会话
        db.close()
        db = None
        
        # 根据execution_task_type分发到不同的执行器
        # 注意：子函数会创建自己的数据库会话，避免并发问题
        if execution_task_type == "scenario":
            return execute_scenario_task_task(self, task_id)
        elif execution_task_type == "interface":
            return execute_interface_task_task(self, task_id)
        elif execution_task_type == "performance":
            return execute_performance_task_task(self, task_id)
        else:
            raise Exception(f"不支持的任务类型: {execution_task_type}")
            
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()
        
        # 使用新的独立数据库会话更新任务状态
        try:
            error_db = SessionLocal()
            try:
                error_task = error_db.query(TestTask).filter(TestTask.id == task_id).first()
                if error_task:
                    error_task.status = "failed"
                    error_task.error_message = error_msg[:1000]  # 限制错误信息长度
                    error_task.completed_at = datetime.now()
                    error_db.commit()
            finally:
                error_db.close()
        except Exception as db_error:
            print(f"[execute_test_task_task] 更新任务状态失败: {db_error}")
        
        safe_error_msg = safe_update_failure_state(self, f'执行失败: {error_msg}')

        # 额外标记Celery任务失败状态，写入带exc_type的异常对象，避免后续解码出现KeyError
        try:
            failure_exc = RuntimeError(safe_error_msg)
            self.update_state(state='FAILURE', meta=failure_exc)
        except Exception as state_error:
            print(f"[execute_test_task_task] 更新Celery失败状态失败: {state_error}")

        raise RuntimeError(f"执行测试任务失败: {safe_error_msg}")
    
    finally:
        if db:
            try:
                db.close()
            except:
                pass


def execute_scenario_task_task(self, task_id: int):
    """执行接口场景用例任务"""
    db = SessionLocal()
    try:
        task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            raise Exception(f"测试任务不存在: {task_id}")
        
        # 获取测试用例组
        if not task.test_case_suite_id:
            raise Exception("接口场景用例执行任务必须指定test_case_suite_id")
        
        suite = db.query(TestCaseSuite).filter(TestCaseSuite.id == task.test_case_suite_id).first()
        if not suite:
            raise Exception(f"测试用例组不存在: {task.test_case_suite_id}")
        
        # 获取用例ID列表
        test_case_ids = json.loads(suite.test_case_ids) if suite.test_case_ids else []
        if not test_case_ids:
            raise Exception("测试用例组为空")
        
        # 获取环境信息
        environment = db.query(TestEnvironment).filter(TestEnvironment.id == task.environment_id).first()
        if not environment:
            raise Exception(f"测试环境不存在: {task.environment_id}")
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"scenario_task_{task_id}_")
        
        try:
            # 执行场景用例
            self.update_state(
                state='PROGRESS',
                meta={'progress': 10, 'message': '开始执行接口场景用例...'}
            )
            
            # 获取所有测试用例
            test_cases = db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).all()
            
            # 创建临时测试文件
            test_file = os.path.join(temp_dir, "test_scenario.py")
            # 这里应该合并所有场景用例的代码到一个文件
            # 简化处理：直接执行每个用例
            
            passed = 0
            failed = 0
            skipped = 0
            execution_logs = []
            
            for idx, test_case in enumerate(test_cases):
                if not test_case.test_code:
                    skipped += 1
                    continue
                
                self.update_state(
                    state='PROGRESS',
                    meta={'progress': 10 + int((idx / len(test_cases)) * 70), 
                          'message': f'正在执行用例: {test_case.name}...'}
                )
                
                # 执行单个用例
                try:
                    # 写入临时文件
                    with open(test_file, 'w', encoding='utf-8') as f:
                        f.write(test_case.test_code)
                    
                    # 执行pytest
                    env = os.environ.copy()
                    env['BASE_URL'] = environment.base_url
                    env['XJID'] = environment.xjid or "30110"
                    
                    result = subprocess.run(
                        ['pytest', test_file, '-v', '--tb=short'],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        env=env
                    )
                    
                    if result.returncode == 0:
                        passed += 1
                    else:
                        failed += 1
                    
                    execution_logs.append({
                        'test_case_id': test_case.id,
                        'test_case_name': test_case.name,
                        'status': 'passed' if result.returncode == 0 else 'failed',
                        'output': result.stdout + result.stderr
                    })
                    
                except Exception as e:
                    failed += 1
                    execution_logs.append({
                        'test_case_id': test_case.id,
                        'test_case_name': test_case.name,
                        'status': 'error',
                        'error': str(e)
                    })
            
            # 生成HTML测试报告
            self.update_state(
                state='PROGRESS',
                meta={'progress': 85, 'message': '正在生成测试报告...'}
            )
            
            report_path = None
            
            # 生成HTML报告（不再使用Allure）
            try:
                from app.services.html_report_generator import generate_html_report
                report_path = generate_html_report(
                    task_id=task_id,
                    task_name=task.name,
                    execution_logs=execution_logs,
                    total_cases=len(test_cases),
                    passed_cases=passed,
                    failed_cases=failed,
                    skipped_cases=skipped,
                    report_type="scenario"
                )
            except Exception as report_error:
                print(f"[execute_scenario_task_task] 生成HTML报告失败: {report_error}")
                import traceback
                traceback.print_exc()
                # 即使报告生成失败，也继续执行，不阻塞任务完成
            
            # 保存报告路径
            if report_path:
                task.allure_report_path = report_path
            task.execution_logs = json.dumps(execution_logs, ensure_ascii=False)
            
            # 更新任务状态
            task.status = "completed" if failed == 0 else "failed"
            task.progress = 100
            task.total_cases = len(test_cases)
            task.passed_cases = passed
            task.failed_cases = failed
            task.skipped_cases = skipped
            task.completed_at = datetime.now()
            task.result_summary = json.dumps({
                'total': len(test_cases),
                'passed': passed,
                'failed': failed,
                'skipped': skipped
            }, ensure_ascii=False)
            db.commit()
            
            self.update_state(
                state='PROGRESS',
                meta={'progress': 100, 'message': '接口场景用例执行完成'}
            )
            
            return {
                "status": "success",
                "task_id": task_id,
                "total": len(test_cases),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "report_path": report_path
            }
        except Exception as inner_e:
            # 内部try块的异常处理
            import traceback
            error_msg = f"{type(inner_e).__name__}: {str(inner_e)}"
            traceback.print_exc()
            raise inner_e
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()
        if task:
            try:
                # 使用新的数据库会话更新任务状态
                error_db = SessionLocal()
                try:
                    error_task = error_db.query(TestTask).filter(TestTask.id == task_id).first()
                    if error_task:
                        error_task.status = "failed"
                        error_task.error_message = error_msg[:1000]  # 限制错误信息长度
                        error_task.completed_at = datetime.now()
                        error_db.commit()
                finally:
                    error_db.close()
            except Exception as db_error:
                print(f"[execute_scenario_task_task] 更新失败状态时出错: {db_error}")
        # 重新抛出异常，确保Celery能正确处理
        raise RuntimeError(error_msg) from e
    finally:
        # 确保关闭数据库会话
        try:
            db.close()
        except:
            pass
        # 清理临时目录（可选，如果需要保留报告则不清理）
        pass


def execute_interface_task_task(self, task_id: int):
    """执行接口测试用例任务"""
    db = SessionLocal()
    try:
        task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            raise Exception(f"测试任务不存在: {task_id}")
        
        test_case_ids = json.loads(task.test_case_ids) if task.test_case_ids else []
        if not test_case_ids:
            raise Exception("测试用例列表为空")
        
        environment = db.query(TestEnvironment).filter(TestEnvironment.id == task.environment_id).first()
        if not environment:
            raise Exception(f"测试环境不存在: {task.environment_id}")
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"interface_task_{task_id}_")
        
        try:
            # 执行接口测试用例
            self.update_state(
                state='PROGRESS',
                meta={'progress': 10, 'message': '开始执行接口测试用例...'}
            )
        
            # 获取所有测试用例
            test_cases = db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).all()
            
            # 合并所有用例代码到一个文件（按模块分组）
            test_files = {}
            for test_case in test_cases:
                if not test_case.test_code:
                    continue
                module = test_case.module or "default"
                if module not in test_files:
                    test_files[module] = []
                test_files[module].append(test_case.test_code)
            
            passed = 0
            failed = 0
            skipped = 0
            execution_logs = []
            
            # 为每个模块创建一个测试文件
            for module_idx, (module, codes) in enumerate(test_files.items()):
                test_file = os.path.join(temp_dir, f"test_{module}_{module_idx}.py")
                
                # 合并代码（添加必要的导入和fixture）
                combined_code = "import pytest\nimport requests\nimport json\n\n"
                combined_code += "# 共享fixture\n"
                xjid_value = environment.xjid or "30110"
                combined_code += f"@pytest.fixture(scope='session')\ndef base_url():\n    return '{environment.base_url}'\n\n"
                combined_code += f"@pytest.fixture(scope='session')\ndef xjid():\n    return '{xjid_value}'\n\n"
                
                for code in codes:
                    combined_code += "\n" + code + "\n"
                
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(combined_code)
                
                # 执行pytest
                self.update_state(
                    state='PROGRESS',
                    meta={'progress': 10 + int((module_idx / len(test_files)) * 70), 
                          'message': f'正在执行模块: {module}...'}
                )
                
                try:
                    env = os.environ.copy()
                    env['BASE_URL'] = environment.base_url
                    env['XJID'] = environment.xjid or "30110"
                    
                    result = subprocess.run(
                        ['pytest', test_file, '-v', '--tb=short'],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        env=env
                    )
                    
                    # 解析结果 - 使用正则表达式解析pytest统计信息
                    output = result.stdout + result.stderr
                    summary = parse_pytest_summary(output)
                    
                    # 调试日志：记录解析结果和累加前的值
                    print(f"[execute_interface_task_task] 模块 {module} parse_pytest_summary返回: passed={summary['passed']}, failed={summary['failed']}, skipped={summary['skipped']}")
                    print(f"[execute_interface_task_task] 累加前: passed={passed}, failed={failed}, skipped={skipped}")
                    
                    passed += summary['passed']
                    failed += summary['failed']
                    skipped += summary['skipped']
                    
                    # 调试日志：记录累加后的值
                    print(f"[execute_interface_task_task] 累加后: passed={passed}, failed={failed}, skipped={skipped}")
                    print(f"[execute_interface_task_task] 模块 {module} 执行结果: passed={summary['passed']}, failed={summary['failed']}, skipped={summary['skipped']}")
                    
                    execution_logs.append({
                        'module': module,
                        'status': 'passed' if result.returncode == 0 else 'failed',
                        'output': output
                    })
                    
                except Exception as e:
                    failed += 1
                    execution_logs.append({
                        'module': module,
                        'status': 'error',
                        'error': str(e)
                    })
        
            # 生成HTML测试报告
            self.update_state(
                state='PROGRESS',
                meta={'progress': 85, 'message': '正在生成测试报告...'}
            )
            
            report_path = None
            try:
                from app.services.html_report_generator import generate_html_report
                report_path = generate_html_report(
                    task_id=task_id,
                    task_name=task.name,
                    execution_logs=execution_logs,
                    total_cases=len(test_cases),
                    passed_cases=passed,
                    failed_cases=failed,
                    skipped_cases=skipped,
                    report_type="interface"
                )
            except Exception as report_error:
                print(f"[execute_interface_task_task] 生成HTML报告失败: {report_error}")
                import traceback
                traceback.print_exc()
                # 即使报告生成失败，也继续执行，不阻塞任务完成
            
            # 保存报告路径
            if report_path:
                task.allure_report_path = report_path
            task.execution_logs = json.dumps(execution_logs, ensure_ascii=False)
            
            # 更新任务状态
            task.status = "completed" if failed == 0 else "failed"
            task.progress = 100
            task.total_cases = len(test_cases)
            task.passed_cases = passed
            task.failed_cases = failed
            task.skipped_cases = skipped
            task.completed_at = datetime.now()
            task.result_summary = json.dumps({
                'total': len(test_cases),
                'passed': passed,
                'failed': failed,
                'skipped': skipped
            }, ensure_ascii=False)
            db.commit()
            
            self.update_state(
                state='PROGRESS',
                meta={'progress': 100, 'message': '接口测试用例执行完成'}
            )
            
            return {
                "status": "success",
                "task_id": task_id,
                "total": len(test_cases),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "report_path": report_path
            }
        except Exception as inner_e:
            import traceback
            error_msg = f"{type(inner_e).__name__}: {str(inner_e)}"
            traceback.print_exc()
            raise inner_e
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()
        if task:
            try:
                # 使用新的数据库会话更新任务状态
                error_db = SessionLocal()
                try:
                    error_task = error_db.query(TestTask).filter(TestTask.id == task_id).first()
                    if error_task:
                        error_task.status = "failed"
                        error_task.error_message = error_msg[:1000]  # 限制错误信息长度
                        error_task.completed_at = datetime.now()
                        error_db.commit()
                finally:
                    error_db.close()
            except Exception as db_error:
                print(f"[execute_interface_task_task] 更新失败状态时出错: {db_error}")
        # 重新抛出异常，确保Celery能正确处理
        raise RuntimeError(error_msg) from e
    finally:
        try:
            if db:
                db.close()
        except:
            pass


def execute_performance_task_task(self, task_id: int):
    """执行性能测试任务（支持断点续传）"""
    db = SessionLocal()
    try:
        task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            raise Exception(f"测试任务不存在: {task_id}")
        
        test_case_ids = json.loads(task.test_case_ids) if task.test_case_ids else []
        if not test_case_ids:
            raise Exception("测试用例列表为空")
        
        environment = db.query(TestEnvironment).filter(TestEnvironment.id == task.environment_id).first()
        if not environment:
            raise Exception(f"测试环境不存在: {task.environment_id}")
        
        # 检查是否有checkpoint（断点续传）
        checkpoint = None
        if task.execution_checkpoint:
            try:
                checkpoint = json.loads(task.execution_checkpoint)
                print(f"[性能测试任务执行] 发现checkpoint，进度: {checkpoint.get('progress', 0)}%")
            except:
                checkpoint = None
        
        # 如果有checkpoint且进度>=30%，尝试从checkpoint恢复
        if checkpoint and checkpoint.get('progress', 0) >= 30:
            print(f"[性能测试任务执行] 从checkpoint恢复，进度: {checkpoint.get('progress', 0)}%")
            # 恢复进度
            task.progress = checkpoint.get('progress', 0)
            # 检查JTL文件是否已存在（如果JMeter已执行完成）
            result_file = checkpoint.get('result_file')
            if result_file:
                # 检查JTL文件是否存在
                check_result = subprocess.run(
                    ['docker', 'exec', 'api_test_jmeter', 'test', '-f', result_file],
                    capture_output=True,
                    timeout=5
                )
                if check_result.returncode == 0:
                    # JTL文件存在，说明JMeter已执行完成，直接进入分析阶段
                    print(f"[性能测试任务执行] JTL文件已存在，跳过JMeter执行，直接分析结果")
                    jtl_file_path = result_file
                    html_report_dir = checkpoint.get('html_report_dir')
                    # 跳转到分析阶段
                    try:
                        self.update_state(
                            state='PROGRESS',
                            meta={'progress': 80, 'message': '从checkpoint恢复，正在分析性能测试结果...'}
                        )
                    except Exception as e:
                        print(f"[execute_performance_task_task] 更新Celery状态失败（从checkpoint恢复）: {e}")
                    task.progress = 80
                    db.commit()
                    print(f"[execute_performance_task_task] 从checkpoint恢复，进度已更新为80%")
                else:
                    # JTL文件不存在，需要重新执行JMeter
                    checkpoint = None  # 清除checkpoint，从头执行
                    print(f"[性能测试任务执行] JTL文件不存在，从头执行JMeter")
            else:
                checkpoint = None  # 没有JTL路径，从头执行
        
        # 如果没有checkpoint或需要从头执行
        if not checkpoint:
            # 执行JMeter性能测试（使用现有的execute_jmeter_performance_test_task逻辑）
            self.update_state(
                state='PROGRESS',
                meta={'progress': 10, 'message': '开始执行性能测试...'}
            )
            task.progress = 10
            db.commit()
        
        # 获取第一个测试用例（性能测试通常只有一个JMX文件）
        test_case = db.query(TestCase).filter(TestCase.id == test_case_ids[0]).first()
        if not test_case or not test_case.test_code:
            raise Exception("性能测试用例不存在或没有测试代码")
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"performance_task_{task_id}_")
        jmx_file = os.path.join(temp_dir, f"test_{task_id}.jmx")
        
        try:
            # 写入JMX文件
            with open(jmx_file, 'w', encoding='utf-8') as f:
                f.write(test_case.test_code)
            
            # 执行JMeter（使用docker exec）
            result_dir = f"/app/jmeter-results/task_{task_id}"
            result_file = f"{result_dir}/result.jtl"
            log_file = f"{result_dir}/jmeter.log"
            html_report_dir = f"{result_dir}/html-report"
            
            # 创建结果目录
            subprocess.run(
                ['docker', 'exec', 'api_test_jmeter', 'mkdir', '-p', result_dir],
                timeout=10
            )
            
            # 复制JMX文件到容器
            subprocess.run(
                ['docker', 'cp', jmx_file, f'api_test_jmeter:/app/jmeter-scripts/test_{task_id}.jmx'],
                timeout=10
            )
            
            # 更新线程数和执行时长（如果需要）
            # 注意：这里访问task属性时，会话仍然打开，所以是安全的
            if task.threads or task.duration:
                import xml.etree.ElementTree as ET
                try:
                    tree = ET.parse(jmx_file)
                    root = tree.getroot()
                    for thread_group in root.findall('.//ThreadGroup'):
                        # 更新线程数
                        if task.threads:
                            num_threads_elem = thread_group.find(".//stringProp[@name='ThreadGroup.num_threads']")
                            if num_threads_elem is not None:
                                num_threads_elem.text = str(task.threads)
                        
                        # 更新执行时长
                        if task.duration:
                            # 设置scheduler为true
                            scheduler_elem = thread_group.find(".//boolProp[@name='ThreadGroup.scheduler']")
                            if scheduler_elem is not None:
                                scheduler_elem.text = "true"
                            else:
                                # 如果不存在，创建scheduler元素（在ThreadGroup下直接添加）
                                bool_prop = ET.Element("boolProp", {"name": "ThreadGroup.scheduler"})
                                bool_prop.text = "true"
                                # 找到第一个子元素的位置，在它之前插入
                                first_child = thread_group.find(".//*")
                                if first_child is not None:
                                    # 获取第一个子元素的索引
                                    index = list(thread_group).index(first_child)
                                    thread_group.insert(index, bool_prop)
                                else:
                                    thread_group.append(bool_prop)
                            
                            # 设置duration（秒数 = 分钟数 * 60）
                            duration_seconds = task.duration * 60
                            duration_elem = thread_group.find(".//stringProp[@name='ThreadGroup.duration']")
                            if duration_elem is not None:
                                duration_elem.text = str(duration_seconds)
                            else:
                                # 如果不存在，创建duration元素
                                string_prop = ET.Element("stringProp", {"name": "ThreadGroup.duration"})
                                string_prop.text = str(duration_seconds)
                                # 在scheduler之后插入
                                scheduler_elem = thread_group.find(".//boolProp[@name='ThreadGroup.scheduler']")
                                if scheduler_elem is not None:
                                    # 找到scheduler的索引，在它之后插入
                                    index = list(thread_group).index(scheduler_elem)
                                    thread_group.insert(index + 1, string_prop)
                                else:
                                    thread_group.append(string_prop)
                            
                            # 确保ramp_time已设置（如果为0，设置为1）
                            ramp_time_elem = thread_group.find(".//stringProp[@name='ThreadGroup.ramp_time']")
                            if ramp_time_elem is not None:
                                if not ramp_time_elem.text or ramp_time_elem.text == "0":
                                    ramp_time_elem.text = "1"
                    
                    tree.write(jmx_file)
                    # 重新复制
                    subprocess.run(
                        ['docker', 'cp', jmx_file, f'api_test_jmeter:/app/jmeter-scripts/test_{task_id}.jmx'],
                        timeout=10
                    )
                except ET.ParseError as e:
                    print(f"[性能测试任务执行] 无法解析JMX更新线程/时长，继续使用原始脚本: {e}")
                except Exception as e:
                    print(f"[性能测试任务执行] 更新JMX线程/时长时发生异常，继续使用原始脚本: {e}")
            
            # 清理旧结果
            subprocess.run(
                ['docker', 'exec', 'api_test_jmeter', 'rm', '-rf', html_report_dir],
                timeout=10
            )
            subprocess.run(
                ['docker', 'exec', 'api_test_jmeter', 'rm', '-f', result_file],
                timeout=10
            )
            
            # 保存checkpoint（在执行前保存）
            checkpoint_data = {
                'progress': 30,
                'result_file': result_file,
                'html_report_dir': html_report_dir,
                'log_file': log_file
            }
            task.execution_checkpoint = json.dumps(checkpoint_data, ensure_ascii=False)
            task.progress = 30
            db.commit()
            
            # 在启动线程之前，保存需要使用的属性值，避免DetachedInstanceError
            task_threads = task.threads
            task_duration = task.duration
            
            # 执行JMeter（使用Popen和定期进度更新，避免卡住）
            duration_text = f"{task_duration}分钟" if task_duration else "默认"
            self.update_state(
                state='PROGRESS',
                meta={'progress': 30, 'message': f'正在执行JMeter测试（线程数: {task_threads}，执行时长: {duration_text}）...'}
            )
            task.progress = 30
            db.commit()
            
            jmeter_cmd = f"jmeter -n -t /app/jmeter-scripts/test_{task_id}.jmx -l {result_file} -j {log_file} -e -o {html_report_dir}"
            
            # 使用Popen而不是run，避免输出缓冲区过大导致卡住
            import threading
            import time as time_module
            
            exec_process = subprocess.Popen(
                ['docker', 'exec', '-w', '/app', 'api_test_jmeter', 'sh', '-c', jmeter_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # 行缓冲
            )
            
            # 初始化变量
            returncode = -1
            exec_stdout = ""
            exec_stderr = ""
            
            # 在启动线程之前，保存需要使用的属性值，避免DetachedInstanceError
            task_threads = task.threads
            task_duration = task.duration
            # 确保task_id被正确捕获
            captured_task_id = task_id
            
            # 定期更新进度的线程
            progress_update_stop = threading.Event()
            
            def update_progress_periodically():
                """定期更新进度（每10秒更新一次）"""
                base_progress = 30
                max_progress = 75
                elapsed = 0
                # 根据执行时长计算总时长（秒）
                total_duration = (task_duration * 60) if task_duration else 300  # 默认5分钟
                while not progress_update_stop.is_set():
                    time_module.sleep(10)
                    elapsed += 10
                    # 进度从30%逐步增加到75%（根据实际执行时长动态计算）
                    progress = min(base_progress + int((elapsed / total_duration) * 45), max_progress)
                    elapsed_minutes = elapsed // 60
                    elapsed_seconds = elapsed % 60
                    try:
                        # 检查captured_task_id是否有效
                        if not captured_task_id:
                            print(f"[execute_performance_task_task] 警告: captured_task_id为空，跳过进度更新")
                            continue
                        
                        # 同时更新Celery任务状态和数据库进度
                        try:
                            # 检查self.request.id是否存在，如果不存在则只更新数据库
                            if hasattr(self, 'request') and self.request and hasattr(self.request, 'id') and self.request.id:
                                self.update_state(
                                    state='PROGRESS',
                                    meta={'progress': progress, 'message': f'正在执行JMeter测试（线程数: {task_threads}，执行时长: {task_duration}分钟，已运行{elapsed_minutes}分{elapsed_seconds}秒）...'}
                                )
                            else:
                                print(f"[execute_performance_task_task] 警告: Celery任务ID不存在，仅更新数据库进度")
                        except Exception as celery_error:
                            # 如果update_state失败，只记录错误，继续更新数据库
                            print(f"[execute_performance_task_task] Celery状态更新失败: {celery_error}")
                        
                        # 使用独立的数据库会话更新进度，避免并发问题
                        thread_db = SessionLocal()
                        try:
                            # 使用捕获的task_id
                            thread_task = thread_db.query(TestTask).filter(TestTask.id == captured_task_id).first()
                            if thread_task:
                                thread_task.progress = progress
                                thread_db.commit()
                        except Exception as db_error:
                            print(f"[execute_performance_task_task] 线程中更新数据库进度失败: {db_error}")
                        finally:
                            thread_db.close()
                    except Exception as e:
                        print(f"[execute_performance_task_task] 更新进度时出错: {e}")
                        import traceback
                        traceback.print_exc()
                        pass
            
            progress_thread = threading.Thread(target=update_progress_periodically, daemon=True)
            progress_thread.start()
            
            try:
                # 等待进程完成，但定期检查进度更新
                start_wait = time_module.time()
                # 根据执行时长设置超时时间（执行时长 + 5分钟缓冲时间），默认10分钟
                jmeter_timeout = (task_duration * 60 + 300) if task_duration else 600
                
                while exec_process.poll() is None:
                    # 检查是否超时
                    if time_module.time() - start_wait > jmeter_timeout:
                        exec_process.kill()
                        raise Exception(f"JMeter执行超时（超过{jmeter_timeout}秒）")
                    time_module.sleep(1)
                
                # 获取输出（限制大小，避免内存问题）
                stdout, stderr = exec_process.communicate(timeout=5)
                returncode = exec_process.returncode
                exec_stdout = stdout[:10000] if stdout else ""  # 限制输出长度
                exec_stderr = stderr[:10000] if stderr else ""
                
                progress_update_stop.set()
                print(f"[execute_performance_task_task] JMeter命令执行完成，退出码: {returncode}")
                
                # 如果退出码不为0，记录错误信息
                if returncode != 0:
                    error_msg = exec_stderr[:1000] if exec_stderr else "未知错误"
                    print(f"[execute_performance_task_task] JMeter执行失败: {error_msg}")
                    raise Exception(f"JMeter执行失败: {error_msg}")
                    
            except subprocess.TimeoutExpired:
                progress_update_stop.set()
                exec_process.kill()
                raise Exception("JMeter执行超时")
            except Exception as e:
                progress_update_stop.set()
                if exec_process.poll() is None:
                    exec_process.kill()
                raise
            
            # 更新checkpoint（JMeter执行完成）
            checkpoint_data = {
                'progress': 80,
                'result_file': result_file,
                'html_report_dir': html_report_dir,
                'log_file': log_file
            }
            task.execution_checkpoint = json.dumps(checkpoint_data, ensure_ascii=False)
            task.progress = 80
            db.commit()
            
            # 读取结果
            self.update_state(
                state='PROGRESS',
                meta={'progress': 80, 'message': '正在分析性能测试结果...'}
            )
            task.progress = 80
            db.commit()
            
            # 复制报告到本地（如果需要）
            local_report_dir = f"/tmp/reports/performance_task_{task_id}"
            os.makedirs(local_report_dir, exist_ok=True)
            
            # 在访问task属性之前，确保会话仍然有效
            # 使用DeepSeek分析性能瓶颈（添加超时保护）
            jtl_file_path = result_file  # 在容器内的路径
            task_name = task.name
            task_threads = task.threads
            task_duration = task.duration
            
            # 停止进度更新线程
            progress_update_stop.set()
            
            # 使用超时机制调用分析函数，避免卡死
            import signal
            import threading as analysis_threading
            
            analysis_result = None
            analysis_error = None
            
            def run_analysis():
                nonlocal analysis_result, analysis_error
                try:
                    print(f"[execute_performance_task_task] 开始调用DeepSeek分析性能瓶颈...")
                    print(f"[execute_performance_task_task] JTL文件路径: {jtl_file_path}, 任务ID: {task_id}")
                    analysis_result = analyze_performance_with_deepseek(
                        jtl_file_path=jtl_file_path,
                        task_id=task_id,
                        task_name=task_name,
                        threads=task_threads,
                        duration=task_duration
                    )
                    print(f"[execute_performance_task_task] DeepSeek分析完成，结果: {json.dumps(analysis_result, ensure_ascii=False)[:200] if analysis_result else 'None'}")
                except Exception as e:
                    analysis_error = str(e)
                    print(f"[execute_performance_task_task] 性能分析失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 在单独的线程中运行分析，设置超时
            analysis_thread = analysis_threading.Thread(target=run_analysis, daemon=True)
            analysis_thread.start()
            analysis_thread.join(timeout=180)  # 3分钟超时
            
            if analysis_thread.is_alive():
                # 分析超时，返回错误结果
                print(f"[execute_performance_task_task] 性能分析超时（超过3分钟）")
                analysis_result = {
                    "error": "性能分析超时，请稍后查看JTL报告",
                    "status": "timeout"
                }
            elif analysis_error:
                analysis_result = {
                    "error": f"性能分析失败: {analysis_error}",
                    "status": "error"
                }
            elif not analysis_result:
                analysis_result = {
                    "error": "性能分析未返回结果",
                    "status": "error"
                }
            
            # 保存报告路径和分析结果
            task.jtl_report_path = html_report_dir  # 容器内路径，前端通过API访问
            task.performance_analysis = json.dumps(analysis_result, ensure_ascii=False)
            
            # 确保生成并保存HTML报告
            if 'html_report' in analysis_result and analysis_result.get('html_report'):
                task.performance_report_html = analysis_result['html_report']
            else:
                # 如果没有html_report，生成一个HTML报告
                has_error = 'error' in analysis_result
                try:
                    from app.services.performance_report_generator import generate_performance_report_html
                    # 从容器中复制JTL文件到本地临时文件
                    local_jtl = f"/tmp/jtl_task_{task_id}_auto.jtl"
                    try:
                        subprocess.run(
                            ['docker', 'cp', f'api_test_jmeter:{jtl_file_path}', local_jtl],
                            timeout=10,
                            check=True
                        )
                        # 构建deepseek_analysis对象
                        if not has_error and analysis_result:
                            # 如果analysis_result有analysis字段，直接使用
                            deepseek_analysis_data = analysis_result.get('analysis', {})
                            if not deepseek_analysis_data:
                                # 如果没有analysis字段，将整个analysis_result作为analysis
                                deepseek_analysis_data = analysis_result
                            deepseek_analysis_for_report = {
                                "analysis": deepseek_analysis_data,
                                "basic_stats": analysis_result.get('basic_stats', {}),
                                "error_analysis": analysis_result.get('error_analysis', {}),
                                "throughput_stats": analysis_result.get('throughput_stats', {})
                            }
                        else:
                            deepseek_analysis_for_report = None
                        
                        html_report = generate_performance_report_html(
                            jtl_file_path=local_jtl,
                            task_id=task_id,
                            task_name=task_name or f"任务{task_id}",
                            threads=task_threads,
                            duration=task_duration,
                            deepseek_analysis=deepseek_analysis_for_report
                        )
                        task.performance_report_html = html_report
                        # 清理临时文件
                        if os.path.exists(local_jtl):
                            os.remove(local_jtl)
                    except Exception as cp_error:
                        print(f"[execute_performance_task_task] 复制JTL文件失败: {cp_error}")
                        # 如果复制失败，生成一个简单的HTML报告
                        error_info = ""
                        if has_error:
                            error_info = f'<div class="error"><h2>分析错误</h2><p>{analysis_result.get("error", "未知错误")}</p></div>'
                        html_content = f"""
                        <html>
                        <head>
                            <title>性能瓶颈分析报告 - {task_name or f'任务{task_id}'}</title>
                            <style>
                                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                                h1 {{ color: #333; }}
                                .error {{ color: red; background: #ffe6e6; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                                .info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                                pre {{ background: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
                            </style>
                        </head>
                        <body>
                            <h1>性能瓶颈分析报告</h1>
                            <div class="info">
                                <h2>任务信息</h2>
                                <p><strong>任务名称:</strong> {task_name or f'任务{task_id}'}</p>
                                <p><strong>线程数:</strong> {task_threads}</p>
                                <p><strong>执行时长:</strong> {task_duration} 分钟</p>
                            </div>
                            {error_info}
                            <h2>分析结果</h2>
                            <pre>{json.dumps(analysis_result, ensure_ascii=False, indent=2)}</pre>
                        </body>
                        </html>
                        """
                        task.performance_report_html = html_content
                except Exception as gen_error:
                    print(f"[execute_performance_task_task] 生成HTML报告失败: {gen_error}")
                    import traceback
                    traceback.print_exc()
                    # 生成一个简单的HTML报告作为后备
                    error_info = ""
                    if has_error:
                        error_info = f'<div class="error"><h2>分析错误</h2><p>{analysis_result.get("error", "未知错误")}</p></div>'
                    html_content = f"""
                    <html>
                    <head>
                        <title>性能瓶颈分析报告 - {task_name or f'任务{task_id}'}</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; margin: 20px; }}
                            h1 {{ color: #333; }}
                            .error {{ color: red; background: #ffe6e6; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                            .info {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                            pre {{ background: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
                        </style>
                    </head>
                    <body>
                        <h1>性能瓶颈分析报告</h1>
                        <div class="info">
                            <h2>任务信息</h2>
                            <p><strong>任务名称:</strong> {task_name or f'任务{task_id}'}</p>
                            <p><strong>线程数:</strong> {task_threads}</p>
                            <p><strong>执行时长:</strong> {task_duration} 分钟</p>
                        </div>
                        {error_info}
                        <h2>分析结果</h2>
                        <pre>{json.dumps(analysis_result, ensure_ascii=False, indent=2)}</pre>
                    </body>
                    </html>
                    """
                    task.performance_report_html = html_content
            
            # 读取执行日志
            log_result = subprocess.run(
                ['docker', 'exec', 'api_test_jmeter', 'cat', log_file],
                capture_output=True,
                text=True,
                timeout=10
            )
            if log_result.returncode == 0:
                task.execution_logs = log_result.stdout
            
            # 更新任务状态
            task.status = "completed"
            task.progress = 100
            task.completed_at = datetime.now()
            task.execution_checkpoint = None  # 清除checkpoint
            
            # 只保存摘要信息到result_summary，完整数据已保存在performance_analysis和performance_report_html中
            summary_data = {
                'threads': task_threads,
                'duration': task_duration,
                'analysis_status': analysis_result.get('status', 'unknown') if isinstance(analysis_result, dict) else 'unknown',
                'has_analysis': 'analysis' in analysis_result if isinstance(analysis_result, dict) else False,
                'has_error': 'error' in analysis_result if isinstance(analysis_result, dict) else False
            }
            # 如果分析成功，添加简要摘要
            if isinstance(analysis_result, dict) and 'analysis' in analysis_result:
                analysis = analysis_result.get('analysis', {})
                if isinstance(analysis, dict) and 'summary' in analysis:
                    # 只保存summary的前200字符，避免过长
                    summary_text = str(analysis.get('summary', ''))[:200]
                    summary_data['summary'] = summary_text
            
            task.result_summary = json.dumps(summary_data, ensure_ascii=False)
            db.commit()
            
            print(f"[execute_performance_task_task] 任务 {task_id} 完成，性能瓶颈分析报告已生成并保存")
            
            self.update_state(
                state='PROGRESS',
                meta={'progress': 100, 'message': '性能测试执行完成'}
            )
            
            return {
                "status": "success",
                "task_id": task_id,
                "jtl_report_path": html_report_dir,
                "performance_analysis": analysis_result
            }
        except Exception as inner_e:
            import traceback
            error_msg = f"{type(inner_e).__name__}: {str(inner_e)}"
            traceback.print_exc()
            raise inner_e
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()
        if task:
            try:
                # 使用新的数据库会话更新任务状态
                error_db = SessionLocal()
                try:
                    error_task = error_db.query(TestTask).filter(TestTask.id == task_id).first()
                    if error_task:
                        error_task.status = "failed"
                        error_task.error_message = error_msg[:1000]  # 限制错误信息长度
                        error_task.completed_at = datetime.now()
                        error_db.commit()
                finally:
                    error_db.close()
            except Exception as db_error:
                print(f"[execute_performance_task_task] 更新失败状态时出错: {db_error}")
        # 重新抛出异常，确保Celery能正确处理
        raise RuntimeError(error_msg) from e
    finally:
        try:
            if db:
                db.close()
        except:
            pass
        # 清理临时文件
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


@celery_app.task(bind=True, time_limit=600, soft_time_limit=540)
def generate_allure_report_async(self, task_id: int):
    """异步生成指定任务的Allure HTML报告，并将状态写入Redis"""

    redis_client = get_redis_client()
    redis_key = f"test_task:allure:{task_id}"
    redis_client.hset(redis_key, mapping={
        "status": "generating",
        "message": "Allure报告正在生成中",
    })
    redis_client.expire(redis_key, 3600)

    db = SessionLocal()
    try:
        task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            redis_client.hset(redis_key, mapping={
                "status": "error",
                "message": "测试任务不存在，无法生成Allure报告",
            })
            redis_client.expire(redis_key, 600)
            return

        if not task.allure_report_path:
            redis_client.hset(redis_key, mapping={
                "status": "error",
                "message": "未找到Allure结果目录",
            })
            redis_client.expire(redis_key, 600)
            return

        current_path = task.allure_report_path
        # 如果已经存在HTML报告，直接返回成功
        if os.path.isdir(current_path) and os.path.exists(os.path.join(current_path, "index.html")):
            redis_client.hset(redis_key, mapping={
                "status": "success",
                "message": "Allure报告已生成",
                "url": f"/api/jobs/{task_id}/allure-report",
            })
            redis_client.expire(redis_key, 3600)
            return

        # 推断allure-results与allure-report路径
        if current_path.endswith("allure-report"):
            report_dir = current_path
            results_dir = current_path.replace("allure-report", "allure-results")
        else:
            results_dir = current_path
            report_dir = os.path.join(os.path.dirname(current_path), "allure-report")

        # 检查results_dir是否存在，并添加详细日志
        print(f"[generate_allure_report_async] 检查results_dir: {results_dir}")
        print(f"[generate_allure_report_async] os.path.exists: {os.path.exists(results_dir)}")
        print(f"[generate_allure_report_async] os.path.isdir: {os.path.isdir(results_dir)}")
        
        if not os.path.isdir(results_dir):
            error_msg = f"未找到Allure原始结果目录: {results_dir}（路径存在: {os.path.exists(results_dir)}）"
            print(f"[generate_allure_report_async] {error_msg}")
            redis_client.hset(redis_key, mapping={
                "status": "error",
                "message": error_msg,
            })
            redis_client.expire(redis_key, 600)
            return
        
        # 检查目录是否为空
        try:
            files_in_dir = os.listdir(results_dir)
            if len(files_in_dir) == 0:
                error_msg = f"Allure原始结果目录为空: {results_dir}"
                print(f"[generate_allure_report_async] {error_msg}")
                redis_client.hset(redis_key, mapping={
                    "status": "error",
                    "message": error_msg,
                })
                redis_client.expire(redis_key, 600)
                return
            print(f"[generate_allure_report_async] 找到 {len(files_in_dir)} 个结果文件")
        except Exception as e:
            error_msg = f"无法读取Allure结果目录: {str(e)}"
            print(f"[generate_allure_report_async] {error_msg}")
            redis_client.hset(redis_key, mapping={
                "status": "error",
                "message": error_msg,
            })
            redis_client.expire(redis_key, 600)
            return

        # 确保报告目录存在
        os.makedirs(report_dir, exist_ok=True)

        # 检查allure命令
        # 检查Allure是否安装（使用完整路径或which命令）
        allure_path = '/usr/local/bin/allure'
        # 先检查完整路径是否存在
        if not os.path.exists(allure_path):
            # 如果完整路径不存在，尝试使用which命令查找
            allure_check = subprocess.run([
                'which', 'allure'
            ], capture_output=True, text=True, timeout=5)
            if allure_check.returncode == 0:
                allure_path = allure_check.stdout.decode().strip()
            else:
                allure_path = None

        if not allure_path or not os.path.exists(allure_path):
            redis_client.hset(redis_key, mapping={
                "status": "error",
                "message": "Allure命令未安装，无法生成报告",
            })
            redis_client.expire(redis_key, 600)
            return

        # 生成Allure报告
        result = subprocess.run(
            [allure_path, 'generate', results_dir, '-o', report_dir, '--clean'],
            capture_output=True,
            text=True,
            timeout=180
        )

        if result.returncode != 0:
            error_msg = result.stderr[:500] if result.stderr else "未知错误"
            redis_client.hset(redis_key, mapping={
                "status": "error",
                "message": f"Allure报告生成失败: {error_msg}",
            })
            redis_client.expire(redis_key, 600)
            return

        # 更新任务记录
        task.allure_report_path = report_dir
        db.commit()

        redis_client.hset(redis_key, mapping={
            "status": "success",
            "message": "Allure报告生成完成",
            "url": f"/api/jobs/{task_id}/allure-report",
        })
        redis_client.expire(redis_key, 3600)
    except Exception as e:
        redis_client.hset(redis_key, mapping={
            "status": "error",
            "message": f"生成Allure报告时发生异常: {str(e)}",
        })
        redis_client.expire(redis_key, 600)
        raise
    finally:
        db.close()


def analyze_performance_with_deepseek(jtl_file_path: str, task_id: int, task_name: str = "", threads: int = 10, duration: int = 5) -> Dict[str, Any]:
    """
    使用DeepSeek分析JTL文件，提供性能瓶颈分析和优化建议，并生成HTML报告
    
    Args:
        jtl_file_path: JTL文件路径（容器内路径）
        task_id: 任务ID
        task_name: 任务名称
        threads: 线程数
        duration: 执行时长（分钟）
        
    Returns:
        分析结果字典，包含HTML报告
    """
    import pandas as pd
    import requests
    from app.config import settings
    
    # 从容器中读取JTL文件
    local_jtl = f"/tmp/jtl_task_{task_id}.jtl"
    try:
        # 先复制到本地临时文件
        subprocess.run(
            ['docker', 'cp', f'api_test_jmeter:{jtl_file_path}', local_jtl],
            timeout=10,
            check=True
        )
        
        # 读取JTL文件
        df = pd.read_csv(local_jtl)
        df['timeStamp'] = pd.to_datetime(df['timeStamp'], unit='ms')
    except Exception as e:
        return {"error": f"读取JTL文件失败: {str(e)}"}
    
    # 基本统计分析
    basic_stats = df.groupby('label')['elapsed'].agg([
        'count', 'mean', 'median', 'min', 'max', 'std'
    ]).round(2)
    
    # 错误分析
    error_analysis = df[df['success'] == False].groupby('label').size()
    
    # 吞吐量分析（按时间窗口）
    df['time_window'] = ((df['timeStamp'] - df['timeStamp'].min()).dt.total_seconds() // 10) * 10
    throughput = df.groupby('time_window').size()
    
    # 构建分析提示词（参考专业的JTL分析方法）
    analysis_prompt = f"""
你是一个专业的性能测试分析专家。请根据以下JMeter测试数据，按照系统性的分析方法进行性能瓶颈识别和优化建议。

## 测试数据概览

### 1. 基本统计信息（响应时间，单位：毫秒）
{basic_stats.to_string()}

### 2. 错误分析
{error_analysis.to_string() if not error_analysis.empty else "无错误"}

### 3. 吞吐量统计（每10秒的请求数）
- 平均吞吐量: {throughput.mean():.2f} 请求/10秒
- 最大吞吐量: {throughput.max()} 请求/10秒
- 最小吞吐量: {throughput.min()} 请求/10秒

## 分析要求

请按照以下系统性方法进行分析：

### 一、响应时间分析
1. **慢接口识别**：识别响应时间超过1000ms的慢接口，重点关注P95和P99分位数
2. **响应时间分布**：分析响应时间的分布特征（正态分布、长尾分布等）
3. **响应时间趋势**：检查响应时间是否随时间变化，是否存在性能退化

### 二、吞吐量分析
1. **TPS评估**：评估TPS是否达到预期，是否存在瓶颈
2. **吞吐量稳定性**：分析吞吐量是否稳定，是否存在波动
3. **吞吐量瓶颈**：识别吞吐量达到平台期的接口

### 三、错误率分析
1. **错误率统计**：计算各接口的错误率
2. **错误类型分析**：分析错误类型分布（4xx、5xx等）
3. **错误时间分布**：检查错误是否集中在特定时间段

### 四、并发性能分析
1. **并发效率**：分析并发线程数与吞吐量的关系
2. **并发瓶颈**：识别并发数增加但吞吐量不增长的情况
3. **资源利用率**：评估系统资源利用情况

### 五、瓶颈类型识别（重点）
根据以下模式识别瓶颈类型：

1. **应用层瓶颈**
   - 特征：响应时间随并发线性增长，错误率在高压下急剧上升
   - 可能原因：代码效率低、算法复杂、缺少缓存

2. **数据库瓶颈**
   - 特征：响应时间出现周期性峰值，特定查询接口性能差
   - 可能原因：慢查询、缺少索引、连接池配置不当

3. **网络瓶颈**
   - 特征：高连接时间（Connect Time），吞吐量达到网络带宽上限
   - 可能原因：网络延迟高、带宽不足、连接未复用

4. **内存瓶颈**
   - 特征：响应时间逐渐变慢，错误率随时间推移增加
   - 可能原因：内存泄漏、缓存策略不当、GC频繁

5. **CPU瓶颈**
   - 特征：响应时间与CPU使用率强相关，吞吐量达到平台期
   - 可能原因：CPU密集型操作、线程竞争、计算效率低

### 六、性能退化分析
1. **时间分段对比**：将测试时间分为多个阶段，对比各阶段性能
2. **性能变化趋势**：识别性能下降超过10%的接口
3. **内存泄漏检测**：检查是否存在响应时间逐渐增长的情况

### 七、资源瓶颈识别
1. **连接时间分析**：识别连接时间大于100ms的接口（网络问题）
2. **服务器延迟分析**：识别服务器处理延迟大于500ms的接口（应用问题）
3. **资源竞争分析**：识别资源竞争导致的性能问题

## 优化建议要求

请针对识别出的瓶颈，提供具体的、可执行的优化建议：

### 1. 应用层优化
- 代码优化：具体指出哪些代码需要优化
- 算法优化：建议更高效的算法
- 缓存策略：建议缓存哪些数据，使用什么缓存策略

### 2. 数据库优化
- 查询优化：指出慢查询，建议优化方案
- 索引优化：建议添加哪些索引
- 连接池配置：建议连接池参数调整

### 3. 网络优化
- CDN使用：建议使用CDN的场景
- 负载均衡：建议负载均衡策略
- 连接复用：建议连接复用方案

### 4. 架构优化
- 微服务拆分：建议拆分的服务
- 异步处理：建议异步化的操作
- 消息队列：建议使用消息队列的场景

## 输出格式要求

请以结构化的JSON格式返回分析结果，必须包含以下字段：

```json
{{
  "summary": "总体分析摘要（200-300字）",
  "bottlenecks": [
    {{
      "type": "瓶颈类型（应用层/数据库/网络/内存/CPU）",
      "api": "接口名称或标识",
      "severity": "严重程度（高/中/低）",
      "impact": "影响描述（具体说明对性能的影响）",
      "evidence": "证据（提供数据支撑）",
      "suggestion": "具体优化建议"
    }}
  ],
  "recommendations": [
    {{
      "category": "建议类别（应用层优化/数据库优化/网络优化/架构优化）",
      "description": "详细描述（具体说明如何优化）",
      "priority": "优先级（高/中/低）",
      "difficulty": "实施难度（高/中/低）",
      "expected_improvement": "预期改善（说明优化后预期达到的效果）"
    }}
  ],
  "metrics": {{
    "avg_response_time": "平均响应时间（ms）",
    "max_response_time": "最大响应时间（ms）",
    "p95_response_time": "P95响应时间（ms）",
    "p99_response_time": "P99响应时间（ms）",
    "error_rate": "错误率（%）",
    "throughput": "吞吐量（请求/秒）",
    "concurrent_efficiency": "并发效率"
  }},
  "key_findings": [
    "关键发现1（具体的数据和结论）",
    "关键发现2",
    "关键发现3"
  ]
}}
```

**重要提示**：
1. 必须基于提供的数据进行客观分析，不要编造数据
2. 瓶颈识别要具体到接口级别
3. 优化建议要可执行，避免空泛的建议
4. 如果数据中没有明显的瓶颈，也要说明原因
5. 所有数值要准确，不要估算
"""
    
    # 调用DeepSeek API
    print(f"[analyze_performance_with_deepseek] 准备调用DeepSeek API，API Key: {'已设置' if settings.DEEPSEEK_API_KEY else '未设置'}")
    try:
        print(f"[analyze_performance_with_deepseek] 发送请求到DeepSeek API...")
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的性能测试分析专家，擅长分析JMeter测试结果并提供优化建议。请以JSON格式返回分析结果。"
                    },
                    {
                        "role": "user",
                        "content": analysis_prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 3000
            },
            timeout=60  # 减少超时时间到60秒，避免长时间阻塞
        )
        
        print(f"[analyze_performance_with_deepseek] DeepSeek API响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            analysis_text = result['choices'][0]['message']['content']
            print(f"[analyze_performance_with_deepseek] DeepSeek返回的原始文本长度: {len(analysis_text)}")
            print(f"[analyze_performance_with_deepseek] DeepSeek返回的原始文本前500字符: {analysis_text[:500]}")
            
            # 尝试解析JSON（如果返回的是JSON格式）
            try:
                import re
                json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
                if json_match:
                    analysis_json = json.loads(json_match.group())
                    print(f"[analyze_performance_with_deepseek] 成功解析JSON，包含字段: {list(analysis_json.keys())}")
                else:
                    analysis_json = {"raw_analysis": analysis_text}
                    print(f"[analyze_performance_with_deepseek] 未找到JSON格式，使用原始文本")
            except Exception as parse_error:
                print(f"[analyze_performance_with_deepseek] JSON解析失败: {parse_error}")
                analysis_json = {"raw_analysis": analysis_text}
            
            # 生成HTML报告（在返回前生成，确保JTL文件仍然存在）
            html_report = ""
            try:
                from app.services.performance_report_generator import generate_performance_report_html
                # 构建deepseek_analysis对象，确保analysis字段包含完整的分析结果
                deepseek_analysis_data = {
                    "analysis": analysis_json,  # DeepSeek返回的JSON分析结果
                    "basic_stats": basic_stats.to_dict(),
                    "error_analysis": error_analysis.to_dict() if not error_analysis.empty else {},
                    "throughput_stats": {
                        "mean": float(throughput.mean()),
                        "max": int(throughput.max()),
                        "min": int(throughput.min())
                    }
                }
                
                # 打印调试信息
                print(f"[analyze_performance_with_deepseek] DeepSeek分析结果: {json.dumps(analysis_json, ensure_ascii=False)[:500]}")
                
                html_report = generate_performance_report_html(
                    jtl_file_path=local_jtl,
                    task_id=task_id,
                    task_name=task_name or f"任务{task_id}",
                    threads=threads,
                    duration=duration,
                    deepseek_analysis=deepseek_analysis_data
                )
            except Exception as e:
                print(f"[analyze_performance_with_deepseek] 生成HTML报告失败: {e}")
                import traceback
                traceback.print_exc()
                html_report = f"<html><body><h1>报告生成失败</h1><pre>{str(e)}</pre></body></html>"
            
            result = {
                "status": "success",
                "analysis": analysis_json,
                "html_report": html_report,
                "basic_stats": basic_stats.to_dict(),
                "error_analysis": error_analysis.to_dict() if not error_analysis.empty else {},
                "throughput_stats": {
                    "mean": float(throughput.mean()),
                    "max": int(throughput.max()),
                    "min": int(throughput.min())
                }
            }
            
            # 清理临时文件
            if os.path.exists(local_jtl):
                os.remove(local_jtl)
            
            return result
        else:
            return {"error": f"DeepSeek API调用失败: {response.status_code}", "response": response.text}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 清理临时文件
        if 'local_jtl' in locals() and os.path.exists(local_jtl):
            os.remove(local_jtl)
        return {"error": f"DeepSeek分析失败: {str(e)}"}
