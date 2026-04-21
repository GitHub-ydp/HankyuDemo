import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input, message, Select, Space, Table, Tag, Typography } from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { carrierApi, rateApi } from '../services/api';
import type { Carrier, FreightRate, PaginatedData } from '../types';

export default function RateList() {
  const { t } = useTranslation();
  const [data, setData] = useState<FreightRate[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [carriers, setCarriers] = useState<Carrier[]>([]);
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [carrierId, setCarrierId] = useState<number | undefined>();
  const [status, setStatus] = useState<string | undefined>();

  useEffect(() => {
    carrierApi.list({ page_size: 50 }).then((res: any) => setCarriers(res.data.items));
  }, []);

  const fetchRates = (nextPage = page, nextPageSize = pageSize) => {
    setLoading(true);
    const params: Record<string, unknown> = {
      page: nextPage,
      page_size: nextPageSize,
    };
    if (origin) {
      params.origin = origin;
    }
    if (destination) {
      params.destination = destination;
    }
    if (carrierId) {
      params.carrier_id = carrierId;
    }
    if (status) {
      params.status = status;
    }

    rateApi.list(params)
      .then((res: any) => {
        const payload: PaginatedData<FreightRate> = res.data;
        setData(payload.items);
        setTotal(payload.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchRates();
  }, [page, pageSize]);

  const handleSearch = () => {
    setPage(1);
    fetchRates(1, pageSize);
  };

  const handleStatusChange = async (rateId: number, nextStatus: string) => {
    try {
      await rateApi.updateStatus(rateId, nextStatus);
      message.success(t('rates.statusUpdateSuccess'));
      fetchRates();
    } catch {
      message.error(t('rates.statusUpdateFailed'));
    }
  };

  const renderStatus = (value: string) => {
    if (value === 'active') {
      return t('rates.statusActive');
    }
    if (value === 'draft') {
      return t('rates.statusDraft');
    }
    return t('rates.statusExpired');
  };

  const columns = [
    {
      title: t('rates.originPort'),
      width: 130,
      render: (_: unknown, record: FreightRate) => (
        <span>
          {record.origin_port?.name_en}
          <br />
          <small style={{ color: '#999' }}>{record.origin_port?.name_cn}</small>
        </span>
      ),
    },
    {
      title: t('rates.destinationPort'),
      width: 130,
      render: (_: unknown, record: FreightRate) => (
        <span>
          {record.destination_port?.name_en}
          <br />
          <small style={{ color: '#999' }}>{record.destination_port?.name_cn}</small>
        </span>
      ),
    },
    {
      title: t('rates.shippingLine'),
      width: 80,
      render: (_: unknown, record: FreightRate) => <Tag color="blue">{record.carrier?.code}</Tag>,
    },
    { title: '20GP', dataIndex: 'container_20gp', width: 80, render: (value: string) => (value ? `$${Number(value).toFixed(0)}` : '-') },
    { title: '40GP', dataIndex: 'container_40gp', width: 80, render: (value: string) => (value ? `$${Number(value).toFixed(0)}` : '-') },
    { title: '40HQ', dataIndex: 'container_40hq', width: 80, render: (value: string) => (value ? `$${Number(value).toFixed(0)}` : '-') },
    { title: '45ft', dataIndex: 'container_45', width: 70, render: (value: string) => (value ? `$${Number(value).toFixed(0)}` : '-') },
    { title: t('rates.currency'), dataIndex: 'currency', width: 60 },
    { title: t('rates.effectiveDate'), dataIndex: 'valid_from', width: 110 },
    {
      title: t('rates.transitDays'),
      dataIndex: 'transit_days',
      width: 90,
      render: (value: number) => (value ? t('common.days', { count: value }) : t('common.notAvailable')),
    },
    {
      title: t('rates.source'),
      dataIndex: 'source_type',
      width: 100,
      render: (value: string) => {
        const colors: Record<string, string> = {
          excel: 'green',
          pdf: 'blue',
          email_text: 'orange',
          wechat_image: 'purple',
          manual: 'default',
          inbox_email: 'geekblue',
          inbox_attachment: 'magenta',
        };
        return <Tag color={colors[value] || 'default'}>{t(`rates.sources.${value}`, value)}</Tag>;
      },
    },
    {
      title: t('rates.status'),
      dataIndex: 'status',
      width: 100,
      render: (value: string, record: FreightRate) => {
        const colors: Record<string, string> = { active: 'green', draft: 'gold', expired: 'default' };
        return (
          <Tag
            color={colors[value] || 'default'}
            style={{ cursor: 'pointer' }}
            onClick={() => {
              const nextStatus = value === 'draft' ? 'active' : value === 'active' ? 'expired' : 'active';
              handleStatusChange(record.id, nextStatus);
            }}
          >
            {renderStatus(value)}
          </Tag>
        );
      },
    },
    { title: t('rates.remarks'), dataIndex: 'remarks', ellipsis: true, width: 150 },
  ];

  return (
    <div>
      <Typography.Title level={3}>{t('rates.title')}</Typography.Title>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder={t('rates.searchOrigin')}
            value={origin}
            onChange={(event) => setOrigin(event.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 140 }}
            prefix={<SearchOutlined />}
          />
          <Input
            placeholder={t('rates.searchDestination')}
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 140 }}
          />
          <Select
            placeholder={t('rates.searchShippingLine')}
            value={carrierId}
            onChange={setCarrierId}
            allowClear
            style={{ width: 180 }}
            options={carriers.map((carrier) => ({
              value: carrier.id,
              label: `${carrier.code} - ${carrier.name_cn || carrier.name_en}`,
            }))}
          />
          <Select
            placeholder={t('rates.searchStatus')}
            value={status}
            onChange={setStatus}
            allowClear
            style={{ width: 120 }}
            options={[
              { value: 'active', label: t('rates.statusActive') },
              { value: 'draft', label: t('rates.statusDraft') },
              { value: 'expired', label: t('rates.statusExpired') },
            ]}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
            {t('common.search')}
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              setOrigin('');
              setDestination('');
              setCarrierId(undefined);
              setStatus(undefined);
              fetchRates(1);
            }}
          >
            {t('common.reset')}
          </Button>
        </Space>
      </Card>

      <Card>
        <Table<FreightRate>
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          size="small"
          scroll={{ x: 1400 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (value) => t('common.count', { count: value }),
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            },
          }}
        />
      </Card>
    </div>
  );
}
