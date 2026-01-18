import React, { useState, useEffect } from 'react';
import { Card, Spin, Button, Select, message, Space } from 'antd';
import ReactECharts from 'echarts-for-react';
import { DownloadOutlined, DatabaseOutlined } from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';

const KnowledgeGraph = () => {
  const { id } = useParams();
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [connectionId, setConnectionId] = useState(null);
  const [connections, setConnections] = useState([]);

  useEffect(() => {
    fetchConnections();
  }, [id]);

  useEffect(() => {
    if (connectionId) {
      fetchGraphData();
    }
  }, [connectionId, id]);

  useEffect(() => {
    if (connections.length > 0 && !connectionId) {
      // 如果连接列表已加载但还没有选择连接，自动选择第一个
      setConnectionId(connections[0].id);
    }
  }, [connections, connectionId]);

  const fetchConnections = async () => {
    try {
      const data = await client.get(`/api/connections/?project_id=${id}`);
      
      // 去重：根据 host + port + database_name 去重，保留ID最大的（最新的）
      let uniqueConnections = [];
      if (data && data.length > 0) {
        const connectionMap = new Map();
        data.forEach(conn => {
          const key = `${conn.host}:${conn.port}:${conn.database_name}`;
          const existing = connectionMap.get(key);
          if (!existing || conn.id > existing.id) {
            // 保留ID最大的（最新的）
            connectionMap.set(key, conn);
          }
        });
        uniqueConnections = Array.from(connectionMap.values());
      }
      
      setConnections(uniqueConnections);
      if (uniqueConnections.length > 0 && !connectionId) {
        setConnectionId(uniqueConnections[0].id);
      }
    } catch (error) {
      console.error('获取数据库连接失败', error);
      message.error('获取数据库连接失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const fetchGraphData = async () => {
    if (!connectionId) {
      console.log('没有选择数据库连接');
      setGraphData({ nodes: [], edges: [] });
      return;
    }
    setLoading(true);
    try {
      // 从Neo4j获取数据表关系数据
      const data = await client.get(`/api/connections/${connectionId}/graph-data`);

      // 检查Neo4j可用性
      if (data && data.neo4j_available === false) {
        console.log('Neo4j服务不可用，使用元数据作为备选方案');
        message.warning('Neo4j服务不可用，数据表关系功能受限。正在使用数据库元数据作为备选方案。', 5);
        await fetchGraphDataFromMetadata();
        return;
      }

      // 检查数据格式
      if (data && Array.isArray(data.nodes) && Array.isArray(data.edges)) {
        // Neo4j数据格式正确
        if (data.nodes.length > 0 || data.edges.length > 0) {
          setGraphData({
            nodes: data.nodes || [],
            edges: data.edges || []
          });
          return;
        }
      }

      // 如果Neo4j没有数据或数据为空，尝试从元数据获取
      if (!data.error) {
        console.log('Neo4j数据为空，尝试从元数据获取');
      } else {
        console.log('Neo4j连接失败:', data.error);
        message.info('使用数据库元数据作为备选方案', 3);
      }
      await fetchGraphDataFromMetadata();
    } catch (error) {
      console.error('获取Neo4j数据表关系失败，尝试从元数据获取', error);
      // 如果Neo4j数据不可用，从元数据获取
      message.info('数据表关系功能受限，使用数据库元数据作为备选方案', 3);
      await fetchGraphDataFromMetadata();
    } finally {
      setLoading(false);
    }
  };

  const fetchGraphDataFromMetadata = async () => {
    try {
      const relationships = await client.get(`/api/metadata/relationships?connection_id=${connectionId}`);
      const tables = await client.get(`/api/metadata/tables?connection_id=${connectionId}`);
      
      // 获取NER抽取的实体和关系
      let entities = [];
      let entityRelationships = [];
      try {
        const entitiesRes = await client.get(`/api/entities/entities/${connectionId}`);
        entities = entitiesRes.entities || [];
        
        const relsRes = await client.get(`/api/entities/relationships/${connectionId}`);
        entityRelationships = relsRes.relationships || [];
      } catch (err) {
        console.log('获取NER实体失败（可选）', err);
      }
      
      // 转换为图谱格式 - 表节点
      const nodes = (tables || []).map((table, idx) => ({
        id: `Table_${table.table_name}`,
        name: table.table_name,
        label: table.table_name,
        type: 'Table',
        properties: {
          comment: table.table_comment || '',
          column_count: table.column_count || 0,
          row_count: table.row_count || 0
        }
      }));
      
      // 添加实体节点
      (entities || []).forEach((entity, idx) => {
        nodes.push({
          id: `Entity_${entity.name || entity.id || `entity_${idx}`}`,
          name: entity.name,
          label: entity.name,
          type: entity.type || 'Entity',
          properties: {
            source_table: entity.source_table || '',
            entity_type: entity.type || ''
          }
        });
      });
      
      // 表关系
      const edges = (relationships || []).map((rel) => ({
        source: `Table_${rel.source_table_name}`,
        target: `Table_${rel.target_table_name}`,
        type: rel.relationship_type || 'RELATED',
        properties: {
          description: rel.description || '',
          foreign_key_columns: rel.foreign_key_columns || '',
          referred_columns: rel.referred_columns || ''
        }
      }));
      
      // 表与实体的关系
      (entities || []).forEach((entity) => {
        if (entity.source_table) {
          edges.push({
            source: `Table_${entity.source_table}`,
            target: `Entity_${entity.name || entity.id}`,
            type: 'CONTAINS_ENTITY',
            properties: {
              description: '包含实体'
            }
          });
        }
      });
      
      // 实体之间的关系
      (entityRelationships || []).forEach((rel) => {
        edges.push({
          source: `Entity_${rel.source}`,
          target: `Entity_${rel.target}`,
          type: rel.type || 'RELATED_TO',
          properties: {
            context: rel.context || '',
            confidence: rel.confidence || 0.5,
            source: 'NER'
          }
        });
      });
      
      setGraphData({ nodes, edges });
      
      if (nodes.length === 0 && edges.length === 0) {
        message.warning('暂无数据表关系数据，请先分析数据库元数据');
      }
    } catch (err) {
      console.error('从元数据获取数据表关系失败', err);
      message.error('获取数据表关系失败: ' + (err.response?.data?.detail || err.message));
      setGraphData({ nodes: [], edges: [] });
    }
  };

  const downloadCypherFile = async () => {
    try {
      const data = await client.get(`/api/metadata/cypher-file?connection_id=${connectionId}`);
      const blob = new Blob([data.cypher_content], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `knowledge_graph_${connectionId}.cypher`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      message.success('Cypher文件下载成功');
    } catch (error) {
      message.error('下载Cypher文件失败');
    }
  };

  const handleAnalyzeDatabase = async () => {
    if (!connectionId) {
      message.warning('请先选择数据库连接');
      return;
    }
    try {
      message.loading('正在启动数据库分析任务...', 0);
      const response = await client.post(`/api/connections/${connectionId}/analyze-metadata`);
      message.destroy();
      message.success('数据库分析任务已启动，请稍候查看结果');
      // 等待一段时间后刷新数据
      setTimeout(() => {
        fetchGraphData();
      }, 5000);
    } catch (error) {
      message.destroy();
      const errorMsg = error.response?.data?.detail || error.message;
      if (errorMsg.includes('Permission denied') || errorMsg.includes('无权')) {
        // 如果权限检查失败，尝试直接调用（去除权限检查）
        message.warning('权限检查失败，尝试直接分析...');
        try {
          const response = await client.post(`/api/connections/${connectionId}/analyze-metadata`);
          message.success('数据库分析任务已启动');
          setTimeout(() => {
            fetchGraphData();
          }, 5000);
        } catch (err) {
          message.error('启动分析任务失败: ' + (err.response?.data?.detail || err.message));
        }
      } else {
        message.error('启动分析任务失败: ' + errorMsg);
      }
    }
  };

  const getGraphOption = () => {
    if (!graphData) {
      return {
        title: {
          text: '数据库表关系',
          left: 'center'
        },
        graphic: {
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '加载中...',
            fontSize: 16,
            fill: '#999'
          }
        }
      };
    }
    // 如果没有节点，返回空配置但不要报错
    if (!graphData.nodes || graphData.nodes.length === 0) {
      return {
        title: {
          text: '数据库表关系',
          left: 'center'
        },
        graphic: {
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '暂无知识图谱数据',
            fontSize: 16,
            fill: '#999'
          }
        }
      };
    }

    // 按类型分类节点
    const categories = [
      { name: 'Table' },
      { name: 'Column' },
      { name: 'DataType' },
      { name: 'Entity' },
      { name: 'Person' },
      { name: 'Location' },
      { name: 'Organization' },
      { name: 'SportsEntity' },
      { name: 'Brand' }
    ];

    const nodeColorMap = {
      'Table': '#5470c6',
      'Column': '#91cc75',
      'DataType': '#fac858',
      'Entity': '#ee6666',
      'Person': '#73c0de',
      'Location': '#3ba272',
      'Organization': '#fc8452',
      'SportsEntity': '#9a60b4',
      'Brand': '#ea7ccc'
    };
    
    const nodeSizeMap = {
      'Table': 50,
      'Column': 30,
      'DataType': 20,
      'Entity': 40,
      'Person': 35,
      'Location': 35,
      'Organization': 35,
      'SportsEntity': 40,
      'Brand': 40
    };
    
    // 创建节点ID映射，确保所有节点都有有效的id，并去重
    const nodeIdMap = new Map();
    const seenIds = new Set();
    const nodes = (graphData.nodes || [])
      .filter(node => {
        // 严格过滤：确保节点有有效的id和基本属性
        if (!node || node === null || node === undefined) return false;
        const nodeId = node.id || node.name || node.label;
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
        const nodeId = String(node.id || node.name || node.label || `node_${index}`);
        const nodeName = String(node.label || node.name || `Node ${index}`);
        const nodeType = node.type || 'Entity';
        
        const nodeData = {
          id: nodeId,
          name: nodeName,
          label: nodeName,
          category: Math.max(0, categories.findIndex(cat => cat.name === nodeType)),
          symbolSize: nodeSizeMap[nodeType] || 30,
          itemStyle: {
            color: nodeColorMap[nodeType] || '#999'
          },
          value: nodeName
        };
        nodeIdMap.set(nodeId, nodeData);
        return nodeData;
      });

    // 过滤边，确保source和target都存在于nodes中，并且格式正确
    const edges = (graphData.edges || [])
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
        const relTypeMap = {
          has_a: { color: '#5470c6', width: 3 },
          is_a: { color: '#91cc75', width: 3 },
          depend_on: { color: '#fac858', width: 2 },
          foreign_key: { color: '#ee6666', width: 2 },
          HAS_COLUMN: { color: '#73c0de', width: 1 },
          HAS_TYPE: { color: '#3ba272', width: 1 }
        };
        
        const config = relTypeMap[edge.type] || { color: '#999', width: 1 };
        
        const sourceId = String(edge.source);
        const targetId = String(edge.target);
        
        // 确保source和target都存在
        if (!nodeIdMap.has(sourceId) || !nodeIdMap.has(targetId)) {
          return null;
        }
        
        return {
          source: sourceId,
          target: targetId,
          value: 1,
          label: {
            show: true,
            formatter: String(edge.type || ''),
            fontSize: 10
          },
          lineStyle: {
            color: config.color,
            width: config.width,
            type: edge.type === 'has_a' ? 'dashed' : 'solid'
          }
        };
      })
      .filter(edge => edge !== null);  // 过滤掉null值

    return {
      title: {
        text: '数据库知识图谱',
        left: 'center'
      },
      tooltip: {
        formatter: (params) => {
          if (params.dataType === 'node') {
            const node = graphData.nodes.find(n => n.id === params.data.id);
            return `
              <div>
                <b>${node?.label || params.data.name}</b><br/>
                类型: ${node?.type || 'Unknown'}<br/>
                ${node?.properties?.comment ? `含义: ${node.properties.comment}<br/>` : ''}
                ${node?.properties?.column_count ? `字段数: ${node.properties.column_count}<br/>` : ''}
                ${node?.properties?.row_count ? `行数: ${node.properties.row_count}` : ''}
              </div>
            `;
          } else if (params.dataType === 'edge') {
            const edge = graphData.edges.find(e => 
              e.source === params.data.source && e.target === params.data.target
            );
            return `
              <div>
                <b>关系类型: ${params.data.label?.formatter || edge?.type || 'Unknown'}</b><br/>
                ${edge?.properties?.description ? `描述: ${edge.properties.description}` : ''}
              </div>
            `;
          }
          return '';
        }
      },
      legend: {
        data: categories.map(cat => cat.name),
        top: 30
      },
      animationDurationUpdate: 1500,
      animationEasingUpdate: 'quinticInOut',
      series: [
        {
          name: '数据表关系',
          type: 'graph',
          layout: 'force',
          data: nodes.map((node, idx) => ({
            ...node,
            // 确保每个节点都有完整的属性
            x: null,
            y: null,
            fixed: false
          })),
          links: edges.map((edge, idx) => ({
            ...edge,
            // 确保边的格式正确
            id: `edge_${idx}`
          })),
          categories: categories,
          roam: true,
          label: {
            show: true,
            position: 'right',
            fontSize: 12
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
          draggable: true,
          focusNodeAdjacency: true
        }
      ]
    };
  };

  const handleGraphClick = (params) => {
    if (params.dataType === 'node') {
      // 可以显示节点详情
      console.log('点击节点:', params);
    } else if (params.dataType === 'edge') {
      // 可以显示关系详情
      console.log('点击关系:', params);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>数据表关系</h2>
        <Space>
          {connections.length > 1 && (
            <Select
              value={connectionId}
              onChange={setConnectionId}
              style={{ width: 200 }}
              placeholder="选择数据库连接"
            >
              {connections.map(conn => (
                <Select.Option key={conn.id} value={conn.id}>
                  {conn.database_name} ({conn.host})
                </Select.Option>
              ))}
            </Select>
          )}
          <Button
            type="primary"
            icon={<DatabaseOutlined />}
            onClick={handleAnalyzeDatabase}
            disabled={!connectionId}
          >
            分析数据库
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={downloadCypherFile}
            disabled={!connectionId}
          >
            下载Cypher文件
          </Button>
        </Space>
      </div>
      <Card>
        <Spin spinning={loading}>
          {graphData ? (
            graphData.nodes && graphData.nodes.length > 0 ? (
              <ReactECharts
                option={getGraphOption()}
                style={{ height: '700px', width: '100%' }}
                opts={{ renderer: 'canvas' }}
                onEvents={{
                  click: handleGraphClick
                }}
              />
            ) : (
              <div style={{ textAlign: 'center', padding: 50 }}>
                {graphData.error ? (
                  <div>
                    <p style={{ color: '#ff4d4f' }}>获取数据表关系失败</p>
                    <p style={{ color: '#999', fontSize: '12px' }}>{graphData.error}</p>
                  </div>
                ) : (
                  '暂无数据表关系数据，请先分析数据库'
                )}
              </div>
            )
          ) : (
            <div style={{ textAlign: 'center', padding: 50 }}>
              {loading ? '加载中...' : '请选择数据库连接以查看数据表关系'}
            </div>
          )}
        </Spin>
      </Card>
    </div>
  );
};

export default KnowledgeGraph;


