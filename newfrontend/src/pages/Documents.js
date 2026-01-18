import React, { useState, useEffect } from 'react';
import { Button, Upload, message, Space, Tag, Popconfirm, Modal, Input, Tabs, Spin } from 'antd';
import { UploadOutlined, DeleteOutlined, LinkOutlined, ExperimentOutlined, FileTextOutlined } from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import { getErrorMessage } from '../utils/errorHandler';
import '../styles/animations.css';
import '../styles/minimal-card.css';

const Documents = () => {
  const { id } = useParams();
  const [documents, setDocuments] = useState([]);
  const [fewShotDocuments, setFewShotDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [swaggerModalVisible, setSwaggerModalVisible] = useState(false);
  const [swaggerUrl, setSwaggerUrl] = useState('');
  const [swaggerLoading, setSwaggerLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('normal');
  const [deletingDocuments, setDeletingDocuments] = useState(new Set()); // 追踪正在删除的文档
  const [pagination, setPagination] = useState({ page: 1, page_size: 20, total: 0, total_pages: 0 });
  const [fewShotPagination, setFewShotPagination] = useState({ page: 1, page_size: 20, total: 0, total_pages: 0 });

  useEffect(() => {
    fetchDocuments();
    // 轮询检查解析状态
    const interval = setInterval(() => {
      fetchDocuments();
    }, 5000); // 每5秒刷新一次
    
    return () => clearInterval(interval);
  }, [id]);

  // 监听文档解析完成事件（从其他页面触发）
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === `documents_refresh_${id}` || e.key?.startsWith('documents_refresh_')) {
        fetchDocuments();
      }
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [id]);

  const fetchDocuments = async (page = 1, isFewShot = null) => {
    setLoading(true);
    try {
      // 获取普通文档
      if (isFewShot === null || isFewShot === false) {
        const normalData = await client.get(`/api/files/?project_id=${id}&is_few_shot=false&page=${page}&page_size=20`);
        if (normalData.data) {
          setDocuments(normalData.data);
          setPagination(normalData.pagination || {});
        } else {
          setDocuments(normalData);
        }
      }
      
      // 获取few-shot文档
      if (isFewShot === null || isFewShot === true) {
        const fewShotData = await client.get(`/api/files/?project_id=${id}&is_few_shot=true&page=${page}&page_size=20`);
        if (fewShotData.data) {
          setFewShotDocuments(fewShotData.data);
          setFewShotPagination(fewShotData.pagination || {});
        } else {
          setFewShotDocuments(fewShotData);
        }
      }
    } catch (error) {
      message.error('获取文档列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (file, isFewShot = false) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await client.post(`/api/files/upload?project_id=${id}&is_few_shot=${isFewShot}`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      message.success(response.message || (isFewShot ? 'Few-shot文件上传成功，正在解析中' : '文档上传成功，正在解析中'));
      fetchDocuments();
    } catch (error) {
      message.error('文档上传失败: ' + getErrorMessage(error));
    }
    return false;
  };

  const handleSwaggerUrlSubmit = async () => {
    if (!swaggerUrl || !swaggerUrl.startsWith('http')) {
      message.error('请输入有效的Swagger URL');
      return;
    }

    setSwaggerLoading(true);
    try {
      const response = await client.post(
        `/api/files/upload?project_id=${id}&swagger_url=${encodeURIComponent(swaggerUrl)}&is_few_shot=false`,
        {},
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );
      message.success(response.message || 'Swagger URL添加成功，正在解析中');
      setSwaggerModalVisible(false);
      setSwaggerUrl('');
      fetchDocuments();
    } catch (error) {
      message.error('添加Swagger URL失败: ' + getErrorMessage(error));
    } finally {
      setSwaggerLoading(false);
    }
  };

  const handleDelete = async (documentId) => {
    try {
      // 标记为正在删除
      setDeletingDocuments(prev => new Set(prev).add(documentId));
      
      await client.delete(`/api/files/${documentId}`);
      message.success('文档删除中，请等待后台处理完成');
      
      // 刷新列表（删除会在后台异步进行）
      setTimeout(() => {
        fetchDocuments();
        // 2秒后清除删除状态标记
        setDeletingDocuments(prev => {
          const updated = new Set(prev);
          updated.delete(documentId);
          return updated;
        });
      }, 2000);
    } catch (error) {
      // 移除删除状态标记
      setDeletingDocuments(prev => {
        const updated = new Set(prev);
        updated.delete(documentId);
        return updated;
      });
      message.error('文档删除失败: ' + getErrorMessage(error));
    }
  };

  const getStatusConfig = (status) => {
    const statusMap = {
      uploaded: { text: '已上传', color: 'blue' },
      parsing: { text: '解析中', color: 'processing' },
      parsed: { text: '已解析', color: 'green' },
      error: { text: '错误', color: 'red' },
    };
    return statusMap[status] || { text: status, color: 'default' };
  };

  const renderDocumentList = (docList, isFewShot = false) => {
    if (docList.length === 0 && !loading) {
      return (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#999', background: '#fff', borderRadius: '6px' }}>
          <p style={{ fontSize: 16, marginBottom: 8 }}>暂无文档</p>
          <p style={{ fontSize: 14 }}>
            {isFewShot ? '请上传接口测试参考用例' : '请上传文档或添加Swagger URL'}
          </p>
        </div>
      );
    }

    return (
      <div>
        {docList.map((record) => {
          const isDeleting = deletingDocuments.has(record.id);
          const statusConfig = getStatusConfig(record.status);
          const fileSize = record.file_size ? `${(record.file_size / 1024).toFixed(2)} KB` : '-';
          const createTime = record.created_at ? new Date(record.created_at).toLocaleString() : '-';

          return (
            <div key={record.id} className="minimal-card">
              <div className="card-row">
                <FileTextOutlined style={{ fontSize: '20px', color: '#1890ff', flexShrink: 0 }} />
                <div className="card-content">
                  <div className="card-title">{record.filename || '未命名文档'}</div>
                  <div className="card-url" style={{ fontFamily: 'inherit' }}>
                    {fileSize} • {createTime}
                  </div>
                </div>
                <div className="card-meta">
                  <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
                  <Tag>{record.file_type?.toUpperCase() || 'UNKNOWN'}</Tag>
                </div>
                <span className="card-action" onClick={(e) => e.stopPropagation()}>
                  <Popconfirm
                    title="确定要删除这个文档吗？"
                    description="删除后将清理所有相关数据，此操作不可撤销"
                    onConfirm={() => handleDelete(record.id)}
                    okText="确定"
                    cancelText="取消"
                    disabled={isDeleting}
                  >
                    <Button
                      type="link"
                      danger
                      icon={<DeleteOutlined />}
                      size="small"
                      disabled={isDeleting}
                      loading={isDeleting}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {isDeleting ? '删除中...' : '删除'}
                    </Button>
                  </Popconfirm>
                </span>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // 支持的文件类型
  const supportedFormats = [
    { name: 'Swagger/OpenAPI', ext: 'json, yaml, yml', icon: '📋', color: '#1890ff', bgColor: '#e6f7ff' },
    { name: 'Postman', ext: 'json', icon: '📮', color: '#ff6b35', bgColor: '#fff7e6' },
    { name: 'Apifox', ext: 'json', icon: '🦊', color: '#52c41a', bgColor: '#f6ffed' },
    { name: 'PDF', ext: 'pdf', icon: '📄', color: '#ff4d4f', bgColor: '#fff2f0' },
    { name: 'Word', ext: 'docx, doc', icon: '📝', color: '#2b5797', bgColor: '#e6f4ff' },
    { name: 'Excel', ext: 'xlsx, xls, csv', icon: '📊', color: '#1d6f42', bgColor: '#f6ffed' },
    { name: 'Markdown', ext: 'md', icon: '📖', color: '#000000', bgColor: '#fafafa' },
    { name: 'Text', ext: 'txt', icon: '📃', color: '#8c8c8c', bgColor: '#fafafa' },
    { name: 'JMeter', ext: 'jmx', icon: '⚡', color: '#fa8c16', bgColor: '#fff7e6' },
  ];

  const tabItems = [
    {
      key: 'normal',
      label: '接口文档',
      children: (
        <div>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
            <Space>
              <Button 
                type="default" 
                icon={<LinkOutlined />}
                onClick={() => setSwaggerModalVisible(true)}
              >
                添加Swagger URL
              </Button>
              <Upload beforeUpload={(file) => handleUpload(file, false)} showUploadList={false}>
                <Button type="primary" icon={<UploadOutlined />}>
                  上传文档
                </Button>
              </Upload>
            </Space>
          </div>
          
          {/* 支持的文件类型说明 - 紧凑设计 */}
          <div style={{
            background: 'linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%)',
            padding: '12px 16px',
            borderRadius: '6px',
            marginBottom: '16px',
            border: '1px solid #e8e8e8',
            boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)'
          }}>
            <div style={{ 
              marginBottom: '10px', 
              fontSize: '13px', 
              fontWeight: 600, 
              color: '#262626',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}>
              <span style={{ fontSize: '14px' }}>📚</span>
              <span>支持的文件类型</span>
            </div>
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', 
              gap: '8px' 
            }}>
              {supportedFormats.map((format, index) => (
                <div
                  key={index}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 10px',
                    background: format.bgColor,
                    borderRadius: '4px',
                    border: `1px solid ${format.color}20`,
                    fontSize: '12px',
                    transition: 'all 0.2s',
                    cursor: 'default',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-1px)';
                    e.currentTarget.style.boxShadow = `0 2px 6px ${format.color}25`;
                    e.currentTarget.style.borderColor = format.color;
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.boxShadow = 'none';
                    e.currentTarget.style.borderColor = `${format.color}20`;
                  }}
                >
                  <span style={{ fontSize: '14px', lineHeight: 1 }}>{format.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, color: format.color, fontSize: '12px', lineHeight: 1.3 }}>
                      {format.name}
                    </div>
                    <div style={{ color: '#8c8c8c', fontSize: '10px', lineHeight: 1.2 }}>
                      {format.ext}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Spin spinning={loading}>
            {renderDocumentList(documents, false)}
          </Spin>
        </div>
      ),
    },
    {
      key: 'fewshot',
      label: '接口测试参考用例',
      children: (
        <div>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
            <Upload beforeUpload={(file) => handleUpload(file, true)} showUploadList={false}>
              <Button type="primary" icon={<ExperimentOutlined />}>
                上传测试参考用例
              </Button>
            </Upload>
          </div>
          
          {/* 经典接口测试示例 */}
          <div style={{
            background: 'linear-gradient(135deg, #f0f9ff 0%, #ffffff 100%)',
            padding: '16px',
            borderRadius: '6px',
            marginBottom: '16px',
            border: '1px solid #bfdbfe',
            boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)'
          }}>
            <div style={{ 
              marginBottom: '12px', 
              fontSize: '13px', 
              fontWeight: 600, 
              color: '#1e40af',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}>
              <span style={{ fontSize: '14px' }}>💡</span>
              <span>经典接口测试示例</span>
            </div>
            <div style={{
              background: '#ffffff',
              padding: '12px',
              borderRadius: '4px',
              border: '1px solid #e5e7eb',
              fontSize: '12px',
              fontFamily: 'Monaco, Menlo, "Courier New", monospace',
              lineHeight: '1.6',
              color: '#374151',
              overflowX: 'auto',
              maxHeight: '300px',
              overflowY: 'auto'
            }}>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
{`# 用户登录接口测试示例

## 接口信息
- 接口名称: 用户登录
- 请求方法: POST
- 请求路径: /api/v1/users/login
- 请求头: Content-Type: application/json

## 请求体示例
{
  "username": "testuser",
  "password": "password123"
}

## 预期响应
- 状态码: 200
- 响应体:
{
  "code": 0,
  "message": "登录成功",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user_id": 12345,
    "username": "testuser"
  }
}

## 测试断言
1. 响应状态码为 200
2. 响应体包含 token 字段
3. token 字段不为空
4. user_id 为整数类型
5. username 与请求参数一致

## 测试步骤
1. 发送 POST 请求到 /api/v1/users/login
2. 携带正确的用户名和密码
3. 验证响应状态码
4. 验证响应体结构
5. 提取 token 用于后续接口认证`}
              </pre>
            </div>
          </div>

          <Spin spinning={loading}>
            {renderDocumentList(fewShotDocuments, true)}
          </Spin>
        </div>
      ),
    },
  ];

  return (
    <div style={{ padding: '0' }}>
      {/* 统计信息栏 */}
      <div className="stats-bar">
        <div className="stat-item">
          <span className="stat-label">接口文档:</span>
          <span className="stat-value">{documents.length}</span>
          <span className="stat-label">个</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Few-shot:</span>
          <span className="stat-value">{fewShotDocuments.length}</span>
          <span className="stat-label">个</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">总计:</span>
          <span className="stat-value">{documents.length + fewShotDocuments.length}</span>
          <span className="stat-label">个文档</span>
        </div>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />

      <Modal
        title="添加在线Swagger文档"
        open={swaggerModalVisible}
        onOk={handleSwaggerUrlSubmit}
        onCancel={() => {
          setSwaggerModalVisible(false);
          setSwaggerUrl('');
        }}
        confirmLoading={swaggerLoading}
        okText="添加"
        cancelText="取消"
      >
        <div style={{ marginBottom: 16 }}>
          <p style={{ marginBottom: 8, color: '#8c8c8c' }}>
            请输入Swagger/OpenAPI文档的在线URL地址
          </p>
          <Input
            placeholder="例如: https://api.example.com/v3/api-docs"
            value={swaggerUrl}
            onChange={(e) => setSwaggerUrl(e.target.value)}
            onPressEnter={handleSwaggerUrlSubmit}
          />
        </div>
      </Modal>
    </div>
  );
};

export default Documents;




