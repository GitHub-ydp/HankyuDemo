import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Drawer, Empty, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { EmailItem } from '../../types/email';

interface EmailResultsProps {
  results: EmailItem[];
  loading: boolean;
}

function formatDate(value: string) {
  return value ? value.slice(0, 10) : '-';
}

function scoreColor(score: number) {
  if (score > 0.7) return 'green';
  if (score > 0.5) return 'orange';
  return 'default';
}

export default function EmailResults({ results, loading }: EmailResultsProps) {
  const { t } = useTranslation();
  const [selectedEmail, setSelectedEmail] = useState<EmailItem | null>(null);

  const columns = useMemo<ColumnsType<EmailItem>>(
    () => [
      {
        title: t('email.date'),
        dataIndex: 'date',
        width: 120,
        render: (value: string) => formatDate(value),
      },
      {
        title: t('email.from'),
        dataIndex: 'from_name',
        width: 160,
        render: (_value: string, record) => record.from_name || record.from,
      },
      {
        title: t('email.subject'),
        dataIndex: 'subject',
        ellipsis: true,
      },
      {
        title: t('email.relevance'),
        dataIndex: 'score',
        width: 100,
        render: (value: number) => <Tag color={scoreColor(value)}>{value.toFixed(2)}</Tag>,
      },
      {
        title: t('common.actions'),
        key: 'actions',
        width: 100,
        render: (_value, record) => (
          <Button type="link" onClick={() => setSelectedEmail(record)}>
            {t('email.view')}
          </Button>
        ),
      },
    ],
    [t],
  );

  return (
    <>
      <Card title={t('email.searchResultTitle')}>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={results}
          columns={columns}
          locale={{ emptyText: <Empty description={t('common.noData')} /> }}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 800 }}
        />
      </Card>

      <Drawer
        title={t('email.emailDetail')}
        width={720}
        open={selectedEmail !== null}
        onClose={() => setSelectedEmail(null)}
      >
        {selectedEmail && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Typography.Text strong>{t('email.subject')}: </Typography.Text>
              <Typography.Text>{selectedEmail.subject || '-'}</Typography.Text>
            </div>
            <div>
              <Typography.Text strong>{t('email.from')}: </Typography.Text>
              <Typography.Text>{selectedEmail.from_name || selectedEmail.from}</Typography.Text>
            </div>
            <div>
              <Typography.Text strong>{t('email.to')}: </Typography.Text>
              <Typography.Text>{selectedEmail.to || '-'}</Typography.Text>
            </div>
            <div>
              <Typography.Text strong>{t('email.date')}: </Typography.Text>
              <Typography.Text>{selectedEmail.date || '-'}</Typography.Text>
            </div>
            <div>
              <Typography.Text strong>{t('email.attachment')}: </Typography.Text>
              <Typography.Text>
                {selectedEmail.has_attachment === 'True' ? t('common.yes') : t('common.no')}
              </Typography.Text>
            </div>
            <div>
              <Typography.Title level={5}>{t('email.content')}</Typography.Title>
              <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
                {selectedEmail.content || '-'}
              </Typography.Paragraph>
            </div>
          </Space>
        )}
      </Drawer>
    </>
  );
}
