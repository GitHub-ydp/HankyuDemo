import { useEffect, useState } from 'react';
import { Card, Statistic, Table, Tabs, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import { adminActivityApi } from '../services/api';

interface UserRow {
  email: string;
  name: string;
  is_admin: boolean;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
}
interface LoginRow { email: string; ip: string | null; time: string | null }
interface OpRow {
  source: string; operator: string | null; time: string | null;
  file: string | null; file_type: string | null; status: string | null;
  parsed: number | null; imported: number | null;
}

const fmt = (s: string | null) => (s ? new Date(s).toLocaleString() : '-');

export default function ActivityLog() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [summary, setSummary] = useState({ total: 0, active: 0 });
  const [logins, setLogins] = useState<LoginRow[]>([]);
  const [ops, setOps] = useState<OpRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([adminActivityApi.users(), adminActivityApi.loginEvents(), adminActivityApi.operations()])
      .then(([u, l, o]) => {
        // 响应拦截器已解包 {code,data,message}，u/l/o 即完整 ApiResponse
        const ud = (u as { data: { items: UserRow[]; total: number; active: number } }).data;
        const ld = (l as { data: { items: LoginRow[]; total: number } }).data;
        const od = (o as { data: { items: OpRow[]; total: number } }).data;
        setUsers(ud.items);
        setSummary({ total: ud.total, active: ud.active });
        setLogins(ld.items);
        setOps(od.items);
      })
      .catch((e) => message.error(e instanceof Error ? e.message : t('activity.loadError')))
      .finally(() => setLoading(false));
  }, [t]);

  const userCols: ColumnsType<UserRow> = [
    { title: t('activity.col.email'), dataIndex: 'email' },
    { title: t('activity.col.name'), dataIndex: 'name' },
    {
      title: t('activity.col.role'),
      dataIndex: 'is_admin',
      render: (v: boolean) => (v ? <Tag color="gold">{t('activity.admin')}</Tag> : <Tag>{t('activity.user')}</Tag>),
    },
    {
      title: t('activity.col.status'),
      dataIndex: 'is_active',
      render: (v: boolean) => (v ? <Tag color="green">{t('activity.active')}</Tag> : <Tag color="red">{t('activity.disabled')}</Tag>),
    },
    { title: t('activity.col.lastLogin'), dataIndex: 'last_login_at', render: fmt },
    { title: t('activity.col.createdAt'), dataIndex: 'created_at', render: fmt },
  ];

  const loginCols: ColumnsType<LoginRow> = [
    { title: t('activity.col.email'), dataIndex: 'email' },
    { title: t('activity.col.time'), dataIndex: 'time', render: fmt },
    { title: t('activity.col.ip'), dataIndex: 'ip', render: (v: string | null) => v || '-' },
  ];

  const opCols: ColumnsType<OpRow> = [
    { title: t('activity.col.operator'), dataIndex: 'operator', render: (v: string | null) => v || '-' },
    { title: t('activity.col.time'), dataIndex: 'time', render: fmt },
    { title: t('activity.col.source'), dataIndex: 'source' },
    { title: t('activity.col.file'), dataIndex: 'file', render: (v: string | null) => v || '-' },
    { title: t('activity.col.fileType'), dataIndex: 'file_type', render: (v: string | null) => v || '-' },
    { title: t('activity.col.opStatus'), dataIndex: 'status', render: (v: string | null) => v || '-' },
    { title: t('activity.col.imported'), dataIndex: 'imported', render: (v: number | null) => (v ?? '-') },
  ];

  return (
    <Card title={t('activity.title')}>
      <div style={{ display: 'flex', gap: 32, marginBottom: 16 }}>
        <Statistic title={t('activity.totalUsers')} value={summary.total} />
        <Statistic title={t('activity.activeUsers')} value={summary.active} />
      </div>
      <Tabs
        items={[
          {
            key: 'users',
            label: t('activity.tab.users'),
            children: (
              <Table<UserRow>
                rowKey="email"
                loading={loading}
                columns={userCols}
                dataSource={users}
                size="small"
              />
            ),
          },
          {
            key: 'logins',
            label: t('activity.tab.logins'),
            children: (
              <Table<LoginRow>
                rowKey={(r) => `${r.email}-${r.time}`}
                loading={loading}
                columns={loginCols}
                dataSource={logins}
                size="small"
              />
            ),
          },
          {
            key: 'ops',
            label: t('activity.tab.ops'),
            children: (
              <Table<OpRow>
                rowKey={(r) => `${r.source}-${r.time}-${r.file}`}
                loading={loading}
                columns={opCols}
                dataSource={ops}
                size="small"
              />
            ),
          },
        ]}
      />
    </Card>
  );
}
