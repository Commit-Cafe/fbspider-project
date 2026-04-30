import { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Tag, Space, Input, Select, Tabs,
  Form, message, Empty, Tooltip, Badge, Typography, Alert, Switch,
} from 'antd';
import {
  ReloadOutlined, SendOutlined, GlobalOutlined, AimOutlined,
  PlayCircleOutlined, PauseCircleOutlined, DollarOutlined,
  DesktopOutlined, ChromeOutlined, CheckCircleOutlined,
  ClockCircleOutlined, CloseCircleOutlined, LinkOutlined,
  UserOutlined, SwapOutlined,
} from '@ant-design/icons';
import API from '../api';

const { Text, Title } = Typography;
const { TabPane } = Tabs;

export default function DeviceControl() {
  const [devices, setDevices] = useState({});
  const [loading, setLoading] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState('');
  const [autoRoute, setAutoRoute] = useState(false);
  const [taskResults, setTaskResults] = useState([]);

  const loadDevices = useCallback(async () => {
    setLoading(true);
    try {
      const d = await API.get('/api/device-control/devices');
      if (d.success) {
        setDevices(d.data || {});
        const ids = Object.keys(d.data || {});
        if (ids.length > 0 && !selectedDevice) {
          setSelectedDevice(ids[0]);
        }
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [selectedDevice]);

  useEffect(() => {
    loadDevices();
    const timer = setInterval(loadDevices, 5000);
    return () => clearInterval(timer);
  }, []);

  // 发送指令：自动路由模式不附加 device，由后端根据 account_id 匹配
  const sendAndPoll = async (endpoint, body, label) => {
    try {
      const payload = autoRoute ? body : { device: selectedDevice, ...body };
      const d = await API.post(`/api/device-control/${endpoint}`, payload);
      if (!d.success) {
        message.error(d.message || '发送失败');
        return;
      }
      const target = d.device ? ` → ${d.device.slice(0, 8)}` : '';
      message.info(`${label} 已发送 [${d.task_id}]${target}`);
      addTaskEntry(d.task_id, label, 'pending', null, d.route_trace || []);
      pollResult(d.task_id);
    } catch (e) {
      message.error('发送失败: ' + e.message);
    }
  };

  const addTaskEntry = (taskId, label, status, result, routeTrace = []) => {
    setTaskResults(prev => [{
      task_id: taskId, label, status, result, routeTrace,
      time: new Date().toLocaleTimeString(),
    }, ...prev].slice(0, 50));
  };

  const updateTaskEntry = (taskId, status, result) => {
    setTaskResults(prev => prev.map(t =>
      t.task_id === taskId ? { ...t, status, result } : t
    ));
  };

  const pollResult = (taskId) => {
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const d = await API.get(`/api/device-control/result/${taskId}`);
        if (d.success && d.status === 'done') {
          clearInterval(interval);
          const ok = d.result?.status === 'ok';
          updateTaskEntry(taskId, ok ? 'success' : 'error', d.result);
          if (ok) message.success(`任务 [${taskId}] 完成`);
          else message.error(`任务 [${taskId}] 失败: ${d.result?.message || '未知错误'}`);
        }
      } catch { /* ignore */ }
      if (attempts > 30) {
        clearInterval(interval);
        updateTaskEntry(taskId, 'timeout', null);
        message.warning(`任务 [${taskId}] 超时`);
      }
    }, 2000);
  };

  const deviceIds = Object.keys(devices);
  const currentDevice = devices[selectedDevice];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>设备远程控制</Title>
        <Button icon={<ReloadOutlined />} onClick={loadDevices} loading={loading}>刷新</Button>
      </div>

      {/* 设备选择器 + 自动路由开关 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Space wrap>
            <Text strong>在线设备:</Text>
            {deviceIds.length === 0 ? (
              <Tag color="red">无在线设备</Tag>
            ) : (
              <Select
                value={selectedDevice}
                onChange={setSelectedDevice}
                style={{ minWidth: 320 }}
                placeholder="选择设备"
                disabled={autoRoute}
              >
                {deviceIds.map(did => (
                  <Select.Option key={did} value={did}>
                    <DesktopOutlined /> {did.slice(0, 8)}
                    {devices[did]?.username && (
                      <Tag color="blue" style={{ marginLeft: 6 }}><UserOutlined /> {devices[did].username}</Tag>
                    )}
                    <Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>
                      ({(devices[did]?.tabs || []).length} tab)
                    </Text>
                  </Select.Option>
                ))}
              </Select>
            )}
            <Badge count={deviceIds.length} style={{ backgroundColor: deviceIds.length > 0 ? '#52c41a' : '#ff4d4f' }} />
          </Space>
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>自动路由</Text>
            <Tooltip title="开启后，广告操作根据账户 ID 自动匹配设备，无需手动选择">
              <Switch
                checked={autoRoute}
                onChange={setAutoRoute}
                checkedChildren={<SwapOutlined />}
              />
            </Tooltip>
          </Space>
        </div>
        {autoRoute && (
          <Alert
            type="info" showIcon
            style={{ marginTop: 8 }}
            message="自动路由模式：填入账户 ID 后自动匹配 账户→用户→设备，无需手动选择设备"
          />
        )}
      </Card>

      <div style={{ display: 'flex', gap: 16 }}>
        {/* 左侧：操作面板 */}
        <div style={{ flex: 1 }}>
          <Tabs defaultActiveKey="tabs" type="card">
            <TabPane tab={<span><ChromeOutlined /> 标签页</span>} key="tabs">
              <TabsPanel tabs={currentDevice?.tabs || []} />
            </TabPane>
            <TabPane tab={<span><GlobalOutlined /> 导航</span>} key="navigate">
              <NavigatePanel onSend={(p) => sendAndPoll('navigate', p, '导航')} />
            </TabPane>
            <TabPane tab={<span><LinkOutlined /> 修改URL</span>} key="update-url">
              <UpdateUrlPanel onSend={(p) => sendAndPoll('update-url', p, '修改URL')} />
            </TabPane>
            <TabPane tab={<span><AimOutlined /> 点击</span>} key="click">
              <ClickPanel onSend={(p) => sendAndPoll('click', p, '点击')} />
            </TabPane>
            <TabPane tab={<span><PlayCircleOutlined /> 广告开关</span>} key="toggle">
              <TogglePanel onSend={(p) => sendAndPoll('toggle', p, p.enable ? '开启广告' : '暂停广告')} autoRoute={autoRoute} />
            </TabPane>
            <TabPane tab={<span><DollarOutlined /> 修改预算</span>} key="budget">
              <BudgetPanel onSend={(p) => sendAndPoll('budget', p, '修改预算')} autoRoute={autoRoute} />
            </TabPane>
            <TabPane tab={<span><SendOutlined /> 自定义</span>} key="custom">
              <CustomPanel onSend={(b) => sendAndPoll('send', b, b.action)} />
            </TabPane>
          </Tabs>
        </div>

        {/* 右侧：任务结果 */}
        <Card
          title="任务记录"
          size="small"
          style={{ width: 360, maxHeight: 'calc(100vh - 200px)', overflow: 'auto' }}
        >
          {taskResults.length === 0 ? (
            <Empty description="暂无任务记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            taskResults.map((t, i) => (
              <div key={i} style={{ padding: '6px 0', borderBottom: '1px solid #f0f0f0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Space size={4}>
                    {t.status === 'pending' && <ClockCircleOutlined style={{ color: '#1890ff' }} />}
                    {t.status === 'success' && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                    {t.status === 'error' && <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                    {t.status === 'timeout' && <ClockCircleOutlined style={{ color: '#faad14' }} />}
                    <Text strong style={{ fontSize: 13 }}>{t.label}</Text>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 11 }}>{t.time}</Text>
                </div>
                <Text type="secondary" style={{ fontSize: 11 }}>ID: {t.task_id}</Text>
                {t.result && (
                  <div style={{ fontSize: 11, color: t.status === 'error' ? '#ff4d4f' : '#666', marginTop: 2 }}>
                    {t.result.message || JSON.stringify(t.result.data || t.result).slice(0, 120)}
                  </div>
                )}
                {Array.isArray(t.routeTrace) && t.routeTrace.length > 0 && (
                  <div style={{ marginTop: 6, background: '#fafafa', borderRadius: 6, padding: 6 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>自动路由</Text>
                    {t.routeTrace.map((step, idx) => (
                      <div key={idx} style={{ fontSize: 11, color: '#666', marginTop: 2 }}>
                        {idx + 1}. {step.step} {step.mode ? `(${step.mode})` : ''} {step.device_id ? `→ ${step.device_id.slice(0, 8)}` : ''} {step.username ? `@${step.username}` : ''} {step.account_id ? `acct=${step.account_id}` : ''} {step.reason ? `reason=${step.reason}` : ''}
                      </div>
                    ))}
                  </div>
                )}
                {Array.isArray(t.result?.trace) && t.result.trace.length > 0 && (
                  <div style={{ marginTop: 6, background: '#f6ffed', borderRadius: 6, padding: 6 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>设备执行路径</Text>
                    {t.result.trace.map((step, idx) => (
                      <div key={idx} style={{ fontSize: 11, color: '#666', marginTop: 2 }}>
                        {idx + 1}. {step.step} {step.tab_id ? `tab=${step.tab_id}` : ''} {step.account_id ? `acct=${step.account_id}` : ''} {step.ad_type ? `type=${step.ad_type}` : ''} {step.to_level ? `→ ${step.to_level}` : ''} {step.url ? step.url.slice(0, 90) : ''} {step.message ? `msg=${step.message}` : ''}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </Card>
      </div>
    </div>
  );
}


// ============ 子面板 ============

function TabsPanel({ tabs }) {
  const columns = [
    { title: 'Tab ID', dataIndex: 'tab_id', width: 80 },
    { title: '标题', dataIndex: 'title', ellipsis: true, render: (t) => <Text style={{ fontSize: 13 }}>{t || '-'}</Text> },
    { title: 'URL', dataIndex: 'url', ellipsis: true, render: (u) => <Tooltip title={u}><Text copyable style={{ fontSize: 12 }}>{u}</Text></Tooltip> },
  ];
  return <Table columns={columns} dataSource={tabs} rowKey="tab_id" size="small" pagination={false} locale={{ emptyText: '暂无标签页' }} />;
}

function NavigatePanel({ onSend }) {
  const [form] = Form.useForm();
  return (
    <Form form={form} layout="vertical" onFinish={(v) => { onSend(v); form.resetFields(); }}>
      <Form.Item name="url" label="目标 URL" rules={[{ required: true, message: '请输入 URL' }]}>
        <Input placeholder="https://www.facebook.com/adsmanager" />
      </Form.Item>
      <Form.Item name="new_tab" label="打开方式" initialValue={true}>
        <Select>
          <Select.Option value={true}>新标签页</Select.Option>
          <Select.Option value={false}>当前标签页</Select.Option>
        </Select>
      </Form.Item>
      <Button type="primary" htmlType="submit" icon={<GlobalOutlined />}>导航</Button>
    </Form>
  );
}

function UpdateUrlPanel({ onSend }) {
  const [form] = Form.useForm();
  const [mode, setMode] = useState('replace');
  return (
    <Form form={form} layout="vertical" onFinish={(v) => {
      const params = {};
      if (v.url) params.url = v.url;
      if (mode === 'new_url' && v.new_url) params.new_url = v.new_url;
      if (mode === 'replace' && v.old_str && v.new_str) params.replace = { old: v.old_str, new: v.new_str };
      if (mode === 'set_params' && v.param_key) params.set_params = { [v.param_key]: v.param_value || '' };
      if (mode === 'remove_params' && v.remove_key) params.remove_params = [v.remove_key];
      onSend(params);
      form.resetFields();
    }}>
      <Form.Item name="url" label="匹配标签页 URL 关键字">
        <Input placeholder="adsmanager.facebook.com" />
      </Form.Item>
      <Form.Item label="修改方式">
        <Select value={mode} onChange={setMode}>
          <Select.Option value="replace">替换 URL 片段</Select.Option>
          <Select.Option value="new_url">替换整个 URL</Select.Option>
          <Select.Option value="set_params">设置参数</Select.Option>
          <Select.Option value="remove_params">删除参数</Select.Option>
        </Select>
      </Form.Item>
      {mode === 'replace' && (
        <Space style={{ width: '100%' }} direction="vertical">
          <Form.Item name="old_str" label="查找" rules={[{ required: true }]}>
            <Input placeholder="manage/ads" />
          </Form.Item>
          <Form.Item name="new_str" label="替换为" rules={[{ required: true }]}>
            <Input placeholder="manage/adsets" />
          </Form.Item>
        </Space>
      )}
      {mode === 'new_url' && (
        <Form.Item name="new_url" label="新 URL" rules={[{ required: true }]}>
          <Input placeholder="https://adsmanager.facebook.com/adsmanager/manage/adsets?act=123" />
        </Form.Item>
      )}
      {mode === 'set_params' && (
        <Space style={{ width: '100%' }} direction="vertical">
          <Form.Item name="param_key" label="参数名" rules={[{ required: true }]}>
            <Input placeholder="act" />
          </Form.Item>
          <Form.Item name="param_value" label="参数值">
            <Input placeholder="123456" />
          </Form.Item>
        </Space>
      )}
      {mode === 'remove_params' && (
        <Form.Item name="remove_key" label="删除的参数名" rules={[{ required: true }]}>
          <Input placeholder="selected_adset_ids" />
        </Form.Item>
      )}
      <Button type="primary" htmlType="submit" icon={<LinkOutlined />}>修改 URL</Button>
    </Form>
  );
}

function ClickPanel({ onSend }) {
  const [form] = Form.useForm();
  return (
    <Form form={form} layout="vertical" onFinish={(v) => { onSend(v); form.resetFields(); }}>
      <Form.Item name="url" label="页面 URL 关键字（可选）">
        <Input placeholder="adsmanager.facebook.com" />
      </Form.Item>
      <Form.Item name="selector" label="选择器" rules={[{ required: true, message: '请输入选择器' }]}
        extra="支持: CSS选择器 / text=按钮文字 / aria=标签">
        <Input placeholder="text=创建" />
      </Form.Item>
      <Button type="primary" htmlType="submit" icon={<AimOutlined />}>点击</Button>
    </Form>
  );
}

function TogglePanel({ onSend, autoRoute }) {
  const [form] = Form.useForm();
  return (
    <Form form={form} layout="vertical" onFinish={(v) => { onSend(v); form.resetFields(); }}>
      {autoRoute && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="自动路由：填入账户 ID 后自动定位设备" />
      )}
      <Form.Item name="ad_type" label="广告类型" rules={[{ required: true }]} initialValue="adsets">
        <Select>
          <Select.Option value="campaigns">广告系列 (campaigns)</Select.Option>
          <Select.Option value="adsets">广告组 (adsets)</Select.Option>
          <Select.Option value="ads">广告 (ads)</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item name="ad_id" label="广告 ID" rules={[{ required: true, message: '请输入广告 ID' }]}>
        <Input placeholder="例: 120218560094XXXX" />
      </Form.Item>
      <Form.Item name="account_id" label="广告账户 ID" rules={[{ required: true, message: '请输入账户 ID' }]}
        extra={autoRoute ? '此 ID 同时用于自动匹配设备' : ''}>
        <Input placeholder="例: 1858902XXXXXX" />
      </Form.Item>
      <Form.Item name="enable" label="操作" initialValue={true}>
        <Select>
          <Select.Option value={true}><PlayCircleOutlined style={{ color: '#52c41a' }} /> 开启</Select.Option>
          <Select.Option value={false}><PauseCircleOutlined style={{ color: '#faad14' }} /> 暂停</Select.Option>
        </Select>
      </Form.Item>
      <Button type="primary" htmlType="submit" icon={<PlayCircleOutlined />}>执行</Button>
    </Form>
  );
}

function BudgetPanel({ onSend, autoRoute }) {
  const [form] = Form.useForm();
  return (
    <Form form={form} layout="vertical" onFinish={(v) => { onSend(v); form.resetFields(); }}>
      {autoRoute && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="自动路由：填入账户 ID 后自动定位设备" />
      )}
      <Form.Item name="ad_type" label="广告类型" rules={[{ required: true }]} initialValue="adsets">
        <Select>
          <Select.Option value="campaigns">广告系列 (campaigns)</Select.Option>
          <Select.Option value="adsets">广告组 (adsets)</Select.Option>
          <Select.Option value="ads">广告 (ads)</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item name="ad_id" label="广告 ID" rules={[{ required: true, message: '请输入广告 ID' }]}>
        <Input placeholder="例: 120218560094XXXX" />
      </Form.Item>
      <Form.Item name="account_id" label="广告账户 ID" rules={[{ required: true, message: '请输入账户 ID' }]}
        extra={autoRoute ? '此 ID 同时用于自动匹配设备' : ''}>
        <Input placeholder="例: 1858902XXXXXX" />
      </Form.Item>
      <Form.Item name="budget" label="预算金额" rules={[{ required: true, message: '请输入预算' }]}>
        <Input placeholder="例: 5000" suffix="(币种最小单位)" />
      </Form.Item>
      <Button type="primary" htmlType="submit" icon={<DollarOutlined />}>修改预算</Button>
    </Form>
  );
}

function CustomPanel({ onSend }) {
  const [form] = Form.useForm();
  return (
    <Form form={form} layout="vertical" onFinish={(v) => {
      let params = {};
      try { params = v.params ? JSON.parse(v.params) : {}; } catch { message.error('params JSON 格式错误'); return; }
      onSend({ action: v.action, params });
      form.resetFields();
    }}>
      <Form.Item name="action" label="Action" rules={[{ required: true }]}>
        <Input placeholder="navigate / click / toggle_ad / set_budget / fill / update_url / ping" />
      </Form.Item>
      <Form.Item name="params" label="Params (JSON)" extra='示例: {"url": "https://facebook.com"}'>
        <Input.TextArea rows={4} placeholder='{"url": "https://facebook.com", "new_tab": true}' />
      </Form.Item>
      <Button type="primary" htmlType="submit" icon={<SendOutlined />}>发送</Button>
    </Form>
  );
}
