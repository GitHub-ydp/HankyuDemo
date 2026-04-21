import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Collapse, Flex, Space, Spin, Table, Typography, message } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import type { ColumnsType } from 'antd/es/table';
import { emailApi } from '../../services/emailApi';
import type { EmailItem } from '../../types/email';

interface EmailAnalysisProps {
  analysis: string;
  emails: EmailItem[];
  loading: boolean;
  query: string;
}

function formatDate(value: string) {
  return value ? value.slice(0, 10) : '-';
}

export default function EmailAnalysis({
  analysis,
  emails,
  loading,
  query,
}: EmailAnalysisProps) {
  const { t } = useTranslation();
  const [exporting, setExporting] = useState(false);

  const handleExportReport = async () => {
    if (!query) return;
    setExporting(true);
    try {
      const result = await emailApi.downloadReport(query);
      message.success(t('email.exportSuccess', { filename: result.filename }));
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : t('email.exportFailed'),
      );
    } finally {
      setExporting(false);
    }
  };

  const columns: ColumnsType<EmailItem> = [
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
      render: (value: number) => value.toFixed(2),
    },
  ];

  const loadingText = [
    t('email.loadingSteps.searching'),
    t('email.loadingSteps.analyzing'),
    t('email.loadingSteps.generating'),
  ];

  return (
    <Flex vertical gap={16}>
      <Card
        title={`${t('email.analysisResult')} · ${query}`}
        extra={(
          <Space>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              loading={exporting}
              disabled={loading || !analysis}
              onClick={handleExportReport}
            >
              {t('email.exportReport')}
            </Button>
            <Button
              onClick={async () => {
                await navigator.clipboard.writeText(analysis);
                message.success(t('email.copied'));
              }}
            >
              {t('email.copy')}
            </Button>
          </Space>
        )}
      >
        {loading ? (
          <Flex vertical gap={8}>
            <Spin />
            {loadingText.map((text) => (
              <Typography.Text key={text} type="secondary">
                {text}
              </Typography.Text>
            ))}
          </Flex>
        ) : (
          <div style={{ background: '#fafafa', padding: 16, borderRadius: 8 }}>
            <ReactMarkdown>{analysis}</ReactMarkdown>
          </div>
        )}
      </Card>

      <Collapse
        items={[
          {
            key: 'emails',
            label: `${t('email.relatedEmails')} (${emails.length})`,
            children: (
              <Table
                rowKey="id"
                dataSource={emails}
                columns={columns}
                pagination={false}
                scroll={{ x: 720 }}
              />
            ),
          },
        ]}
      />
    </Flex>
  );
}
