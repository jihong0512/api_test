#!/usr/bin/env python3
"""
修复卡住的文档解析任务
用法: python fix_stuck_documents.py [--reset-all] [--document-id DOCUMENT_ID]
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models import Document
from celery.result import AsyncResult
from app.celery_app import celery_app


def check_and_fix_stuck_documents(reset_all=False, document_id=None):
    """检查并修复卡住的文档"""
    db = SessionLocal()
    try:
        # 构建查询
        query = db.query(Document)
        
        if document_id:
            query = query.filter(Document.id == document_id)
        else:
            # 只查找状态为parsing的文档
            query = query.filter(Document.status == "parsing")
        
        stuck_docs = query.all()
        
        if not stuck_docs:
            print("✅ 没有找到卡住的文档")
            return
        
        print(f"=== 找到 {len(stuck_docs)} 个可能卡住的文档 ===\n")
        
        fixed_count = 0
        for doc in stuck_docs:
            print(f"📄 文档ID: {doc.id}")
            print(f"   文件名: {doc.filename}")
            print(f"   状态: {doc.status}")
            print(f"   创建时间: {doc.created_at}")
            
            # 检查文档年龄
            if doc.created_at:
                age = datetime.now() - doc.created_at.replace(tzinfo=None) if doc.created_at.tzinfo else datetime.now() - doc.created_at
                age_minutes = age.total_seconds() / 60
                print(f"   已解析时长: {age_minutes:.1f} 分钟")
                
                # 如果超过30分钟，认为是卡住了
                is_stuck = age_minutes > 30
            else:
                is_stuck = True
                age_minutes = 0
            
            # 检查任务状态
            task_id = None
            task_status = None
            if doc.parse_result:
                try:
                    result = json.loads(doc.parse_result)
                    task_id = result.get("task_id")
                    if task_id:
                        task_result = AsyncResult(task_id, app=celery_app)
                        task_status = task_result.state
                        print(f"   任务ID: {task_id}")
                        print(f"   任务状态: {task_status}")
                        
                        if task_result.ready():
                            if task_result.successful():
                                print(f"   ✅ 任务已完成，但文档状态未更新")
                                # 任务已完成但文档状态未更新，更新文档状态
                                doc.status = "parsed"
                                doc.parse_result = json.dumps(task_result.result, ensure_ascii=False) if task_result.result else doc.parse_result
                                db.commit()
                                print(f"   ✅ 已更新文档状态为 'parsed'")
                                fixed_count += 1
                            else:
                                print(f"   ❌ 任务失败: {task_result.info}")
                                # 任务失败，更新文档状态
                                doc.status = "error"
                                error_info = {
                                    "error": str(task_result.info)[:500] if task_result.info else "任务执行失败"
                                }
                                doc.parse_result = json.dumps(error_info, ensure_ascii=False)
                                db.commit()
                                print(f"   ✅ 已更新文档状态为 'error'")
                                fixed_count += 1
                        elif task_status in ["PENDING", "STARTED", "PROGRESS"]:
                            if is_stuck:
                                print(f"   ⚠️  任务运行时间过长，可能卡住了")
                                if reset_all:
                                    # 撤销任务
                                    try:
                                        celery_app.control.revoke(task_id, terminate=True)
                                        print(f"   ✅ 已撤销任务")
                                    except Exception as e:
                                        print(f"   ❌ 撤销任务失败: {e}")
                                    
                                    # 重置文档状态
                                    doc.status = "error"
                                    doc.parse_result = json.dumps({
                                        "error": f"任务运行超时（{age_minutes:.1f}分钟），已自动重置"
                                    }, ensure_ascii=False)
                                    db.commit()
                                    print(f"   ✅ 已重置文档状态为 'error'")
                                    fixed_count += 1
                except Exception as e:
                    print(f"   ⚠️  检查任务状态失败: {e}")
                    if is_stuck and reset_all:
                        # 如果文档卡住且无法检查任务，直接重置
                        doc.status = "error"
                        doc.parse_result = json.dumps({
                            "error": f"文档解析超时（{age_minutes:.1f}分钟），无法检查任务状态，已自动重置"
                        }, ensure_ascii=False)
                        db.commit()
                        print(f"   ✅ 已重置文档状态为 'error'")
                        fixed_count += 1
            
            print("-" * 60)
        
        print(f"\n✅ 共修复 {fixed_count} 个文档")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="修复卡住的文档解析任务")
    parser.add_argument("--reset-all", action="store_true", help="重置所有卡住的文档（超过30分钟）")
    parser.add_argument("--document-id", type=int, help="指定要检查的文档ID")
    
    args = parser.parse_args()
    
    check_and_fix_stuck_documents(reset_all=args.reset_all, document_id=args.document_id)

