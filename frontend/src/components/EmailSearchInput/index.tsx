import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SearchOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, Input, Space, Tag, Typography } from 'antd';

interface EmailSearchInputProps {
  onSearch: (query: string) => void;
  onAnalyze: (query: string) => void;
  loading: boolean;
  disabled: boolean;
}

export default function EmailSearchInput({
  onSearch,
  onAnalyze,
  loading,
  disabled,
}: EmailSearchInputProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');

  const templates = [
    t('email.templates.timeline'),
    t('email.templates.rateChanges'),
    t('email.templates.projectProgress'),
  ];

  const trigger = (action: 'search' | 'analyze') => {
    const trimmed = query.trim();
    if (!trimmed) return;
    if (action === 'search') {
      onSearch(trimmed);
      return;
    }
    onAnalyze(trimmed);
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Input.TextArea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t('email.searchPlaceholder')}
        autoSize={{ minRows: 4, maxRows: 8 }}
        disabled={disabled}
        onPressEnter={(event) => {
          if (event.shiftKey) return;
          event.preventDefault();
          trigger('search');
        }}
      />

      <Space wrap>
        <Button
          icon={<SearchOutlined />}
          loading={loading}
          disabled={disabled}
          onClick={() => trigger('search')}
        >
          {t('email.searchBtn')}
        </Button>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={loading}
          disabled={disabled}
          onClick={() => trigger('analyze')}
        >
          {t('email.analyzeBtn')}
        </Button>
      </Space>

      <div>
        <Typography.Text strong>{t('email.quickTemplates')}</Typography.Text>
        <Space wrap style={{ display: 'flex', marginTop: 8 }}>
          {templates.map((template) => (
            <Tag
              key={template}
              style={{ cursor: disabled ? 'not-allowed' : 'pointer', padding: '6px 10px' }}
              onClick={() => {
                if (!disabled) setQuery(template);
              }}
            >
              {template}
            </Tag>
          ))}
        </Space>
      </div>
    </Space>
  );
}
