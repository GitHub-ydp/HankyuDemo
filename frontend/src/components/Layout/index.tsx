import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button, Layout, Menu, Popconfirm, Select, Space, Typography, message } from 'antd';
import {
  DashboardOutlined,
  DollarOutlined,
  UploadOutlined,
  SwapOutlined,
  CarOutlined,
  GlobalOutlined,
  MailOutlined,
  RocketOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { adminApi } from '../../services/api';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [resetting, setResetting] = useState(false);

  const handleResetData = async () => {
    setResetting(true);
    try {
      const res = await adminApi.resetRates();
      const d = (res?.data || {}) as {
        rates_deleted?: number;
        carriers_deleted?: number;
        upload_logs_deleted?: number;
      };
      message.success(
        t('admin.resetSuccess', {
          rates: d.rates_deleted ?? 0,
          carriers: d.carriers_deleted ?? 0,
          logs: d.upload_logs_deleted ?? 0,
        })
      );
      setTimeout(() => window.location.reload(), 600);
    } catch (e) {
      message.error(t('admin.resetFailed') + (e instanceof Error ? e.message : String(e)));
    } finally {
      setResetting(false);
    }
  };

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: t('menu.dashboard') },
    { key: '/pkg', icon: <RocketOutlined />, label: t('menu.pkg') },
    { key: '/rates', icon: <DollarOutlined />, label: t('menu.rates') },
    { key: '/upload', icon: <UploadOutlined />, label: t('menu.upload') },
    { key: '/compare', icon: <SwapOutlined />, label: t('menu.compare') },
    { key: '/carriers', icon: <CarOutlined />, label: t('menu.carriers') },
    { key: '/emails', icon: <MailOutlined />, label: t('menu.emailSearch') },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed}>
        <div style={{ height: 32, margin: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography.Text strong style={{ color: '#fff', fontSize: collapsed ? 12 : 14, whiteSpace: 'nowrap' }}>
            {collapsed ? 'HH' : '阪急阪神'}
          </Typography.Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography.Title level={4} style={{ margin: 0 }}>{t('app.title')}</Typography.Title>
          <Space size="middle">
            <Popconfirm
              title={t('admin.resetTitle')}
              description={t('admin.resetDesc')}
              okText={t('admin.resetOk')}
              cancelText={t('common.cancel')}
              okButtonProps={{ danger: true, loading: resetting }}
              onConfirm={handleResetData}
              placement="bottomRight"
            >
              <Button danger icon={<DeleteOutlined />} loading={resetting}>
                {t('admin.resetBtn')}
              </Button>
            </Popconfirm>
            <Select
              value={i18n.language}
              onChange={(lng) => i18n.changeLanguage(lng)}
              style={{ width: 100 }}
              options={[
                { value: 'zh', label: '中文' },
                { value: 'ja', label: '日本語' },
                { value: 'en', label: 'English' },
              ]}
              suffixIcon={<GlobalOutlined />}
            />
          </Space>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
