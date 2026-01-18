import React, { useState, useEffect } from 'react';
import { Card, Table, Tag, Button, Space, Select, message, Drawer, Descriptions, Popconfirm } from 'antd';
import { LinkOutlined, DeleteOutlined } from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import ReactECharts from 'echarts-for-react';

const ApiDependencies = () => {
  const { id } = useParams(); // project_id
  const [dependencyGraph, setDependencyGraph] = useState(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedApi, setSelectedApi] = useState(null);
  const [apiDetailDrawerVisible, setApiDetailDrawerVisible] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [authInterface, setAuthInterface] = useState(null);
  const [tokenInfo, setTokenInfo] = useState(null);

  useEffect(() => {
    fetchDocuments();
    fetchDependencyGraph();
  }, [id]);

  const fetchDocuments = async () => {
    try {
      const data = await client.get(`/api/files/?project_id=${id}`);
      setDocuments(data || []);
    } catch (error) {
      console.error('获取文档列表失败', error);
    }
  };

  const fetchDependencyGraph = async () => {
    setLoading(true);
    try {
      // 优先从Neo4j获取依赖关系（即使分析未完成，也能获取已完成的组）
      try {
        const neo4jData = await client.get(`/api/relations/dependencies-from-neo4j/${id}`);
        if (neo4jData && neo4jData.dependency_graph) {
          // 即使节点或边数量为0，也设置数据（可能是分析刚开始）
          const graph = neo4jData.dependency_graph || { nodes: [], edges: [] };
          // 只要有节点或边，就更新拓扑图（即使数量很少，也要显示已完成的组）
          if (graph.nodes && graph.nodes.length > 0) {
            setDependencyGraph(graph);
            setAuthInterface(null);
            setTokenInfo(null);
            // 如果有数据但节点数量较少，提示用户分析正在进行中
            if (graph.nodes.length > 0 && graph.nodes.length < 50) {
              console.log(`当前已分析 ${graph.nodes.length} 个接口节点，${graph.edges?.length || 0} 条依赖关系，分析仍在进行中...`);
            }
            return;
          } else if (graph.edges && graph.edges.length > 0) {
            // 即使没有节点，但有边，也设置图结构（可能节点还在加载中）
            setDependencyGraph(graph);
            return;
          } else {
            // 即使没有节点和边，也设置空图结构，避免显示错误
            setDependencyGraph({ nodes: [], edges: [] });
          }
        }
      } catch (neo4jError) {
        console.log('Neo4j依赖分析API调用失败:', neo4jError.response?.status, neo4jError.message);
      }
      
      // 如果Neo4j没有数据，尝试从数据库获取（降级方案）
      try {
        const data = await client.get(`/api/relations/dependency-graph/${id}`);
        if (data && data.dependency_graph) {
          setDependencyGraph(data.dependency_graph);
        } else {
          setDependencyGraph({ nodes: [], edges: [] });
        }
      } catch (dbError) {
        console.log('从数据库获取依赖关系失败:', dbError.response?.status, dbError.message);
        // 如果所有方法都失败，设置空图
        setDependencyGraph({ nodes: [], edges: [] });
      }
    } catch (error) {
      console.error('获取依赖关系图失败', error);
      const status = error.response?.status;
      const messageText = error.response?.data?.detail || error.message;
      
      if (status === 401) {
        message.error('认证失败，请重新登录');
      } else if (status === 404) {
        console.log('API路由不存在，可能是后端未更新');
        message.warning('API路由未找到，请确认后端服务已更新');
      } else {
        message.error(`获取依赖关系图失败: ${messageText}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const [taskId, setTaskId] = useState(null);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [analysisMessage, setAnalysisMessage] = useState('');

  // 轮询任务状态（后台持续监听，即使离开页面也会继续）
  useEffect(() => {
    if (!taskId) return;

    // 使用localStorage保存taskId，以便页面刷新后继续监听
    localStorage.setItem(`analysis_task_${id}`, taskId);

    const pollInterval = setInterval(async () => {
      try {
        const response = await client.get(`/api/relations/task-status/${taskId}`);
        
        if (response.status === 'pending') {
          // pending状态时也显示进度
          setAnalysisProgress(response.progress || 0);
          setAnalysisMessage(response.message || '任务等待执行...');
          setAnalyzing(true);
          // 保存进度到localStorage
          localStorage.setItem(`analysis_progress_${id}`, JSON.stringify({
            progress: response.progress,
            message: response.message,
            taskId: taskId
          }));
        } else if (response.status === 'processing') {
          setAnalysisProgress(response.progress || 0);
          setAnalysisMessage(response.message || '正在处理...');
          setAnalyzing(true);
          // 保存进度到localStorage
          localStorage.setItem(`analysis_progress_${id}`, JSON.stringify({
            progress: response.progress,
            message: response.message,
            taskId: taskId
          }));
          
          // 分析进行中时，定期刷新依赖关系图（显示已完成的组）
          // 每5秒刷新一次，确保实时显示已完成的组
          const currentTime = Date.now();
          const lastRefreshTime = localStorage.getItem(`last_graph_refresh_${id}`);
          if (!lastRefreshTime || (currentTime - parseInt(lastRefreshTime)) > 5000) {
            // 刷新依赖关系图（显示已完成的组）
            fetchDependencyGraph().catch(err => {
              console.log('刷新依赖关系图失败（分析进行中）:', err);
            });
            localStorage.setItem(`last_graph_refresh_${id}`, currentTime.toString());
          }
        } else if (response.status === 'success') {
          clearInterval(pollInterval);
          setAnalyzing(false);
          setTaskId(null);
          setAnalysisProgress(100);
          setAnalysisMessage('分析完成');
          
          // 清除localStorage中的任务信息
          localStorage.removeItem(`analysis_task_${id}`);
          localStorage.removeItem(`analysis_progress_${id}`);
          
          // 显示成功通知（使用toast）
          message.success({
            content: response.message || '接口依赖分析完成！',
            duration: 5,
            key: 'analysis_complete'
          });
          
          // 分析完成后自动刷新依赖关系图
          await fetchDependencyGraph();
          
          // 通知场景用例集页面刷新数据
          localStorage.setItem(`scenario_suites_refresh_${id}`, Date.now().toString());
          // 触发storage事件，让其他页面可以监听到
          window.dispatchEvent(new Event('storage'));
          
          // 延迟重置进度
          setTimeout(() => {
            setAnalysisProgress(0);
            setAnalysisMessage('');
          }, 2000);
        } else if (response.status === 'failure') {
          clearInterval(pollInterval);
          setAnalyzing(false);
          setTaskId(null);
          setAnalysisProgress(0);
          setAnalysisMessage('');
          
          // 清除localStorage中的任务信息
          localStorage.removeItem(`analysis_task_${id}`);
          localStorage.removeItem(`analysis_progress_${id}`);
          
          message.error(response.message || '分析失败');
        }
      } catch (error) {
        console.error('获取任务状态失败', error);
        // 如果出错，继续轮询（不断点续传需要）
      }
    }, 3000); // 每3秒轮询一次（同时会触发依赖图刷新）

    return () => clearInterval(pollInterval);
  }, [taskId, id]);

  // 页面加载时检查是否有未完成的分析任务（恢复断点续传）
  useEffect(() => {
    const savedTaskId = localStorage.getItem(`analysis_task_${id}`);
    const savedProgress = localStorage.getItem(`analysis_progress_${id}`);
    
    if (savedTaskId && !taskId) {
      // 恢复任务ID和进度
      setTaskId(savedTaskId);
      if (savedProgress) {
        try {
          const progress = JSON.parse(savedProgress);
          setAnalysisProgress(progress.progress || 0);
          setAnalysisMessage(progress.message || '正在后台分析...');
          setAnalyzing(true);
          message.info('检测到未完成的分析任务，正在后台继续分析...');
        } catch (e) {
          console.error('解析保存的进度失败', e);
        }
      }
    }
  }, [id]); // 只在项目ID变化时执行

  // 全局分析所有接口的依赖关系
  const handleAnalyzeAll = async () => {
    setAnalyzing(true);
    setAnalysisProgress(0);
    setAnalysisMessage('正在启动分析任务...');
    try {
      message.info('开始全局分析所有接口的依赖关系，请稍候...');
      const response = await client.post(`/api/relations/analyze-all/${id}`, {});
      
      if (response.task_id) {
        setTaskId(response.task_id);
        setAnalysisMessage('任务已启动，正在后台处理...');
      } else {
        // 如果没有task_id，说明是同步调用，直接显示结果
        message.success(response.message || '分析完成');
        setAnalyzing(false);
        await fetchDependencyGraph();
        
        // 通知场景用例集页面刷新数据
        localStorage.setItem(`scenario_suites_refresh_${id}`, Date.now().toString());
        window.dispatchEvent(new Event('storage'));
      }
    } catch (error) {
      console.error('全局分析失败', error);
      const errorMessage = error.response?.data?.detail || error.message || '分析失败';
      message.error(`全局分析失败: ${errorMessage}`);
      setAnalyzing(false);
      setTaskId(null);
      setAnalysisProgress(0);
      setAnalysisMessage('');
    }
  };

  // 删除当前项目的接口依赖分析数据
  const handleDeleteAnalysis = async () => {
    try {
      const response = await client.delete(`/api/relations/dependency-analysis/${id}`);
      message.success(response.message || '依赖分析数据已删除');
      // 刷新依赖关系图（应该显示为空）
      await fetchDependencyGraph();
      // 清除分析进度
      setAnalysisProgress(0);
      setAnalysisMessage('');
      setTaskId(null);
      // 清除localStorage中的任务信息
      localStorage.removeItem(`analysis_task_${id}`);
      localStorage.removeItem(`analysis_progress_${id}`);
    } catch (error) {
      console.error('删除依赖分析失败', error);
      const errorMessage = error.response?.data?.detail || error.message || '删除失败';
      message.error(`删除依赖分析失败: ${errorMessage}`);
    }
  };

  // 删除所有项目的接口依赖分析数据
  const handleDeleteAllAnalysis = async () => {
    try {
      const response = await client.delete(`/api/relations/dependency-analysis/all`);
      message.success(response.message || '所有项目的依赖分析数据已删除');
      // 刷新当前项目的依赖关系图（应该显示为空）
      await fetchDependencyGraph();
      // 清除分析进度
      setAnalysisProgress(0);
      setAnalysisMessage('');
      setTaskId(null);
      // 清除localStorage中的所有任务信息（使用通配符方式清除所有相关key）
      const keys = Object.keys(localStorage);
      keys.forEach(key => {
        if (key.startsWith('analysis_task_') || key.startsWith('analysis_progress_')) {
          localStorage.removeItem(key);
        }
      });
    } catch (error) {
      console.error('删除所有依赖分析失败', error);
      let errorMessage = '删除失败';
      if (error.response?.data) {
        if (typeof error.response.data === 'string') {
          errorMessage = error.response.data;
        } else if (error.response.data.detail) {
          errorMessage = error.response.data.detail;
        } else if (error.response.data.message) {
          errorMessage = error.response.data.message;
        } else {
          errorMessage = JSON.stringify(error.response.data);
        }
      } else if (error.message) {
        errorMessage = error.message;
      }
      message.error(`删除所有依赖分析失败: ${errorMessage}`);
    }
  };

  const getGraphOption = () => {
    if (!dependencyGraph || !dependencyGraph.nodes) {
      return {
        title: {
          text: '接口依赖关系图',
          left: 'center'
        },
        graphic: {
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '暂无依赖关系数据',
            fontSize: 16,
            fill: '#999'
          }
        }
      };
    }

    // 创建节点ID映射，确保所有节点都有有效的id，并去重
    const nodeIdMap = new Map();
    const seenIds = new Set();
    const nodes = (dependencyGraph.nodes || [])
      .filter(node => {
        // 严格过滤：确保节点有有效的id和基本属性
        if (!node || node === null || node === undefined) return false;
        const nodeId = node.id;
        if (nodeId === null || nodeId === undefined || nodeId === '') return false;
        const idStr = String(nodeId);
        // 去重：如果ID已存在，跳过
        if (seenIds.has(idStr)) {
          console.warn(`Duplicate node ID found: ${idStr}, skipping`);
          return false;
        }
        seenIds.add(idStr);
        return true;
      })
      .map((node, index) => {
        const nodeId = String(node.id);  // 确保ID是字符串
        
        // 确保所有必需字段都有值
        const nodeName = String(node.name || node.path || node.url || `接口_${index}`);
        const nodeMethod = String(node.method || 'GET');
        
        const nodeData = {
          id: nodeId,
          name: nodeName,
          label: nodeName,
          method: nodeMethod,
          url: String(node.url || node.path || ''),
          category: nodeMethod,  // 使用method作为category
          symbolSize: 50,
          itemStyle: {
            color: getMethodColor(nodeMethod)
          },
          value: nodeName
        };
        nodeIdMap.set(nodeId, nodeData);
        return nodeData;
      });

    // 过滤边，确保source和target都存在于nodes中，并且格式正确
    const edges = (dependencyGraph.edges || [])
      .filter(edge => {
        // 严格验证边的格式
        if (!edge || typeof edge !== 'object') return false;
        if (edge.source === null || edge.source === undefined || 
            edge.target === null || edge.target === undefined) return false;
        
        const sourceId = String(edge.source);
        const targetId = String(edge.target);
        
        // 确保source和target都存在，并且不是同一个节点
        if (sourceId === targetId) return false;
        if (!nodeIdMap.has(sourceId) || !nodeIdMap.has(targetId)) return false;
        
        return true;
      })
      .map((edge, index) => {
        const edgeConfig = getEdgeConfig(edge.type, edge.dependency_type);
        const edgeType = edge.type || edge.dependency_type || '依赖';
        
        // 获取source和target在nodes中的索引
        const sourceId = String(edge.source);
        const targetId = String(edge.target);
        const sourceNode = nodeIdMap.get(sourceId);
        const targetNode = nodeIdMap.get(targetId);
        
        if (!sourceNode || !targetNode) {
          // 如果节点不存在，返回null（会被过滤掉）
          return null;
        }
        
        // 构建符合ECharts要求的边对象（不使用dataIndex，ECharts会自动处理）
        const edgeData = {
          source: sourceId,  // 确保是字符串
          target: targetId,   // 确保是字符串
          value: Number(edge.value) || 1,  // 边的权重，确保是数字
          label: {
            show: true,
            formatter: String(edgeType)
          },
          lineStyle: {
            color: edgeConfig.color,
            width: edgeConfig.width || 2,
            type: edgeConfig.type || 'solid'
          }
        };
        
        // 添加额外的属性（如果需要）
        if (edge.description) {
          edgeData.description = String(edge.description);
        }
        if (edge.confidence !== undefined) {
          edgeData.confidence = Number(edge.confidence);
        }
        
        return edgeData;
      })
      .filter(edge => edge !== null);  // 过滤掉null值

    // 如果没有节点，返回空配置避免报错（但允许有节点但无边的情况）
    if (nodes.length === 0) {
      return {
        title: {
          text: '接口依赖关系图',
          left: 'center'
        },
        graphic: {
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '暂无节点数据，分析正在进行中...',
            fontSize: 16,
            fill: '#999'
          }
        }
      };
    }
    
    // 如果有节点但没有边，仍然显示节点（可能是分析刚开始）
    if (edges.length === 0 && nodes.length > 0) {
      console.log(`有 ${nodes.length} 个节点但还没有依赖关系，显示节点图`);
    }
    
    // 最终验证：确保所有节点和边都是有效的
    const validNodes = nodes.filter(node => node && node.id);
    const validEdges = edges.filter(edge => {
      if (!edge || !edge.source || !edge.target) return false;
      const sourceExists = validNodes.some(n => String(n.id) === String(edge.source));
      const targetExists = validNodes.some(n => String(n.id) === String(edge.target));
      return sourceExists && targetExists;
    });
    
    // 即使没有边，只要有节点就显示（允许分析过程中的部分显示）
    if (validNodes.length === 0) {
      return {
        title: {
          text: '接口依赖关系图',
          left: 'center'
        },
        graphic: {
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '暂无有效节点数据',
            fontSize: 16,
            fill: '#999'
          }
        }
      };
    }

    const graphOption = {
      title: {
        text: '接口依赖关系图',
        left: 'center'
      },
      tooltip: {
        trigger: 'item',
        formatter: (params) => {
          if (!params || !params.data) return '';
          
          if (params.dataType === 'node') {
            const nodeData = params.data;
            const node = dependencyGraph.nodes.find(n => String(n.id) === String(nodeData.id));
            const nodeName = nodeData.name || node?.name || node?.path || node?.url || '未知接口';
            const nodeUrl = nodeData.url || node?.url || node?.path || '';
            return `
              <div>
                <b>${nodeName}</b><br/>
                方法: ${nodeData.method || node?.method || 'GET'}<br/>
                ${nodeUrl ? `URL: ${nodeUrl}` : ''}
              </div>
            `;
          } else if (params.dataType === 'edge') {
            const edgeData = params.data;
            const edge = edgeData.properties || edgeData;
            return `
              <div>
                <b>依赖类型: ${edge.type || edge.dependency_type || '依赖'}</b><br/>
                描述: ${edge.description || ''}<br/>
                ${edge.dependency_path ? `依赖路径: ${edge.dependency_path}` : ''}
                ${edge.confidence ? `<br/>置信度: ${(edge.confidence * 100).toFixed(0)}%` : ''}
              </div>
            `;
          }
          return '';
        }
      },
      legend: {
        data: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
        top: 30
      },
      animationDurationUpdate: 1500,
      animationEasingUpdate: 'quinticInOut',
      series: [
        {
          name: '接口依赖关系',
          type: 'graph',
          layout: 'force',
          data: validNodes.map((node, idx) => {
            // 确保节点有label字段（兼容旧数据）
            let label = node.label;
            if (!label) {
              const nodeName = node.name || '未知接口';
              const nodeUrl = node.url || '';
              label = nodeUrl ? `${nodeName}\n${nodeUrl}` : nodeName;
            }
            return {
              ...node,
              label: label,  // 确保label字段存在
              // 确保每个节点都有完整的属性
              x: null,
              y: null,
              fixed: false
            };
          }),
          links: validEdges.length > 0 ? validEdges.map((edge, idx) => ({
            ...edge,
            // 确保边的格式正确
            id: `edge_${idx}`
          })) : [],  // 即使没有边，也允许显示节点（分析过程中）
          categories: [
            { name: 'GET' },
            { name: 'POST' },
            { name: 'PUT' },
            { name: 'DELETE' },
            { name: 'PATCH' }
          ],
          roam: true,
          label: {
            show: true,
            position: 'right',
            fontSize: 12,
            formatter: (params) => {
              // 显示接口名称和URL
              const node = params.data;
              if (node.label) {
                return node.label;  // 使用后端返回的label
              }
              const name = node.name || '未知接口';
              const url = node.url || '';
              if (url) {
                return `${name}\n${url}`;
              }
              return name;
            }
          },
          lineStyle: {
            color: 'source',
            curveness: 0.3
          },
          emphasis: {
            focus: 'adjacency',
            lineStyle: {
              width: 4
            }
          },
          force: {
            repulsion: 1000,
            gravity: 0.1,
            edgeLength: 200,
            layoutAnimation: true
          },
          // 确保数据格式正确
          symbolSize: 50,
          // 防止ECharts错误
          silent: false,
          animation: true,
          // 确保每个节点都有唯一标识
          draggable: true
        }
      ]
    };
    
    return graphOption;
  };

  const getMethodColor = (method) => {
    const colorMap = {
      'GET': '#5470c6',
      'POST': '#91cc75',
      'PUT': '#fac858',
      'DELETE': '#ee6666',
      'PATCH': '#73c0de'
    };
    return colorMap[method] || '#999';
  };

  const getEdgeConfig = (type, dependencyType) => {
    // 参数依赖：实线，蓝色
    if (type === 'parameter' || dependencyType === 'parameter') {
      return { color: '#5470c6', width: 2, type: 'solid' };
    }
    // 状态依赖：虚线，绿色
    if (type === 'state' || dependencyType === 'state') {
      return { color: '#91cc75', width: 2, type: 'dashed' };
    }
    // 认证依赖：点线，橙色
    if (type === 'authentication' || dependencyType === 'authentication') {
      return { color: '#fa8c16', width: 2, type: 'dotted' };
    }
    // 数据流依赖：实线，蓝色
    if (type === 'data_flow' || dependencyType === 'data_flow') {
      return { color: '#5470c6', width: 2, type: 'solid' };
    }
    // 业务逻辑依赖：虚线，绿色
    if (type === 'business_logic' || dependencyType === 'business_logic') {
      return { color: '#91cc75', width: 2, type: 'dashed' };
    }
    return { color: '#999', width: 1, type: 'solid' };
  };

  const fetchApiDetail = async (apiId) => {
    try {
      const data = await client.get(`/api/relations/api/${apiId}/dependencies?project_id=${id}`);
      setSelectedApi(data);
    } catch (error) {
      console.error('获取接口详情失败', error);
      message.error('获取接口详情失败');
    }
  };


  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2>
          <LinkOutlined /> 接口依赖分析
        </h2>
      </div>

      <Card title="依赖关系图" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size="small" style={{ width: '100%', marginBottom: 16 }}>
          <Space>
            <Button 
              type="primary" 
              onClick={handleAnalyzeAll} 
              loading={analyzing}
            >
              全局分析所有接口
            </Button>
            <Button onClick={fetchDependencyGraph} loading={loading}>刷新</Button>
            <Popconfirm
              title="确定要删除当前项目的接口依赖分析数据吗？"
              description="删除后将清除Redis、ChromaDB、Neo4j中当前项目的依赖分析数据，此操作不可撤销。删除后需要重新分析才能查看依赖关系。"
              onConfirm={handleDeleteAnalysis}
              okText="确定"
              cancelText="取消"
            >
              <Button 
                danger 
                icon={<DeleteOutlined />}
                disabled={analyzing}
              >
                删除当前项目
              </Button>
            </Popconfirm>
            <Popconfirm
              title="⚠️ 确定要删除所有项目的接口依赖分析数据吗？"
              description="删除后将清除Redis、ChromaDB、Neo4j中所有项目的依赖分析数据，此操作不可撤销且影响所有项目。删除后所有项目都需要重新分析才能查看依赖关系。"
              onConfirm={handleDeleteAllAnalysis}
              okText="确定删除所有"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button 
                danger 
                icon={<DeleteOutlined />}
                disabled={analyzing}
              >
                删除所有项目
              </Button>
            </Popconfirm>
            {documents && documents.length > 0 && (
              <span style={{ color: '#666', fontSize: '12px' }}>
                已上传 {documents.length} 个文档
              </span>
            )}
          </Space>
          {analyzing && (
            <div style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: '12px', color: '#666' }}>
                  {analysisMessage || '正在分析...'}
                  {dependencyGraph && dependencyGraph.nodes && dependencyGraph.nodes.length > 0 && (
                    <span style={{ marginLeft: '10px', color: '#52c41a' }}>
                      （已显示 {dependencyGraph.nodes.length} 个节点）
                    </span>
                  )}
                </span>
                <span style={{ fontSize: '12px', color: '#666' }}>{analysisProgress}%</span>
              </div>
              <div style={{ 
                width: '100%', 
                height: 8, 
                backgroundColor: '#f0f0f0', 
                borderRadius: 4,
                overflow: 'hidden'
              }}>
                <div style={{
                  width: `${analysisProgress}%`,
                  height: '100%',
                  backgroundColor: '#1890ff',
                  transition: 'width 0.3s ease'
                }} />
              </div>
            </div>
          )}
        </Space>
        {authInterface && (
          <div style={{ marginBottom: 16, padding: 12, background: '#f0f9ff', borderRadius: 4 }}>
            <strong>登录接口: </strong>
            <Tag color="green">{authInterface.name}</Tag>
            <Tag>{authInterface.method}</Tag>
            <span style={{ marginLeft: 8 }}>{authInterface.path}</span>
            {tokenInfo && tokenInfo.path && (
              <span style={{ marginLeft: 16, color: '#666' }}>
                Token路径: <code>{tokenInfo.path}</code>
              </span>
            )}
          </div>
        )}
        {!dependencyGraph || !dependencyGraph.nodes || dependencyGraph.nodes.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
            {loading ? (
              <p>加载中...</p>
            ) : (
              <div>
                <p>暂无依赖关系数据</p>
                <p style={{ fontSize: '12px', marginTop: '8px' }}>
                  点击"全局分析所有接口"按钮开始分析
                </p>
              </div>
            )}
          </div>
        ) : (
          <ReactECharts
            option={getGraphOption()}
            style={{ height: '600px', width: '100%' }}
            opts={{ renderer: 'canvas' }}
          />
        )}
      </Card>

      <Drawer
        title="接口依赖详情"
        placement="right"
        width={600}
        onClose={() => setApiDetailDrawerVisible(false)}
        open={apiDetailDrawerVisible}
      >
        {selectedApi && (
          <div>
            <Descriptions title={selectedApi.api_name} bordered column={1}>
              <Descriptions.Item label="URL">{selectedApi.url}</Descriptions.Item>
              <Descriptions.Item label="方法">{selectedApi.method}</Descriptions.Item>
            </Descriptions>
            
            <div style={{ marginTop: 16 }}>
              <h3>数据流依赖</h3>
              {selectedApi.dependencies?.data_flow?.length > 0 ? (
                <Table
                  columns={[
                    { title: '依赖接口', dataIndex: 'api_name', key: 'api_name' },
                    { title: '依赖类型', dataIndex: 'dependency_type', key: 'dependency_type' },
                    { title: '描述', dataIndex: 'description', key: 'description' },
                    { 
                      title: '提取字段', 
                      dataIndex: 'extract_fields', 
                      key: 'extract_fields',
                      render: (fields) => fields?.join(', ') || '-'
                    }
                  ]}
                  dataSource={selectedApi.dependencies.data_flow}
                  pagination={false}
                  size="small"
                />
              ) : (
                <p>无数据流依赖</p>
              )}
            </div>

            <div style={{ marginTop: 16 }}>
              <h3>业务逻辑依赖</h3>
              {selectedApi.dependencies?.business_logic?.length > 0 ? (
                <Table
                  columns={[
                    { title: '依赖接口', dataIndex: 'api_name', key: 'api_name' },
                    { title: '依赖类型', dataIndex: 'dependency_type', key: 'dependency_type' },
                    { title: '描述', dataIndex: 'description', key: 'description' }
                  ]}
                  dataSource={selectedApi.dependencies.business_logic}
                  pagination={false}
                  size="small"
                />
              ) : (
                <p>无业务逻辑依赖</p>
              )}
            </div>

            <div style={{ marginTop: 16 }}>
              <h3>被依赖接口（反向依赖）</h3>
              {selectedApi.dependents?.length > 0 ? (
                <Table
                  columns={[
                    { title: '接口名称', dataIndex: 'api_name', key: 'api_name' },
                    { title: '方法', dataIndex: 'method', key: 'method' },
                    { title: '依赖类型', dataIndex: ['dependency', 'dependency_type'], key: 'dependency_type' }
                  ]}
                  dataSource={selectedApi.dependents}
                  pagination={false}
                  size="small"
                />
              ) : (
                <p>无接口依赖此接口</p>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default ApiDependencies;

