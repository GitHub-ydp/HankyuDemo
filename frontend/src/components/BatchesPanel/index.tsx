import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../Icon';
import { rateBatchApi } from '../../services/api';
import type {
  PaginatedData,
  RateBatchActivateResponse,
  RateBatchDetail,
  RateBatchDiffResponse,
  RateBatchSummary,
} from '../../types';

const PAGE_SIZE = 20;

function statusTag(status: string): string {
  const s = status.toLowerCase();
  if (s === 'draft') return 'tag-warn';
  if (s === 'active' || s === 'activated') return 'tag-success';
  if (s === 'failed' || s === 'rejected') return 'tag-danger';
  return 'tag-muted';
}

function diffStatusTag(status: string): string {
  if (status === 'new') return 'tag-info';
  if (status === 'changed') return 'tag-warn';
  if (status === 'unchanged') return 'tag-success';
  if (status === 'unmatched') return 'tag-muted';
  return 'tag-muted';
}

function formatTimestamp(value: string): string {
  if (!value) return '—';
  return value.replace('T', ' ').slice(0, 19);
}

interface DetailDrawerProps {
  batchId: string;
  onClose: () => void;
  onActivated?: () => void;
}

function DetailDrawer({ batchId, onClose, onActivated }: DetailDrawerProps) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState<RateBatchDetail | null>(null);
  const [diff, setDiff] = useState<RateBatchDiffResponse | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [activate, setActivate] = useState<RateBatchActivateResponse | null>(null);
  const [activating, setActivating] = useState(false);
  const [section, setSection] = useState<'preview' | 'diff'>('preview');

  const fetchDetail = async () => {
    try {
      const res = await rateBatchApi.detail(batchId);
      const envelope = res as { data?: RateBatchDetail };
      if (envelope.data) setDetail(envelope.data);
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('batches.detailFailed'));
    }
  };

  useEffect(() => {
    fetchDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  const runDiff = async () => {
    setDiffLoading(true);
    try {
      const res = await rateBatchApi.diff(batchId);
      const envelope = res as { code?: number; message?: string; data?: RateBatchDiffResponse };
      if (envelope.code !== 0 && envelope.code !== undefined) {
        message.error(envelope.message || t('batches.diffFailed'));
        return;
      }
      if (envelope.data) setDiff(envelope.data);
      setSection('diff');
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('batches.diffFailed'));
    } finally {
      setDiffLoading(false);
    }
  };

  const runActivate = async (dryRun: boolean) => {
    setActivating(true);
    try {
      const res = await rateBatchApi.activate(batchId, { dry_run: dryRun });
      const envelope = res as { code?: number; message?: string; data?: RateBatchActivateResponse };
      if (envelope.code !== 0 && envelope.code !== undefined) {
        message.error(envelope.message || t('batches.activateFailed'));
        return;
      }
      if (envelope.data && !dryRun) {
        const status = envelope.data.activation_status;
        if (status === 'failed') {
          const errDetail =
            envelope.data.errors?.[0]?.detail ||
            envelope.data.message ||
            t('batches.activateFailed');
          message.error(errDetail);
          setActivate(envelope.data);
          return;
        }
        if (status === 'empty_batch') {
          message.warning(envelope.data.message || t('batches.emptyBatchMsg'));
          setActivate(envelope.data);
          return;
        }
        if (status === 'already_active') {
          message.info(envelope.data.message || t('batches.alreadyActiveMsg'));
          setActivate(envelope.data);
          return;
        }
      }
      if (envelope.data) {
        setActivate(envelope.data);
        message.success(envelope.data.message || t('batches.activateOk'));
      }
      if (!dryRun) {
        await fetchDetail();
        onActivated?.();
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('batches.activateFailed'));
    } finally {
      setActivating(false);
    }
  };

  const downloadOriginal = () => {
    window.open(rateBatchApi.downloadUrl(batchId), '_blank');
  };

  const content = (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer" style={{ width: 720 }}>
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4, flexWrap: 'wrap' }}>
              <h2 style={{ fontFamily: 'var(--font-en)', fontSize: 14 }}>{batchId.slice(0, 8)}</h2>
              {detail && (
                <>
                  <span className={`tag zh tag-dot ${statusTag(detail.batch_status)}`}>
                    {detail.batch_status}
                  </span>
                  {detail.adapter_key && (
                    <span className="tag tag-teal">{detail.adapter_key.toUpperCase()}</span>
                  )}
                  {detail.carrier_code && (
                    <span className="tag tag-info">{detail.carrier_code}</span>
                  )}
                </>
              )}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: 'var(--ink-500)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={detail?.file_name}
            >
              {detail?.file_name || '...'}
            </div>
          </div>
          <button className="icon-btn" onClick={onClose}>
            <Icon name="close" size={16} />
          </button>
        </div>

        <div className="drawer-body">
          {!detail ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--ink-500)' }}>
              {t('common.loading')}
            </div>
          ) : (
            <>
              <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <div className="stat-tile">
                  <div className="l">{t('batches.totalRows')}</div>
                  <div className="v">{detail.total_rows.toLocaleString()}</div>
                </div>
                <div className="stat-tile accent">
                  <div className="l">{t('batches.previewCount')}</div>
                  <div className="v">{detail.preview_count}</div>
                </div>
                <div className="stat-tile">
                  <div className="l">{t('batches.sheets')}</div>
                  <div className="v">{detail.sheets.length || '—'}</div>
                </div>
                <div className={`stat-tile ${detail.warnings.length > 0 ? 'warn' : ''}`}>
                  <div className="l">{t('batches.warnings')}</div>
                  <div className="v">{detail.warnings.length}</div>
                </div>
              </div>

              {activate && activate.activated && (
                <div
                  className="stat-grid"
                  style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginTop: -6, marginBottom: 14 }}
                >
                  <div className="stat-tile success">
                    <div className="l">{t('batches.activatedFlag')}</div>
                    <div className="v"><Icon name="check" size={16} /></div>
                  </div>
                  <div className="stat-tile">
                    <div className="l">{t('batches.importedRows')}</div>
                    <div className="v">{activate.imported_rows}</div>
                  </div>
                  <div className="stat-tile">
                    <div className="l">{t('batches.skippedRows')}</div>
                    <div className="v">{activate.skipped_rows}</div>
                  </div>
                </div>
              )}

              {detail.warnings.length > 0 && (
                <div className="alert alert-warn" style={{ marginBottom: 14 }}>
                  <div className="alert-icon">
                    <Icon name="alert" size={16} />
                  </div>
                  <div className="alert-body">
                    <div className="alert-title">
                      {t('batches.warnings')} ({detail.warnings.length})
                    </div>
                    <ul style={{ margin: '6px 0 0', paddingLeft: 20, fontSize: 12, color: 'var(--ink-700)' }}>
                      {detail.warnings.slice(0, 8).map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                      {detail.warnings.length > 8 && (
                        <li>... +{detail.warnings.length - 8}</li>
                      )}
                    </ul>
                  </div>
                </div>
              )}

              <div className="tabs">
                <button
                  type="button"
                  className={`tab${section === 'preview' ? ' on' : ''}`}
                  onClick={() => setSection('preview')}
                >
                  <Icon name="rates" size={13} />
                  {t('batches.tabPreview')} ({detail.preview_rows.length})
                </button>
                <button
                  type="button"
                  className={`tab${section === 'diff' ? ' on' : ''}`}
                  onClick={() => {
                    if (!diff) runDiff();
                    else setSection('diff');
                  }}
                  disabled={diffLoading}
                >
                  <Icon name="compare" size={13} />
                  {diffLoading ? t('batches.diffing') : t('batches.tabDiff')}
                  {diff && (
                    <span style={{ color: 'var(--ink-500)', fontSize: 11 }}>
                      · {diff.summary.total_rows}
                    </span>
                  )}
                </button>
              </div>

              {section === 'preview' && (
                <div className="table-scroll">
                  <table className="rtable" style={{ minWidth: 720, fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th style={{ width: 40 }}>#</th>
                        <th>{t('batches.col.carrier')}</th>
                        <th>{t('batches.col.origin')}</th>
                        <th>{t('batches.col.destination')}</th>
                        <th className="c-right">20&apos;</th>
                        <th className="c-right">40&apos;</th>
                        <th className="c-right">40&apos;HC</th>
                        <th className="c-center">{t('batches.col.transit')}</th>
                        <th>{t('batches.col.valid')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.preview_rows.map((row) => (
                        <tr key={row.row_index}>
                          <td className="num" style={{ color: 'var(--ink-500)' }}>{row.row_index}</td>
                          <td>
                            {row.carrier ? (
                              <span className="tag tag-teal">{row.carrier}</span>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td>{row.origin_port || '—'}</td>
                          <td>{row.destination_port || '—'}</td>
                          <td className="c-right num">{row.container_20gp || '—'}</td>
                          <td className="c-right num">
                            <b>{row.container_40gp || '—'}</b>
                          </td>
                          <td className="c-right num">{row.container_40hq || '—'}</td>
                          <td className="c-center num" style={{ color: 'var(--ink-500)' }}>
                            {row.transit_days ? `${row.transit_days}d` : '—'}
                          </td>
                          <td className="num" style={{ color: 'var(--ink-500)', fontSize: 11 }}>
                            {row.valid_from || '—'}
                            {row.valid_to ? ` → ${row.valid_to}` : ''}
                          </td>
                        </tr>
                      ))}
                      {detail.preview_rows.length === 0 && (
                        <tr>
                          <td colSpan={9} style={{ textAlign: 'center', padding: 24, color: 'var(--ink-500)' }}>
                            {t('common.noData')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                  {detail.preview_truncated && (
                    <div style={{ padding: 10, fontSize: 11.5, color: 'var(--ink-500)', textAlign: 'center' }}>
                      {t('batches.previewTruncated', { total: detail.total_rows, shown: detail.preview_rows.length })}
                    </div>
                  )}
                </div>
              )}

              {section === 'diff' && (
                <>
                  {!diff ? (
                    <div style={{ padding: 24, textAlign: 'center', color: 'var(--ink-500)' }}>
                      {diffLoading ? t('batches.diffing') : t('batches.diffEmpty')}
                    </div>
                  ) : (
                    <>
                      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                        <div className="stat-tile success">
                          <div className="l">{t('batches.diffNew')}</div>
                          <div className="v">{diff.summary.new_rows}</div>
                        </div>
                        <div className="stat-tile warn">
                          <div className="l">{t('batches.diffChanged')}</div>
                          <div className="v">{diff.summary.changed_rows}</div>
                        </div>
                        <div className="stat-tile">
                          <div className="l">{t('batches.diffUnchanged')}</div>
                          <div className="v">{diff.summary.unchanged_rows}</div>
                        </div>
                      </div>
                      <div className="table-scroll">
                        <table className="rtable" style={{ minWidth: 680, fontSize: 12 }}>
                          <thead>
                            <tr>
                              <th style={{ width: 40 }}>#</th>
                              <th style={{ width: 100 }}>{t('batches.col.diffStatus')}</th>
                              <th>{t('batches.col.carrier')}</th>
                              <th>{t('batches.col.origin')}</th>
                              <th>{t('batches.col.destination')}</th>
                              <th>{t('batches.col.changedFields')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {diff.items
                              .filter((item) => item.status !== 'unmatched')
                              .map((item) => (
                                <tr key={item.row_index}>
                                  <td className="num" style={{ color: 'var(--ink-500)' }}>{item.row_index}</td>
                                  <td>
                                    <span className={`tag zh ${diffStatusTag(item.status)}`}>
                                      {t(`batches.diffStatus.${item.status}`, item.status)}
                                    </span>
                                  </td>
                                  <td>{item.preview.carrier || '—'}</td>
                                  <td>{item.preview.origin_port || '—'}</td>
                                  <td>{item.preview.destination_port || '—'}</td>
                                  <td style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>
                                    {item.changed_fields.length > 0 ? item.changed_fields.join(', ') : '—'}
                                  </td>
                                </tr>
                              ))}
                            {diff.items.filter((item) => item.status !== 'unmatched').length === 0 && (
                              <tr>
                                <td colSpan={6} style={{ textAlign: 'center', padding: 24, color: 'var(--ink-500)' }}>
                                  {t('common.noData')}
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </>
              )}

            </>
          )}
        </div>

        <div className="drawer-foot">
          <button className="btn btn-ghost" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            className="btn btn-primary"
            onClick={() => runActivate(false)}
            disabled={activating || !detail}
            title={t('batches.activateRealHint')}
          >
            <Icon name="check" size={13} />
            {t('batches.activateReal')}
          </button>
          <button className="btn btn-secondary" onClick={downloadOriginal} disabled={!detail}>
            <Icon name="download" size={13} />
            {t('batches.download')}
          </button>
        </div>
      </div>
    </>
  );

  return createPortal(content, document.body);
}

interface BatchesPanelProps {
  reloadKey?: number;
  focusBatchId?: string | null;
  onOpenDetail?: (id: string) => void;
}

export default function BatchesPanel({ reloadKey, focusBatchId, onOpenDetail }: BatchesPanelProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<RateBatchSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const fetchList = (next = page) => {
    setLoading(true);
    rateBatchApi
      .list({ page: next, page_size: PAGE_SIZE })
      .then((res) => {
        const data = (res as { data?: PaginatedData<RateBatchSummary> }).data;
        setItems(data?.items || []);
        setTotal(data?.total || 0);
      })
      .catch(() => {
        setItems([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchList(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, reloadKey]);

  useEffect(() => {
    if (!focusBatchId) return;
    if (!items.some((i) => i.batch_id === focusBatchId)) return;
    setSelected(focusBatchId);
    const el = document.querySelector<HTMLTableRowElement>(
      `tr[data-batch-id="${focusBatchId}"]`
    );
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [focusBatchId, items]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageNumbers = useMemo(() => {
    const arr: number[] = [];
    for (let i = 1; i <= Math.min(totalPages, 5); i += 1) arr.push(i);
    return arr;
  }, [totalPages]);

  const openDetail = (id: string) => {
    setSelected(id);
    onOpenDetail?.(id);
  };

  return (
    <>
      <div className="card" style={{ marginBottom: 16, opacity: loading ? 0.7 : 1 }}>
        <div className="card-head">
          <h3>{t('batches.listTitle')}</h3>
          <span className="sub right">DRAFTS</span>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          <div className="table-scroll">
            <table className="rtable" style={{ minWidth: 920 }}>
            <thead>
              <tr>
                <th style={{ width: 100 }}>{t('batches.col.batchId')}</th>
                <th>{t('batches.col.fileName')}</th>
                <th style={{ width: 110 }}>{t('batches.col.parser')}</th>
                <th style={{ width: 90 }}>{t('batches.col.carrier')}</th>
                <th style={{ width: 80 }} className="c-right">{t('batches.col.rows')}</th>
                <th style={{ width: 100 }}>{t('batches.col.status')}</th>
                <th style={{ width: 90 }} className="c-right">{t('batches.col.warnings')}</th>
                <th style={{ width: 160 }}>{t('batches.col.createdAt')}</th>
                <th style={{ width: 80 }} />
              </tr>
            </thead>
            <tbody>
              {items.map((b) => (
                <tr
                  key={b.batch_id}
                  data-batch-id={b.batch_id}
                  onClick={() => openDetail(b.batch_id)}
                  className={selected === b.batch_id ? 'sel' : ''}
                >
                  <td>
                    <span className="num" style={{ fontFamily: 'var(--font-en)' }}>
                      {b.batch_id.slice(0, 8)}
                    </span>
                  </td>
                  <td
                    style={{
                      maxWidth: 0,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={b.file_name}
                  >
                    {b.file_name}
                  </td>
                  <td>
                    {b.source_type === 'excel_ai_fallback' ? (
                      <span className="tag tag-info">AI</span>
                    ) : b.adapter_key ? (
                      <span className="tag tag-teal">{b.adapter_key.toUpperCase()}</span>
                    ) : (
                      <span className="tag tag-muted">—</span>
                    )}
                  </td>
                  <td>
                    {b.carrier_code ? (
                      <span className="tag tag-info">{b.carrier_code}</span>
                    ) : (
                      <span style={{ color: 'var(--ink-400)' }}>—</span>
                    )}
                  </td>
                  <td className="c-right num">{b.total_rows.toLocaleString()}</td>
                  <td>
                    <span className={`tag zh tag-dot ${statusTag(b.batch_status)}`}>
                      {b.batch_status}
                    </span>
                  </td>
                  <td className="c-right num" style={{ color: b.warnings.length > 0 ? 'var(--warn)' : 'var(--ink-400)' }}>
                    {b.warnings.length || '—'}
                  </td>
                  <td className="num" style={{ color: 'var(--ink-500)', fontSize: 11.5 }}>
                    {formatTimestamp(b.created_at)}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => openDetail(b.batch_id)}
                    >
                      <Icon name="eye" size={12} /> {t('batches.openDetail')}
                    </button>
                  </td>
                </tr>
              ))}
              {items.length === 0 && !loading && (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
                    {t('batches.empty')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
          {total > 0 && (
            <div className="pager">
              <div className="pg-total">
                {t('batches.pageSummary', { total, page, totalPages })}
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
      </div>

      {selected && (
        <DetailDrawer
          batchId={selected}
          onClose={() => setSelected(null)}
          onActivated={() => fetchList()}
        />
      )}
    </>
  );
}
