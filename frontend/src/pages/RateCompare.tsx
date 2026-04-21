import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Col, message, Row, Select, Space, Table, Tag, Typography } from 'antd';
import { SearchOutlined, SwapRightOutlined } from '@ant-design/icons';
import { portApi, rateApi } from '../services/api';
import type { CompareRateItem, CompareResult, Port } from '../types';

export default function RateCompare() {
  const { t } = useTranslation();
  const [ports, setPorts] = useState<Port[]>([]);
  const [originId, setOriginId] = useState<number | undefined>();
  const [destId, setDestId] = useState<number | undefined>();
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    portApi.list({ page_size: 500 }).then((res: any) => setPorts(res.data.items));
  }, []);

  const handleCompare = async () => {
    if (!originId || !destId) {
      message.warning(t('compare.missingPorts'));
      return;
    }

    setLoading(true);
    try {
      const res: any = await rateApi.compare(originId, destId);
      if (res.code !== 0) {
        message.error(res.message);
        return;
      }
      setResult(res.data);
      if (res.data.total === 0) {
        message.info(t('compare.noData'));
      }
    } catch (error: any) {
      message.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  const portOptions = ports.map((port) => ({
    value: port.id,
    label: `${port.un_locode} - ${port.name_en} / ${port.name_cn || ''}`,
    searchText: `${port.un_locode} ${port.name_en} ${port.name_cn || ''} ${port.country || ''}`,
  }));

  const columns = [
    {
      title: t('rates.shippingLine'),
      dataIndex: 'carrier_code',
      width: 120,
      render: (value: string, record: CompareRateItem) => (
        <div>
          <Tag color="blue">{value}</Tag>
          <br />
          <small>{record.carrier_name}</small>
        </div>
      ),
    },
    {
      title: '20GP',
      dataIndex: 'container_20gp',
      width: 90,
      sorter: (a: CompareRateItem, b: CompareRateItem) => Number(a.container_20gp || 0) - Number(b.container_20gp || 0),
      render: (value: string) => (value ? <strong style={{ color: '#1890ff' }}>${Number(value).toFixed(0)}</strong> : '-'),
    },
    {
      title: '40GP',
      dataIndex: 'container_40gp',
      width: 90,
      sorter: (a: CompareRateItem, b: CompareRateItem) => Number(a.container_40gp || 0) - Number(b.container_40gp || 0),
      render: (value: string) => (value ? <strong>${Number(value).toFixed(0)}</strong> : '-'),
    },
    { title: '40HQ', dataIndex: 'container_40hq', width: 90, render: (value: string) => (value ? `$${Number(value).toFixed(0)}` : '-') },
    {
      title: 'BAF(20/40)',
      width: 100,
      render: (_: unknown, record: CompareRateItem) => {
        if (!record.baf_20 && !record.baf_40) {
          return '-';
        }
        return `$${Number(record.baf_20 || 0).toFixed(0)}/$${Number(record.baf_40 || 0).toFixed(0)}`;
      },
    },
    { title: t('rates.effectiveDate'), dataIndex: 'valid_from', width: 110 },
    { title: t('compare.expiryDate'), dataIndex: 'valid_to', width: 110, render: (value: string) => value || '-' },
    {
      title: t('rates.transitDays'),
      dataIndex: 'transit_days',
      width: 90,
      render: (value: number) => (value ? t('common.days', { count: value }) : t('common.notAvailable')),
    },
    {
      title: t('compare.direct'),
      dataIndex: 'is_direct',
      width: 90,
      render: (value: boolean) => (
        value
          ? <Tag color="green">{t('compare.direct')}</Tag>
          : <Tag>{t('compare.transshipment')}</Tag>
      ),
    },
    {
      title: t('rates.source'),
      dataIndex: 'source_type',
      width: 100,
      render: (value: string) => <Tag>{t(`rates.sources.${value}`, value)}</Tag>,
    },
    {
      title: t('rates.status'),
      dataIndex: 'status',
      width: 110,
      render: (value: string) => {
        const label = value === 'active'
          ? t('rates.statusActive')
          : value === 'draft'
            ? t('rates.statusDraft')
            : t('rates.statusExpired');
        return <Tag color={value === 'active' ? 'green' : value === 'draft' ? 'gold' : 'default'}>{label}</Tag>;
      },
    },
  ];

  return (
    <div>
      <Typography.Title level={3}>{t('compare.title')}</Typography.Title>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="1">
            <Select
              showSearch
              placeholder={t('compare.selectOrigin')}
              value={originId}
              onChange={setOriginId}
              options={portOptions}
              filterOption={(input, option) => (option?.searchText?.toLowerCase() ?? '').includes(input.toLowerCase())}
              style={{ width: '100%' }}
              size="large"
            />
          </Col>
          <Col>
            <SwapRightOutlined style={{ fontSize: 24, color: '#1890ff' }} />
          </Col>
          <Col flex="1">
            <Select
              showSearch
              placeholder={t('compare.selectDestination')}
              value={destId}
              onChange={setDestId}
              options={portOptions}
              filterOption={(input, option) => (option?.searchText?.toLowerCase() ?? '').includes(input.toLowerCase())}
              style={{ width: '100%' }}
              size="large"
            />
          </Col>
          <Col>
            <Button type="primary" size="large" icon={<SearchOutlined />} onClick={handleCompare} loading={loading}>
              {t('compare.compareBtn')}
            </Button>
          </Col>
        </Row>
      </Card>

      {result && (
        <Card
          title={(
            <Space>
              <span>{result.origin.name_en} ({result.origin.un_locode})</span>
              <SwapRightOutlined />
              <span>{result.destination.name_en} ({result.destination.un_locode})</span>
              <Tag color="blue">{t('compare.totalQuotes', { count: result.total })}</Tag>
            </Space>
          )}
        >
          <Table<CompareRateItem>
            columns={columns}
            dataSource={result.rates}
            rowKey="rate_id"
            loading={loading}
            size="small"
            scroll={{ x: 1100 }}
            pagination={false}
          />
        </Card>
      )}
    </div>
  );
}
