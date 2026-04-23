import { Fragment, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../components/Icon';
import { biddingApi } from '../services/api';
import type {
  BiddingAutoFillResponse,
  BiddingConfidence,
  BiddingErrorCode,
  FillBlock,
  FillRowBlock,
  IdentifyBlock,
  ParseBlock,
  DownloadTokens,
  UiState,
} from '../types/bidding';

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const SAMPLE_ROW_LIMIT = 5;

const COST_TYPE_LABEL: Record<string, string> = {
  air_freight: 'pkg.costTypes.airFreight',
  local_delivery: 'pkg.costTypes.localDelivery',
};

const CONFIDENCE_CLASS: Record<BiddingConfidence, string> = {
  high: 'tag-success',
  medium: 'tag-info',
  low: 'tag-danger',
};

const ROW_STATUS_CLASS: Record<string, string> = {
  filled: 'tag-success',
  no_rate: 'tag-danger',
  already_filled: 'tag-teal',
  example: 'tag-muted',
  non_local_leg: 'tag-muted',
  local_delivery_manual: 'tag-info',
  constraint_block: 'tag-warn',
  overridden: 'tag-info',
};

function StepBar({ state }: { state: UiState['kind'] }) {
  const { t } = useTranslation();
  const stepIdx =
    state === 'idle' ? 0
    : state === 'uploading' || state === 'processing' ? 1
    : state === 'success' ? 2
    : state === 'rejected' || state === 'error' ? 1
    : 0;
  const steps = [
    t('bidding.stepBar.upload'),
    t('bidding.stepBar.processing'),
    t('bidding.stepBar.done'),
  ];
  return (
    <div className="steps">
      {steps.map((label, i) => (
        <Fragment key={i}>
          <div className={`step${i === stepIdx ? ' active' : ''}${i < stepIdx ? ' done' : ''}`}>
            <div className="step-num">
              {i < stepIdx ? <Icon name="check" size={14} /> : i + 1}
            </div>
            <div className="step-body">
              <div className="step-title">{label}</div>
            </div>
          </div>
          {i < steps.length - 1 && (
            <div className={`step-line${i < stepIdx ? ' done' : ''}`} />
          )}
        </Fragment>
      ))}
    </div>
  );
}

function UploadZone({
  onFile,
  disabled,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept=".xlsx"
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = '';
        }}
      />
      <div
        className={`dropzone${dragging ? ' drag' : ''}${disabled ? ' disabled' : ''}`}
        onClick={() => !disabled && fileRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f && !disabled) onFile(f);
        }}
      >
        <div className="dropzone-icon">
          <Icon name="import" size={24} />
        </div>
        <div className="dropzone-text">{t('bidding.upload.dragText')}</div>
        <div className="dropzone-hint">{t('bidding.upload.hint')}</div>
        <div className="dropzone-hint" style={{ fontSize: 11.5, marginTop: 6, color: 'var(--ink-500)' }}>
          {t('bidding.upload.limitExt')} · {t('bidding.upload.limitSize')}
        </div>
      </div>
    </>
  );
}

function UploadingView({ progress }: { progress: number }) {
  const { t } = useTranslation();
  return (
    <div className="card" style={{ padding: 24 }}>
      <div style={{ fontSize: 14, marginBottom: 10 }}>
        {t('bidding.upload.uploading', { progress })}
      </div>
      <div className="progress-inline" style={{ height: 8 }}>
        <i style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}

function ProcessingView() {
  const { t } = useTranslation();
  return (
    <div className="card" style={{ padding: 24 }}>
      <div style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
        <Icon name="sparkles" size={16} />
        {t('bidding.upload.processing')}
      </div>
    </div>
  );
}

function IdentifyPanel({ identify }: { identify: IdentifyBlock }) {
  const { t } = useTranslation();
  const [showWarnings, setShowWarnings] = useState(false);
  const confCls = CONFIDENCE_CLASS[identify.confidence] ?? 'tag-muted';
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>{t('bidding.identify.title')}</h3>
      </div>
      <div className="card-body">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
          <div>
            <span className="sub" style={{ marginRight: 6 }}>
              {t('bidding.identify.customerLabel')}:
            </span>
            <b style={{ fontSize: 15 }}>{identify.matched_customer}</b>
          </div>
          <div>
            <span className="sub" style={{ marginRight: 6 }}>
              {t('bidding.identify.confidenceLabel')}:
            </span>
            <span className={`tag zh ${confCls}`}>
              {t(`bidding.identify.confidence.${identify.confidence}`)}
            </span>
          </div>
          <div>
            <span className="sub" style={{ marginRight: 6 }}>
              {t('bidding.identify.dimensionsLabel')}:
            </span>
            {identify.matched_dimensions.length > 0 ? (
              identify.matched_dimensions.map((d) => (
                <span key={d} className="tag tag-teal" style={{ marginRight: 4 }}>
                  {d}
                </span>
              ))
            ) : (
              <span className="sub">{t('bidding.identify.noDimensions')}</span>
            )}
          </div>
        </div>
        {identify.warnings.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowWarnings((v) => !v)}
            >
              <Icon name={showWarnings ? 'arrow-up' : 'arrow-down'} size={12} />
              {t('bidding.identify.warningsToggle', { count: identify.warnings.length })}
            </button>
            {showWarnings && (
              <div style={{ marginTop: 8, paddingLeft: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--ink-400, #999)', fontStyle: 'italic', marginBottom: 4 }}>{t('bidding.common.technicalLog')}</div>
                <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--ink-700)', fontSize: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace' }}>
                {identify.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ParsePanel({ parse }: { parse: ParseBlock }) {
  const { t } = useTranslation();
  const [showWarnings, setShowWarnings] = useState(false);
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>{t('bidding.parse.title')}</h3>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 13, color: 'var(--ink-700)', marginBottom: 10 }}>
          {t('bidding.parse.summaryTemplate', {
            period: parse.period || '—',
            sheet: parse.sheet_name,
            sections: parse.section_count,
            rows: parse.row_count,
          })}
        </div>
        {parse.sample_rows.length > 0 && (
          <div className="table-scroll">
            <table className="rtable" style={{ minWidth: 560 }}>
              <thead>
                <tr>
                  <th style={{ width: 60 }}>{t('bidding.parse.colRow')}</th>
                  <th style={{ width: 80 }}>{t('bidding.parse.colSection')}</th>
                  <th>{t('bidding.parse.colDestination')}</th>
                  <th style={{ width: 120 }}>{t('bidding.parse.colCostType')}</th>
                </tr>
              </thead>
              <tbody>
                {parse.sample_rows.slice(0, SAMPLE_ROW_LIMIT).map((r) => (
                  <tr key={r.row_idx}>
                    <td className="num">{r.row_idx}</td>
                    <td><span className="tag tag-teal">{r.section_code}</span></td>
                    <td style={{ whiteSpace: 'pre-wrap', fontSize: 12.5 }}>{r.destination_text}</td>
                    <td>
                      {COST_TYPE_LABEL[r.cost_type] ? (
                        <span className="tag zh tag-info">{t(COST_TYPE_LABEL[r.cost_type])}</span>
                      ) : (
                        <span className="tag tag-muted">{r.cost_type}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {parse.warnings.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowWarnings((v) => !v)}
            >
              <Icon name={showWarnings ? 'arrow-up' : 'arrow-down'} size={12} />
              {t('bidding.parse.warningsToggle', { count: parse.warnings.length })}
            </button>
            {showWarnings && (
              <div style={{ marginTop: 8, paddingLeft: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--ink-400, #999)', fontStyle: 'italic', marginBottom: 4 }}>{t('bidding.common.technicalLog')}</div>
                <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--ink-700)', fontSize: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace' }}>
                {parse.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FillPanel({ fill }: { fill: FillBlock }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [showWarnings, setShowWarnings] = useState(false);

  const filledRows = useMemo(
    () => fill.rows.filter((r) => r.status === 'filled'),
    [fill.rows],
  );
  const visibleRows = expanded ? fill.rows : filledRows;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>{t('bidding.fill.title')}</h3>
      </div>
      <div className="card-body">
        <div className="stat-grid" style={{ marginBottom: 12 }}>
          <div className="stat-tile success">
            <div className="l">{t('bidding.fill.filled')}</div>
            <div className="v">{fill.filled_count}</div>
          </div>
          <div className="stat-tile danger">
            <div className="l">{t('bidding.fill.noRate')}</div>
            <div className="v">{fill.no_rate_count}</div>
          </div>
          <div className="stat-tile">
            <div className="l">{t('bidding.fill.skipped')}</div>
            <div className="v">{fill.skipped_count}</div>
          </div>
        </div>

        <div style={{ fontSize: 12, color: 'var(--ink-500)', marginBottom: 12 }}>
          {t('bidding.fill.markupHintTemplate', { ratio: fill.markup_ratio })}
        </div>

        {fill.global_warnings.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowWarnings((v) => !v)}
            >
              <Icon name={showWarnings ? 'arrow-up' : 'arrow-down'} size={12} />
              {t('bidding.fill.warningsToggle', { count: fill.global_warnings.length })}
            </button>
            {showWarnings && (
              <div style={{ marginTop: 8, paddingLeft: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--ink-400, #999)', fontStyle: 'italic', marginBottom: 4 }}>{t('bidding.common.technicalLog')}</div>
                <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--ink-700)', fontSize: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace' }}>
                {fill.global_warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
              </div>
            )}
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <h4 style={{ fontSize: 13, margin: 0 }}>{t('bidding.fill.rowsTableTitle')}</h4>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded
              ? t('bidding.fill.rowsCollapseBtn')
              : t('bidding.fill.rowsShowAllBtn', { count: fill.rows.length })}
          </button>
          {!expanded && (
            <span className="sub" style={{ fontSize: 11.5 }}>
              {t('bidding.fill.filterFilledOnly')} · {filledRows.length} / {fill.rows.length}
            </span>
          )}
        </div>

        <div className="table-scroll">
          <table className="rtable" style={{ minWidth: 900 }}>
            <thead>
              <tr>
                <th style={{ width: 50 }}>{t('bidding.fill.colRow')}</th>
                <th style={{ width: 70 }}>{t('bidding.fill.colSection')}</th>
                <th style={{ width: 100 }}>{t('bidding.fill.colDest')}</th>
                <th style={{ width: 140 }}>{t('bidding.fill.colStatus')}</th>
                <th style={{ width: 90 }} className="c-right">{t('bidding.fill.colCost')}</th>
                <th style={{ width: 90 }} className="c-right">{t('bidding.fill.colSell')}</th>
                <th>{t('bidding.fill.colBatch')}</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r) => (
                <FillRow key={r.row_idx} row={r} />
              ))}
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', color: 'var(--ink-400)', padding: 16 }}>
                    —
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function FillRow({ row }: { row: FillRowBlock }) {
  const { t } = useTranslation();
  const statusKey = `bidding.fill.rowStatus.${row.status}`;
  const statusLabel = t(statusKey, { defaultValue: row.status });
  const cls = ROW_STATUS_CLASS[row.status] ?? 'tag-muted';
  return (
    <tr>
      <td className="num" style={{ color: 'var(--ink-500)' }}>{row.row_idx}</td>
      <td><span className="tag tag-teal">{row.section_code}</span></td>
      <td>{row.destination_code}</td>
      <td><span className={`tag zh ${cls}`}>{statusLabel}</span></td>
      <td className="c-right num">
        {row.cost_price ?? <span style={{ color: 'var(--ink-400)' }}>—</span>}
      </td>
      <td className="c-right num">
        {row.sell_price ?? <span style={{ color: 'var(--ink-400)' }}>—</span>}
      </td>
      <td style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>
        {row.source_batch_id || '—'}
      </td>
    </tr>
  );
}

function DownloadPanel({
  download,
  onReset,
  onDownloaded,
}: {
  download: DownloadTokens;
  onReset: () => void;
  onDownloaded: (kind: 'cost' | 'sr') => void;
}) {
  const { t } = useTranslation();
  const trigger = (kind: 'cost' | 'sr') => {
    const token = kind === 'cost' ? download.cost_token : download.sr_token;
    const filename = kind === 'cost' ? download.cost_filename : download.sr_filename;
    window.open(biddingApi.downloadUrl(token), '_blank');
    onDownloaded(kind);
    message.success(t('bidding.download.downloadStarted', { filename }));
  };
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h3>{t('bidding.download.title')}</h3>
      </div>
      <div className="card-body">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
          <button className="btn btn-primary" onClick={() => trigger('cost')}>
            <Icon name="download" size={13} />
            {t('bidding.download.costBtn')}
          </button>
          <button className="btn btn-secondary" onClick={() => trigger('sr')}>
            <Icon name="download" size={13} />
            {t('bidding.download.srBtn')}
          </button>
          <button className="btn btn-ghost" onClick={onReset}>
            {t('bidding.download.resetBtn')}
          </button>
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>
          {t('bidding.download.expiresHint')}
        </div>
      </div>
    </div>
  );
}

function RejectedPanel({
  identify,
  onReset,
}: {
  identify: IdentifyBlock;
  onReset: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="alert alert-warn" style={{ marginBottom: 16 }}>
      <div className="alert-icon">
        <Icon name="alert" size={16} />
      </div>
      <div className="alert-body">
        <div className="alert-title">{t('bidding.identify.rejected.title')}</div>
        {identify.unmatched_reason && (
          <div className="alert-desc" style={{ marginTop: 6 }}>
            <span className="sub">{t('bidding.identify.rejected.reasonLabel')}:</span>
            <div style={{ marginTop: 4 }}>
              <div style={{ fontSize: 11, color: 'var(--ink-400, #999)', fontStyle: 'italic', marginBottom: 4 }}>{t('bidding.common.technicalLog')}</div>
              <div style={{ fontSize: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', color: 'var(--ink-700)', background: 'var(--bg-subtle, #f5f5f5)', padding: 8, borderRadius: 4, wordBreak: 'break-word' }}>
                {identify.unmatched_reason}
              </div>
            </div>
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-secondary" onClick={onReset}>
            {t('bidding.identify.rejected.backBtn')}
          </button>
        </div>
      </div>
    </div>
  );
}

function ErrorPanel({
  code,
  detail,
  onReset,
}: {
  code: BiddingErrorCode;
  detail?: string;
  onReset: () => void;
}) {
  const { t } = useTranslation();
  const [showDetail, setShowDetail] = useState(false);
  const messageKey = `bidding.errors.${code.toLowerCase()}`;
  return (
    <div className="alert alert-danger" style={{ marginBottom: 16 }}>
      <div className="alert-icon">
        <Icon name="alert" size={16} />
      </div>
      <div className="alert-body">
        <div className="alert-title">{t(messageKey, { defaultValue: code })}</div>
        {detail && (
          <div style={{ marginTop: 8 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowDetail((v) => !v)}
            >
              <Icon name={showDetail ? 'arrow-up' : 'arrow-down'} size={12} />
              {t('bidding.errors.detailLabel')}
            </button>
            {showDetail && (
              <pre style={{ marginTop: 6, fontSize: 11, background: 'var(--ink-50)', padding: 8, borderRadius: 4, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {detail}
              </pre>
            )}
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-secondary" onClick={onReset}>
            {t('bidding.errors.retryBtn')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PkgAutoFill() {
  const { t } = useTranslation();
  const [ui, setUi] = useState<UiState>({ kind: 'idle' });

  const reset = () => setUi({ kind: 'idle' });

  const handleFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setUi({ kind: 'error', resp: null, code: 'F7_WRONG_EXTENSION', detail: file.name });
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setUi({
        kind: 'error',
        resp: null,
        code: 'F6_FILE_TOO_LARGE',
        detail: `${file.size} bytes`,
      });
      return;
    }

    setUi({ kind: 'uploading', progress: 0 });
    try {
      const resp: BiddingAutoFillResponse = await biddingApi.autoFill(file, (p) => {
        setUi({ kind: 'uploading', progress: p });
        if (p >= 100) {
          setUi({ kind: 'processing' });
        }
      });
      if (resp.ok) {
        setUi({ kind: 'success', resp });
        return;
      }
      if (resp.error?.code === 'F2_UNSUPPORTED_CUSTOMER') {
        setUi({ kind: 'rejected', resp });
        return;
      }
      const code = (resp.error?.code ?? 'F8_NETWORK_ERROR') as BiddingErrorCode;
      setUi({ kind: 'error', resp, code, detail: resp.error?.detail });
    } catch (e) {
      const err = e as Error;
      // 尝试用 HTTP 状态/错误消息区分 F6/F7；interceptor 把 detail 塞进 message
      const msg = err.message || '';
      let code: BiddingErrorCode = 'F8_NETWORK_ERROR';
      if (msg.includes('F6_FILE_TOO_LARGE')) code = 'F6_FILE_TOO_LARGE';
      else if (msg.includes('F7_WRONG_EXTENSION')) code = 'F7_WRONG_EXTENSION';
      setUi({ kind: 'error', resp: null, code, detail: msg });
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('bidding.title')}</h1>
        <div className="sub">BIDDING AUTO FILL · v0.1</div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <div style={{ fontSize: 13, color: 'var(--ink-700)', lineHeight: 1.65, marginBottom: 8 }}>
            {t('bidding.subtitle')}
          </div>
          <StepBar state={ui.kind} />
        </div>
      </div>

      {ui.kind === 'idle' && <UploadZone onFile={handleFile} />}
      {ui.kind === 'uploading' && <UploadingView progress={ui.progress} />}
      {ui.kind === 'processing' && <ProcessingView />}

      {ui.kind === 'success' && (
        <>
          <IdentifyPanel identify={ui.resp.identify} />
          {ui.resp.parse && <ParsePanel parse={ui.resp.parse} />}
          {ui.resp.fill && <FillPanel fill={ui.resp.fill} />}
          {ui.resp.download && (
            <DownloadPanel
              download={ui.resp.download}
              onReset={reset}
              onDownloaded={() => undefined}
            />
          )}
        </>
      )}

      {ui.kind === 'rejected' && (
        <>
          <IdentifyPanel identify={ui.resp.identify} />
          <RejectedPanel identify={ui.resp.identify} onReset={reset} />
        </>
      )}

      {ui.kind === 'error' && (
        <>
          {ui.resp && <IdentifyPanel identify={ui.resp.identify} />}
          <ErrorPanel code={ui.code} detail={ui.detail} onReset={reset} />
        </>
      )}
    </div>
  );
}
