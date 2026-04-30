import { useState, useEffect } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Layout as AntLayout, Menu, Select, Button, Badge, Typography } from 'antd';
import {
  LineChartOutlined, BankOutlined, CodeOutlined, PictureOutlined,
  RocketOutlined, SettingOutlined, UserSwitchOutlined, LogoutOutlined,
  ControlOutlined, KeyOutlined, PlusCircleOutlined,
} from '@ant-design/icons';
import { useAuth } from '../auth';
import API, {
  getCurrentTargetUserId, setCurrentTargetUserId, setCurrentUserId,
} from '../api';

const { Sider, Content, Header } = AntLayout;
const { Text } = Typography;

const menuItems = [
  { key: '/dashboard', icon: <LineChartOutlined />, label: '广告账户' },
  { key: '/bm', icon: <BankOutlined />, label: 'BM 管理' },
  { key: '/pixels', icon: <CodeOutlined />, label: 'Pixel 管理' },
  { key: '/campaigns', icon: <RocketOutlined />, label: '广告系列' },
  { key: '/create-ad', icon: <PlusCircleOutlined />, label: '创建广告' },
  { key: '/ad-library', icon: <PictureOutlined />, label: '素材库' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
];

const adminMenuItems = [
  { key: '/device-control', icon: <ControlOutlined />, label: '设备控制' },
  { key: '/api-keys', icon: <KeyOutlined />, label: 'API Key' },
  { key: '/users', icon: <UserSwitchOutlined />, label: '用户管理' },
];

function isManagerRole(role) {
  return role === 'admin' || role === 'leader';
}

function roleLabel(role) {
  if (role === 'admin') return '管理员';
  if (role === 'leader') return '组长';
  return '用户';
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const [connStatus, setConnStatus] = useState(null);
  const [userList, setUserList] = useState([]);

  const items = isManagerRole(user?.role) ? [...menuItems, ...adminMenuItems] : menuItems;

  // Check connection
  useEffect(() => {
    const check = async () => {
      try {
        const data = await API.get('/api/connection-state');
        if (data.success) {
          setConnStatus(data.data);
          if (data.data.fb_user_id) setCurrentUserId(data.data.fb_user_id);
        }
      } catch { /* ignore */ }
    };
    check();
    const timer = setInterval(check, 30000);
    return () => clearInterval(timer);
  }, []);

  // Load manageable users for admin/leader
  useEffect(() => {
    if (!isManagerRole(user?.role)) return;
    API.get('/api/auth/users').then(d => {
      if (d.success) setUserList(d.data);
    }).catch(() => {});
  }, [user]);

  const statusColor = connStatus?.has_token ? '#52c41a' : '#faad14';
  const statusText = connStatus?.has_token ? '已连接' : '待初始化';

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider width={240} theme="dark" style={{ position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 100, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: 16 }}>
          <img src="/fbhelper1.png" alt="fbhelper" style={{ width: '100%', borderRadius: 12, background: '#fff', padding: '6px 8px', boxShadow: '0 2px 10px rgba(0,0,0,.18)' }} />
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1 }}
        />
        <div style={{ padding: '12px 16px' }}>
          <Badge color={statusColor} text={<Text style={{ color: 'rgba(255,255,255,.65)', fontSize: 12 }}>{statusText}</Text>} />
          {connStatus && (
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,.45)', marginTop: 4 }}>
              {connStatus.has_token ? `FB: ${connStatus.fb_user_name || connStatus.fb_user_id || '已连接'}` : 'FB Token: 未获取'}
              {' | '}{connStatus.heartbeat_ok ? '插件在线' : '插件离线'}
            </div>
          )}
        </div>
      </Sider>

      <AntLayout style={{ marginLeft: 240 }}>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #f0f0f0', height: 56 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {isManagerRole(user?.role) && (
              <>
                <Text type="secondary" style={{ fontSize: 13 }}>数据视图</Text>
                <Select
                  value={getCurrentTargetUserId()}
                  onChange={(val) => { setCurrentTargetUserId(val); window.location.reload(); }}
                  style={{ width: 200 }}
                  size="small"
                >
                  <Select.Option value="__all__">{user?.role === 'admin' ? '全部用户' : '我的用户'}</Select.Option>
                  {user?.username && <Select.Option value={user.username}>{user.username}</Select.Option>}
                  {userList.filter(u => u.username !== user?.username).map(u => (
                    <Select.Option key={u.username} value={u.username}>{u.username}</Select.Option>
                  ))}
                </Select>
              </>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              {user?.display_name || user?.username} ({roleLabel(user?.role)})
            </Text>
            <Button size="small" icon={<LogoutOutlined />} onClick={logout}>退出</Button>
          </div>
        </Header>
        <Content style={{ padding: 24, background: '#f5f6fa' }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}
