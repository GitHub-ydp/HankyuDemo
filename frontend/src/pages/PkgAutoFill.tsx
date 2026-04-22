import { Fragment, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../components/Icon';
import { pkgApi } from '../services/api';

interface Lane {
  row: number;
  origin: string;
  destination: string;
  cost_type: string;
  volume_desc: string;
  currency: string;
  unit_price: number | null;
  lead_time: string | null;
  carrier_route: string | null;
  remarks: string | null;
}

interface Section {
  header_row: number;
  origin: string;
  origin_code: string;
  currency: string;
  currency_unit: string;
  lanes: Lane[];
}

interface ParseResult {
  filename: string;
  sheet_name: string;
  period: string;
  total_sections: number;
  total_lanes: number;
  sections: Section[];
}

type FillStatus = 'filled' | 'no_rate' | 'already_filled' | 'skipped';

interface FillResultItem {
  row: number;
  origin: string;
  destination: string;
  cost_type: string;
  status: FillStatus;
  confidence: number;
  unit_price: number | null;
  lead_time: string | null;
  carrier_route: string | null;
  remarks: string | null;
  original_price: number | null;
}

interface FillSummary {
  input_file: string;
  output_file: string;
  total_lanes: number;
  filled_count: number;
  no_rate_count: number;
  already_filled_count: number;
  skipped_count: number;
  results: FillResultItem[];
}

const costTypeLabel = (value: string, t: (key: string) => string) => {
  if (value === 'AIR_FREIGHT') return t('pkg.costTypes.airFreight');
  if (value === 'LOCAL_DELIVERY') return t('pkg.costTypes.localDelivery');
  return value;
};

const currencySymbol = (currency: string) => {
  const symbols: Record<string, string> = { JPY: '¥', CNY: '¥', USD: '$', EUR: '€' };
  return symbols[currency] || currency;
};

function StepBar({ step }: { step: number }) {
  const { t } = useTranslation();
  const steps = [
    { title: t('pkg.stepUpload'), desc: t('pkg.stepUploadDesc') },
    { title: t('pkg.stepReview'), desc: t('pkg.stepReviewDesc') },
    { title: t('pkg.stepDownload'), desc: t('pkg.stepDownloadDesc') },
  ];
  return (
    <div className="steps">
      {steps.map((s, i) => (
        <Fragment key={i}>
          <div className={`step${i === step ? ' active' : ''}${i < step ? ' done' : ''}`}>
            <div className="step-num">{i < step ? <Icon name="check" size={14} /> : i + 1}</div>
            <div className="step-body">
              <div className="step-title">{s.title}</div>
              <div className="step-desc">{s.desc}</div>
            </div>
          </div>
          {i < steps.length - 1 && <div className={`step-line${i < step ? ' done' : ''}`} />}
        </Fragment>
      ))}
    </div>
  );
}

function fillTag(status: FillStatus, confidence: number, t: (k: string) => string) {
  if (status === 'filled') {
    const label =
      confidence >= 0.9
        ? t('pkg.highConfidence')
        : confidence >= 0.7
          ? t('pkg.mediumConfidence')
          : t('pkg.lowConfidence');
    const cls =
      confidence >= 0.9 ? 'tag-success' : confidence >= 0.7 ? 'tag-info' : 'tag-warn';
    return (
      <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
        <span className={`tag zh ${cls}`}>{label}</span>
        <span className="num" style={{ color: 'var(--ink-500)', fontSize: 11.5 }}>
          {Math.round(confidence * 100)}%
        </span>
      </span>
    );
  }
  if (status === 'no_rate') return <span className="tag zh tag-danger">{t('pkg.noMatchedRate')}</span>;
  if (status === 'already_filled') return <span className="tag zh tag-teal">{t('pkg.alreadyFilled')}</span>;
  return <span className="tag zh tag-muted">{t('pkg.skipped')}</span>;
}

export default function PkgAutoFill() {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [filling, setFilling] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [fillSummary, setFillSummary] = useState<FillSummary | null>(null);
  const [openSections, setOpenSections] = useState<Set<number>>(new Set());
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const res = (await pkgApi.upload(file)) as {
        data: { session_id: string; parse_result: ParseResult };
      };
      setSessionId(res.data.session_id);
      setParseResult(res.data.parse_result);
      setOpenSections(new Set(res.data.parse_result.sections.map((_, i) => i)));
      setStep(1);
      message.success(
        t('pkg.parseSuccess', {
          sections: res.data.parse_result.total_sections,
          lanes: res.data.parse_result.total_lanes,
        })
      );
    } catch (error) {
      message.error(
        t('pkg.parseFailed', {
          message: error instanceof Error ? error.message : t('common.unknownError'),
        })
      );
    } finally {
      setUploading(false);
    }
  };

  const handleFill = async () => {
    if (!sessionId) return;
    setFilling(true);
    try {
      const res = (await pkgApi.fill(sessionId)) as { data: FillSummary };
      setFillSummary(res.data);
      setStep(2);
      message.success(
        t('pkg.fillSuccess', {
          filled: res.data.filled_count,
          total: res.data.total_lanes,
        })
      );
    } catch (error) {
      message.error(
        t('pkg.fillFailed', {
          message: error instanceof Error ? error.message : t('common.unknownError'),
        })
      );
    } finally {
      setFilling(false);
    }
  };

  const handleDownload = () => {
    if (sessionId) window.open(pkgApi.downloadUrl(sessionId), '_blank');
  };

  const handleReset = () => {
    setStep(0);
    setSessionId(null);
    setParseResult(null);
    setFillSummary(null);
    setOpenSections(new Set());
  };

  const stats = useMemo(() => {
    if (!fillSummary) return null;
    const fillRate =
      fillSummary.total_lanes > 0
        ? Math.round((fillSummary.filled_count / fillSummary.total_lanes) * 100)
        : 0;
    const filledRows = fillSummary.results.filter((r) => r.status === 'filled');
    const avgConfidence =
      filledRows.length > 0
        ? Math.round(
            (filledRows.reduce((s, r) => s + r.confidence, 0) / filledRows.length) * 100
          )
        : 0;
    return { fillRate, avgConfidence };
  }, [fillSummary]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('pkg.title')}</h1>
        <div className="sub">PKG AUTO FILL</div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <div style={{ fontSize: 13, color: 'var(--ink-700)', lineHeight: 1.65, marginBottom: 8 }}>
            {t('pkg.subtitle')}
          </div>
          <StepBar step={step} />

          {step === 0 && (
            <>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xls"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleUpload(file);
                  e.target.value = '';
                }}
              />
              <div
                className={`dropzone${dragging ? ' drag' : ''}${uploading ? ' disabled' : ''}`}
                onClick={() => !uploading && fileRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file && !uploading) handleUpload(file);
                }}
              >
                <div className="dropzone-icon">
                  <Icon name="import" size={24} />
                </div>
                <div className="dropzone-text">
                  {uploading ? t('pkg.uploading') : t('pkg.uploadDragText')}
                </div>
                <div className="dropzone-hint">{t('pkg.uploadHint')}</div>
              </div>
            </>
          )}

          {step === 1 && parseResult && (
            <>
              <div className="alert alert-success" style={{ marginBottom: 16 }}>
                <div className="alert-icon">
                  <Icon name="check" size={16} />
                </div>
                <div className="alert-body">
                  <div className="alert-title">{t('pkg.parseDone', { filename: parseResult.filename })}</div>
                  <div className="alert-desc">
                    {t('pkg.parseSummary', {
                      period: parseResult.period,
                      sheet: parseResult.sheet_name,
                      sections: parseResult.total_sections,
                      lanes: parseResult.total_lanes,
                    })}
                  </div>
                </div>
              </div>

              {parseResult.sections.map((section, idx) => {
                const open = openSections.has(idx);
                return (
                  <div className="card" key={idx} style={{ marginBottom: 12 }}>
                    <div className="card-head">
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => {
                          setOpenSections((prev) => {
                            const next = new Set(prev);
                            if (next.has(idx)) next.delete(idx);
                            else next.add(idx);
                            return next;
                          });
                        }}
                      >
                        <Icon name={open ? 'arrow-up' : 'arrow-down'} size={12} />
                      </button>
                      <span className="tag tag-teal">{section.origin_code}</span>
                      <h3 style={{ fontSize: 13.5 }}>{section.origin.replace(/\n/g, ' ')}</h3>
                      <span className="sub" style={{ marginLeft: 8 }}>
                        {section.currency_unit}
                      </span>
                      <span className="sub right">{section.lanes.length} LANES</span>
                    </div>
                    {open && (
                      <div className="table-scroll">
                        <table className="rtable" style={{ minWidth: 800 }}>
                          <thead>
                            <tr>
                              <th style={{ width: 50 }}>{t('pkg.row')}</th>
                              <th style={{ width: 160 }}>{t('pkg.origin')}</th>
                              <th>{t('pkg.destination')}</th>
                              <th style={{ width: 130 }}>{t('pkg.type')}</th>
                              <th style={{ width: 80 }}>{t('pkg.currency')}</th>
                              <th style={{ width: 120 }} className="c-right">
                                {t('pkg.currentPrice')}
                              </th>
                              <th style={{ width: 110 }}>{t('pkg.leadTime')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {section.lanes.map((lane) => (
                              <tr key={lane.row}>
                                <td className="num" style={{ color: 'var(--ink-500)' }}>{lane.row}</td>
                                <td style={{ fontSize: 12.5 }}>
                                  {lane.origin?.replace(/\n/g, ' ') || '—'}
                                </td>
                                <td>{lane.destination || '—'}</td>
                                <td>
                                  <span
                                    className={`tag zh ${
                                      lane.cost_type === 'AIR_FREIGHT' ? 'tag-info' : 'tag-teal'
                                    }`}
                                  >
                                    {costTypeLabel(lane.cost_type, t)}
                                  </span>
                                </td>
                                <td>
                                  <span className="tag tag-muted">{lane.currency}</span>
                                </td>
                                <td className="c-right num">
                                  {lane.unit_price !== null && lane.unit_price !== 0 ? (
                                    <b style={{ color: 'var(--ink-900)' }}>
                                      {currencySymbol(lane.currency)}
                                      {lane.unit_price}
                                    </b>
                                  ) : (
                                    <span style={{ color: 'var(--ink-400)' }}>
                                      {t('pkg.waitingFill')}
                                    </span>
                                  )}
                                </td>
                                <td style={{ color: 'var(--ink-500)' }}>
                                  {lane.lead_time || '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}

              <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
                <button className="btn btn-primary" onClick={handleFill} disabled={filling}>
                  <Icon name="sparkles" size={13} />
                  {filling ? t('common.loading') : t('pkg.filledAction')}
                </button>
                <button className="btn btn-secondary" onClick={handleReset}>
                  {t('pkg.reupload')}
                </button>
              </div>
            </>
          )}

          {step === 2 && fillSummary && stats && (
            <>
              <div className="stat-grid">
                <div className="stat-tile">
                  <div className="l">{t('pkg.totalLanes')}</div>
                  <div className="v">{fillSummary.total_lanes.toLocaleString()}</div>
                </div>
                <div className="stat-tile success">
                  <div className="l">{t('pkg.filledCount')}</div>
                  <div className="v">
                    {fillSummary.filled_count.toLocaleString()}
                    <span className="u">/ {fillSummary.total_lanes}</span>
                  </div>
                </div>
                <div className="stat-tile accent">
                  <div className="l">{t('pkg.fillRate')}</div>
                  <div className="v">
                    {stats.fillRate}
                    <span className="u">%</span>
                  </div>
                  <div className="progress-inline">
                    <i style={{ width: `${stats.fillRate}%` }} />
                  </div>
                </div>
                <div className={`stat-tile ${stats.avgConfidence >= 80 ? 'success' : 'danger'}`}>
                  <div className="l">{t('pkg.avgConfidence')}</div>
                  <div className="v">
                    {stats.avgConfidence}
                    <span className="u">%</span>
                  </div>
                </div>
              </div>

              {fillSummary.no_rate_count > 0 && (
                <div className="alert alert-warn" style={{ marginBottom: 16 }}>
                  <div className="alert-icon">
                    <Icon name="alert" size={16} />
                  </div>
                  <div className="alert-body">
                    <div className="alert-title">
                      {t('pkg.noRateWarning', { count: fillSummary.no_rate_count })}
                    </div>
                  </div>
                </div>
              )}

              <div className="card" style={{ marginBottom: 16, padding: 0, overflow: 'hidden' }}>
                <div className="card-head">
                  <h3>{t('pkg.details')}</h3>
                  <span className="sub right">{fillSummary.results.length} ROWS</span>
                </div>
                <div className="table-scroll">
                  <table className="rtable" style={{ minWidth: 1100 }}>
                    <thead>
                      <tr>
                        <th style={{ width: 50 }}>{t('pkg.row')}</th>
                        <th style={{ width: 140 }}>{t('pkg.origin')}</th>
                        <th>{t('pkg.destination')}</th>
                        <th style={{ width: 110 }}>{t('pkg.type')}</th>
                        <th style={{ width: 150 }}>{t('pkg.status')}</th>
                        <th style={{ width: 100 }} className="c-right">
                          {t('pkg.originalValue')}
                        </th>
                        <th style={{ width: 100 }} className="c-right">
                          {t('pkg.filledValue')}
                        </th>
                        <th style={{ width: 110 }}>{t('pkg.leadTime')}</th>
                        <th>{t('pkg.carrierRoute')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fillSummary.results.map((row) => (
                        <tr key={row.row}>
                          <td className="num" style={{ color: 'var(--ink-500)' }}>{row.row}</td>
                          <td style={{ fontSize: 12.5 }}>{row.origin?.replace(/\n/g, ' ') || '—'}</td>
                          <td>{row.destination || '—'}</td>
                          <td>
                            <span
                              className={`tag zh ${
                                row.cost_type === 'AIR_FREIGHT' ? 'tag-info' : 'tag-teal'
                              }`}
                            >
                              {costTypeLabel(row.cost_type, t)}
                            </span>
                          </td>
                          <td>{fillTag(row.status, row.confidence, t)}</td>
                          <td className="c-right num" style={{ color: 'var(--ink-400)', textDecoration: 'line-through' }}>
                            {row.original_price !== null && row.original_price !== 0 ? row.original_price : '—'}
                          </td>
                          <td
                            className="c-right num"
                            style={{
                              color: row.status === 'filled' ? 'var(--success)' : 'var(--ink-400)',
                              fontWeight: row.status === 'filled' ? 600 : 400,
                            }}
                          >
                            {row.status === 'filled' && row.unit_price !== null
                              ? row.unit_price
                              : '—'}
                          </td>
                          <td style={{ color: 'var(--ink-500)' }}>
                            {row.status === 'filled' && row.lead_time ? row.lead_time : '—'}
                          </td>
                          <td
                            style={{
                              fontSize: 12,
                              color: 'var(--ink-700)',
                              maxWidth: 240,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                            title={row.carrier_route || ''}
                          >
                            {row.status === 'filled' && row.carrier_route && row.carrier_route !== '－'
                              ? row.carrier_route
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10 }}>
                <button className="btn btn-primary" onClick={handleDownload}>
                  <Icon name="download" size={13} />
                  {t('pkg.downloadFile')}
                </button>
                <button className="btn btn-secondary" onClick={handleReset}>
                  {t('pkg.newFile')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
