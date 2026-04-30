import { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Table, Button, Input, Form, Descriptions, Tag, Space, Popconfirm, message, Modal } from 'antd';
import {
  SettingOutlined, KeyOutlined, DeleteOutlined, ClearOutlined,
} from '@ant-design/icons';
import API, { getAuthUser, hasSpecificTargetUser, isManagerRole, sendCommand } from '../api';

export default function Settings() {
  const [dbStats, setDbStats] = useState({});
  const [connStatus, setConnStatus] = useState({});
  const [statsData, setStatsData] = useState({});
  const [tokenInfo, setTokenInfo] = useState({});
  const [logs, setLogs] = useState([]);
  const [callbackLogs, setCallbackLogs] = useState([]);
  const [callbackLogDetail, setCallbackLogDetail] = useState(null);
  const [callbackLogOpen, setCallbackLogOpen] = useState(false);
  const [callbackLoading, setCallbackLoading] = useState(false);
  const [dslPushLogs, setDslPushLogs] = useState([]);
  const [dslOverview, setDslOverview] = useState({ summary: {}, data: [] });
  const [form] = Form.useForm();
  const authUser = getAuthUser();
  const isAdmin = authUser?.role === 'admin';

  const loadAll = useCallback(async () => {
    const requests = [
      API.get('/api/db-stats'),
      API.get('/api/stats'),
      API.get('/api/connection-state'),
      API.get('/api/logs?per_page=20'),
    ];
    if (isAdmin) {
      requests.push(API.get('/api/callback-logs?limit=50'));
    }
    requests.push(API.get('/api/dsl-push-logs?limit=30'));
    requests.push(API.get('/api/dsl-overview'));
    const [db, stats, conn, logsRes, callbackLogsRes, dslLogsRes, dslOverviewRes] = await Promise.all(requests);
    if (db.success) setDbStats(db.data);
    if (stats.success) setStatsData(stats.data);
    if (conn.success) {
      setConnStatus(conn.data || {});
      setTokenInfo(conn.data || {});
    }
    if (logsRes.success) setLogs(logsRes.data);
    if (callbackLogsRes?.success) setCallbackLogs(callbackLogsRes.data);
    if (dslLogsRes?.success) setDslPushLogs(dslLogsRes.data);
    if (dslOverviewRes?.success) setDslOverview(dslOverviewRes);
  }, [isAdmin]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const changePassword = async (values) => {
    if (values.newPassword !== values.confirmPassword) {
      message.error('两次输入的新密码不一致');
      return;
    }
    const result = await API.post('/api/auth/change-password', {
      current_password: values.currentPassword,
      new_password: values.newPassword,
    });
    if (result.success) {
      message.success('密码已更新');
      form.resetFields();
    } else {
      message.error(result.message || '修改密码失败');
    }
  };

  const clearData = async (table) => {
    if (isManagerRole(getAuthUser()?.role) && !hasSpecificTargetUser()) {
      message.error('请先选择一个具体用户再清空数据');
      return;
    }
    const result = await API.post('/api/clear-data', { table });
    if (result.success) {
      message.success('数据已清空');
      loadAll();
    } else {
      message.error('清空失败');
    }
  };

  const logColumns = [
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 180, render: v => <span style={{ fontSize: 12 }}>{v}</span> },
    { title: '操作', dataIndex: 'action', key: 'action', width: 200 },
    { title: '详情', dataIndex: 'details', key: 'details', render: v => <span style={{ fontSize: 12 }}>{v}</span> },
  ];

  const openCallbackLog = async (filename) => {
    setCallbackLoading(true);
    const result = await API.get(`/api/callback-logs/${encodeURIComponent(filename)}`);
    setCallbackLoading(false);
    if (!result.success) {
      message.error(result.message || '加载回调日志失败');
      return;
    }
    setCallbackLogDetail(result.data);
    setCallbackLogOpen(true);
  };

  const callbackColumns = [
    { title: '时间', dataIndex: 'logged_at', key: 'logged_at', width: 220, render: v => <span style={{ fontSize: 12 }}>{v || '-'}</span> },
    { title: '阶段', dataIndex: 'stage', key: 'stage', width: 130, render: v => <Tag>{v || '-'}</Tag> },
    { title: '批次槽位', dataIndex: 'slot', key: 'slot', width: 190, render: v => <code>{v || '-'}</code> },
    { title: '数量', dataIndex: 'count', key: 'count', width: 80 },
    { title: '状态码', dataIndex: 'status_code', key: 'status_code', width: 100, render: v => v ?? '-' },
    {
      title: '响应/错误', key: 'message',
      render: (_, r) => <span style={{ fontSize: 12 }}>{r.error || r.response || '-'}</span>,
    },
    {
      title: '操作', key: 'action', width: 90,
      render: (_, r) => <Button size="small" onClick={() => openCallbackLog(r.filename)}>详情</Button>,
    },
  ];

  return (
    <>
      <h4 style={{ marginBottom: 16 }}><SettingOutlined style={{ marginRight: 8 }} />设置 / 状态</h4>

      <Row gutter={[16, 16]}>
        {/* Connection Status */}
        <Col span={12}>
          <Card title="插件连接状态" size="small">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="服务器状态"><Tag color="success">运行中</Tag></Descriptions.Item>
              <Descriptions.Item label="系统账号"><code>{getAuthUser()?.username || '-'}</code></Descriptions.Item>
              <Descriptions.Item label="Facebook 用户"><code>{connStatus.fb_user_id || '-'}</code></Descriptions.Item>
              <Descriptions.Item label="Facebook 名称">{connStatus.fb_user_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="Token 状态">{connStatus.has_token ? <Tag color="success">已获取</Tag> : <Tag color="warning">未获取</Tag>}</Descriptions.Item>
              <Descriptions.Item label="插件心跳">{connStatus.heartbeat_ok ? <Tag color="success">在线</Tag> : <Tag color="default">离线</Tag>}</Descriptions.Item>
              <Descriptions.Item label="最近 Token 时间">{connStatus.last_token_time || '-'}</Descriptions.Item>
              <Descriptions.Item label="总账户数">{statsData.total_accounts}</Descriptions.Item>
              <Descriptions.Item label="BM 数量">{statsData.bm_count}</Descriptions.Item>
              <Descriptions.Item label="Pixel 数量">{statsData.pixel_count}</Descriptions.Item>
              <Descriptions.Item label="素材数量">{statsData.ad_library_count}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* Token Info */}
        <Col span={12}>
          <Card title="Token 信息" size="small" extra={
            <Button size="small" icon={<KeyOutlined />} onClick={() => sendCommand('refresh_token').then(() => message.success('刷新Token命令已发送')).catch(e => message.error(e.message))}>
              刷新Token
            </Button>
          }>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="是否已获取 Token">{tokenInfo.has_token ? '是' : '否'}</Descriptions.Item>
              <Descriptions.Item label="Facebook 用户 ID"><code>{tokenInfo.fb_user_id || '-'}</code></Descriptions.Item>
              <Descriptions.Item label="Facebook 用户名">{tokenInfo.fb_user_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="最近 Token 时间">{tokenInfo.last_token_time || '-'}</Descriptions.Item>
              <Descriptions.Item label="最近心跳">{tokenInfo.last_heartbeat || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* DB Stats */}
        <Col span={12}>
          <Card title="数据库统计" size="small">
            <Descriptions column={1} size="small" bordered>
              {Object.entries(dbStats).map(([k, v]) => (
                <Descriptions.Item key={k} label={k}><b>{v}</b></Descriptions.Item>
              ))}
            </Descriptions>
          </Card>
        </Col>

        {/* Password */}
        <Col span={12}>
          <Card title="修改密码" size="small">
            <Form form={form} layout="vertical" onFinish={changePassword}>
              <Form.Item label="当前密码" name="currentPassword" rules={[{ required: true, message: '请输入当前密码' }]}>
                <Input.Password />
              </Form.Item>
              <Form.Item label="新密码" name="newPassword" rules={[{ required: true, message: '请输入新密码' }]}>
                <Input.Password />
              </Form.Item>
              <Form.Item label="确认新密码" name="confirmPassword" rules={[{ required: true, message: '请确认新密码' }]}>
                <Input.Password />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<KeyOutlined />}>保存新密码</Button>
            </Form>
          </Card>
        </Col>

        {/* Data Management */}
        <Col span={12}>
          <Card title="数据管理" size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              {[
                { key: 'ad_accounts', label: '清空广告账户数据' },
                { key: 'bm_list', label: '清空BM数据' },
                { key: 'pixels', label: '清空Pixel数据' },
                { key: 'ad_library_items', label: '清空素材库' },
              ].map(item => (
                <Button key={item.key} block icon={<ClearOutlined />} onClick={() => clearData(item.key)} style={{ textAlign: 'left' }}>
                  {item.label}
                </Button>
              ))}
              <Popconfirm title="确定清空所有数据？" onConfirm={() => clearData('all')} okText="确定" cancelText="取消">
                <Button block danger icon={<DeleteOutlined />} style={{ textAlign: 'left' }}>清空所有数据</Button>
              </Popconfirm>
            </Space>
          </Card>
        </Col>

        {/* Logs */}
        <Col span={24}>
          <Card title="最近操作日志" size="small" bodyStyle={{ padding: 0 }}>
            <Table columns={logColumns} dataSource={logs} rowKey={(r, i) => i} size="small" pagination={false} />
          </Card>
        </Col>

        {isAdmin && (
          <Col span={24}>
            <Card title="回调记录" size="small" bodyStyle={{ padding: 0 }}>
              <Table columns={callbackColumns} dataSource={callbackLogs} rowKey="filename" size="small" pagination={{ pageSize: 10 }} />
            </Card>
          </Col>
        )}

        {/* DSL Push Overview */}
        <Col span={24}>
          <Card
            title="临时限额(DSL)推送状态"
            size="small"
            extra={
              <Space>
                <Tag color="blue">总计 {dslOverview.summary?.total || 0}</Tag>
                <Tag color="success">已获取 {dslOverview.summary?.has_formatted_dsl || 0}</Tag>
                <Tag color="error">未获取 {dslOverview.summary?.missing_formatted_dsl || 0}</Tag>
                {!!dslOverview.summary?.missing_by_reason?.missing_session && <Tag color="gold">缺会话 {dslOverview.summary.missing_by_reason.missing_session}</Tag>}
                {!!dslOverview.summary?.missing_by_reason?.no_formatted_dsl && <Tag color="orange">无返回值 {dslOverview.summary.missing_by_reason.no_formatted_dsl}</Tag>}
                {!!dslOverview.summary?.missing_by_reason?.tab_unreachable && <Tag color="magenta">页面无响应 {dslOverview.summary.missing_by_reason.tab_unreachable}</Tag>}
                {!!dslOverview.summary?.missing_by_reason?.http_error && <Tag color="volcano">HTTP异常 {dslOverview.summary.missing_by_reason.http_error}</Tag>}
              </Space>
            }
            bodyStyle={{ padding: 0 }}
          >
            <Table
              columns={[
                { title: '账户ID', dataIndex: 'account_id', key: 'account_id', width: 160, render: v => <code style={{ fontSize: 12 }}>{v}</code> },
                { title: '名称', dataIndex: 'name', key: 'name', width: 180, ellipsis: true },
                { title: '状态', dataIndex: 'account_status', key: 'account_status', width: 100, render: v => <Tag color={v === 'ACTIVE' || v === '1' ? 'success' : 'default'}>{v || '-'}</Tag> },
                { title: '币种', dataIndex: 'currency', key: 'currency', width: 70 },
                { title: '临时限额', dataIndex: 'formatted_dsl', key: 'formatted_dsl', width: 160, render: (v, r) => v ? <span style={{ color: '#52c41a', fontWeight: 500 }}>{r.formatted_dsl_tous ? `${v} (${r.formatted_dsl_tous})` : v}</span> : <Tag color="error">未获取</Tag> },
                { title: '单日限额', dataIndex: 'adtrust_dsl', key: 'adtrust_dsl', width: 140, render: (v, r) => v || r.adtrust_dsl_tous || '-' },
                { title: '抓取状态', dataIndex: 'dsl_fetch_status', key: 'dsl_fetch_status', width: 120, render: (v, r) => {
                  if (r.formatted_dsl) return <Tag color="success">success</Tag>;
                  const colorMap = { missing_session: 'gold', no_formatted_dsl: 'orange', tab_unreachable: 'magenta', http_error: 'volcano', fetch_error: 'red', missing: 'default' };
                  return <Tag color={colorMap[v] || 'default'}>{v || 'unknown'}</Tag>;
                } },
                { title: '重试', dataIndex: 'dsl_fetch_attempts', key: 'dsl_fetch_attempts', width: 70, render: v => v || 0 },
                { title: '失败原因', dataIndex: 'dsl_fetch_error', key: 'dsl_fetch_error', width: 260, ellipsis: true, render: v => <span style={{ fontSize: 12 }}>{v || '-'}</span> },
                { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 180, render: v => <span style={{ fontSize: 12 }}>{v || '-'}</span> },
              ]}
              dataSource={dslOverview.data}
              rowKey="account_id"
              size="small"
              pagination={{ pageSize: 10 }}
            />
          </Card>
        </Col>

        {/* DSL Push Logs */}
        <Col span={24}>
          <Card title="DSL推送记录（插件主动推送）" size="small" bodyStyle={{ padding: 0 }}>
            <Table
              columns={[
                { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 180, render: v => <span style={{ fontSize: 12 }}>{v}</span> },
                { title: '详情', dataIndex: 'details', key: 'details', render: v => <code style={{ fontSize: 12 }}>{v}</code> },
                { title: '用户', dataIndex: 'user_id', key: 'user_id', width: 160, render: v => <span style={{ fontSize: 12 }}>{v || '-'}</span> },
              ]}
              dataSource={dslPushLogs}
              rowKey={(r, i) => i}
              size="small"
              pagination={{ pageSize: 10 }}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        title="回调日志详情"
        open={callbackLogOpen}
        onCancel={() => setCallbackLogOpen(false)}
        footer={null}
        width={900}
      >
        <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, maxHeight: '65vh', overflow: 'auto', fontSize: 12, margin: 0 }}>
          {callbackLoading ? '加载中...' : JSON.stringify(callbackLogDetail, null, 2)}
        </pre>
      </Modal>
    </>
  );
}
