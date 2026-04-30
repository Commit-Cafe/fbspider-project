import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Steps, Button, Form, Input, InputNumber, Select, DatePicker,
  TimePicker, Switch, Radio, Alert, message, Descriptions, Tag,
  Table, Divider, Typography, Row, Col, Spin, Timeline, Space, Tooltip,
  Upload,
} from 'antd';
import {
  RocketOutlined, AimOutlined, ShoppingCartOutlined, TeamOutlined,
  ThunderboltOutlined, AppstoreOutlined, EyeOutlined,
  CheckCircleOutlined, SendOutlined, HistoryOutlined,
  LoadingOutlined, CloseCircleOutlined, ClockCircleOutlined,
  SyncOutlined, InfoCircleOutlined, DollarOutlined, FundOutlined,
  StopOutlined, PictureOutlined, VideoCameraOutlined, FileImageOutlined,
  UploadOutlined, InboxOutlined,
} from '@ant-design/icons';
import API, {
  canBrowseData, hasSpecificTargetUser, isManagerRole, getAuthUser,
  appendTargetUser,
} from '../api';
import dayjs from 'dayjs';

const { Text } = Typography;

const AD_OBJECTIVES = [
  { key: 'OUTCOME_AWARENESS', label: '知名度', icon: <EyeOutlined />, desc: '向可能记住广告的用户展示广告' },
  { key: 'OUTCOME_TRAFFIC', label: '流量', icon: <ThunderboltOutlined />, desc: '将用户引导至网站或应用等目标位置' },
  { key: 'OUTCOME_ENGAGEMENT', label: '互动', icon: <TeamOutlined />, desc: '获取更多消息对话、视频观看、帖子互动等' },
  { key: 'OUTCOME_LEADS', label: '潜在客户', icon: <AimOutlined />, desc: '为业务获取潜在客户' },
  { key: 'OUTCOME_APP_PROMOTION', label: '应用推广', icon: <AppstoreOutlined />, desc: '吸引新用户安装应用并继续使用' },
  { key: 'OUTCOME_SALES', label: '销量', icon: <ShoppingCartOutlined />, desc: '寻找可能购买商品或服务的用户' },
];

const BID_STRATEGIES = [
  { value: 'LOWEST_COST_WITHOUT_CAP', label: '最低费用', desc: '自动竞价，尽量用最低费用获取最多成效' },
  { value: 'LOWEST_COST_WITH_BID_CAP', label: '竞价上限', desc: '设定竞价上限，控制单次竞价的最高金额' },
  { value: 'COST_CAP', label: '费用上限', desc: '控制每次成效的平均费用' },
  { value: 'LOWEST_COST_WITH_MIN_ROAS', label: '最低 ROAS', desc: '设定最低广告支出回报率' },
];

const OPTIMIZATION_GOALS = [
  { value: 'REACH', label: '覆盖人数' },
  { value: 'IMPRESSIONS', label: '展示次数' },
  { value: 'LINK_CLICKS', label: '链接点击量' },
  { value: 'LANDING_PAGE_VIEWS', label: '落地页浏览量' },
  { value: 'POST_ENGAGEMENT', label: '帖子互动' },
  { value: 'CONVERSATIONS', label: '对话量' },
  { value: 'LEAD_GENERATION', label: '潜在客户' },
  { value: 'APP_INSTALLS', label: '应用安装量' },
  { value: 'OFFSITE_CONVERSIONS', label: '转化量' },
  { value: 'VALUE', label: '转化价值' },
  { value: 'THRUPLAY', label: 'ThruPlay 视频观看' },
  { value: 'VIDEO_VIEWS', label: '2 秒连续视频观看' },
];

const CTA_TYPES = [
  { value: 'LEARN_MORE', label: '了解详情' },
  { value: 'SHOP_NOW', label: '立即选购' },
  { value: 'SIGN_UP', label: '注册' },
  { value: 'BOOK_TRAVEL', label: '预订' },
  { value: 'CONTACT_US', label: '联系我们' },
  { value: 'DOWNLOAD', label: '下载' },
  { value: 'GET_OFFER', label: '获取优惠' },
  { value: 'GET_QUOTE', label: '获取报价' },
  { value: 'APPLY_NOW', label: '立即申请' },
  { value: 'SUBSCRIBE', label: '订阅' },
  { value: 'WATCH_MORE', label: '观看更多' },
  { value: 'NO_BUTTON', label: '无按钮' },
];

// Step status → icon mapping
function stepIcon(status) {
  if (status === 'done') return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
  if (status === 'running') return <LoadingOutlined style={{ color: '#1677ff' }} />;
  if (status === 'error') return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
  return <ClockCircleOutlined style={{ color: '#d9d9d9' }} />;
}
function stepColor(status) {
  if (status === 'done') return 'green';
  if (status === 'running') return 'blue';
  if (status === 'error') return 'red';
  return 'gray';
}

export default function CreateAd() {
  const [current, setCurrent] = useState(0);
  const [form] = Form.useForm();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [selectedObjective, setSelectedObjective] = useState('');
  const [budgetScheduleEnabled, setBudgetScheduleEnabled] = useState(false);
  const [budgetLevel, setBudgetLevel] = useState('campaign'); // 'campaign' (CBO) | 'adset' (ABO)
  const [budgetType, setBudgetType] = useState('daily'); // 'daily' | 'lifetime'
  const [creativeType, setCreativeType] = useState('image'); // 'image' | 'video'
  const [uploadedImageUrl, setUploadedImageUrl] = useState('');
  const [uploadedVideoUrl, setUploadedVideoUrl] = useState('');
  const [imageFileList, setImageFileList] = useState([]);
  const [videoFileList, setVideoFileList] = useState([]);

  // === Progress tracking ===
  const [trackingTaskId, setTrackingTaskId] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const pollRef = useRef(null);

  // Ad task history
  const [tasks, setTasks] = useState([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksTotal, setTasksTotal] = useState(0);
  const [tasksPage, setTasksPage] = useState(1);

  // Load ad accounts
  const loadAccounts = useCallback(async () => {
    if (!canBrowseData()) return;
    setLoading(true);
    try {
      const res = await API.get(appendTargetUser('/api/accounts?page=1&per_page=500'));
      if (res.success) {
        setAccounts((res.data || []).filter(a => {
          const s = String(a.account_status || a.status || '').toUpperCase();
          return s === 'ACTIVE' || s === '1';
        }));
      }
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  // Load ad tasks history
  const loadTasks = useCallback(async (p) => {
    if (!canBrowseData()) return;
    setTasksLoading(true);
    const pg = p || tasksPage;
    try {
      const res = await API.get(appendTargetUser(`/api/ads/tasks?page=${pg}&per_page=10`));
      if (res.success) {
        setTasks(res.data || []);
        setTasksTotal(res.total || 0);
      }
    } catch { /* ignore */ }
    setTasksLoading(false);
  }, [tasksPage]);

  useEffect(() => { loadAccounts(); loadTasks(); }, []);

  // === Poll for progress when tracking a task ===
  useEffect(() => {
    if (!trackingTaskId) return;
    let active = true;
    async function poll() {
      try {
        const res = await API.get(`/api/ads/tasks/${trackingTaskId}/progress`);
        if (!active) return;
        if (res.success && res.data) {
          setProgressData(res.data);
          // Stop polling once completed or failed
          const st = res.data.status;
          if (st === 'completed' || st === 'failed') {
            clearInterval(pollRef.current);
            pollRef.current = null;
            loadTasks(); // refresh history
          }
        }
      } catch { /* ignore */ }
    }
    poll(); // immediate first poll
    pollRef.current = setInterval(poll, 1500);
    return () => { active = false; clearInterval(pollRef.current); pollRef.current = null; };
  }, [trackingTaskId]);

  const objectiveLabel = (key) => AD_OBJECTIVES.find(o => o.key === key)?.label || key;

  // Step navigation
  const next = async () => {
    try {
      if (current === 0) await form.validateFields(['account_id', 'objective']);
      else if (current === 1) {
        await form.validateFields(['campaign_name', 'budget_amount']);
        // Validate schedule >= 24h for daily budget
        if (budgetScheduleEnabled && budgetType === 'daily') {
          const v = form.getFieldsValue(['start_date', 'start_time', 'end_date', 'end_time']);
          if (v.start_date && v.end_date) {
            const start = dayjs(v.start_date).hour(v.start_time ? dayjs(v.start_time).hour() : 0).minute(v.start_time ? dayjs(v.start_time).minute() : 0);
            const end = dayjs(v.end_date).hour(v.end_time ? dayjs(v.end_time).hour() : 0).minute(v.end_time ? dayjs(v.end_time).minute() : 0);
            if (end.diff(start, 'hour') < 24) {
              message.error('使用单日预算时，排期不得低于 24 小时');
              return;
            }
          }
        }
      }
      else if (current === 2) await form.validateFields(['page_id', 'primary_text', 'link_url']);
      setCurrent(current + 1);
    } catch { /* validation error shown by form */ }
  };
  const prev = () => setCurrent(current - 1);

  // Submit
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      const payload = {
        account_id: values.account_id,
        objective: values.objective,
        campaign_name: values.campaign_name,
        budget_level: budgetLevel,
        budget_type: budgetType,
        budget_amount: values.budget_amount,
        bid_strategy: values.bid_strategy || 'LOWEST_COST_WITHOUT_CAP',
        bid_amount: values.bid_amount || null,
        optimization_goal: values.optimization_goal || 'REACH',
        billing_event: values.billing_event || 'IMPRESSIONS',
        budget_schedule_enabled: budgetScheduleEnabled,
        start_date: values.start_date ? dayjs(values.start_date).format('YYYY-MM-DD') : '',
        start_time: values.start_time ? dayjs(values.start_time).format('HH:mm') : '00:00',
        end_date: values.end_date ? dayjs(values.end_date).format('YYYY-MM-DD') : '',
        end_time: values.end_time ? dayjs(values.end_time).format('HH:mm') : '00:00',
        // Creative params
        page_id: values.page_id || '',
        creative_type: creativeType,
        image_url: values.image_url || '',
        video_url: values.video_url || '',
        primary_text: values.primary_text || '',
        headline: values.headline || '',
        description: values.description || '',
        link_url: values.link_url || '',
        call_to_action: values.call_to_action || 'LEARN_MORE',
      };

      const res = await API.post('/api/ads/create', payload);
      setSubmitting(false);

      if (res.success) {
        setTrackingTaskId(res.task_id);
        setProgressData(null);
        message.success('广告创建命令已发送');
      } else {
        message.error(res.message || '创建失败');
      }
    } catch (e) {
      setSubmitting(false);
      message.error(e.message || '请检查表单填写');
    }
  };

  // Reset
  const handleReset = () => {
    form.resetFields();
    setSelectedObjective('');
    setBudgetScheduleEnabled(false);
    setBudgetLevel('campaign');
    setBudgetType('daily');
    setCreativeType('image');
    setUploadedImageUrl('');
    setUploadedVideoUrl('');
    setImageFileList([]);
    setVideoFileList([]);
    setTrackingTaskId(null);
    setProgressData(null);
    setCurrent(0);
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  // Cancel task
  const handleCancel = async (taskId) => {
    try {
      const res = await API.post(`/api/ads/tasks/${taskId || trackingTaskId}/cancel`);
      if (res.success) {
        message.success('任务已取消');
        loadTasks();
      } else {
        message.error(res.message || '取消失败');
      }
    } catch { message.error('取消请求失败'); }
  };

  // ============ Progress panel renderer ============
  const renderProgressPanel = () => {
    if (!trackingTaskId) return null;

    const steps = progressData?.progress?.steps || [];
    const taskStatus = progressData?.status || 'pending';
    const isFinished = taskStatus === 'completed' || taskStatus === 'failed' || taskStatus === 'cancelled';

    return (
      <Card
        title={
          <span>
            {taskStatus === 'completed'
              ? <><CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />创建完成</>
              : taskStatus === 'cancelled'
              ? <><StopOutlined style={{ color: '#faad14', marginRight: 8 }} />已取消</>
              : taskStatus === 'failed'
              ? <><CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />创建失败</>
              : <><SyncOutlined spin style={{ color: '#1677ff', marginRight: 8 }} />正在创建广告...</>
            }
          </span>
        }
        style={{ marginBottom: 16 }}
        extra={<Space>
          {!isFinished && <Button danger icon={<StopOutlined />} onClick={() => handleCancel()}>取消任务</Button>}
          {isFinished && <Button type="primary" onClick={handleReset}>创建新广告</Button>}
        </Space>}
      >
        {!progressData ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin tip="正在加载进度..." />
          </div>
        ) : (
          <Timeline
            items={steps.map((s) => ({
              color: stepColor(s.status),
              dot: stepIcon(s.status),
              children: (
                <div>
                  <div style={{ fontWeight: 500 }}>{s.label}</div>
                  {s.message && (
                    <div style={{
                      fontSize: 12,
                      color: s.status === 'error' ? '#ff4d4f' : '#888',
                      marginTop: 2,
                    }}>
                      {s.message}
                    </div>
                  )}
                  {s.ts && (
                    <div style={{ fontSize: 11, color: '#bbb', marginTop: 2 }}>
                      {dayjs(s.ts).format('HH:mm:ss')}
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        )}

        {/* Show result summary if completed */}
        {taskStatus === 'completed' && progressData?.result && (
          <Alert
            type="success"
            showIcon
            message="广告创建成功"
            description={
              <div>
                {progressData.result.campaign_id && <div>Campaign ID: <Text copyable>{progressData.result.campaign_id}</Text></div>}
                {progressData.result.adset_id && <div>Ad Set ID: <Text copyable>{progressData.result.adset_id}</Text></div>}
                {progressData.result.message && <div>{progressData.result.message}</div>}
              </div>
            }
            style={{ marginTop: 16 }}
          />
        )}
        {taskStatus === 'failed' && (
          <Alert
            type="error"
            showIcon
            message="创建失败"
            description={steps.filter(s => s.status === 'error').map(s => s.message).join('; ') || '未知错误'}
            style={{ marginTop: 16 }}
          />
        )}
        {taskStatus === 'cancelled' && (
          <Alert
            type="warning"
            showIcon
            message="任务已取消"
            description="该广告创建任务已被手动取消"
            style={{ marginTop: 16 }}
          />
        )}
      </Card>
    );
  };

  // ============ Task history columns ============
  const taskColumns = [
    {
      title: '广告账户', dataIndex: ['params', 'account_id'], key: 'account_id', width: 160,
      render: (v) => <Text copyable style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '广告目标', dataIndex: ['params', 'objective'], key: 'objective', width: 100,
      render: (v) => <Tag color="blue">{objectiveLabel(v)}</Tag>,
    },
    {
      title: '系列名称', dataIndex: ['params', 'campaign_name'], key: 'campaign_name', ellipsis: true,
    },
    {
      title: '预算', dataIndex: ['params'], key: 'budget', width: 140,
      render: (_, row) => {
        const p = row.params || {};
        const lvl = p.budget_level === 'adset' ? 'ABO' : 'CBO';
        const tp = p.budget_type === 'lifetime' ? '总' : '日';
        return <span>{lvl} / {tp} {p.budget_amount || p.daily_budget || '-'}</span>;
      },
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s) => {
        if (s === 'completed') return <Tag color="success">已完成</Tag>;
        if (s === 'pending') return <Tag color="default">等待中</Tag>;
        if (s === 'running') return <Tag icon={<SyncOutlined spin />} color="processing">执行中</Tag>;
        if (s === 'failed') return <Tag color="error">失败</Tag>;
        if (s === 'cancelled') return <Tag color="warning">已取消</Tag>;
        return <Tag>{s}</Tag>;
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_, row) => {
        if (row.status === 'pending' || row.status === 'running') {
          return <Button size="small" danger icon={<StopOutlined />} onClick={() => handleCancel(row.id)}>取消</Button>;
        }
        return null;
      },
    },
  ];

  // ============ Form step renderers ============

  const renderStep0 = () => (
    <div>
      <Form.Item name="account_id" label="选择广告账户" rules={[{ required: true, message: '请选择广告账户' }]}>
        <Select
          showSearch placeholder="搜索并选择广告账户" optionFilterProp="label" loading={loading}
          options={accounts.map(a => ({ value: a.account_id, label: `${a.name || '未命名'} (${a.account_id})` }))}
          style={{ maxWidth: 500 }}
        />
      </Form.Item>
      <Form.Item name="objective" label="广告目标" rules={[{ required: true, message: '请选择广告目标' }]}>
        <Radio.Group onChange={(e) => setSelectedObjective(e.target.value)} value={selectedObjective}>
          <Row gutter={[12, 12]}>
            {AD_OBJECTIVES.map(obj => (
              <Col xs={24} sm={12} md={8} key={obj.key}>
                <Radio.Button value={obj.key} style={{ width: '100%', height: 'auto', padding: '12px 16px', textAlign: 'left', whiteSpace: 'normal', borderRadius: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 20 }}>{obj.icon}</span>
                    <div>
                      <div style={{ fontWeight: 600 }}>{obj.label}</div>
                      <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>{obj.desc}</div>
                    </div>
                  </div>
                </Radio.Button>
              </Col>
            ))}
          </Row>
        </Radio.Group>
      </Form.Item>
    </div>
  );

  const needsBidAmount = ['LOWEST_COST_WITH_BID_CAP', 'COST_CAP'].includes(form.getFieldValue('bid_strategy'));

  const renderStep1 = () => (
    <div>
      <Form.Item name="campaign_name" label="广告系列名称" rules={[{ required: true, message: '请填写广告系列名称' }]}>
        <Input placeholder="输入广告系列名称" style={{ maxWidth: 500 }} />
      </Form.Item>

      <Divider orientation="left" plain>预算设置</Divider>

      {/* Budget level: CBO vs ABO */}
      <Form.Item label={<span>预算层级 <Tooltip title="广告系列预算 (CBO): 由系统自动在广告组间分配预算。广告组预算 (ABO): 每个广告组单独设定预算。"><InfoCircleOutlined style={{ color: '#999' }} /></Tooltip></span>}>
        <Radio.Group value={budgetLevel} onChange={e => setBudgetLevel(e.target.value)}>
          <Radio.Button value="campaign"><FundOutlined /> 广告系列预算 (CBO)</Radio.Button>
          <Radio.Button value="adset"><DollarOutlined /> 广告组预算 (ABO)</Radio.Button>
        </Radio.Group>
      </Form.Item>

      {/* Budget type: daily vs lifetime */}
      <Form.Item label="预算类型">
        <Radio.Group value={budgetType} onChange={e => setBudgetType(e.target.value)}>
          <Radio.Button value="daily">单日预算</Radio.Button>
          <Radio.Button value="lifetime">总预算</Radio.Button>
        </Radio.Group>
      </Form.Item>

      <Form.Item
        name="budget_amount"
        label={budgetType === 'daily' ? '单日预算金额' : '总预算金额'}
        rules={[{ required: true, message: '请填写预算金额' }]}
        extra={budgetLevel === 'campaign' ? '此预算将设置在广告系列级别，由系统自动分配给各广告组' : '此预算将设置在广告组级别'}
      >
        <InputNumber min={1} step={1} placeholder="输入预算金额" style={{ width: 260 }} addonAfter="(账户货币)" />
      </Form.Item>

      <Divider orientation="left" plain>竞价与优化</Divider>

      <Row gutter={16}>
        <Col xs={24} sm={12}>
          <Form.Item name="bid_strategy" label="竞价策略" initialValue="LOWEST_COST_WITHOUT_CAP">
            <Select options={BID_STRATEGIES.map(b => ({ value: b.value, label: b.label }))} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item name="optimization_goal" label="优化目标" initialValue="REACH">
            <Select options={OPTIMIZATION_GOALS.map(g => ({ value: g.value, label: g.label }))} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      {needsBidAmount && (
        <Form.Item name="bid_amount" label="竞价金额" extra="仅在使用竞价上限或费用上限策略时需要填写">
          <InputNumber min={0.01} step={0.1} placeholder="输入竞价金额" style={{ width: 200 }} addonAfter="(账户货币)" />
        </Form.Item>
      )}

      <Form.Item name="billing_event" label="计费事件" initialValue="IMPRESSIONS">
        <Select style={{ width: 200 }} options={[
          { value: 'IMPRESSIONS', label: '展示次数 (CPM)' },
          { value: 'LINK_CLICKS', label: '链接点击 (CPC)' },
          { value: 'APP_INSTALLS', label: '应用安装' },
          { value: 'THRUPLAY', label: 'ThruPlay 视频观看' },
        ]} />
      </Form.Item>

      <Divider orientation="left" plain>排期设置</Divider>
      <Form.Item label="设定排期">
        <Switch checked={budgetScheduleEnabled} onChange={setBudgetScheduleEnabled} checkedChildren="开启" unCheckedChildren="关闭" />
      </Form.Item>
      {budgetScheduleEnabled && (
        <Row gutter={16}>
          <Col span={12}><Form.Item name="start_date" label="开始日期"><DatePicker style={{ width: '100%' }} placeholder="选择开始日期" /></Form.Item></Col>
          <Col span={12}><Form.Item name="start_time" label="开始时间"><TimePicker format="HH:mm" style={{ width: '100%' }} placeholder="00:00" /></Form.Item></Col>
          <Col span={12}><Form.Item name="end_date" label="结束日期"><DatePicker style={{ width: '100%' }} placeholder="选择结束日期" /></Form.Item></Col>
          <Col span={12}><Form.Item name="end_time" label="结束时间"><TimePicker format="HH:mm" style={{ width: '100%' }} placeholder="00:00" /></Form.Item></Col>
        </Row>
      )}
    </div>
  );

  const budgetLevelLabel = budgetLevel === 'campaign' ? '广告系列预算 (CBO)' : '广告组预算 (ABO)';
  const budgetTypeLabel = budgetType === 'daily' ? '单日预算' : '总预算';
  const bidStrategyLabel = (v) => BID_STRATEGIES.find(b => b.value === v)?.label || v;
  const optimizationLabel = (v) => OPTIMIZATION_GOALS.find(g => g.value === v)?.label || v;
  const ctaLabel = (v) => CTA_TYPES.find(c => c.value === v)?.label || v;

  // Upload handler for image/video
  const handleUpload = async (file, type) => {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const headers = {};
      const token = localStorage.getItem('fbhelper_auth_token');
      if (token) headers.Authorization = `Bearer ${token}`;
      const resp = await fetch('/api/upload/creative', { method: 'POST', headers, body: formData });
      const res = await resp.json();
      if (res.success) {
        if (type === 'image') {
          setUploadedImageUrl(res.url);
          form.setFieldValue('image_url', res.url);
        } else {
          setUploadedVideoUrl(res.url);
          form.setFieldValue('video_url', res.url);
        }
        message.success('上传成功');
      } else {
        message.error(res.message || '上传失败');
      }
    } catch (e) {
      message.error('上传出错: ' + e.message);
    }
    return false; // prevent antd default upload
  };

  const renderStep2 = () => (
    <div>
      <Divider orientation="left" plain>Facebook 主页</Divider>
      <Form.Item name="page_id" label="Facebook Page ID" rules={[{ required: true, message: '请填写 Facebook Page ID' }]}
        extra="广告将以此主页的身份发布，可在主页「关于」中找到 Page ID">
        <Input placeholder="例如：123456789012345" style={{ maxWidth: 400 }} />
      </Form.Item>

      <Divider orientation="left" plain>素材类型</Divider>
      <Form.Item label="素材类型">
        <Radio.Group value={creativeType} onChange={e => setCreativeType(e.target.value)}>
          <Radio.Button value="image"><PictureOutlined /> 图片广告</Radio.Button>
          <Radio.Button value="video"><VideoCameraOutlined /> 视频广告</Radio.Button>
        </Radio.Group>
      </Form.Item>

      {creativeType === 'image' && (
        <Form.Item label="广告图片" extra="支持 JPG/PNG/GIF/WebP，最大 30MB。上传后会自动填入链接，也可手动输入 URL。">
          <Upload.Dragger
            accept="image/*"
            maxCount={1}
            fileList={imageFileList}
            beforeUpload={(file) => { handleUpload(file, 'image'); setImageFileList([file]); return false; }}
            onRemove={() => { setImageFileList([]); setUploadedImageUrl(''); form.setFieldValue('image_url', ''); }}
            showUploadList={{ showPreviewIcon: true, showRemoveIcon: true }}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p className="ant-upload-text">点击或拖拽图片到此区域上传</p>
          </Upload.Dragger>
          {uploadedImageUrl && (
            <div style={{ marginTop: 8 }}>
              <img src={uploadedImageUrl} alt="preview" style={{ maxWidth: 200, maxHeight: 150, borderRadius: 4, border: '1px solid #d9d9d9' }} />
            </div>
          )}
          <Form.Item name="image_url" noStyle>
            <Input placeholder="或直接输入图片 URL" style={{ maxWidth: 500, marginTop: 8 }} />
          </Form.Item>
        </Form.Item>
      )}
      {creativeType === 'video' && (
        <Form.Item label="广告视频" extra="支持 MP4/MOV/AVI/WebM，最大 500MB。上传后会自动填入链接，也可手动输入 URL。">
          <Upload
            accept="video/*"
            maxCount={1}
            fileList={videoFileList}
            beforeUpload={(file) => { handleUpload(file, 'video'); setVideoFileList([file]); return false; }}
            onRemove={() => { setVideoFileList([]); setUploadedVideoUrl(''); form.setFieldValue('video_url', ''); }}
          >
            <Button icon={<UploadOutlined />}>选择视频文件</Button>
          </Upload>
          {uploadedVideoUrl && (
            <div style={{ marginTop: 8 }}>
              <Tag color="green">已上传</Tag>
              <Text copyable ellipsis style={{ maxWidth: 400, fontSize: 12 }}>{uploadedVideoUrl}</Text>
            </div>
          )}
          <Form.Item name="video_url" noStyle>
            <Input placeholder="或直接输入视频 URL" style={{ maxWidth: 500, marginTop: 8 }} />
          </Form.Item>
        </Form.Item>
      )}

      <Divider orientation="left" plain>广告文案</Divider>
      <Form.Item name="primary_text" label="正文" rules={[{ required: true, message: '请填写广告正文' }]}>
        <Input.TextArea rows={3} placeholder="广告的主要文案，会显示在素材上方" style={{ maxWidth: 500 }} />
      </Form.Item>
      <Row gutter={16}>
        <Col xs={24} sm={12}>
          <Form.Item name="headline" label="标题">
            <Input placeholder="简短有力的标题" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item name="description" label="描述">
            <Input placeholder="链接下方的描述文字" />
          </Form.Item>
        </Col>
      </Row>

      <Divider orientation="left" plain>落地页与行动号召</Divider>
      <Form.Item name="link_url" label="落地页链接" rules={[{ required: true, message: '请填写落地页链接' }]}>
        <Input placeholder="https://yourwebsite.com/landing-page" style={{ maxWidth: 500 }} />
      </Form.Item>
      <Form.Item name="call_to_action" label="行动号召按钮" initialValue="LEARN_MORE">
        <Select options={CTA_TYPES} style={{ width: 200 }} />
      </Form.Item>
    </div>
  );

  const renderStep3 = () => {
    const values = form.getFieldsValue();
    const account = accounts.find(a => a.account_id === values.account_id);
    return (
      <div>
        <Alert type="info" showIcon message={'请确认以下广告配置信息，确认无误后点击「发布」按钮。'} style={{ marginBottom: 24 }} />
        <Descriptions bordered column={1} size="middle">
          <Descriptions.Item label="广告账户">{account ? `${account.name || '未命名'} (${values.account_id})` : values.account_id}</Descriptions.Item>
          <Descriptions.Item label="广告目标"><Tag color="blue">{objectiveLabel(values.objective)}</Tag></Descriptions.Item>
          <Descriptions.Item label="广告系列名称">{values.campaign_name}</Descriptions.Item>
          <Descriptions.Item label="预算层级"><Tag color={budgetLevel === 'campaign' ? 'purple' : 'cyan'}>{budgetLevelLabel}</Tag></Descriptions.Item>
          <Descriptions.Item label={budgetTypeLabel}>{values.budget_amount}</Descriptions.Item>
          <Descriptions.Item label="竞价策略">{bidStrategyLabel(values.bid_strategy)}</Descriptions.Item>
          <Descriptions.Item label="优化目标">{optimizationLabel(values.optimization_goal)}</Descriptions.Item>
          <Descriptions.Item label="计费事件">{values.billing_event || 'IMPRESSIONS'}</Descriptions.Item>
          {values.bid_amount && <Descriptions.Item label="竞价金额">{values.bid_amount}</Descriptions.Item>}
          {budgetScheduleEnabled && (
            <>
              <Descriptions.Item label="排期">已开启</Descriptions.Item>
              <Descriptions.Item label="开始时间">{values.start_date ? dayjs(values.start_date).format('YYYY-MM-DD') : '-'} {values.start_time ? dayjs(values.start_time).format('HH:mm') : '00:00'}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{values.end_date ? dayjs(values.end_date).format('YYYY-MM-DD') : '-'} {values.end_time ? dayjs(values.end_time).format('HH:mm') : '00:00'}</Descriptions.Item>
            </>
          )}
        </Descriptions>
        <Divider orientation="left" plain style={{ marginTop: 16 }}>广告素材</Divider>
        <Descriptions bordered column={1} size="middle">
          <Descriptions.Item label="Page ID">{values.page_id || '-'}</Descriptions.Item>
          <Descriptions.Item label="素材类型"><Tag color={creativeType === 'video' ? 'purple' : 'blue'}>{creativeType === 'video' ? '视频' : '图片'}</Tag></Descriptions.Item>
          {creativeType === 'image' && values.image_url && <Descriptions.Item label="图片链接"><Text copyable ellipsis style={{ maxWidth: 400 }}>{values.image_url}</Text></Descriptions.Item>}
          {creativeType === 'video' && values.video_url && <Descriptions.Item label="视频链接"><Text copyable ellipsis style={{ maxWidth: 400 }}>{values.video_url}</Text></Descriptions.Item>}
          <Descriptions.Item label="正文">{values.primary_text || '-'}</Descriptions.Item>
          {values.headline && <Descriptions.Item label="标题">{values.headline}</Descriptions.Item>}
          {values.description && <Descriptions.Item label="描述">{values.description}</Descriptions.Item>}
          <Descriptions.Item label="落地页">{values.link_url || '-'}</Descriptions.Item>
          <Descriptions.Item label="行动号召"><Tag>{ctaLabel(values.call_to_action || 'LEARN_MORE')}</Tag></Descriptions.Item>
        </Descriptions>
      </div>
    );
  };

  const formSteps = [
    { title: '选择账户与目标', icon: <AimOutlined /> },
    { title: '广告系列设置', icon: <RocketOutlined /> },
    { title: '广告素材', icon: <FileImageOutlined /> },
    { title: '确认并发布', icon: <CheckCircleOutlined /> },
  ];

  // ============ Render ============

  // If we are tracking progress (after submit), show progress panel + form is hidden
  if (trackingTaskId) {
    return (
      <div>
        {renderProgressPanel()}
        <Card title={<span><HistoryOutlined style={{ marginRight: 8 }} />创建记录</span>} size="small">
          <Table dataSource={tasks} columns={taskColumns} rowKey="id" size="small" loading={tasksLoading}
            pagination={{ current: tasksPage, pageSize: 10, total: tasksTotal, showTotal: (t) => `共 ${t} 条`, onChange: (p) => { setTasksPage(p); loadTasks(p); } }}
          />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <Card title={<span><RocketOutlined style={{ marginRight: 8 }} />创建广告</span>} style={{ marginBottom: 16 }}>
        {!canBrowseData() && <Alert type="warning" showIcon message="请先初始化连接" style={{ marginBottom: 16 }} />}
        {isManagerRole(getAuthUser()?.role) && !hasSpecificTargetUser() && <Alert type="warning" showIcon message="请先在顶部选择具体用户" style={{ marginBottom: 16 }} />}

        <Steps current={current} items={formSteps} style={{ marginBottom: 32 }} />

        <Form form={form} layout="vertical" style={{ maxWidth: 800 }}>
          <div style={{ display: current === 0 ? 'block' : 'none' }}>{renderStep0()}</div>
          <div style={{ display: current === 1 ? 'block' : 'none' }}>{renderStep1()}</div>
          <div style={{ display: current === 2 ? 'block' : 'none' }}>{renderStep2()}</div>
          <div style={{ display: current === 3 ? 'block' : 'none' }}>{renderStep3()}</div>
        </Form>

        <div style={{ marginTop: 24, display: 'flex', gap: 8 }}>
          {current > 0 && <Button onClick={prev}>上一步</Button>}
          {current < formSteps.length - 1 && <Button type="primary" onClick={next}>继续</Button>}
          {current === formSteps.length - 1 && (
            <Button type="primary" icon={<SendOutlined />} loading={submitting} onClick={handleSubmit}>发布</Button>
          )}
        </div>
      </Card>

      <Card title={<span><HistoryOutlined style={{ marginRight: 8 }} />创建记录</span>} size="small">
        <Table dataSource={tasks} columns={taskColumns} rowKey="id" size="small" loading={tasksLoading}
          pagination={{ current: tasksPage, pageSize: 10, total: tasksTotal, showTotal: (t) => `共 ${t} 条`, onChange: (p) => { setTasksPage(p); loadTasks(p); } }}
        />
      </Card>
    </div>
  );
}
