import { Fragment, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../components/Icon';
import type { IconName } from '../components/Icon';
import { aiParseApi, rateApi } from '../services/api';
import type { ParsePreviewRow } from '../types';

interface InboxImageMeta {
  index: number;
  filename: string;
  content_type: string;
  size: number;
}

interface InboxEmailItem {
  cache_key: string;
  id: string;
  subject: string;
  from: string;
  from_name: string;
  date: string;
  snippet: string;
  has_attachment: boolean;
  attachment_names: string[];
  image_attachments: InboxImageMeta[];
  folder: string;
  body_length: number;
}

interface ParseResult {
  batch_id: string;
  file_name: string;
  source_type: string;
  carrier_code: string;
  total_rows: number;
  preview_rows: ParsePreviewRow[];
  warnings: string[];
  sheets?: { name: string; rows: number }[];
}

interface ImportResult {
  batch_id: string;
  records_parsed: number;
  records_imported: number;
  errors: string[];
}

type SourceTab = 'excel' | 'inbox' | 'email' | 'wechat';

// --- Drop zone helper ---
function DropZone({
  icon,
  text,
  hint,
  accept,
  disabled,
  onFile,
}: {
  icon: IconName;
  text: string;
  hint: ReactNode;
  accept: string;
  disabled?: boolean;
  onFile: (file: File) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept={accept}
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = '';
        }}
      />
      <div
        className={`dropzone${dragging ? ' drag' : ''}${disabled ? ' disabled' : ''}`}
        onClick={() => !disabled && ref.current?.click()}
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
          <Icon name={icon} size={24} />
        </div>
        <div className="dropzone-text">{text}</div>
        <div className="dropzone-hint">{hint}</div>
      </div>
    </>
  );
}

// --- Steps ---
function UploadSteps({ step }: { step: number }) {
  const { t } = useTranslation();
  const steps = [
    t('upload.stepSelectSource'),
    t('upload.stepPreview'),
    t('upload.stepDone'),
  ];
  return (
    <div className="steps">
      {steps.map((title, i) => (
        <Fragment key={i}>
          <div className={`step${i === step ? ' active' : ''}${i < step ? ' done' : ''}`}>
            <div className="step-num">{i < step ? <Icon name="check" size={14} /> : i + 1}</div>
            <div className="step-body">
              <div className="step-title">{title}</div>
            </div>
          </div>
          {i < steps.length - 1 && <div className={`step-line${i < step ? ' done' : ''}`} />}
        </Fragment>
      ))}
    </div>
  );
}

// --- Inbox email card ---
function InboxRow({
  item,
  parsingKey,
  parsingAttachKey,
  loading,
  onParse,
  onParseAttach,
  extraTags,
  onClear,
}: {
  item: InboxEmailItem;
  parsingKey: string;
  parsingAttachKey: string;
  loading: boolean;
  onParse: (i: InboxEmailItem) => void;
  onParseAttach: (i: InboxEmailItem, img: InboxImageMeta) => void;
  extraTags?: ReactNode;
  onClear?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="list-row">
      <div className="list-row-head">
        <div className="title">{item.subject || t('common.unknownSubject')}</div>
        {extraTags}
        {item.has_attachment && (
          <span className="tag tag-warn">
            📎 {t('upload.attachments', { count: item.attachment_names.length })}
          </span>
        )}
        {item.folder && <span className="tag tag-muted">{item.folder}</span>}
      </div>
      <div className="list-row-meta">
        {item.from_name || item.from} · {(item.date || '').slice(0, 16).replace('T', ' ')}
      </div>
      <div className="list-row-snippet">{item.snippet || t('common.emptyContent')}</div>
      {item.image_attachments.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', marginTop: 4 }}>
          <span
            style={{
              fontSize: 11.5,
              color: 'var(--ink-500)',
              fontFamily: 'var(--font-en)',
              letterSpacing: '.04em',
            }}
          >
            {t('upload.imageAttachments')}
          </span>
          {item.image_attachments.map((img) => {
            const key = `${item.cache_key}_${img.index}`;
            const busy = parsingAttachKey === key;
            return (
              <button
                type="button"
                key={key}
                className="btn btn-secondary btn-sm"
                disabled={(loading && !busy) || busy}
                onClick={() => onParseAttach(item, img)}
              >
                <Icon name="sparkles" size={11} />
                {img.filename || `image-${img.index + 1}`}
                <span style={{ color: 'var(--ink-500)', fontSize: 11 }}>
                  ({Math.round(img.size / 1024)}KB)
                </span>
              </button>
            );
          })}
        </div>
      )}
      <div className="list-row-actions">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={(loading && parsingKey !== item.cache_key) || parsingKey === item.cache_key}
          onClick={() => onParse(item)}
        >
          <Icon name="sparkles" size={11} />
          {t('upload.parseBody')}
        </button>
        {onClear && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
            {t('common.cancel')}
          </button>
        )}
      </div>
    </div>
  );
}

export default function RateUpload() {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<SourceTab>('excel');
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [emailText, setEmailText] = useState('');
  const [imageContext, setImageContext] = useState('');
  const [inboxEmails, setInboxEmails] = useState<InboxEmailItem[]>([]);
  const [inboxLoading, setInboxLoading] = useState(false);
  const [inboxFetchedAt, setInboxFetchedAt] = useState('');
  const [parsingKey, setParsingKey] = useState('');
  const [parsingAttachKey, setParsingAttachKey] = useState('');
  const [localMsgItem, setLocalMsgItem] = useState<InboxEmailItem | null>(null);
  const [msgUploading, setMsgUploading] = useState(false);

  const handleParseSuccess = (res: unknown) => {
    const envelope = res as { code?: number; message?: string; data?: ParseResult & { message?: string } };
    if (envelope.code !== 0 && envelope.code !== undefined) {
      message.error(envelope.message || t('upload.parseFailed'));
      return;
    }
    const data = (envelope.data || envelope) as ParseResult & { message?: string };
    if (!data.total_rows) {
      message.warning(data.message || t('upload.noRatesExtracted'));
      if (data.warnings?.length) message.warning(data.warnings[0]);
      return;
    }
    setParseResult(data);
    setStep(1);
    message.success(t('upload.parseCompleted', { count: data.total_rows }));
  };

  const handleExcelUpload = async (file: File) => {
    setLoading(true);
    try {
      const res = await rateApi.uploadAndParse(file);
      handleParseSuccess(res);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('upload.uploadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleEmailParse = async () => {
    if (!emailText.trim()) {
      message.warning(t('upload.pasteEmailFirst'));
      return;
    }
    setLoading(true);
    try {
      const res = await aiParseApi.parseEmailText(emailText);
      handleParseSuccess(res);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('upload.aiParseFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleFetchInbox = async () => {
    setInboxLoading(true);
    try {
      const res = await aiParseApi.listInboxEmails({ limit: 20 });
      const envelope = res as {
        code?: number;
        message?: string;
        data?: { emails?: InboxEmailItem[] };
      };
      if (envelope.code !== 0 && envelope.code !== undefined) {
        message.error(envelope.message || t('upload.inboxFetchFailed'));
        return;
      }
      const emails = envelope.data?.emails || [];
      setInboxEmails(emails);
      setInboxFetchedAt(new Date().toLocaleTimeString());
      if (emails.length === 0) message.info(t('upload.inboxEmpty'));
      else message.success(t('upload.inboxFetched', { count: emails.length }));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('upload.inboxFetchFailed'));
    } finally {
      setInboxLoading(false);
    }
  };

  const handleParseInboxEmail = async (item: InboxEmailItem) => {
    setParsingKey(item.cache_key);
    setLoading(true);
    try {
      const res = await aiParseApi.parseInboxEmail(item.cache_key);
      handleParseSuccess(res);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('upload.parseInboxFailed'));
    } finally {
      setLoading(false);
      setParsingKey('');
    }
  };

  const handleParseAttachment = async (item: InboxEmailItem, image: InboxImageMeta) => {
    const key = `${item.cache_key}_${image.index}`;
    setParsingAttachKey(key);
    setLoading(true);
    try {
      const res = await aiParseApi.parseInboxAttachment(item.cache_key, image.index);
      handleParseSuccess(res);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('upload.parseAttachmentFailed'));
    } finally {
      setLoading(false);
      setParsingAttachKey('');
    }
  };

  const handleMsgUpload = async (file: File) => {
    setMsgUploading(true);
    try {
      const res = await aiParseApi.uploadMsgFile(file);
      const envelope = res as { code?: number; message?: string; data?: InboxEmailItem };
      if (envelope.code !== 0 && envelope.code !== undefined) {
        message.error(envelope.message || t('upload.msgUploadFailed'));
        return;
      }
      const data = envelope.data;
      if (!data) return;
      setLocalMsgItem(data);
      message.success(t('upload.msgUploadSuccess', { subject: data.subject || '' }));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('upload.msgUploadFailed'));
    } finally {
      setMsgUploading(false);
    }
  };

  const handleImageUpload = async (file: File) => {
    setLoading(true);
    try {
      const res = await aiParseApi.parseWechatImage(file, imageContext);
      handleParseSuccess(res);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('upload.parseImageFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!parseResult) return;
    setLoading(true);
    try {
      const isAi = ['email_text', 'wechat_image', 'inbox_email', 'inbox_attachment'].includes(
        parseResult.source_type
      );
      const fn = isAi ? aiParseApi.confirmImport : rateApi.confirmImport;
      const res = await fn(parseResult.batch_id);
      const envelope = res as { code?: number; message?: string; data?: ImportResult };
      if (envelope.code !== 0 && envelope.code !== undefined) {
        message.error(envelope.message || t('upload.importFailed'));
        return;
      }
      const data = envelope.data;
      if (!data) return;
      setImportResult(data);
      setStep(2);
      message.success(t('upload.importSuccess', { count: data.records_imported }));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('upload.importFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setStep(0);
    setParseResult(null);
    setImportResult(null);
  };

  const sourceTagClass = (type: string) =>
    type === 'excel'
      ? 'tag-success'
      : type === 'wechat_image' || type === 'inbox_attachment'
        ? 'tag-warn'
        : 'tag-info';

  const tabs: { key: SourceTab; label: string; icon: IconName }[] = [
    { key: 'excel', label: t('upload.tabExcel'), icon: 'import' },
    { key: 'inbox', label: t('upload.tabInbox'), icon: 'mail' },
    { key: 'email', label: t('upload.tabEmailText'), icon: 'mail' },
    { key: 'wechat', label: t('upload.tabWechat'), icon: 'sparkles' },
  ];

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('upload.title')}</h1>
        <div className="sub">RATE IMPORT</div>
      </div>

      <div className="card" style={{ opacity: loading ? 0.75 : 1 }}>
        <div className="card-body">
          <UploadSteps step={step} />

          {step === 0 && (
            <>
              <div className="tabs">
                {tabs.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    className={`tab${activeTab === tab.key ? ' on' : ''}`}
                    onClick={() => setActiveTab(tab.key)}
                  >
                    <Icon name={tab.icon} size={13} />
                    {tab.label}
                  </button>
                ))}
              </div>

              {activeTab === 'excel' && (
                <DropZone
                  icon="import"
                  text={t('upload.excelDragText')}
                  hint={
                    <>
                      {t('upload.excelHint')}
                      <br />
                      {t('upload.excelHint2')}
                    </>
                  }
                  accept=".xlsx,.xls,.csv"
                  disabled={loading}
                  onFile={handleExcelUpload}
                />
              )}

              {activeTab === 'inbox' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div className="alert alert-info">
                    <div className="alert-icon">
                      <Icon name="mail" size={16} />
                    </div>
                    <div className="alert-body">
                      <div className="alert-title">{t('upload.inboxInfo')}</div>
                      <div className="alert-desc">{t('upload.inboxInfoDesc')}</div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleFetchInbox}
                      disabled={inboxLoading}
                    >
                      <Icon name="refresh" size={13} />
                      {inboxEmails.length > 0 ? t('upload.refetchInbox') : t('upload.fetchInbox')}
                    </button>
                    {inboxFetchedAt && (
                      <span style={{ fontSize: 12, color: 'var(--ink-500)' }}>
                        {t('upload.lastFetchTime', { time: inboxFetchedAt })}
                      </span>
                    )}
                  </div>

                  {inboxEmails.length === 0 ? (
                    <div
                      style={{
                        padding: 40,
                        textAlign: 'center',
                        color: 'var(--ink-500)',
                        fontSize: 13,
                        background: 'var(--mist)',
                        borderRadius: 8,
                      }}
                    >
                      {inboxLoading ? t('upload.fetchingInbox') : t('upload.clickFetchInbox')}
                    </div>
                  ) : (
                    <div>
                      {inboxEmails.map((item) => (
                        <InboxRow
                          key={item.cache_key}
                          item={item}
                          parsingKey={parsingKey}
                          parsingAttachKey={parsingAttachKey}
                          loading={loading}
                          onParse={handleParseInboxEmail}
                          onParseAttach={handleParseAttachment}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'email' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div className="alert alert-info">
                    <div className="alert-icon">
                      <Icon name="mail" size={16} />
                    </div>
                    <div className="alert-body">
                      <div className="alert-title">{t('upload.emailTextInfo')}</div>
                    </div>
                  </div>

                  <DropZone
                    icon="mail"
                    text={msgUploading ? t('upload.msgUploading') : t('upload.msgDragText')}
                    hint={t('upload.msgHint')}
                    accept=".msg"
                    disabled={msgUploading}
                    onFile={handleMsgUpload}
                  />

                  {localMsgItem && (
                    <InboxRow
                      item={localMsgItem}
                      parsingKey={parsingKey}
                      parsingAttachKey={parsingAttachKey}
                      loading={loading}
                      onParse={handleParseInboxEmail}
                      onParseAttach={handleParseAttachment}
                      extraTags={<span className="tag tag-teal">.msg</span>}
                      onClear={() => setLocalMsgItem(null)}
                    />
                  )}

                  <div style={{ fontSize: 12.5, color: 'var(--ink-500)' }}>
                    {t('upload.orPasteText')}
                  </div>
                  <textarea
                    className="input"
                    rows={10}
                    placeholder={t('upload.emailPlaceholder')}
                    value={emailText}
                    onChange={(e) => setEmailText(e.target.value)}
                    style={{ resize: 'vertical', minHeight: 180, lineHeight: 1.6 }}
                  />
                  <div>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleEmailParse}
                      disabled={!emailText.trim() || loading}
                    >
                      <Icon name="sparkles" size={13} />
                      {t('upload.parseEmailText')}
                    </button>
                  </div>
                </div>
              )}

              {activeTab === 'wechat' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div className="alert alert-info">
                    <div className="alert-icon">
                      <Icon name="sparkles" size={16} />
                    </div>
                    <div className="alert-body">
                      <div className="alert-title">{t('upload.wechatInfo')}</div>
                    </div>
                  </div>

                  <input
                    className="input"
                    placeholder={t('upload.wechatContextPlaceholder')}
                    value={imageContext}
                    onChange={(e) => setImageContext(e.target.value)}
                  />

                  <DropZone
                    icon="sparkles"
                    text={t('upload.imageDragText')}
                    hint={
                      <>
                        {t('upload.imageHint')}
                        <br />
                        {t('upload.imageHint2')}
                      </>
                    }
                    accept=".png,.jpg,.jpeg,.gif,.webp,.bmp"
                    disabled={loading}
                    onFile={handleImageUpload}
                  />
                </div>
              )}
            </>
          )}

          {step === 1 && parseResult && (
            <>
              <div className="alert alert-success" style={{ marginBottom: 14 }}>
                <div className="alert-icon">
                  <Icon name="check" size={16} />
                </div>
                <div className="alert-body">
                  <div className="alert-title" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                    <span className={`tag zh ${sourceTagClass(parseResult.source_type)}`}>
                      {t(`rates.sources.${parseResult.source_type}`, parseResult.source_type)}
                    </span>
                    <span>
                      {t('upload.fileLabel')}: <strong>{parseResult.file_name}</strong>
                    </span>
                    {parseResult.carrier_code && (
                      <span className="tag tag-teal">{parseResult.carrier_code}</span>
                    )}
                    <span>{t('upload.parsedRates', { count: parseResult.total_rows })}</span>
                  </div>
                  {parseResult.sheets && parseResult.sheets.length > 0 && (
                    <div className="alert-desc">
                      {parseResult.sheets
                        .map((sheet) => t('upload.sheetSummary', { name: sheet.name, count: sheet.rows }))
                        .join(' · ')}
                    </div>
                  )}
                </div>
              </div>

              {parseResult.warnings.length > 0 && (
                <div className="alert alert-warn" style={{ marginBottom: 14 }}>
                  <div className="alert-icon">
                    <Icon name="alert" size={16} />
                  </div>
                  <div className="alert-body">
                    <div className="alert-title">
                      {t('upload.warnings', { count: parseResult.warnings.length })}
                    </div>
                    <ul style={{ margin: '8px 0 0', paddingLeft: 20, fontSize: 12.5, color: 'var(--ink-700)' }}>
                      {parseResult.warnings.slice(0, 10).map((warning, i) => (
                        <li key={i}>{warning}</li>
                      ))}
                      {parseResult.warnings.length > 10 && (
                        <li>{t('upload.moreWarnings', { count: parseResult.warnings.length - 10 })}</li>
                      )}
                    </ul>
                  </div>
                </div>
              )}

              <div
                className="card"
                style={{ padding: 0, overflow: 'hidden', marginBottom: 14 }}
              >
                <div className="table-scroll">
                  <table className="rtable" style={{ minWidth: 1200 }}>
                    <thead>
                      <tr>
                        <th>{t('rates.originPort')}</th>
                        <th>{t('rates.destinationPort')}</th>
                        <th>{t('rates.shippingLine')}</th>
                        <th className="c-right">20GP</th>
                        <th className="c-right">40GP</th>
                        <th className="c-right">40HQ</th>
                        <th className="c-right">45ft</th>
                        <th className="c-right">BAF 20/40</th>
                        <th>{t('rates.effectiveDate')}</th>
                        <th className="c-center">{t('rates.transitDays')}</th>
                        <th>{t('rates.remarks')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {parseResult.preview_rows.map((row, i) => (
                        <tr key={i}>
                          <td>{row.origin_port || '—'}</td>
                          <td>{row.destination_port || '—'}</td>
                          <td>
                            <span className="tag tag-teal">{row.carrier}</span>
                          </td>
                          <td className="c-right num">{row.container_20gp ? `$${row.container_20gp}` : '—'}</td>
                          <td className="c-right num">{row.container_40gp ? `$${row.container_40gp}` : '—'}</td>
                          <td className="c-right num">{row.container_40hq ? `$${row.container_40hq}` : '—'}</td>
                          <td className="c-right num">{row.container_45 ? `$${row.container_45}` : '—'}</td>
                          <td className="c-right num" style={{ color: 'var(--ink-500)' }}>
                            {row.baf_20 || row.baf_40
                              ? `${row.baf_20 || '0'}/${row.baf_40 || '0'}`
                              : '—'}
                          </td>
                          <td className="num" style={{ color: 'var(--ink-500)' }}>{row.valid_from || '—'}</td>
                          <td className="c-center num" style={{ color: 'var(--ink-500)' }}>
                            {row.transit_days
                              ? t('common.days', { count: row.transit_days })
                              : '—'}
                          </td>
                          <td
                            style={{
                              maxWidth: 240,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              fontSize: 12.5,
                              color: 'var(--ink-700)',
                            }}
                            title={row.remarks || ''}
                          >
                            {row.remarks || '—'}
                          </td>
                        </tr>
                      ))}
                      {parseResult.preview_rows.length === 0 && (
                        <tr>
                          <td colSpan={11} style={{ textAlign: 'center', padding: 32, color: 'var(--ink-500)' }}>
                            {t('common.noData')}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10 }}>
                <button className="btn btn-primary" onClick={handleConfirm} disabled={loading}>
                  <Icon name="check" size={13} />
                  {t('upload.confirmImport', { count: parseResult.total_rows })}
                </button>
                <button className="btn btn-secondary" onClick={handleReset}>
                  {t('common.cancel')}
                </button>
              </div>
            </>
          )}

          {step === 2 && importResult && (
            <>
              <div className="result-hero">
                <div className="r-icon">
                  <Icon name="check" size={28} />
                </div>
                <div className="r-title">{t('upload.successTitle')}</div>
                <div className="r-sub">
                  {t('upload.successSubtitle', {
                    imported: importResult.records_imported,
                    parsed: importResult.records_parsed,
                  })}
                </div>
                <div className="r-actions">
                  <button
                    className="btn btn-primary"
                    onClick={() => {
                      window.location.href = '/rates';
                    }}
                  >
                    {t('upload.viewRates')}
                  </button>
                  <button className="btn btn-secondary" onClick={handleReset}>
                    {t('upload.continueImport')}
                  </button>
                </div>
              </div>

              {importResult.errors.length > 0 && (
                <div className="alert alert-danger" style={{ marginTop: 10 }}>
                  <div className="alert-icon">
                    <Icon name="alert" size={16} />
                  </div>
                  <div className="alert-body">
                    <div className="alert-title">
                      {t('upload.importErrors', { count: importResult.errors.length })}
                    </div>
                    <div className="alert-desc" style={{ whiteSpace: 'pre-wrap' }}>
                      {importResult.errors.join('\n')}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
