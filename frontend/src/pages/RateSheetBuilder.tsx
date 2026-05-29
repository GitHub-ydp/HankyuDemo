import { Fragment, useEffect, useState } from 'react';
import { Upload, Input, InputNumber, Table, Tooltip, message } from 'antd';
import type { UploadFile } from 'antd';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icon';
import { rateSheetApi } from '../services/api';

interface FileResult {
  name: string;
  source_type: string;
  status: string;
  row_count: number;
  warnings: string[];
  message: string;
}

interface PreviewRow {
  _rid?: number;
  origin?: string;
  destination?: string;
  carrier?: string;
  freight_20?: number | string | null;
  freight_40?: number | string | null;
  service?: string;
  day1?: number | string | null;
  day2?: number | string | null;
  day3?: number | string | null;
  day4?: number | string | null;
  day5?: number | string | null;
  day6?: number | string | null;
  day7?: number | string | null;
  // 档位源(EES/唯凯)：稀疏档位 dict(KG→价)。JSON 往返后键是字符串('45')。
  tier_prices?: Record<string, number | null>;
  remark?: string | null;
  needs_review?: boolean;
}

interface ApiLike {
  code: number;
  message?: string;
  data?: unknown;
}

export default function RateSheetBuilder() {
  const { t } = useTranslation();
  const [templateType, setTemplateType] = useState<string | null>('air');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [fileResults, setFileResults] = useState<FileResult[]>([]);
  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [summary, setSummary] = useState<{ total_rows: number; needs_review: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [editedRows, setEditedRows] = useState<Record<number, Partial<PreviewRow>>>({});

  const resetSession = () => {
    setFileList([]);
    setFileResults([]);
    setRows([]);
    setSummary(null);
  };

  const onSelectTemplate = async (val: string) => {
    setTemplateType(val);
    resetSession();
    try {
      const res = (await rateSheetApi.createSession(val)) as ApiLike;
      if (res.code === 0) {
        setSessionId((res.data as { session_id: string }).session_id);
      } else {
        message.error(res.message || t('rateSheet.createFailed'));
        setSessionId(null);
      }
    } catch {
      message.error(t('rateSheet.createFailed'));
      setSessionId(null);
    }
  };

  // 默认就选中 Air：挂载时建好会话，让上传立刻可用，避免「看着选中却要再点一下」的割裂。
  useEffect(() => {
    onSelectTemplate('air');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleUpload = async () => {
    if (!sessionId) {
      message.warning(t('rateSheet.noSession'));
      return;
    }
    if (fileList.length === 0) {
      message.warning(t('rateSheet.noFiles'));
      return;
    }
    setUploading(true);
    try {
      const files = fileList
        .map((f) => f.originFileObj as File | undefined)
        .filter((f): f is File => Boolean(f));
      const res = (await rateSheetApi.uploadFiles(sessionId, files)) as ApiLike;
      if (res.code === 0) {
        const data = res.data as { files: FileResult[]; summary: { total_rows: number; needs_review: number } };
        setFileResults(data.files);
        setSummary(data.summary);
        const pv = (await rateSheetApi.preview(sessionId)) as ApiLike;
        if (pv.code === 0) {
          const pvRows = (pv.data as { rows: PreviewRow[] }).rows.map((r, i) => ({ ...r, _rid: i }));
          setRows(pvRows);
          setSelectedRowKeys(pvRows.map((r) => r._rid as number));
          setEditedRows({});
        }
      } else {
        message.error(res.message || t('rateSheet.uploadFailed'));
      }
    } catch {
      message.error(t('rateSheet.uploadFailed'));
    } finally {
      setUploading(false);
    }
  };

  const keptCount = selectedRowKeys.length;
  const keptReview = rows.filter(
    (r) => selectedRowKeys.includes(r._rid as number) && r.needs_review,
  ).length;

  // 勾选保留 + 行内编辑后的最终行（下载与入库共用）
  const buildFinalRows = () =>
    rows
      .filter((r) => selectedRowKeys.includes(r._rid as number))
      .map((r) => {
        const merged = { ...r, ...editedRows[r._rid as number] };
        delete (merged as { _rid?: number })._rid;
        return merged;
      });

  const handleDownload = async () => {
    if (!sessionId) return;
    try {
      const blob = await rateSheetApi.downloadFilled(sessionId, buildFinalRows());
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${templateType ?? 'rate'}_rate_sheet_filled.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      message.error(t('rateSheet.downloadFailed'));
    }
  };

  const handleCommit = async () => {
    if (!sessionId) return;
    try {
      const res = (await rateSheetApi.commitToDb(sessionId, buildFinalRows())) as ApiLike;
      if (res.code === 0) {
        const d = res.data as { tier_rows: number; skipped_weekly: number };
        message.success(t('rateSheet.commitSuccess', { tier: d.tier_rows, skipped: d.skipped_weekly }));
      } else {
        message.error(res.message || t('rateSheet.commitFailed'));
      }
    } catch {
      message.error(t('rateSheet.commitFailed'));
    }
  };

  const statusTag = (status: string) => {
    const map: Record<string, { cls: string; key: string }> = {
      parsed: { cls: 'tag-success', key: 'rateSheet.statusParsed' },
      skipped: { cls: 'tag-warn', key: 'rateSheet.statusSkipped' },
      error: { cls: 'tag-danger', key: 'rateSheet.statusError' },
    };
    const m = map[status] || { cls: 'tag-muted', key: status };
    return <span className={`tag ${m.cls}`}>{t(m.key)}</span>;
  };

  const fileColumns = [
    { title: t('rateSheet.fileName'), dataIndex: 'name', key: 'name', width: 160 },
    { title: t('rateSheet.sourceType'), dataIndex: 'source_type', key: 'source_type', width: 80 },
    { title: t('rateSheet.status'), dataIndex: 'status', key: 'status', width: 84, render: statusTag },
    { title: t('rateSheet.rowCount'), dataIndex: 'row_count', key: 'row_count', width: 90 },
    {
      title: t('rateSheet.colRemark'),
      key: 'message',
      render: (_: unknown, r: FileResult) => r.message || (r.warnings || []).join('；'),
    },
  ];

  const valueOf = (r: PreviewRow, field: keyof PreviewRow) =>
    ({ ...r, ...editedRows[r._rid as number] })[field];

  const editCell = (rid: number, field: keyof PreviewRow, value: unknown) =>
    setEditedRows((prev) => ({ ...prev, [rid]: { ...prev[rid], [field]: value } }));

  const textCol = (title: string, field: keyof PreviewRow) => ({
    title,
    key: field as string,
    render: (_: unknown, r: PreviewRow) => (
      <Input
        size="small"
        variant="outlined"
        value={(valueOf(r, field) as string) ?? ''}
        onChange={(e) => editCell(r._rid as number, field, e.target.value)}
      />
    ),
  });

  const numCol = (title: string, field: keyof PreviewRow) => ({
    title,
    key: field as string,
    width: 92,
    render: (_: unknown, r: PreviewRow) => (
      <InputNumber
        size="small"
        variant="outlined"
        style={{ width: '100%' }}
        value={valueOf(r, field) as number | null | undefined}
        onChange={(v) => editCell(r._rid as number, field, v)}
      />
    ),
  });

  // 档位列(动态)：读写嵌套的 tier_prices[kg]。编辑时整份合并写回，保证下载的 {...r,...edited} 整体替换正确。
  const mergedTiers = (r: PreviewRow): Record<string, number | null> =>
    (editedRows[r._rid as number]?.tier_prices ?? r.tier_prices ?? {});

  const editTier = (r: PreviewRow, kg: number, value: number | null) =>
    editCell(r._rid as number, 'tier_prices', { ...mergedTiers(r), [String(kg)]: value });

  const tierCol = (kg: number) => ({
    title: `${kg}KG`,
    key: `tier_${kg}`,
    width: 88,
    render: (_: unknown, r: PreviewRow) => (
      <InputNumber
        size="small"
        variant="outlined"
        style={{ width: '100%' }}
        value={mergedTiers(r)[String(kg)] as number | null | undefined}
        onChange={(v) => editTier(r, kg, v as number | null)}
      />
    ),
  });

  // air 档位源：全表档位并集(升序)。非空即进「档位模式」(动态 KG 列)，否则用 day1-7 周表列。
  const tierColumns = Array.from(
    new Set(rows.flatMap((r) => Object.keys(r.tier_prices ?? {}).map(Number))),
  ).sort((a, b) => a - b);

  const reviewCol = {
    title: (
      <Tooltip title={t('rateSheet.needsReview')}>
        <span className="rs-review-th">
          <Icon name="review" size={14} />
        </span>
      </Tooltip>
    ),
    key: 'needs_review',
    width: 44,
    align: 'center' as const,
    render: (_: unknown, r: PreviewRow) =>
      r.needs_review ? (
        <Tooltip title={t('rateSheet.needsReview')}>
          <span className="rs-review-dot" aria-label={t('rateSheet.needsReview')} />
        </Tooltip>
      ) : null,
  };

  const seaCols = [
    textCol(t('rateSheet.colDestination'), 'destination'),
    textCol(t('rateSheet.colCarrier'), 'carrier'),
    numCol(t('rateSheet.colFreight20'), 'freight_20'),
    numCol(t('rateSheet.colFreight40'), 'freight_40'),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
  // 起运港：联运商均沪发，默认 PVG；只读展示（不参与编辑），让客户一眼看清从哪发。
  const originCol = {
    title: t('rateSheet.colOrigin'),
    key: 'origin',
    width: 72,
    render: (_: unknown, r: PreviewRow) => r.origin ?? '',
  };
  const airDayCols = Array.from({ length: 7 }, (_, i) =>
    numCol(t('rateSheet.colDay', { n: i + 1 }), `day${i + 1}` as keyof PreviewRow),
  );
  const airCols = [
    originCol,
    textCol(t('rateSheet.colDestination'), 'destination'),
    textCol(t('rateSheet.colService'), 'service'),
    // 档位模式 → 动态 KG 列；否则 day1-7 周表列(Market Price 周报)。
    ...(tierColumns.length > 0 ? tierColumns.map((kg) => tierCol(kg)) : airDayCols),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
  const previewCols = templateType === 'air' ? airCols : seaCols;

  // 顶部进度：选模板(已默认) → 上传 → AI抽取 → 审核/下载
  const activeStep = rows.length ? 3 : uploading ? 2 : 1;
  const flowSteps = [
    t('rateSheet.flow1'),
    t('rateSheet.flow2'),
    t('rateSheet.flow3'),
    t('rateSheet.flow4'),
  ];

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('rateSheet.title')}</h1>
        <div className="sub">RATE SHEET BUILDER</div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <div className="steps">
            {flowSteps.map((title, i) => (
              <Fragment key={i}>
                <div className={`step${i === activeStep ? ' active' : ''}${i < activeStep ? ' done' : ''}`}>
                  <div className="step-num">{i < activeStep ? <Icon name="check" size={14} /> : i + 1}</div>
                  <div className="step-body">
                    <div className="step-title">{title}</div>
                  </div>
                </div>
                {i < flowSteps.length - 1 && <div className={`step-line${i < activeStep ? ' done' : ''}`} />}
              </Fragment>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h3>{t('rateSheet.step1')}</h3>
        </div>
        <div className="card-body">
          <div className="chip-group">
            {[
              { v: 'air', l: t('rateSheet.templateAir') },
              { v: 'sea', l: t('rateSheet.templateSea') },
            ].map((o) => (
              <button
                key={o.v}
                type="button"
                className={`chip${templateType === o.v ? ' on' : ''}`}
                onClick={() => onSelectTemplate(o.v)}
              >
                {o.l}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h3>{t('rateSheet.step2')}</h3>
        </div>
        <div className="card-body">
          <div className="rs-dropwrap">
            <Upload
              multiple
              beforeUpload={() => false}
              fileList={fileList}
              onChange={({ fileList: fl }) => setFileList(fl)}
              disabled={!sessionId}
            >
              <div className={`dropzone${!sessionId ? ' disabled' : ''}`}>
                <div className="dropzone-icon">
                  <Icon name="import" size={22} />
                </div>
                <div className="dropzone-text">{t('rateSheet.uploadHint')}</div>
                <div className="dropzone-hint">{t('rateSheet.uploadHintSub')}</div>
              </div>
            </Upload>
          </div>

          <button
            type="button"
            className="btn btn-primary"
            style={{ marginTop: 14 }}
            disabled={!sessionId || fileList.length === 0 || uploading}
            onClick={handleUpload}
          >
            {uploading ? `${t('rateSheet.flow3')}…` : t('rateSheet.uploadBtn')}
          </button>

          {fileResults.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Table
                className="rs-files"
                size="small"
                rowKey={(_, i) => String(i)}
                columns={fileColumns}
                dataSource={fileResults}
                pagination={false}
              />
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>{t('rateSheet.step3')}</h3>
          {tierColumns.length > 0 && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ marginLeft: 'auto' }}
              disabled={!summary || keptCount === 0}
              onClick={handleCommit}
            >
              <Icon name="import" size={14} />
              {t('rateSheet.commit')}
            </button>
          )}
          <button
            type="button"
            className="btn btn-primary btn-sm"
            style={{ marginLeft: tierColumns.length > 0 ? 8 : 'auto' }}
            disabled={!summary || keptCount === 0}
            onClick={handleDownload}
          >
            <Icon name="download" size={14} />
            {t('rateSheet.download')}
          </button>
        </div>
        <div className="card-body">
          {summary ? (
            <>
              <div
                className="kpi-grid"
                style={{ gridTemplateColumns: 'repeat(2, minmax(150px, 220px))', marginBottom: 18 }}
              >
                <div className="kpi">
                  <div className="kpi-label">
                    <span className="zh">{t('rateSheet.summaryTotal')}</span>
                  </div>
                  <div className="kpi-value">
                    {keptCount} <span style={{ color: 'var(--ink-400)', fontWeight: 400 }}>/ {summary.total_rows}</span>
                  </div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">
                    <span className="zh">{t('rateSheet.summaryReview')}</span>
                  </div>
                  <div className="kpi-value" style={{ color: keptReview > 0 ? 'var(--warn)' : undefined }}>
                    {keptReview} <span style={{ color: 'var(--ink-400)', fontWeight: 400 }}>/ {summary.needs_review}</span>
                  </div>
                </div>
              </div>
              <div className="rs-edit-hint">
                <Icon name="review" size={13} />
                {t('rateSheet.editHint')}
              </div>
              <Table
                className="rs-table"
                size="small"
                rowKey={(r: PreviewRow) => r._rid as number}
                rowSelection={{
                  selectedRowKeys,
                  onChange: (keys) => setSelectedRowKeys(keys as number[]),
                }}
                columns={previewCols}
                dataSource={rows}
                rowClassName={(r: PreviewRow) =>
                  !selectedRowKeys.includes(r._rid as number)
                    ? 'row-excluded'
                    : r.needs_review
                      ? 'row-needs-review'
                      : ''
                }
                pagination={{ pageSize: 20 }}
              />
            </>
          ) : (
            <div className="rs-empty">{t('rateSheet.previewTitle')}</div>
          )}
        </div>
      </div>
    </div>
  );
}
