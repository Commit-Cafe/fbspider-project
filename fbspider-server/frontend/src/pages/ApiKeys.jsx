import { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, InputNumber, Select,
  Tag, Space, Typography, message, Popconfirm, Tooltip, Alert,
} from 'antd';
import {
  PlusOutlined, CopyOutlined, DeleteOutlined, StopOutlined,
  KeyOutlined, ReloadOutlined,
} from '@ant-design/icons';
import API from '../api';

const { Text, Paragraph } = Typography;

const SCOPE_OPTIONS = [
  { label: '设备控制', value: 'device-control' },
];

const STATUS_MAP = {
  active: { color: 'green', text: '正常' },
  revoked: { color: 'red', text: '已撤销' },
};

export default function ApiKeys() {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newKey, setNewKey] = useState(null); // 刚创建的明文 key
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await API.get('/api/keys');
      if (res.success) setKeys(res.data);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      const res = await API.post('/api/keys', values);
      if (res.success) {
        setNewKey(res.data.key);
        message.success('API Key 创建成功');
        setCreateOpen(false);
        form.resetFields();
        load();
      } else {
        message.error(res.message || '创建失败');
      }
    } catch { /* validation */ }
  };

  const handleRevoke = async (id) => {
    const res = await API.post(`/api/keys/${id}/revoke`);
    if (res.success) {
      message.success('已撤销');
      load();
    } else {
      message.error(res.message || '撤销失败');
    }
  };

  const handleDelete = async (id) => {
    const res = await API.delete(`/api/keys/${id}`);
    if (res.success) {
      message.success('已删除');
      load();
    } else {
      message.error(res.message || '删除失败');
    }
  };

  const copyKey = (text) => {
    navigator.clipboard.writeText(text).then(() => message.success('已复制'));
  };

  const columns = [
    {
      title: '名称', dataIndex: 'name', width: 160,
    },
    {
      title: '用户', dataIndex: 'username', width: 120,
    },
    {
      title: 'Key 前缀', dataIndex: 'key_prefix', width: 140,
      render: (v) => <Text code>{v}...</Text>,
    },
    {
      title: 'Scopes', dataIndex: 'scopes', width: 160,
      render: (scopes) => scopes?.map(s => <Tag key={s}>{s}</Tag>),
    },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (s) => {
        const m = STATUS_MAP[s] || { color: 'default', text: s };
        return <Tag color={m.color}>{m.text}</Tag>;
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', width: 170,
      render: (v) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: '过期时间', dataIndex: 'expires_at', width: 170,
      render: (v) => v ? new Date(v).toLocaleString() : '永不过期',
    },
    {
      title: '最后使用', dataIndex: 'last_used_at', width: 170,
      render: (v) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: '操作', width: 140, fixed: 'right',
      render: (_, row) => (
        <Space size="small">
          {row.status === 'active' && (
            <Popconfirm title="确认撤销此 Key？" onConfirm={() => handleRevoke(row.id)}>
              <Tooltip title="撤销">
                <Button size="small" icon={<StopOutlined />} danger />
              </Tooltip>
            </Popconfirm>
          )}
          <Popconfirm title="确认永久删除？" onConfirm={() => handleDelete(row.id)}>
            <Tooltip title="删除">
              <Button size="small" icon={<DeleteOutlined />} danger type="text" />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={<><KeyOutlined /> API Key 管理</>}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              创建 API Key
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="API Key 用于外部系统通过 HTTP 接口控制设备"
          description={
            <div>
              <div>请求时添加 Header: <Text code>X-API-Key: your_key_here</Text></div>
              <div>接口前缀: <Text code>/api/open/</Text>（与管理面板的 <Text code>/api/device-control/</Text> 功能相同）</div>
              <div>可用端点: <Text code>GET /devices</Text>, <Text code>POST /send</Text>, <Text code>POST /navigate</Text>, <Text code>POST /toggle</Text>, <Text code>POST /budget</Text>, <Text code>POST /update-url</Text>, <Text code>GET /result/:task_id</Text></div>
            </div>
          }
        />
        <Table
          rowKey="id"
          columns={columns}
          dataSource={keys}
          loading={loading}
          pagination={false}
          scroll={{ x: 1300 }}
          size="small"
        />
      </Card>

      {/* 创建对话框 */}
      <Modal
        title="创建 API Key"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        okText="创建"
      >
        <Form form={form} layout="vertical" initialValues={{ scopes: ['device-control'] }}>
          <Form.Item name="username" label="绑定用户" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="此 Key 关联的用户名" />
          </Form.Item>
          <Form.Item name="name" label="Key 名称">
            <Input placeholder="便于识别的名称，如：外部系统A" />
          </Form.Item>
          <Form.Item name="scopes" label="权限范围">
            <Select mode="multiple" options={SCOPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="expires_days" label="有效天数（留空为永不过期）">
            <InputNumber min={1} max={3650} style={{ width: '100%' }} placeholder="如 90" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 显示新创建的 Key */}
      <Modal
        title="API Key 已创建"
        open={!!newKey}
        onOk={() => setNewKey(null)}
        onCancel={() => setNewKey(null)}
        cancelButtonProps={{ style: { display: 'none' } }}
        okText="我已保存"
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="请立即复制并保存此 Key，关闭后将无法再次查看完整 Key！"
        />
        <div style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Text code style={{ flex: 1, wordBreak: 'break-all', fontSize: 13 }}>{newKey}</Text>
          <Button icon={<CopyOutlined />} onClick={() => copyKey(newKey)} size="small">复制</Button>
        </div>
        <Paragraph type="secondary" style={{ marginTop: 12, fontSize: 12 }}>
          使用示例: <Text code>curl -H "X-API-Key: {newKey?.slice(0, 12)}..." http://server/api/open/devices</Text>
        </Paragraph>
      </Modal>
    </div>
  );
}
