import { useState, useEffect, useCallback } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, Tag, Space, Popconfirm, message } from 'antd';
import { UserSwitchOutlined, PlusOutlined } from '@ant-design/icons';
import API, { getAuthUser } from '../api';

function roleTag(role) {
  if (role === 'admin') return <Tag color="geekblue">管理员</Tag>;
  if (role === 'leader') return <Tag color="purple">组长</Tag>;
  return <Tag>用户</Tag>;
}

export default function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editUsername, setEditUsername] = useState('');
  const [form] = Form.useForm();
  const currentUser = getAuthUser();
  const canAssignManagerRole = currentUser?.role === 'admin';

  const loadUsers = useCallback(async () => {
    setLoading(true);
    const data = await API.get('/api/auth/users');
    setLoading(false);
    if (data.success) setUsers(data.data);
  }, []);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  const openCreate = () => {
    setEditMode(false);
    setEditUsername('');
    form.resetFields();
    form.setFieldsValue({ role: 'user', status: 'active' });
    setModalOpen(true);
  };

  const openEdit = (user) => {
    setEditMode(true);
    setEditUsername(user.username);
    form.setFieldsValue({
      username: user.username,
      display_name: user.display_name || '',
      password: '',
      role: user.role || 'user',
      status: user.status || 'active',
    });
    setModalOpen(true);
  };

  const saveUser = async (values) => {
    const payload = { ...values };
    let result;
    if (editMode) {
      result = await API.put(`/api/auth/users/${encodeURIComponent(editUsername)}`, payload);
    } else {
      result = await API.post('/api/auth/users', payload);
    }
    if (result.success) {
      message.success('用户已保存');
      setModalOpen(false);
      loadUsers();
    } else {
      message.error(result.message || '保存失败');
    }
  };

  const removeUser = async (username) => {
    const result = await API.delete(`/api/auth/users/${encodeURIComponent(username)}`);
    if (result.success) {
      message.success('用户已删除');
      loadUsers();
    } else {
      message.error(result.message || '删除失败');
    }
  };

  const columns = [
    { title: '用户名', dataIndex: 'username', key: 'username', render: v => <code>{v}</code> },
    { title: '显示名', dataIndex: 'display_name', key: 'display_name' },
    {
      title: '角色', dataIndex: 'role', key: 'role',
      render: v => roleTag(v),
    },
    { title: '创建者', dataIndex: 'created_by', key: 'created_by', render: v => v ? <code>{v}</code> : '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: v => v === 'active' ? <Tag color="success">启用</Tag> : <Tag color="error">禁用</Tag>,
    },
    { title: '广告账户', key: 'ad', render: (_, r) => r.summary?.ad_accounts || 0 },
    { title: 'BM', key: 'bm', render: (_, r) => r.summary?.bm_count || 0 },
    { title: 'Pixel', key: 'pixel', render: (_, r) => r.summary?.pixel_count || 0 },
    { title: '素材', key: 'lib', render: (_, r) => r.summary?.ad_library_count || 0 },
    {
      title: '操作', key: 'action', width: 140,
      render: (_, r) => (
        <Space>
          <Button size="small" onClick={() => openEdit(r)}>编辑</Button>
          {r.username !== 'admin' && (
            <Popconfirm title={`确定删除用户 ${r.username} 吗？该用户数据也会被一并删除。`} onConfirm={() => removeUser(r.username)} okText="确定" cancelText="取消">
              <Button size="small" danger>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h4 style={{ margin: 0 }}><UserSwitchOutlined style={{ marginRight: 8 }} />{currentUser?.role === 'leader' ? '我的用户' : '用户管理'}</h4>
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={openCreate}>新增用户</Button>
      </div>

      <Card bodyStyle={{ padding: 0 }}>
        <Table columns={columns} dataSource={users} rowKey="username" loading={loading} size="small" pagination={false} />
      </Card>

      <Modal
        title={editMode ? `编辑用户: ${editUsername}` : '新增用户'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" onFinish={saveUser}>
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input disabled={editMode} />
          </Form.Item>
          <Form.Item label="显示名" name="display_name">
            <Input />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={editMode ? [] : [{ required: true, message: '请输入密码' }]}>
            <Input.Password placeholder={editMode ? '留空表示不修改' : ''} />
          </Form.Item>
          <Space style={{ width: '100%' }}>
            <Form.Item label="角色" name="role" style={{ width: 200 }}>
              <Select>
                <Select.Option value="user">普通用户</Select.Option>
                {canAssignManagerRole && <Select.Option value="leader">组长</Select.Option>}
                {canAssignManagerRole && <Select.Option value="admin">管理员</Select.Option>}
              </Select>
            </Form.Item>
            <Form.Item label="状态" name="status" style={{ width: 200 }}>
              <Select>
                <Select.Option value="active">启用</Select.Option>
                <Select.Option value="disabled">禁用</Select.Option>
              </Select>
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </>
  );
}
