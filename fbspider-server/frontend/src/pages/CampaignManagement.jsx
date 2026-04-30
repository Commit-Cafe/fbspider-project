import { useState, useEffect, useCallback } from 'react';
import { Card, Table, Button, Tag, Switch, Select, Space, Input, message, Modal, Divider } from 'antd';
import { SyncOutlined, ThunderboltOutlined, PlayCircleOutlined, PauseCircleOutlined, SearchOutlined } from '@ant-design/icons';
import API, {
  canBrowseData, getAuthUser, hasSpecificTargetUser, getCurrentUserId,
  isManagerRole, sendCommand, appendTargetUser,
} from '../api';

const statusColors = {
  ACTIVE: 'green',
  PAUSED: 'orange',
  DELETED: 'red',
  ARCHIVED: 'default',
  DRAFT: 'blue',
};

const effectiveStatusColors = {
  ACTIVE: 'green',
  PAUSED: 'orange',
  DELETED: 'red',
  ARCHIVED: 'default',
  DRAFT: 'blue',
  CAMPAIGN_PAUSED: 'orange',
  ADSET_PAUSED: 'orange',
  PENDING_REVIEW: 'blue',
  DISAPPROVED: 'red',
  IN_PROCESS: 'blue',
  WITH_ISSUES: 'volcano',
};

export default function CampaignManagement() {
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [togglingIds, setTogglingIds] = useState(new Set());
  const [manualCampaignId, setManualCampaignId] = useState('');

  useEffect(() => {
    if (!canBrowseData()) return;
    API.get(appendTargetUser('/api/accounts?page=1&per_page=1000')).then(d => {
      if (d.success) setAccounts(d.data || []);
    }).catch(() => {});
  }, []);

  const loadCampaigns = useCallback(async (acctId) => {
    if (!acctId) return;
    setLoading(true);
    try {
      const d = await API.get(appendTargetUser(`/api/campaigns?account_id=${acctId}`));
      if (d.success) setCampaigns(d.data || []);
    } catch (e) {
      message.error('加载失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleAccountChange = (val) => {
    setSelectedAccount(val);
    loadCampaigns(val);
  };

  const checkAuth = () => {
    const authUser = getAuthUser();
    if (isManagerRole(authUser?.role) && !hasSpecificTargetUser()) {
      message.warning('请先选择具体用户');
      return false;
    }
    return true;
  };

  const fetchFromFB = async () => {
    if (!selectedAccount) { message.warning('请先选择账户'); return; }
    if (!checkAuth()) return;
    setFetching(true);
    try {
      const result = await sendCommand('fetch_campaigns', { account_id: selectedAccount });
      if (result?.success) {
        message.info('获取命令已发送，5秒后刷新...');
        setTimeout(() => {
          loadCampaigns(selectedAccount);
          setFetching(false);
        }, 5000);
      }
    } catch (e) {
      message.error(e.message);
      setFetching(false);
    }
  };

  const fetchByCampaignId = async () => {
    const cid = manualCampaignId.trim();
    if (!cid) { message.warning('请输入广告系列ID'); return; }
    if (!selectedAccount) { message.warning('请先选择账户'); return; }
    if (!checkAuth()) return;
    setFetching(true);
    try {
      const result = await sendCommand('fetch_campaigns', {
        account_id: selectedAccount,
        campaign_id: cid,
      });
      if (result?.success) {
        message.info('查询命令已发送，5秒后刷新...');
        setTimeout(() => {
          loadCampaigns(selectedAccount);
          setFetching(false);
        }, 5000);
      }
    } catch (e) {
      message.error(e.message);
      setFetching(false);
    }
  };

  const toggleCampaign = async (record) => {
    const newStatus = record.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE';
    const actionText = newStatus === 'ACTIVE' ? '开启' : '暂停';

    Modal.confirm({
      title: `${actionText}广告系列？`,
      content: `确定要${actionText} "${record.name}" 吗？`,
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        setTogglingIds(prev => new Set(prev).add(record.campaign_id));
        try {
          const result = await sendCommand('toggle_campaign', {
            campaign_id: record.campaign_id,
            account_id: selectedAccount,
            status: newStatus,
          });
          if (result?.success) {
            message.success(`命令已发送: ${record.name} → ${newStatus}`);
            setTimeout(() => {
              loadCampaigns(selectedAccount);
              setTogglingIds(prev => {
                const next = new Set(prev);
                next.delete(record.campaign_id);
                return next;
              });
            }, 3000);
          }
        } catch (e) {
          message.error(e.message);
          setTogglingIds(prev => {
            const next = new Set(prev);
            next.delete(record.campaign_id);
            return next;
          });
        }
      },
    });
  };

  const columns = [
    {
      title: '广告系列名称', dataIndex: 'name', key: 'name', ellipsis: true,
      render: (v, r) => (
        <span style={{ fontWeight: 500 }}>
          {v}
          {r._source === 'draft' && <Tag color="blue" style={{ marginLeft: 6, fontSize: 10 }}>草稿</Tag>}
        </span>
      ),
    },
    { title: '广告系列ID', dataIndex: 'campaign_id', key: 'campaign_id', width: 180, render: v => <code style={{ fontSize: 12 }}>{v}</code> },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: v => <Tag color={statusColors[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '投放状态', dataIndex: 'effective_status', key: 'effective_status', width: 130,
      render: v => <Tag color={effectiveStatusColors[v] || 'default'}>{v}</Tag>,
    },
    { title: '目标', dataIndex: 'objective', key: 'objective', width: 140, render: v => <span style={{ fontSize: 12 }}>{v}</span> },
    { title: '日预算', dataIndex: 'daily_budget', key: 'daily_budget', width: 100, render: v => v ? (parseFloat(v) / 100).toFixed(2) : '-' },
    { title: '竞价策略', dataIndex: 'bid_strategy', key: 'bid_strategy', width: 160, render: v => <span style={{ fontSize: 11 }}>{v || '-'}</span> },
    { title: '购买类型', dataIndex: 'buying_type', key: 'buying_type', width: 100, render: v => <span style={{ fontSize: 12 }}>{v}</span> },
    {
      title: '开关', key: 'toggle', width: 80, fixed: 'right',
      render: (_, r) => (
        <Switch
          checked={r.status === 'ACTIVE'}
          loading={togglingIds.has(r.campaign_id)}
          onChange={() => toggleCampaign(r)}
          checkedChildren={<PlayCircleOutlined />}
          unCheckedChildren={<PauseCircleOutlined />}
        />
      ),
    },
  ];

  return (
    <>
      <Card bodyStyle={{ padding: '12px 16px' }} style={{ marginBottom: 16 }}>
        <Space wrap>
          <span style={{ fontWeight: 500 }}>选择账户:</span>
          <Select
            showSearch
            placeholder="选择广告账户"
            value={selectedAccount || undefined}
            onChange={handleAccountChange}
            style={{ width: 340 }}
            optionFilterProp="children"
            filterOption={(input, option) =>
              (option?.children || '').toLowerCase().includes(input.toLowerCase())
            }
          >
            {accounts.map(a => (
              <Select.Option key={a.account_id} value={a.account_id}>
                {a.account_id} - {a.name || '未命名'}
              </Select.Option>
            ))}
          </Select>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={fetching}
            disabled={!selectedAccount}
            onClick={fetchFromFB}
          >
            从Facebook获取
          </Button>
          <Button
            icon={<SyncOutlined />}
            disabled={!selectedAccount}
            loading={loading}
            onClick={() => loadCampaigns(selectedAccount)}
          >
            刷新
          </Button>
        </Space>
        <Divider style={{ margin: '10px 0' }} />
        <Space wrap>
          <span style={{ fontSize: 12, color: '#6b7280' }}>手动查询广告系列:</span>
          <Input
            placeholder="输入广告系列ID (campaign_id)"
            value={manualCampaignId}
            onChange={e => setManualCampaignId(e.target.value)}
            style={{ width: 260 }}
            size="small"
            onPressEnter={fetchByCampaignId}
          />
          <Button
            size="small"
            icon={<SearchOutlined />}
            loading={fetching}
            disabled={!selectedAccount}
            onClick={fetchByCampaignId}
          >
            查询
          </Button>
          <span style={{ fontSize: 11, color: '#9ca3af' }}>
            如自动获取为空，可从 Ads Manager 复制广告系列ID手动查询
          </span>
        </Space>
      </Card>

      <Card title={`广告系列${selectedAccount ? ` (${campaigns.length})` : ''}`} size="small">
        <Table
          dataSource={campaigns}
          columns={columns}
          rowKey="campaign_id"
          loading={loading}
          size="small"
          pagination={{ pageSize: 50 }}
          scroll={{ x: 1200 }}
          locale={{ emptyText: selectedAccount ? '暂无广告系列数据。点击"从Facebook获取"拉取，或手动输入广告系列ID查询。' : '请先选择广告账户。' }}
        />
      </Card>
    </>
  );
}
