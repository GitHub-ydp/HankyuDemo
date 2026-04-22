import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import Icon from '../Icon';
import type { EmailItem } from '../../types/email';

interface EmailResultsProps {
  results: EmailItem[];
  loading: boolean;
}

function formatDate(value: string) {
  return value ? value.slice(0, 10) : '—';
}

function scoreClass(score: number) {
  if (score > 0.7) return 'tag-success';
  if (score > 0.5) return 'tag-warn';
  return 'tag-muted';
}

const PAGE_SIZE = 10;

export default function EmailResults({ results, loading }: EmailResultsProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<EmailItem | null>(null);
  const [page, setPage] = useState(1);

  const total = results.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const paged = results.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const pageNumbers: number[] = [];
  for (let i = 1; i <= Math.min(totalPages, 5); i += 1) pageNumbers.push(i);

  return (
    <>
      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 16, opacity: loading ? 0.7 : 1 }}>
        <div className="card-head">
          <h3>{t('email.searchResultTitle')}</h3>
          <span className="sub right">{total} RESULTS</span>
        </div>
        <div className="table-scroll">
          <table className="rtable" style={{ minWidth: 800 }}>
            <thead>
              <tr>
                <th style={{ width: 110 }}>{t('email.date')}</th>
                <th style={{ width: 180 }}>{t('email.from')}</th>
                <th>{t('email.subject')}</th>
                <th style={{ width: 110 }}>{t('email.relevance')}</th>
                <th style={{ width: 100 }}>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((email) => (
                <tr key={email.id}>
                  <td className="num" style={{ color: 'var(--ink-500)' }}>{formatDate(email.date)}</td>
                  <td style={{ fontSize: 12.5 }}>{email.from_name || email.from}</td>
                  <td style={{ maxWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {email.subject || t('common.unknownSubject')}
                  </td>
                  <td>
                    <span className={`tag ${scoreClass(email.score)}`}>{email.score.toFixed(2)}</span>
                  </td>
                  <td>
                    <button className="btn btn-ghost btn-sm" onClick={() => setSelected(email)}>
                      <Icon name="eye" size={12} /> {t('email.view')}
                    </button>
                  </td>
                </tr>
              ))}
              {paged.length === 0 && !loading && (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
                    {t('common.noData')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {total > PAGE_SIZE && (
          <div className="pager">
            <div className="pg-total">
              共 {total} 条 · 第 {page} / {totalPages} 页
            </div>
            <button disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              ‹
            </button>
            {pageNumbers.map((n) => (
              <button key={n} className={page === n ? 'on' : ''} onClick={() => setPage(n)}>
                {n}
              </button>
            ))}
            <button
              disabled={page === totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              ›
            </button>
          </div>
        )}
      </div>

      {selected &&
        createPortal(
          <>
            <div className="drawer-backdrop" onClick={() => setSelected(null)} />
            <div className="drawer">
              <div className="drawer-head">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <h2 style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {selected.subject || t('common.unknownSubject')}
                  </h2>
                  <div style={{ fontSize: 12.5, color: 'var(--ink-500)', marginTop: 4 }}>
                    {selected.from_name || selected.from} · {formatDate(selected.date)}
                  </div>
                </div>
                <button className="icon-btn" onClick={() => setSelected(null)}>
                  <Icon name="close" size={16} />
                </button>
              </div>
              <div className="drawer-body">
                <dl className="kv-grid">
                  <dt>{t('email.subject')}</dt>
                  <dd>{selected.subject || '—'}</dd>
                  <dt>{t('email.from')}</dt>
                  <dd>{selected.from_name || selected.from}</dd>
                  <dt>{t('email.to')}</dt>
                  <dd>{selected.to || '—'}</dd>
                  <dt>{t('email.date')}</dt>
                  <dd className="num">{selected.date || '—'}</dd>
                  <dt>{t('email.attachment')}</dt>
                  <dd>{selected.has_attachment === 'True' ? t('common.yes') : t('common.no')}</dd>
                </dl>

                <div className="rail-title">{t('email.content')}</div>
                <div
                  style={{
                    fontSize: 13,
                    color: 'var(--ink-800)',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.7,
                  }}
                >
                  {selected.content || t('common.emptyContent')}
                </div>
              </div>
            </div>
          </>,
          document.body
        )}
    </>
  );
}
