import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, Col, Row, Statistic, Typography } from 'antd';
import {
  BranchesOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  EditOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { rateApi } from '../services/api';
import type { RateStats } from '../types';

export default function Dashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [stats, setStats] = useState<RateStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    rateApi.stats()
      .then((res: any) => setStats(res.data))
      .finally(() => setLoading(false));
  }, []);

  const cards = [
    { title: t('dashboard.totalRates'), value: stats?.total_rates ?? 0, icon: <DatabaseOutlined />, color: '#1890ff' },
    { title: t('dashboard.activeRates'), value: stats?.active_rates ?? 0, icon: <CheckCircleOutlined />, color: '#52c41a' },
    { title: t('dashboard.draftRates'), value: stats?.draft_rates ?? 0, icon: <EditOutlined />, color: '#faad14' },
    { title: t('dashboard.lanes'), value: stats?.routes_count ?? 0, icon: <BranchesOutlined />, color: '#722ed1' },
    { title: t('dashboard.carriers'), value: stats?.carriers_count ?? 0, icon: <TeamOutlined />, color: '#13c2c2' },
  ];

  return (
    <div>
      <Typography.Title level={3}>{t('dashboard.title')}</Typography.Title>
      <Row gutter={[16, 16]}>
        {cards.map((card) => (
          <Col xs={24} sm={12} md={8} lg={4} key={card.title}>
            <Card loading={loading}>
              <Statistic
                title={card.title}
                value={card.value}
                prefix={card.icon}
                valueStyle={{ color: card.color }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col span={24}>
          <Card title={t('dashboard.quickActions')}>
            <Row gutter={16}>
              <Col span={8}>
                <Card hoverable onClick={() => navigate('/upload')}>
                  <Card.Meta
                    title={t('dashboard.uploadRates')}
                    description={t('dashboard.uploadRatesDesc')}
                  />
                </Card>
              </Col>
              <Col span={8}>
                <Card hoverable onClick={() => navigate('/rates')}>
                  <Card.Meta
                    title={t('dashboard.browseRates')}
                    description={t('dashboard.browseRatesDesc')}
                  />
                </Card>
              </Col>
              <Col span={8}>
                <Card hoverable onClick={() => navigate('/compare')}>
                  <Card.Meta
                    title={t('dashboard.compareRates')}
                    description={t('dashboard.compareRatesDesc')}
                  />
                </Card>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
