import { useState, useEffect, useRef, useCallback } from 'react';
import { Card, Row, Col, Table, Input, Button, Alert, Statistic, Space, Tag, Tooltip, message } from 'antd';
import {
  TeamOutlined, CheckCircleOutlined, StopOutlined, DollarOutlined,
  SyncOutlined, DownloadOutlined, SearchOutlined, ApiOutlined, BankOutlined,
} from '@ant-design/icons';
import API, {
  canBrowseData, getCurrentUserId, setCurrentUserId, getAuthUser,
  hasSpecificTargetUser, isManagerRole, sendCommand, appendTargetUser,
} from '../api';

function statusTag(status) {
  const s = String(status).toUpperCase();
  if (s === 'ACTIVE' || s === '1') return <Tag color="success">Active</Tag>;
  if (s === 'DISABLED' || s === '2') return <Tag color="error">Disabled</Tag>;
  if (s.includes('PENDING')) return <Tag color="warning">Pending</Tag>;
  if (s === 'CLOSED' || s === '101') return <Tag color="default">Closed</Tag>;
  return <Tag>{status || 'Unknown'}</Tag>;
}

export default function Dashboard() {
  const [stats, setStats] = useState({ total: '-', active: '-', disabled: '-', balance: '-' });
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState({ field: 'updated_at', order: 'descend' });
  const [statusMsg, setStatusMsg] = useState(null);
  const [tokenReady, setTokenReady] = useState(false);
  const [initBtnText, setInitBtnText] = useState('① 初始化连接');
  const timerRef = useRef();

  const loadStats = useCallback(async () => {
    if (!canBrowseData()) return;
    const res = await API.get('/api/stats');
    if (res.success) {
      setStats({
        total: res.data.total_accounts,
        active: res.data.active_accounts,
        disabled: res.data.disabled_accounts,
        balance: res.data.total_balance_usd,
      });
    }
  }, []);

  const loadAccounts = useCallback(async (p, s, sortInfo) => {
    if (!canBrowseData()) return;
    const pg = p || page;
    const q = s ?? search;
    const si = sortInfo || sort;
    const sortField = si.field || 'updated_at';
    const sortOrder = si.order === 'ascend' ? 'asc' : 'desc';
    setLoading(true);
    const res = await API.get(`/api/accounts?page=${pg}&sort=${sortField}&order=${sortOrder}&search=${encodeURIComponent(q)}`);
    setLoading(false);
    if (res.success) {
      setData(res.data);
      setTotal(res.total);
    }
  }, [page, search, sort]);

  // Hydrate stored connection state
  const hydrateConnection = useCallback(async () => {
    try {
      const resp = await API.get('/api/connection-state');
      if (!resp.success) return;
      const state = resp.data || {};
      if (state.fb_user_id) setCurrentUserId(state.fb_user_id);
      if (state.has_token) {
        setTokenReady(true);
        setInitBtnText(`已连接${state.fb_user_name ? ` ${state.fb_user_name}` : ''}`);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    hydrateConnection();
    loadStats();
    loadAccounts(1);
    timerRef.current = setInterval(() => { loadStats(); }, 30000);
    return () => clearInterval(timerRef.current);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Extension message listener
  useEffect(() => {
    const handler = (event) => {
      if (event.source !== window) return;

      if (event.data.type === 'contentRefreshTokenReply') {
        if (event.data.message) {
          setTokenReady(true);
          const d = event.data.data || {};
          if (d.id) setCurrentUserId(d.id);
          setInitBtnText('已连接');
          setStatusMsg({ type: 'success', text: `Token 获取成功！用户: ${d.name || d.id || 'Unknown'}，可以开始获取数据了。` });
          fetch('/api/receive/token-info', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: getCurrentUserId(), timestamp: new Date().toISOString(), ...d }),
          }).catch(() => {});
        } else {
          setStatusMsg({ type: 'error', text: 'Token 获取失败！请确保你已在 Chrome 中登录了 Facebook。' });
        }
      }

      if (event.data.type === 'contentgetaduserListReply') {
        const resp = event.data.message;
        if (resp?.success) {
          setStatusMsg({ type: 'success', text: `已获取 ${resp.data?.length || 0} 个广告账户！数据正在写入数据库...` });
          setTimeout(() => { loadStats(); loadAccounts(1); setStatusMsg(null); }, 3000);
        } else {
          setStatusMsg({ type: 'error', text: `获取账户失败: ${resp?.data || resp?.error || '未知错误'}` });
        }
      }

      if (event.data.type === 'contentgetBmuserListReply') {
        const resp = event.data.message;
        if (resp?.success) {
          setStatusMsg({ type: 'success', text: `BM 列表已获取！共 ${resp.data?.length || 0} 个 BM。` });
          setTimeout(() => setStatusMsg(null), 3000);
        } else {
          setStatusMsg({ type: 'error', text: `获取BM失败: ${resp?.error || '未知错误'}` });
        }
      }

      if (event.data.type === 'contentgetVersionReply') {
        if (event.data.message) {
          setTokenReady(true);
          setInitBtnText('已连接 v' + event.data.message);
        }
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const initConnection = () => {
    setStatusMsg({ type: 'warning', text: '正在初始化连接，获取 Facebook Token...（需要几秒钟）' });
    window.postMessage({ type: 'callGetVersionMethod' }, '*');
    setTimeout(() => {
      window.postMessage({ type: 'callRefreshTokenMethod', uid: '0' }, '*');
    }, 500);
  };

  const fetchAllAccounts = () => {
    const auth = getAuthUser();
    if (isManagerRole(auth?.role) && !hasSpecificTargetUser()) {
      setStatusMsg({ type: 'warning', text: '管理员请先选择一个具体用户，再发起采集命令。' });
      return;
    }
    if (!getCurrentUserId()) {
      setStatusMsg({ type: 'warning', text: '请先初始化连接获取 Facebook 用户信息' });
      return;
    }
    setStatusMsg({ type: 'info', text: '正在获取所有数据（广告账户 + BM 列表）...这可能需要 30 秒到几分钟。' });
    window.postMessage({ type: 'callGetaduserListMethod' }, '*');
    setTimeout(() => window.postMessage({ type: 'callGetBmuserListMethod' }, '*'), 1000);
  };

  const fetchBMList = () => {
    const auth = getAuthUser();
    if (isManagerRole(auth?.role) && !hasSpecificTargetUser()) {
      setStatusMsg({ type: 'warning', text: '管理员请先选择一个具体用户，再发起采集命令。' });
      return;
    }
    if (!getCurrentUserId()) {
      setStatusMsg({ type: 'warning', text: '请先初始化连接获取 Facebook 用户信息' });
      return;
    }
    setStatusMsg({ type: 'info', text: '正在获取 BM 列表...' });
    window.postMessage({ type: 'callGetBmuserListMethod' }, '*');
  };

  const handleTableChange = (pagination, _filters, sorter) => {
    const newPage = pagination.current;
    const newSort = { field: sorter.field || 'updated_at', order: sorter.order || 'descend' };
    setPage(newPage);
    setSort(newSort);
    loadAccounts(newPage, search, newSort);
  };

  const columns = [
    { title: '系统用户', dataIndex: 'user_id', key: 'user_id', sorter: true, width: 100, render: v => <span style={{ fontSize: 12 }}>{v}</span> },
    { title: '账户ID', dataIndex: 'account_id', key: 'account_id', sorter: true, render: v => <code>{v}</code> },
    { title: '名称', dataIndex: 'name', key: 'name', sorter: true, ellipsis: true },
    { title: '状态', dataIndex: 'account_status', key: 'account_status', sorter: true, render: v => statusTag(v) },
    { title: '余额', dataIndex: 'balance', key: 'balance' },
    { title: '余额(USD)', dataIndex: 'balance_tous', key: 'balance_tous' },
    { title: '花费', dataIndex: 'amount_spent', key: 'amount_spent' },
    { title: '花费(USD)', dataIndex: 'amount_spent_tous', key: 'amount_spent_tous' },
    {
      title: '限额', dataIndex: 'adtrust_dsl_tous', key: 'adtrust_dsl_tous',
      render: (v, r) => <Tooltip title={`本币: ${r.adtrust_dsl || ''}\n门槛: ${r.threshold_amount || ''}`}>{v || r.adtrust_dsl}</Tooltip>,
    },
    {
      title: '临时限额', dataIndex: 'formatted_dsl_tous', key: 'formatted_dsl_tous',
      render: (v, r) => <Tooltip title={r.formatted_dsl || ''}>{v || r.formatted_dsl || ''}</Tooltip>,
    },
    { title: '支付卡', dataIndex: 'paymentcard', key: 'paymentcard', render: v => <span style={{ fontSize: 12 }}>{v}</span> },
    { title: '类型', dataIndex: 'account_type', key: 'account_type', render: v => <span style={{ fontSize: 12 }}>{v}</span> },
    { title: '角色', dataIndex: 'ownership', key: 'ownership', render: v => <span style={{ fontSize: 12 }}>{v}</span> },
    { title: 'BM', dataIndex: 'bm_name', key: 'bm_name', render: (v, r) => <Tooltip title={r.bm_id || ''}><span style={{ fontSize: 12 }}>{v || r.bm_id || ''}</span></Tooltip> },
    {
      title: '操作', key: 'action', width: 60,
      render: (_, r) => (
        <Button size="small" icon={<SyncOutlined />} onClick={() => {
          sendCommand('refresh_account', { account_id: r.account_id }).then(res => {
            if (res?.success) message.success('刷新命令已发送');
          }).catch(e => message.error(e.message));
        }} />
      ),
    },
  ];

  return (
    <>
      {/* Init Banner */}
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          <Space wrap>
            <span><b>使用步骤：</b>① 先在 Chrome 中登录 Facebook → ② 点击「初始化连接」获取 Token → ③ 点击「获取所有账户」拉取数据</span>
            <Button size="small" type="primary" style={{ background: tokenReady ? '#52c41a' : '#faad14', borderColor: tokenReady ? '#52c41a' : '#faad14' }} icon={<ApiOutlined />} onClick={initConnection}>
              {initBtnText}
            </Button>
            <Button size="small" type="primary" icon={<DownloadOutlined />} disabled={!tokenReady} onClick={fetchAllAccounts}>
              ② 获取所有账户
            </Button>
            <Button size="small" icon={<BankOutlined />} onClick={fetchBMList}>获取BM列表</Button>
          </Space>
        }
      />

      {statusMsg && <Alert type={statusMsg.type} message={statusMsg.text} closable onClose={() => setStatusMsg(null)} style={{ marginBottom: 16 }} showIcon />}

      {/* Stats */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="总账户数" value={stats.total} prefix={<TeamOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title="活跃账户" value={stats.active} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title="禁用账户" value={stats.disabled} valueStyle={{ color: '#ff4d4f' }} prefix={<StopOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title="总余额 (USD)" value={stats.balance} valueStyle={{ color: '#1677ff' }} prefix={<DollarOutlined />} /></Card></Col>
      </Row>

      {/* Toolbar */}
      <Card bodyStyle={{ padding: '8px 16px' }} style={{ marginBottom: 16 }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
          <Input.Search
            placeholder="搜索账户ID/名称..."
            allowClear
            style={{ width: 320 }}
            prefix={<SearchOutlined />}
            value={search}
            onChange={e => setSearch(e.target.value)}
            onSearch={(v) => { setPage(1); loadAccounts(1, v); }}
          />
          <Space>
            <Button type="primary" icon={<SyncOutlined />} size="small" onClick={fetchAllAccounts}>刷新全部</Button>
            <Button icon={<DownloadOutlined />} size="small" onClick={() => window.location.href = appendTargetUser('/api/accounts/export')}>导出CSV</Button>
          </Space>
        </Space>
      </Card>

      {/* Table */}
      <Card bodyStyle={{ padding: 0 }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="account_id"
          loading={loading}
          size="small"
          scroll={{ x: 1400 }}
          onChange={handleTableChange}
          pagination={{
            current: page,
            total,
            pageSize,
            showTotal: (t, range) => `显示 ${range[0]}-${range[1]} / 共 ${t} 条`,
            showSizeChanger: false,
          }}
        />
      </Card>
    </>
  );
}
