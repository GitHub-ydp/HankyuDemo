import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../Icon';

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
    if (action === 'search') onSearch(trimmed);
    else onAnalyze(trimmed);
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>{t('email.title')}</h3>
        <span className="sub right">QUERY & ANALYSIS</span>
      </div>
      <div className="card-body">
        <textarea
          className="input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('email.searchPlaceholder')}
          disabled={disabled}
          rows={4}
          style={{ width: '100%', resize: 'vertical', minHeight: 96, lineHeight: 1.6 }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              trigger('search');
            }
          }}
        />

        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={disabled || loading}
            onClick={() => trigger('search')}
          >
            <Icon name="search" size={13} />
            {t('email.searchBtn')}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={disabled || loading}
            onClick={() => trigger('analyze')}
          >
            <Icon name="sparkles" size={13} />
            {t('email.analyzeBtn')}
          </button>
        </div>

        <div style={{ marginTop: 18 }}>
          <div
            style={{
              fontSize: 11.5,
              color: 'var(--ink-500)',
              fontFamily: 'var(--font-en)',
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              marginBottom: 8,
            }}
          >
            {t('email.quickTemplates')}
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {templates.map((template) => (
              <button
                type="button"
                key={template}
                className={`chip-link${disabled ? ' disabled' : ''}`}
                onClick={() => {
                  if (!disabled) setQuery(template);
                }}
                disabled={disabled}
              >
                {template}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
