import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import ReactMarkdown from 'react-markdown';
import Icon from '../Icon';
import { emailApi } from '../../services/emailApi';
import type { EmailItem } from '../../types/email';

interface EmailAnalysisProps {
  analysis: string;
  emails: EmailItem[];
  loading: boolean;
  query: string;
}

function formatDate(value: string) {
  return value ? value.slice(0, 10) : '—';
}

export default function EmailAnalysis({
  analysis,
  emails,
  loading,
  query,
}: EmailAnalysisProps) {
  const { t } = useTranslation();
  const [exporting, setExporting] = useState(false);
  const [showEmails, setShowEmails] = useState(false);

  const handleExportReport = async () => {
    if (!query) return;
    setExporting(true);
    try {
      const result = await emailApi.downloadReport(query);
      message.success(t('email.exportSuccess', { filename: result.filename }));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('email.exportFailed'));
    } finally {
      setExporting(false);
    }
  };

  const copy = async () => {
    await navigator.clipboard.writeText(analysis);
    message.success(t('email.copied'));
  };

  const loadingText = [
    t('email.loadingSteps.searching'),
    t('email.loadingSteps.analyzing'),
    t('email.loadingSteps.generating'),
  ];

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <div>
            <h3>{t('email.analysisResult')}</h3>
            <div style={{ fontSize: 11.5, color: 'var(--ink-500)', marginTop: 2 }}>· {query}</div>
          </div>
          <div className="right" style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={copy} disabled={loading || !analysis}>
              <Icon name="download" size={12} /> {t('email.copy')}
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleExportReport}
              disabled={loading || !analysis || exporting}
            >
              <Icon name="download" size={12} />
              {exporting ? '...' : t('email.exportReport')}
            </button>
          </div>
        </div>
        <div className="card-body">
          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {loadingText.map((txt) => (
                <div key={txt} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--ink-500)' }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--teal-500)', animation: 'blink 1.4s infinite' }} />
                  {txt}
                </div>
              ))}
            </div>
          ) : (
            <div className="md-box">
              <ReactMarkdown>{analysis}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>
            {t('email.relatedEmails')} <span style={{ fontFamily: 'var(--font-en)', color: 'var(--ink-500)' }}>({emails.length})</span>
          </h3>
          <button
            className="btn btn-ghost btn-sm"
            style={{ marginLeft: 'auto' }}
            onClick={() => setShowEmails((v) => !v)}
          >
            <Icon name={showEmails ? 'arrow-up' : 'arrow-down'} size={12} />
          </button>
        </div>
        {showEmails && (
          <div className="table-scroll">
            <table className="rtable" style={{ minWidth: 720 }}>
              <thead>
                <tr>
                  <th style={{ width: 110 }}>{t('email.date')}</th>
                  <th style={{ width: 180 }}>{t('email.from')}</th>
                  <th>{t('email.subject')}</th>
                  <th style={{ width: 100 }} className="c-right">
                    {t('email.relevance')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {emails.map((email) => (
                  <tr key={email.id}>
                    <td className="num" style={{ color: 'var(--ink-500)' }}>{formatDate(email.date)}</td>
                    <td style={{ fontSize: 12.5 }}>{email.from_name || email.from}</td>
                    <td style={{ maxWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {email.subject || '—'}
                    </td>
                    <td className="c-right num" style={{ color: 'var(--ink-500)' }}>
                      {email.score.toFixed(2)}
                    </td>
                  </tr>
                ))}
                {emails.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', padding: 32, color: 'var(--ink-500)' }}>
                      {t('common.noData')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
