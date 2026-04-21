import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Collapse, DatePicker, Flex, InputNumber, Space, Spin, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { emailApi } from '../../services/emailApi';
import type { EmailItem } from '../../types/email';

interface EmailConnectionProps {
  onIndexComplete: (payload: { count: number; emails: EmailItem[] }) => void;
}

export default function EmailConnection({ onIndexComplete }: EmailConnectionProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [indexCount, setIndexCount] = useState<number | null>(null);
  const [sinceDate, setSinceDate] = useState('2025-01-01');
  const [limit, setLimit] = useState(200);

  const runIndex = async () => {
    setLoading(true);
    try {
      const response = await emailApi.indexFromImap({
        force: true,
        limit,
        since_date: sinceDate,
      });

      setIndexCount(response.count);
      onIndexComplete({ count: response.count, emails: response.emails });
      message.success(t('email.indexSuccess'));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('email.indexFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Collapse
      items={[
        {
          key: 'connection',
          label: t('email.connectionTitle'),
          children: (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Alert
                type={indexCount ? 'success' : 'info'}
                message={
                  indexCount
                    ? t('email.indexed', { count: indexCount })
                    : t('email.notIndexed')
                }
                showIcon
              />

              <Flex gap={16} wrap="wrap" align="end">
                <div>
                  <Typography.Text>{t('email.sinceDate')}</Typography.Text>
                  <DatePicker
                    style={{ display: 'block', width: 220, marginTop: 8 }}
                    value={dayjs(sinceDate)}
                    onChange={(_, dateString) => {
                      if (typeof dateString === 'string' && dateString) {
                        setSinceDate(dateString);
                      }
                    }}
                  />
                </div>

                <div>
                  <Typography.Text>{t('email.emailLimit')}</Typography.Text>
                  <InputNumber
                    min={1}
                    max={1000}
                    value={limit}
                    onChange={(value) => setLimit(value ?? 200)}
                    style={{ display: 'block', width: 160, marginTop: 8 }}
                  />
                </div>
              </Flex>

              <Space wrap>
                <Button type="primary" loading={loading} onClick={runIndex}>
                  {t('email.connectAndIndex')}
                </Button>
              </Space>

              {loading && (
                <Flex align="center" gap={12}>
                  <Spin size="small" />
                  <Typography.Text>{t('email.connecting')}</Typography.Text>
                </Flex>
              )}
            </Space>
          ),
        },
      ]}
    />
  );
}
