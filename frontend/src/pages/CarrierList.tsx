import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input, message, Space, Table, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { carrierApi } from '../services/api';
import type { Carrier, PaginatedData } from '../types';

export default function CarrierList() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [data, setData] = useState<PaginatedData<Carrier>>({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
    total_pages: 0,
  });

  const fetchData = async (page = 1) => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: 50 };
      if (keyword) {
        params.keyword = keyword;
      }
      const res = await carrierApi.list(params);
      setData(res.data as PaginatedData<Carrier>);
    } catch {
      message.error(t('carrier.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const typeColors: Record<string, string> = {
    shipping_line: 'cyan',
    co_loader: 'orange',
    agent: 'green',
    nvo: 'purple',
  };

  const columns = [
    { title: t('carrier.id'), dataIndex: 'id', width: 50 },
    { title: t('carrier.code'), dataIndex: 'code', width: 90, render: (value: string) => <Tag color="blue">{value}</Tag> },
    { title: t('carrier.nameEn'), dataIndex: 'name_en', width: 220 },
    { title: t('carrier.nameCn'), dataIndex: 'name_cn', width: 120 },
    {
      title: t('carrier.type'),
      dataIndex: 'carrier_type',
      width: 110,
      render: (value: string) => <Tag color={typeColors[value]}>{t(`carrier.types.${value}`, value)}</Tag>,
    },
    { title: t('carrier.country'), dataIndex: 'country', width: 100 },
    {
      title: t('carrier.status'),
      dataIndex: 'is_active',
      width: 90,
      render: (value: boolean) => (
        <Tag color={value ? 'green' : 'default'}>
          {value ? t('carrier.activeStatus') : t('carrier.inactiveStatus')}
        </Tag>
      ),
    },
  ];

  return (
    <Card title={t('carrier.title')}>
      <Space style={{ marginBottom: 16 }}>
        <Input
          placeholder={t('carrier.searchPlaceholder')}
          prefix={<SearchOutlined />}
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onPressEnter={() => fetchData()}
          style={{ width: 250 }}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => fetchData()}>
          {t('common.search')}
        </Button>
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={data.items}
        loading={loading}
        size="small"
        pagination={{
          current: data.page,
          pageSize: data.page_size,
          total: data.total,
          onChange: (page) => fetchData(page),
          showTotal: (total) => t('common.count', { count: total }),
        }}
      />
    </Card>
  );
}
