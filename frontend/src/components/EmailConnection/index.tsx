import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../Icon';
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
  const [expanded, setExpanded] = useState(true);

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

  const badge = indexCount
    ? { className: 'alert alert-success', title: t('email.indexed', { count: indexCount }) }
    : { className: 'alert alert-info', title: t('email.notIndexed') };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>{t('email.connectionTitle')}</h3>
        <span className="sub right">IMAP CONNECTION</span>
        <button
          className="btn btn-ghost btn-sm"
          style={{ marginLeft: 'auto' }}
          onClick={() => setExpanded((v) => !v)}
        >
          <Icon name={expanded ? 'arrow-up' : 'arrow-down'} size={12} />
        </button>
      </div>
      {expanded && (
        <div className="card-body">
          <div className={badge.className} style={{ marginBottom: 14 }}>
            <div className="alert-icon">
              <Icon name={indexCount ? 'check' : 'mail'} size={16} />
            </div>
            <div className="alert-body">
              <div className="alert-title">{badge.title}</div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="field">
              <label>{t('email.sinceDate')}</label>
              <input
                className="input"
                type="date"
                value={sinceDate}
                onChange={(e) => setSinceDate(e.target.value)}
                style={{ minWidth: 180 }}
              />
            </div>
            <div className="field">
              <label>{t('email.emailLimit')}</label>
              <input
                className="input"
                type="number"
                min={1}
                max={1000}
                value={limit}
                onChange={(e) => setLimit(Math.max(1, Math.min(1000, Number(e.target.value) || 200)))}
                style={{ minWidth: 140 }}
              />
            </div>
            <button className="btn btn-primary" onClick={runIndex} disabled={loading}>
              <Icon name="refresh" size={13} />
              {loading ? t('email.connecting') : t('email.connectAndIndex')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
