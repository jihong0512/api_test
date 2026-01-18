import React, { useState, useEffect } from 'react';
import { Table, Button, Upload, message, Space, Tag, Popconfirm, Modal, Input, Tabs, Spin } from 'antd';
import { UploadOutlined, DeleteOutlined, LinkOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import client from '../api/client';
import { getErrorMessage } from '../utils/errorHandler';
import '../styles/animations.css';

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
        `/api/files/upload?project_id=${id}&swagger_url=${encodeURIComponent(swaggerUrl)}`,
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

  const columns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
    },
    {
      title: '类型',
      dataIndex: 'file_type',
      key: 'file_type',
      render: (type) => <Tag>{type.toUpperCase()}</Tag>,
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      key: 'file_size',
      render: (size) => size ? `${(size / 1024).toFixed(2)} KB` : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const statusMap = {
          uploaded: { text: '已上传', color: 'blue' },
          parsing: { text: '解析中', color: 'processing' },
          parsed: { text: '已解析', color: 'green' },
          error: { text: '错误', color: 'red' },
        };
        const config = statusMap[status] || { text: status, color: 'default' };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => {
        const isDeleting = deletingDocuments.has(record.id);
        return (
          <Spin spinning={isDeleting} size="small">
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
              >
                {isDeleting ? '删除中...' : '删除'}
              </Button>
            </Popconfirm>
          </Spin>
        );
      },
    },
  ];

  const tabItems = [
    {
      key: 'normal',
      label: '普通文档',
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
          <Table
            columns={columns}
            dataSource={documents}
            loading={loading}
            rowKey="id"
            pagination={{
              current: pagination.page,
              pageSize: pagination.page_size,
              total: pagination.total,
              totalPages: pagination.total_pages,
              onChange: (page) => fetchDocuments(page, false),
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50'],
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条数据`
            }}
          />
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
          <Table
            columns={columns}
            dataSource={fewShotDocuments}
            loading={loading}
            rowKey="id"
            pagination={{
              current: fewShotPagination.page,
              pageSize: fewShotPagination.page_size,
              total: fewShotPagination.total,
              totalPages: fewShotPagination.total_pages,
              onChange: (page) => fetchDocuments(page, true),
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50'],
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条数据`
            }}
          />
        </div>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 'bold' }}>文档管理</h2>
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




