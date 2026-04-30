import { useState } from 'react';
import { Card, Form, Input, Button, Alert, Typography } from 'antd';
import { useAuth } from '../auth';

export default function Login() {
  const { login } = useAuth();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onFinish = async ({ username, password }) => {
    setError('');
    setLoading(true);
    try {
      await login(username, password);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f5f6fa' }}>
      <Card style={{ width: 400, borderRadius: 12, boxShadow: '0 2px 12px rgba(0,0,0,.08)' }} bordered={false}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <img src="/fbhelper1.png" alt="fbhelper" style={{ maxWidth: 220 }} />
          <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
            请输入账号密码登录管理系统
          </Typography.Text>
        </div>
        {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}
        <Form onFinish={onFinish} layout="vertical" autoComplete="on">
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>登录</Button>
        </Form>
      </Card>
    </div>
  );
}
