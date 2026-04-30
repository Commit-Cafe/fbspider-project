import { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Button, Tag, Table, Descriptions, Empty, Typography, message } from 'antd';
import { SyncOutlined, BankOutlined } from '@ant-design/icons';
import API, { canBrowseData, getAuthUser, hasSpecificTargetUser, getCurrentUserId, isManagerRole, sendCommand } from '../api';

const { Text } = Typography;

export default function BMManagement() {
  const [bmList, setBmList] = useState([]);
  const [selectedBM, setSelectedBM] = useState(null);
  const [bmDetail, setBmDetail] = useState(null);
  const [bmAccounts, setBmAccounts] = useState([]);
  const [bmUsers, setBmUsers] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadBMs = useCallback(async () => {
    if (!canBrowseData()) return;
    setLoading(true);
    const data = await API.get('/api/bms');
    setLoading(false);
    if (data.success) setBmList(data.data);
  }, []);

  useEffect(() => { loadBMs(); }, [loadBMs]);

  // Extension message listener
  useEffect(() => {
    const handler = (event) => {
      if (event.source !== window) return;
      if (event.data.type === 'contentgetBmuserListReply') {
        const resp = event.data.message;
        if (resp?.success) {
          message.success(`BM 列表已获取 (${resp.data?.length || 0} 个)`);
          setTimeout(loadBMs, 2000);
        } else {
          message.error('获取BM失败');
        }
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [loadBMs]);

  const refreshBM = async () => {
    if (isManagerRole(getAuthUser()?.role) && !hasSpecificTargetUser()) {
      message.error('管理员/组长请先选择一个具体用户，再发起 BM 采集。');
      return;
    }
    if (!isManagerRole(getAuthUser()?.role) && !getCurrentUserId()) {
      message.error('请先在 Dashboard 页初始化 Facebook 连接');
      return;
    }
    try {
      const result = await sendCommand('refresh_bm_list');
      if (result?.success) {
        message.info('BM 刷新命令已发送，稍后自动刷新列表');
        setTimeout(loadBMs, 4000);
      }
    } catch (e) {
      message.error(e.message);
    }
  };

  const selectBM = async (bmId) => {
    setSelectedBM(bmId);
    const [bmData, accountsData] = await Promise.all([
      API.get(`/api/bms/${bmId}`),
      API.get(`/api/bms/${bmId}/accounts`),
    ]);
    if (bmData.success) {
      setBmDetail(bmData.data);
      // Parse business_users JSON
      try {
        const parsed = JSON.parse(bmData.data.business_users || '{}');
        setBmUsers(parsed.data || []);
      } catch { setBmUsers([]); }
    }
    if (accountsData.success) setBmAccounts(accountsData.data);
  };

  const accountColumns = [
    { title: '账户ID', dataIndex: 'account_id', key: 'account_id', render: v => <code>{v}</code> },
    { title: '名称', dataIndex: 'name', key: 'name', render: (v, r) => v || (r.is_placeholder ? <Text type="secondary">仅映射记录，暂无账户详情</Text> : '-') },
    { title: '状态', dataIndex: 'account_status', key: 'account_status', render: v => {
      const s = String(v).toUpperCase();
      if (s === 'ACTIVE' || s === '1') return <Tag color="success">Active</Tag>;
      if (s === 'DISABLED' || s === '2') return <Tag color="error">Disabled</Tag>;
      if (s === 'UNKNOWN') return <Tag>Unknown</Tag>;
      return <Tag>{v}</Tag>;
    }},
    { title: '余额', dataIndex: 'balance', key: 'balance' },
    { title: '类型', dataIndex: 'bm_account_type', key: 'bm_account_type' },
  ];

  const userColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '角色', dataIndex: 'role', key: 'role' },
  ];

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h4 style={{ margin: 0 }}><BankOutlined style={{ marginRight: 8 }} />Business Manager 管理</h4>
        <Button type="primary" size="small" icon={<SyncOutlined />} onClick={refreshBM}>从Facebook获取BM列表</Button>
      </div>

      <Row gutter={16}>
        <Col span={8}>
          <Card title="BM 列表" bodyStyle={{ maxHeight: '70vh', overflowY: 'auto', padding: 8 }} loading={loading}>
            {bmList.length === 0 ? (
              <Empty description="暂无BM数据">
                <Button type="primary" size="small" onClick={refreshBM}>从 Facebook 获取</Button>
              </Empty>
            ) : bmList.map(bm => (
              <div
                key={bm.bm_id}
                onClick={() => selectBM(bm.bm_id)}
                style={{
                  cursor: 'pointer', borderRadius: 6, padding: 10, marginBottom: 4,
                  background: selectedBM === bm.bm_id ? '#1677ff' : 'transparent',
                  color: selectedBM === bm.bm_id ? '#fff' : 'inherit',
                  transition: 'all .15s',
                }}
                onMouseEnter={e => { if (selectedBM !== bm.bm_id) e.currentTarget.style.background = '#f5f5f5'; }}
                onMouseLeave={e => { if (selectedBM !== bm.bm_id) e.currentTarget.style.background = 'transparent'; }}
              >
                <div style={{ fontWeight: 600 }}>{bm.name}</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, opacity: 0.7 }}>{bm.bm_id}</span>
                  {bm.is_restricted
                    ? <Tag color="error" style={{ margin: 0 }}>受限</Tag>
                    : <Tag color="success" style={{ margin: 0 }}>正常</Tag>}
                </div>
                <div style={{ fontSize: 12, opacity: 0.7 }}>{bm.account_count || 0} 个广告账户</div>
                {Array.isArray(bm.account_preview) && bm.account_preview.length > 0 && (
                  <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {bm.account_preview.map((account) => (
                      <Tag key={account.account_id} style={{ marginInlineEnd: 0 }}>
                        {account.name ? `${account.name} (${account.account_id})` : account.account_id}
                      </Tag>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </Card>
        </Col>

        <Col span={16}>
          <Card title={bmDetail ? (bmDetail.name || selectedBM) : '选择一个 BM 查看详情'}>
            {!bmDetail ? (
              <Empty description="点击左侧 BM 查看详情和旗下广告账户" />
            ) : (
              <>
                <Row gutter={24}>
                  <Col span={12}>
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label="BM ID"><code>{bmDetail.bm_id}</code></Descriptions.Item>
                      <Descriptions.Item label="类型">{bmDetail.bmtype}</Descriptions.Item>
                      <Descriptions.Item label="状态">{bmDetail.is_restricted ? <Tag color="error">受限</Tag> : <Tag color="success">正常</Tag>}</Descriptions.Item>
                      <Descriptions.Item label="验证状态">{bmDetail.verification_status}</Descriptions.Item>
                    </Descriptions>
                  </Col>
                  <Col span={12}>
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label="创建时间">{bmDetail.created_time}</Descriptions.Item>
                      <Descriptions.Item label="共享资格">{bmDetail.sharing_eligibility_status}</Descriptions.Item>
                      <Descriptions.Item label="可创建广告账户">{bmDetail.can_create_ad_account ? '是' : '否'}</Descriptions.Item>
                    </Descriptions>
                  </Col>
                </Row>

                {bmUsers.length > 0 && (
                  <>
                    <h5 style={{ marginTop: 24 }}>用户/角色</h5>
                    <Table columns={userColumns} dataSource={bmUsers} rowKey="id" size="small" pagination={false} />
                  </>
                )}

                {bmAccounts.length > 0 && (
                  <>
                    <h5 style={{ marginTop: 24 }}>旗下广告账户 ({bmAccounts.length})</h5>
                    <Table columns={accountColumns} dataSource={bmAccounts} rowKey="account_id" size="small" pagination={false} />
                  </>
                )}
              </>
            )}
          </Card>
        </Col>
      </Row>
    </>
  );
}
