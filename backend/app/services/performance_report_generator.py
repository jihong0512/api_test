"""
性能测试报告生成器
生成包含图表的HTML性能分析报告
"""
import pandas as pd
import numpy as np
import base64
import io
from typing import Dict, Any, Optional
from datetime import datetime
import json

try:
    import matplotlib
    matplotlib.use('Agg')  # 使用非交互式后端
    import matplotlib.pyplot as plt
    import seaborn as sns
    # 配置中文字体，解决乱码问题
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'SimHei', 'WenQuanYi Micro Hei', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    sns = None


def load_jtl_file(file_path: str) -> pd.DataFrame:
    """读取JTL文件"""
    df = pd.read_csv(file_path)
    df['timeStamp'] = pd.to_datetime(df['timeStamp'], unit='ms')
    df['timestamp_seconds'] = (df['timeStamp'] - df['timeStamp'].min()).dt.total_seconds()
    return df


def basic_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """基本统计信息"""
    stats = df.groupby('label')['elapsed'].agg([
        'count', 'mean', 'median', 'min', 'max', 'std',
        lambda x: x.quantile(0.90),  # 90% 分位
        lambda x: x.quantile(0.95),  # 95% 分位
        lambda x: x.quantile(0.99)   # 99% 分位
    ]).round(2)
    
    # 使用英文列名避免乱码
    stats.columns = ['Count', 'Mean', 'Median', 'Min', 'Max', 'Std', 'P90', 'P95', 'P99']
    return stats


def analyze_response_times(df: pd.DataFrame) -> Dict[str, Any]:
    """分析响应时间分布"""
    if not MATPLOTLIB_AVAILABLE:
        return {"error": "matplotlib不可用"}
    
    try:
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('响应时间分析', fontsize=16, fontweight='bold')
        
        # 1. 响应时间箱线图
        labels = df['label'].unique()
        data_for_boxplot = [df[df['label'] == label]['elapsed'].values for label in labels]
        # 处理标签：如果包含非ASCII字符或过长，使用API编号
        display_labels = []
        for i, label in enumerate(labels):
            label_str = str(label)
            # 检查是否包含非ASCII字符（中文等）
            if any(ord(c) > 127 for c in label_str) or len(label_str) > 20:
                display_labels.append(f"API_{i+1}")
            else:
                display_labels.append(label_str[:20])
        axes[0, 0].boxplot(data_for_boxplot, labels=display_labels)
        axes[0, 0].set_title('Response Time Distribution - Boxplot', fontsize=12)
        axes[0, 0].set_ylabel('Response Time (ms)', fontsize=10)
        axes[0, 0].tick_params(axis='x', rotation=45, labelsize=8)
        axes[0, 0].grid(True, alpha=0.3)
        
        # 2. 响应时间趋势
        for i, label in enumerate(labels[:10]):  # 限制最多10个接口，避免图表过于拥挤
            label_data = df[df['label'] == label]
            if len(label_data) > 0:
                label_str = str(label)
                # 检查是否包含非ASCII字符或过长
                if any(ord(c) > 127 for c in label_str) or len(label_str) > 15:
                    display_label = f"API_{i+1}"
                else:
                    display_label = label_str[:15]
                axes[0, 1].plot(label_data['timestamp_seconds'], 
                              label_data['elapsed'], label=display_label, alpha=0.7, linewidth=1)
        axes[0, 1].set_title('Response Time Trend', fontsize=12)
        axes[0, 1].legend(loc='upper right', fontsize=7)
        axes[0, 1].set_ylabel('Response Time (ms)', fontsize=10)
        axes[0, 1].set_xlabel('Time (seconds)', fontsize=10)
        axes[0, 1].grid(True, alpha=0.3)
        
        # 3. 响应时间分布直方图
        axes[1, 0].hist(df['elapsed'], bins=50, edgecolor='black', alpha=0.7)
        axes[1, 0].set_title('Response Time Histogram', fontsize=12)
        axes[1, 0].set_xlabel('Response Time (ms)', fontsize=10)
        axes[1, 0].set_ylabel('Frequency', fontsize=10)
        axes[1, 0].grid(True, alpha=0.3)
        
        # 4. 累积分布函数
        sorted_times = np.sort(df['elapsed'])
        yvals = np.arange(len(sorted_times)) / float(len(sorted_times))
        axes[1, 1].plot(sorted_times, yvals, linewidth=2)
        axes[1, 1].set_title('Response Time CDF', fontsize=12)
        axes[1, 1].set_xlabel('Response Time (ms)', fontsize=10)
        axes[1, 1].set_ylabel('Cumulative Probability', fontsize=10)
        axes[1, 1].grid(True, alpha=0.3)
        
        fig.suptitle('Response Time Analysis', fontsize=14, fontweight='bold')
        plt.tight_layout()
        
        # 转换为base64图片
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode('utf-8')
        plt.close(fig)
        
        return {"chart_base64": img_base64}
    except Exception as e:
        return {"error": f"生成响应时间图表失败: {str(e)}"}


def analyze_throughput(df: pd.DataFrame) -> Dict[str, Any]:
    """分析吞吐量"""
    if not MATPLOTLIB_AVAILABLE:
        return {"error": "matplotlib不可用"}
    
    try:
        # 按时间窗口统计吞吐量
        df['time_window'] = (df['timestamp_seconds'] // 10) * 10  # 10秒窗口
        
        throughput = df.groupby(['time_window', 'label']).size().unstack(fill_value=0)
        
        fig, axes = plt.subplots(2, 1, figsize=(12, 8))
        fig.suptitle('Throughput Analysis', fontsize=16, fontweight='bold')
        
        # 总吞吐量
        total_throughput = df.groupby('time_window').size()
        axes[0].plot(total_throughput.index, total_throughput.values, linewidth=2, color='#2E86AB')
        axes[0].fill_between(total_throughput.index, total_throughput.values, alpha=0.3, color='#2E86AB')
        axes[0].set_title('Total Throughput (requests/10s)', fontsize=12)
        axes[0].set_ylabel('Request Count', fontsize=10)
        axes[0].set_xlabel('Time (seconds)', fontsize=10)
        axes[0].grid(True, alpha=0.3)
        
        # 各接口吞吐量（最多显示10个接口）
        top_labels = df['label'].value_counts().head(10).index
        for i, label in enumerate(top_labels):
            if label in throughput.columns:
                label_str = str(label)
                # 检查是否包含非ASCII字符或过长
                if any(ord(c) > 127 for c in label_str) or len(label_str) > 15:
                    display_label = f"API_{i+1}"
                else:
                    display_label = label_str[:15]
                axes[1].plot(throughput.index, throughput[label], label=display_label, linewidth=1.5, alpha=0.7)
        axes[1].set_title('API Throughput', fontsize=12)
        axes[1].set_ylabel('Request Count', fontsize=10)
        axes[1].set_xlabel('Time (seconds)', fontsize=10)
        axes[1].legend(loc='upper right', fontsize=7)
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 转换为base64图片
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode('utf-8')
        plt.close(fig)
        
        # 计算吞吐量统计
        throughput_stats = {
            "mean": float(total_throughput.mean()),
            "max": int(total_throughput.max()),
            "min": int(total_throughput.min()),
            "std": float(total_throughput.std())
        }
        
        return {
            "chart_base64": img_base64,
            "stats": throughput_stats
        }
    except Exception as e:
        return {"error": f"生成吞吐量图表失败: {str(e)}"}


def analyze_errors(df: pd.DataFrame) -> Dict[str, Any]:
    """分析错误情况"""
    if not MATPLOTLIB_AVAILABLE:
        return {"error": "matplotlib不可用"}
    
    try:
        error_analysis = df.groupby('label').agg({
            'responseCode': 'count',
            'success': lambda x: (x == False).sum()
        }).rename(columns={'responseCode': 'Total', 'success': 'Failed'})
        
        error_analysis['ErrorRate'] = (error_analysis['Failed'] / error_analysis['Total'] * 100).round(2)
        error_analysis['SuccessRate'] = 100 - error_analysis['ErrorRate']
        
        # 错误类型分析
        error_codes = df[df['success'] == False]['responseCode'].value_counts()
        
        fig, axes = plt.subplots(1, 2, figsize=(15, 5))
        fig.suptitle('Error Analysis', fontsize=16, fontweight='bold')
        
        # 错误率柱状图
        if not error_analysis.empty and error_analysis['ErrorRate'].sum() > 0:
            # 处理API名称，如果包含中文则使用索引编号
            error_analysis_display = error_analysis.copy()
            error_analysis_display.index = [f"API_{i+1}" if len(str(idx)) > 20 or any(ord(c) > 127 for c in str(idx)) else str(idx)[:20] 
                                           for i, idx in enumerate(error_analysis.index)]
            error_analysis_display['ErrorRate'].plot.bar(ax=axes[0], color='#E63946')
            axes[0].set_title('Error Rate by API', fontsize=12)
            axes[0].set_ylabel('Error Rate (%)', fontsize=10)
            axes[0].tick_params(axis='x', rotation=45, labelsize=8)
            axes[0].grid(True, alpha=0.3, axis='y')
        else:
            axes[0].text(0.5, 0.5, 'No Errors', ha='center', va='center', fontsize=14)
            axes[0].set_title('Error Rate by API', fontsize=12)
        
        # 错误类型分布
        if not error_codes.empty:
            error_codes.head(10).plot.bar(ax=axes[1], color='#F77F00')
            axes[1].set_title('Error Type Distribution', fontsize=12)
            axes[1].set_ylabel('Error Count', fontsize=10)
            axes[1].tick_params(axis='x', rotation=45, labelsize=8)
            axes[1].grid(True, alpha=0.3, axis='y')
        else:
            axes[1].text(0.5, 0.5, 'No Errors', ha='center', va='center', fontsize=14)
            axes[1].set_title('Error Type Distribution', fontsize=12)
        
        plt.tight_layout()
        
        # 转换为base64图片
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode('utf-8')
        plt.close(fig)
        
        return {
            "chart_base64": img_base64,
            "error_analysis": error_analysis.to_dict('index'),
            "error_codes": error_codes.to_dict()
        }
    except Exception as e:
        return {"error": f"生成错误分析图表失败: {str(e)}"}


def identify_slow_requests(df: pd.DataFrame, threshold_ms: int = 1000) -> Dict[str, Any]:
    """识别慢请求"""
    slow_requests = df[df['elapsed'] > threshold_ms]
    
    if not slow_requests.empty:
        slow_by_label = slow_requests.groupby('label').agg({
            'elapsed': ['count', 'mean', 'max']
        }).round(2)
        slow_by_label.columns = ['慢请求数', '平均响应时间', '最大响应时间']
        
        return {
            "slow_count": len(slow_requests),
            "slow_by_label": slow_by_label.to_dict('index'),
            "threshold_ms": threshold_ms
        }
    else:
        return {
            "slow_count": 0,
            "slow_by_label": {},
            "threshold_ms": threshold_ms
        }


def analyze_concurrent_performance(df: pd.DataFrame) -> Dict[str, Any]:
    """分析并发性能"""
    if not MATPLOTLIB_AVAILABLE:
        return {"error": "matplotlib不可用"}
    
    try:
        # 检查是否有allThreads列
        if 'allThreads' not in df.columns:
            return {"error": "JTL文件中没有allThreads列"}
        
        # 线程数随时间变化
        df['minute'] = (df['timestamp_seconds'] // 60).astype(int)
        
        concurrent_stats = df.groupby('minute').agg({
            'allThreads': 'max',  # 最大并发线程数
            'elapsed': 'mean',    # 平均响应时间
            'label': 'count'      # 吞吐量
        }).rename(columns={'allThreads': 'MaxConcurrency', 'elapsed': 'AvgResponseTime', 'label': 'RequestCount'})
        
        # 计算并发效率
        concurrent_stats['ConcurrencyEfficiency'] = (concurrent_stats['RequestCount'] / concurrent_stats['MaxConcurrency']).round(2)
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Concurrent Performance Analysis', fontsize=16, fontweight='bold')
        
        # 并发数 vs 响应时间
        axes[0, 0].scatter(concurrent_stats['MaxConcurrency'], concurrent_stats['AvgResponseTime'], 
                         alpha=0.6, s=50, color='#2E86AB')
        axes[0, 0].set_xlabel('Concurrent Threads', fontsize=10)
        axes[0, 0].set_ylabel('Avg Response Time (ms)', fontsize=10)
        axes[0, 0].set_title('Concurrency vs Response Time', fontsize=12)
        axes[0, 0].grid(True, alpha=0.3)
        
        # 并发数 vs 吞吐量
        axes[0, 1].scatter(concurrent_stats['MaxConcurrency'], concurrent_stats['RequestCount'], 
                          alpha=0.6, s=50, color='#A23B72')
        axes[0, 1].set_xlabel('Concurrent Threads', fontsize=10)
        axes[0, 1].set_ylabel('Throughput (req/min)', fontsize=10)
        axes[0, 1].set_title('Concurrency vs Throughput', fontsize=12)
        axes[0, 1].grid(True, alpha=0.3)
        
        # 并发效率
        axes[1, 0].plot(concurrent_stats.index, concurrent_stats['ConcurrencyEfficiency'], 
                       linewidth=2, color='#F18F01')
        axes[1, 0].set_xlabel('Time (minutes)', fontsize=10)
        axes[1, 0].set_ylabel('Concurrency Efficiency', fontsize=10)
        axes[1, 0].set_title('Concurrency Efficiency Trend', fontsize=12)
        axes[1, 0].grid(True, alpha=0.3)
        
        # 响应时间分布热力图
        pivot_data = df.pivot_table(values='elapsed', 
                                   index='minute', 
                                   columns='label', 
                                   aggfunc='mean')
        if not pivot_data.empty:
            # 处理API名称，如果包含中文或过长则使用编号
            pivot_data.columns = [f"API_{i+1}" if len(str(col)) > 15 or any(ord(c) > 127 for c in str(col)) else str(col)[:15] 
                                 for i, col in enumerate(pivot_data.columns)]
            sns.heatmap(pivot_data.head(20), ax=axes[1, 1], cmap='YlOrRd', cbar_kws={'label': 'Response Time (ms)'})
            axes[1, 1].set_title('API Response Time Heatmap', fontsize=12)
            axes[1, 1].set_xlabel('API', fontsize=10)
            axes[1, 1].set_ylabel('Time (minutes)', fontsize=10)
        
        plt.tight_layout()
        
        # 转换为base64图片
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode('utf-8')
        plt.close(fig)
        
        return {
            "chart_base64": img_base64,
            "stats": concurrent_stats.to_dict('index')
        }
    except Exception as e:
        return {"error": f"生成并发性能图表失败: {str(e)}"}


def analyze_performance_degradation(df: pd.DataFrame) -> Dict[str, Any]:
    """分析性能退化"""
    # 将测试时间分为几个阶段
    df['phase'] = pd.cut(df['timestamp_seconds'], bins=4, labels=['Phase1', 'Phase2', 'Phase3', 'Phase4'])
    
    phase_comparison = df.groupby(['phase', 'label']).agg({
        'elapsed': ['mean', 'std', 'count'],
        'success': 'mean'
    }).round(2)
    
    # 计算性能变化
    phase_pivot = df.pivot_table(values='elapsed', 
                                index='label', 
                                columns='phase', 
                                aggfunc='mean')
    
    if 'Phase1' in phase_pivot.columns and 'Phase4' in phase_pivot.columns:
        phase_pivot['性能变化'] = ((phase_pivot['Phase4'] - phase_pivot['Phase1']) / phase_pivot['Phase1'] * 100).round(2)
    else:
        phase_pivot['性能变化'] = 0
    
    # 识别性能退化的接口
    degraded_apis = phase_pivot[phase_pivot['性能变化'] > 10]  # 性能下降超过10%
    
    return {
        "phase_comparison": phase_comparison.to_dict('index') if not phase_comparison.empty else {},
        "phase_pivot": phase_pivot.to_dict('index'),
        "degraded_apis": degraded_apis.to_dict('index') if not degraded_apis.empty else {}
    }


def identify_resource_bottlenecks(df: pd.DataFrame) -> Dict[str, Any]:
    """识别资源瓶颈模式"""
    result = {}
    
    # 连接时间分析
    if 'Connect' in df.columns:
        connect_analysis = df.groupby('label')['Connect'].agg(['mean', 'max', 'std']).round(2)
        high_connect_apis = connect_analysis[connect_analysis['mean'] > 100]  # 连接时间大于100ms
        result['connect_analysis'] = connect_analysis.to_dict('index')
        result['high_connect_apis'] = high_connect_apis.to_dict('index') if not high_connect_apis.empty else {}
    
    # 延迟分析
    if 'Latency' in df.columns:
        latency_analysis = df.groupby('label')['Latency'].agg(['mean', 'max', 'std']).round(2)
        high_latency_apis = latency_analysis[latency_analysis['mean'] > 500]  # 服务器处理延迟大于500ms
        result['latency_analysis'] = latency_analysis.to_dict('index')
        result['high_latency_apis'] = high_latency_apis.to_dict('index') if not high_latency_apis.empty else {}
    
    return result


def _get_summary(deepseek_analysis: Optional[Dict[str, Any]]) -> str:
    """提取摘要"""
    if not deepseek_analysis:
        return "暂无摘要"
    
    # 支持多种数据结构
    # 1. 直接是analysis字段
    analysis = deepseek_analysis.get('analysis', {})
    if not analysis and isinstance(deepseek_analysis, dict):
        # 2. 整个对象就是analysis
        analysis = deepseek_analysis
    
    if isinstance(analysis, dict):
        # 尝试多种可能的字段名
        summary = analysis.get('summary', '') or analysis.get('摘要', '') or analysis.get('overview', '')
        if summary:
            return str(summary)
        raw = analysis.get('raw_analysis', '') or str(analysis)
        if raw and isinstance(raw, str):
            # 如果raw_analysis太长，取前500字符
            return raw[:500] + "..." if len(raw) > 500 else raw
    return "暂无摘要"


def _get_bottlenecks(deepseek_analysis: Optional[Dict[str, Any]]) -> list:
    """提取瓶颈列表"""
    if not deepseek_analysis:
        return []
    
    # 支持多种数据结构
    # 1. 直接是analysis字段
    analysis = deepseek_analysis.get('analysis', {})
    if not analysis and isinstance(deepseek_analysis, dict):
        # 2. 整个对象就是analysis
        analysis = deepseek_analysis
    
    if isinstance(analysis, dict):
        # 尝试多种可能的字段名
        bottlenecks = analysis.get('bottlenecks', []) or analysis.get('bottleneck', [])
        if bottlenecks and isinstance(bottlenecks, list):
            return bottlenecks
        # 如果没有结构化数据，尝试从raw_analysis中提取
        raw = analysis.get('raw_analysis', '') or str(analysis)
        if isinstance(raw, str):
            # 如果包含瓶颈相关关键词，返回原始分析
            if any(keyword in raw for keyword in ['瓶颈', 'bottleneck', '性能问题', '慢']):
                return [{"类型": "性能瓶颈", "描述": raw[:500]}]
    return []


def _get_recommendations(deepseek_analysis: Optional[Dict[str, Any]]) -> list:
    """提取优化建议列表"""
    if not deepseek_analysis:
        return []
    
    # 支持多种数据结构
    # 1. 直接是analysis字段
    analysis = deepseek_analysis.get('analysis', {})
    if not analysis and isinstance(deepseek_analysis, dict):
        # 2. 整个对象就是analysis
        analysis = deepseek_analysis
    
    if isinstance(analysis, dict):
        # 尝试多种可能的字段名
        recommendations = analysis.get('recommendations', []) or analysis.get('recommendation', [])
        if recommendations and isinstance(recommendations, list):
            return recommendations
        # 如果没有结构化数据，尝试从raw_analysis中提取
        raw = analysis.get('raw_analysis', '') or str(analysis)
        if isinstance(raw, str):
            # 如果包含建议相关关键词，返回原始分析
            if any(keyword in raw for keyword in ['优化', '建议', 'recommendation', '建议', '优化方案']):
                # 尝试将文本分割成多个建议
                suggestions = []
                lines = raw.split('\n')
                current_suggestion = ""
                for line in lines:
                    line = line.strip()
                    if line and (line.startswith('-') or line.startswith('•') or line.startswith('1.') or line.startswith('2.')):
                        if current_suggestion:
                            suggestions.append({"类别": "通用", "描述": current_suggestion, "优先级": "中", "实施难度": "中"})
                        current_suggestion = line.lstrip('-•1234567890. ')[:200]
                if current_suggestion:
                    suggestions.append({"类别": "通用", "描述": current_suggestion, "优先级": "中", "实施难度": "中"})
                if suggestions:
                    return suggestions
                return [{"类别": "通用", "描述": raw[:500], "优先级": "中", "实施难度": "中"}]
    return []


def generate_performance_report_html(
    jtl_file_path: str,
    task_id: int,
    task_name: str,
    threads: int,
    duration: int,
    deepseek_analysis: Optional[Dict[str, Any]] = None
) -> str:
    """
    生成包含图表的HTML性能分析报告
    
    Args:
        jtl_file_path: JTL文件路径
        task_id: 任务ID
        task_name: 任务名称
        threads: 线程数
        duration: 执行时长（分钟）
        deepseek_analysis: DeepSeek分析结果
        
    Returns:
        HTML报告内容
    """
    try:
        # 读取JTL文件
        df = load_jtl_file(jtl_file_path)
        
        # 生成各种分析
        basic_stats = basic_statistics(df)
        response_time_chart = analyze_response_times(df)
        throughput_analysis = analyze_throughput(df)
        error_analysis = analyze_errors(df)
        slow_requests = identify_slow_requests(df)
        concurrent_performance = analyze_concurrent_performance(df)
        performance_degradation = analyze_performance_degradation(df)
        resource_bottlenecks = identify_resource_bottlenecks(df)
        
        # 构建HTML报告
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>性能瓶颈分析报告 - {task_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 700;
        }}
        .header .meta {{
            font-size: 1.1em;
            opacity: 0.9;
            margin-top: 15px;
        }}
        .content {{
            padding: 40px;
        }}
        .section {{
            margin-bottom: 50px;
            padding: 30px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .section h2 {{
            color: #333;
            font-size: 1.8em;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e0e0e0;
        }}
        .section h3 {{
            color: #555;
            font-size: 1.4em;
            margin: 25px 0 15px 0;
        }}
        .stats-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .stats-table th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        .stats-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #e0e0e0;
        }}
        .stats-table tr:hover {{
            background: #f5f5f5;
        }}
        .chart-container {{
            text-align: center;
            margin: 30px 0;
            padding: 20px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
        }}
        .bottleneck-card {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .recommendation-card {{
            background: #d1ecf1;
            border-left: 4px solid #17a2b8;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .metric-box {{
            display: inline-block;
            background: white;
            padding: 15px 25px;
            margin: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
            min-width: 150px;
        }}
        .metric-box .value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        .metric-box .label {{
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        .summary {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}
        .summary h2 {{
            color: white;
            border-bottom: 2px solid rgba(255,255,255,0.3);
        }}
        .badge {{
            display: inline-block;
            padding: 5px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            margin: 5px;
        }}
        .badge-success {{
            background: #28a745;
            color: white;
        }}
        .badge-warning {{
            background: #ffc107;
            color: #333;
        }}
        .badge-danger {{
            background: #dc3545;
            color: white;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 性能瓶颈分析报告</h1>
            <div class="meta">
                <p><strong>任务名称:</strong> {task_name}</p>
                <p><strong>任务ID:</strong> {task_id} | <strong>线程数:</strong> {threads} | <strong>执行时长:</strong> {duration}分钟</p>
                <p><strong>生成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </div>
        
        <div class="content">
            <!-- 总体摘要 -->
            <div class="section summary">
                <h2>📊 总体分析摘要</h2>
                <div style="margin-top: 20px;">
                    {_get_summary(deepseek_analysis)}
                </div>
            </div>
            
            <!-- 关键指标 -->
            <div class="section">
                <h2>📈 关键性能指标</h2>
                <div style="text-align: center; margin: 20px 0;">
                    <div class="metric-box">
                        <div class="value">{len(df):,}</div>
                        <div class="label">总请求数</div>
                    </div>
                    <div class="metric-box">
                        <div class="value">{df['elapsed'].mean():.0f}ms</div>
                        <div class="label">平均响应时间</div>
                    </div>
                    <div class="metric-box">
                        <div class="value">{df['elapsed'].max():.0f}ms</div>
                        <div class="label">最大响应时间</div>
                    </div>
                    <div class="metric-box">
                        <div class="value">{(df['success'] == False).sum()}</div>
                        <div class="label">失败请求数</div>
                    </div>
                    <div class="metric-box">
                        <div class="value">{((df['success'] == False).sum() / len(df) * 100):.2f}%</div>
                        <div class="label">错误率</div>
                    </div>
                </div>
            </div>
            
            <!-- 基本统计 -->
            <div class="section">
                <h2>📋 基本统计信息</h2>
                <table class="stats-table">
                    <thead>
                        <tr>
                            <th>API Name</th>
                            <th>Count</th>
                            <th>Mean (ms)</th>
                            <th>Median (ms)</th>
                            <th>Min (ms)</th>
                            <th>Max (ms)</th>
                            <th>P90 (ms)</th>
                            <th>P95 (ms)</th>
                            <th>P99 (ms)</th>
                        </tr>
                    </thead>
                    <tbody>
"""
        
        # 添加统计表格
        for label, row in basic_stats.iterrows():
            # 处理API名称，如果包含中文则转义
            label_display = str(label)
            if any(ord(c) > 127 for c in label_display):
                # 包含非ASCII字符，使用HTML实体编码
                label_display = label_display.encode('ascii', 'xmlcharrefreplace').decode('ascii')
            html_content += f"""
                        <tr>
                            <td><strong>{label_display}</strong></td>
                            <td>{int(row['Count'])}</td>
                            <td>{row['Mean']:.2f}</td>
                            <td>{row['Median']:.2f}</td>
                            <td>{row['Min']:.2f}</td>
                            <td>{row['Max']:.2f}</td>
                            <td>{row['P90']:.2f}</td>
                            <td>{row['P95']:.2f}</td>
                            <td>{row['P99']:.2f}</td>
                        </tr>
"""
        
        html_content += """
                    </tbody>
                </table>
            </div>
            
            <!-- 响应时间分析 -->
            <div class="section">
                <h2>⏱️ 响应时间分析</h2>
"""
        
        if 'chart_base64' in response_time_chart:
            html_content += f"""
                <div class="chart-container">
                    <img src="data:image/png;base64,{response_time_chart['chart_base64']}" alt="响应时间分析图表">
                </div>
"""
        
        if slow_requests.get('slow_count', 0) > 0:
            html_content += f"""
                <h3>🐌 慢请求分析</h3>
                <p>发现 <strong>{slow_requests['slow_count']}</strong> 个慢请求（响应时间 > {slow_requests['threshold_ms']}ms）</p>
"""
        
        html_content += """
            </div>
            
            <!-- 吞吐量分析 -->
            <div class="section">
                <h2>📊 吞吐量分析</h2>
"""
        
        if 'chart_base64' in throughput_analysis:
            html_content += f"""
                <div class="chart-container">
                    <img src="data:image/png;base64,{throughput_analysis['chart_base64']}" alt="吞吐量分析图表">
                </div>
"""
        
        if 'stats' in throughput_analysis:
            stats = throughput_analysis['stats']
            html_content += f"""
                <div style="margin-top: 20px;">
                    <p><strong>平均吞吐量:</strong> {stats.get('mean', 0):.2f} 请求/10秒</p>
                    <p><strong>最大吞吐量:</strong> {stats.get('max', 0)} 请求/10秒</p>
                    <p><strong>最小吞吐量:</strong> {stats.get('min', 0)} 请求/10秒</p>
                </div>
"""
        
        html_content += """
            </div>
            
            <!-- 错误分析 -->
            <div class="section">
                <h2>❌ 错误分析</h2>
"""
        
        if 'chart_base64' in error_analysis:
            html_content += f"""
                <div class="chart-container">
                    <img src="data:image/png;base64,{error_analysis['chart_base64']}" alt="错误分析图表">
                </div>
"""
        
        html_content += """
            </div>
"""
        
        # 并发性能分析
        if 'chart_base64' in concurrent_performance:
            html_content += """
            <!-- 并发性能分析 -->
            <div class="section">
                <h2>🔄 并发性能分析</h2>
"""
            html_content += f"""
                <div class="chart-container">
                    <img src="data:image/png;base64,{concurrent_performance['chart_base64']}" alt="并发性能分析图表">
                </div>
"""
            html_content += """
            </div>
"""
        
        # 关键发现（如果有）
        if deepseek_analysis:
            analysis = deepseek_analysis.get('analysis', {})
            if isinstance(analysis, dict):
                key_findings = analysis.get('key_findings', [])
                if key_findings and isinstance(key_findings, list):
                    html_content += """
            <!-- 关键发现 -->
            <div class="section">
                <h2>🔑 关键发现</h2>
                <ul class="findings-list">
"""
                    for finding in key_findings[:5]:  # 最多显示5个
                        html_content += f"""
                    <li>{finding}</li>
"""
                    html_content += """
                </ul>
            </div>
"""
        
        # 性能瓶颈
        html_content += """
            <!-- 性能瓶颈 -->
            <div class="section">
                <h2>🔍 性能瓶颈识别</h2>
"""
        
        bottlenecks = _get_bottlenecks(deepseek_analysis)
        
        if bottlenecks:
            for bottleneck in bottlenecks[:10]:  # 最多显示10个
                bottleneck_type = bottleneck.get('类型', bottleneck.get('type', '未知'))
                bottleneck_api = bottleneck.get('接口', bottleneck.get('api', '未知'))
                bottleneck_impact = bottleneck.get('影响', bottleneck.get('impact', '未知'))
                bottleneck_suggestion = bottleneck.get('建议', bottleneck.get('suggestion', '未知'))
                bottleneck_severity = bottleneck.get('严重程度', bottleneck.get('severity', '中'))
                bottleneck_evidence = bottleneck.get('证据', bottleneck.get('evidence', ''))
                
                severity_badge = 'badge-danger' if bottleneck_severity == '高' else 'badge-warning' if bottleneck_severity == '中' else 'badge-success'
                
                html_content += f"""
                <div class="bottleneck-card">
                    <h4>{bottleneck_type} - {bottleneck_api} <span class="badge {severity_badge}">{bottleneck_severity}严重</span></h4>
                    <p><strong>影响:</strong> {bottleneck_impact}</p>
                    {f'<p><strong>证据:</strong> {bottleneck_evidence}</p>' if bottleneck_evidence else ''}
                    <p><strong>建议:</strong> {bottleneck_suggestion}</p>
                </div>
"""
        else:
            html_content += "<p>未发现明显的性能瓶颈</p>"
        
        html_content += """
            </div>
            
            <!-- 优化建议 -->
            <div class="section">
                <h2>💡 性能优化建议</h2>
"""
        
        recommendations = _get_recommendations(deepseek_analysis)
        
        if recommendations:
            for rec in recommendations[:15]:  # 最多显示15个
                rec_category = rec.get('类别', rec.get('category', '通用'))
                rec_desc = rec.get('描述', rec.get('description', '未知'))
                rec_priority = rec.get('优先级', rec.get('priority', '中'))
                rec_difficulty = rec.get('实施难度', rec.get('difficulty', '中'))
                rec_improvement = rec.get('预期改善', rec.get('expected_improvement', ''))
                
                priority_badge = 'badge-danger' if rec_priority == '高' else 'badge-warning' if rec_priority == '中' else 'badge-success'
                
                html_content += f"""
                <div class="recommendation-card">
                    <h4>{rec_category} <span class="badge {priority_badge}">{rec_priority}优先级</span> <span class="badge badge-warning">{rec_difficulty}难度</span></h4>
                    <p>{rec_desc}</p>
                    {f'<p><strong>预期改善:</strong> {rec_improvement}</p>' if rec_improvement else ''}
                </div>
"""
        else:
            html_content += "<p>暂无优化建议</p>"
        
        html_content += """
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        return html_content
        
    except Exception as e:
        import traceback
        error_msg = f"生成性能分析报告失败: {str(e)}\n{traceback.format_exc()}"
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>报告生成失败</title>
</head>
<body>
    <h1>报告生成失败</h1>
    <pre>{error_msg}</pre>
</body>
</html>
"""

