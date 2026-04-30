import { useState, useEffect, useCallback } from 'react';
import { Card, Table, Button, Tag, Modal, Tabs, message } from 'antd';
import { CodeOutlined, SyncOutlined, EyeOutlined, DeleteOutlined } from '@ant-design/icons';
import API, { canBrowseData, getAuthUser, hasSpecificTargetUser, getCurrentUserId, isManagerRole, sendCommand } from '../api';

export default function PixelManagement() {
  const [pixels, setPixels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalTitle, setModalTitle] = useState('');
  const [detailData, setDetailData] = useState(null);
  const [purchaseData, setPurchaseData] = useState(null);

  const loadPixels = useCallback(async () => {
    if (!canBrowseData()) return;
    setLoading(true);
    const data = await API.get('/api/pixels');
    setLoading(false);
    if (data.success) setPixels(data.data);
  }, []);

  useEffect(() => { loadPixels(); }, [loadPixels]);

  const refreshPixels = async () => {
    if (isManagerRole(getAuthUser()?.role) && !hasSpecificTargetUser()) {
      message.error('管理员/组长请先选择一个具体用户，再发起 Pixel 刷新。');
      return;
    }
    if (!isManagerRole(getAuthUser()?.role) && !getCurrentUserId()) {
      message.error('请先在 Dashboard 页初始化 Facebook 连接');
      return;
    }
    try {
      const result = await sendCommand('refresh_pixels');
      if (result?.success) {
        message.info('Pixel 刷新命令已发送，稍后自动刷新列表');
        setTimeout(loadPixels, 7000);
      }
    } catch (e) {
      message.error(e.message);
    }
  };

  const showDetail = async (pixelId) => {
    const [pixelRes, purchaseRes] = await Promise.all([
      API.get(`/api/pixels/${pixelId}`),
      API.get(`/api/pixels/${pixelId}/purchases`),
    ]);
    if (!pixelRes.success) return;
    setDetailData(pixelRes.data);
    setPurchaseData(purchaseRes.success ? purchaseRes.data : null);
    setModalTitle(`Pixel: ${pixelRes.data.name || pixelId}`);
    setModalOpen(true);
  };

  const columns = [
    { title: 'Pixel ID', dataIndex: 'pixel_id', key: 'pixel_id', render: v => <code>{v}</code> },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '所属 BM', dataIndex: 'owner_bm_id', key: 'owner_bm_id' },
    { title: '状态', dataIndex: 'status', key: 'status' },
    {
      title: '操作', key: 'action', width: 100,
      render: (_, r) => <Button size="small" icon={<EyeOutlined />} onClick={() => showDetail(r.pixel_id)}>详情</Button>,
    },
  ];

  // Association table for modal
  const renderAssocTable = (items, type) => {
    if (!items || items.length === 0) return <span style={{ color: '#999' }}>无数据</span>;
    return (
      <Table
        size="small"
        pagination={false}
        rowKey="assoc_id"
        dataSource={items}
        columns={[
          { title: 'ID', dataIndex: 'assoc_id', key: 'assoc_id', render: v => <code>{v}</code> },
          { title: '名称', dataIndex: 'assoc_name', key: 'assoc_name' },
          {
            title: '操作', key: 'action', width: 60,
            render: (_, r) => (
              <Button size="small" danger icon={<DeleteOutlined />} onClick={() => {
                sendCommand(`remove_pixel_${type}`, { pixel_id: detailData.pixel_id, [`${type}_id`]: r.assoc_id })
                  .then(() => message.success('命令已发送'))
                  .catch(e => message.error(e.message));
              }} />
            ),
          },
        ]}
      />
    );
  };

  const assocs = detailData?.associations || [];
  const users = assocs.filter(a => a.assoc_type === 'user');
  const partners = assocs.filter(a => a.assoc_type === 'partner');
  const adaccounts = assocs.filter(a => a.assoc_type === 'adaccount');

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h4 style={{ margin: 0 }}><CodeOutlined style={{ marginRight: 8 }} />Pixel 管理</h4>
        <Button type="primary" size="small" icon={<SyncOutlined />} onClick={refreshPixels}>刷新Pixel</Button>
      </div>

      <Card bodyStyle={{ padding: 0 }}>
        <Table columns={columns} dataSource={pixels} rowKey="pixel_id" loading={loading} size="small" pagination={false} />
      </Card>

      <Modal title={modalTitle} open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} width={800}>
        <Tabs items={[
          { key: 'users', label: `用户 (${users.length})`, children: renderAssocTable(users, 'user') },
          { key: 'partners', label: `合作伙伴 (${partners.length})`, children: renderAssocTable(partners, 'partner') },
          { key: 'adaccounts', label: `广告账户 (${adaccounts.length})`, children: renderAssocTable(adaccounts, 'adaccount') },
          {
            key: 'purchases', label: '购买事件',
            children: purchaseData
              ? <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, maxHeight: 300, overflow: 'auto', fontSize: 12 }}>{JSON.stringify(purchaseData.event_data, null, 2)}</pre>
              : <span style={{ color: '#999' }}>无购买事件数据</span>,
          },
        ]} />
      </Modal>
    </>
  );
}
