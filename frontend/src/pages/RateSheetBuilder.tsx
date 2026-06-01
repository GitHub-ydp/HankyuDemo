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
  // 结构化海运字段(入库 commit_ocean_rows 读这些；审核台价格列直接绑定它们)
  container_20gp?: number | string | null;
  container_40gp?: number | string | null;
  container_40hq?: number | string | null;
  container_45?: number | string | null;
  currency?: string | null;
  via?: string | null;
  commodity?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  rate_level?: string | null;
  service_code?: string | null;
  lss_cic?: number | string | null;
  baf?: number | string | null;
  transit_days?: number | string | null;
  transit?: number | string | null;
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
        const merged = { ...r, ...editedRows[r._rid as number] } as PreviewRow;
        delete (merged as { _rid?: number })._rid;
        // 海运：价格/航程审核台编辑的是结构化字段(container_*/transit_days，入库读这些)；
        // 这里派生下载链路用的合并字段(freight_*/transit，template_filler 读这些)，让两条路都吃到编辑。
        if (templateType === 'sea') {
          merged.freight_20 = (merged.container_20gp as number | null) ?? null;
          merged.freight_40 =
            (merged.container_40gp as number | null) ?? (merged.container_40hq as number | null) ?? null;
          merged.transit = (merged.transit_days as number | null) ?? null;
        }
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
        // 后端按行形状分流：海运返回 fcl_rows，空运重量档返回 tier_rows。
        const d = res.data as {
          tier_rows?: number;
          skipped_weekly?: number;
          fcl_rows?: number;
          skipped_no_price?: number;
          skipped_unresolved?: number;
        };
        if (typeof d.fcl_rows === 'number') {
          message.success(
            t('rateSheet.commitSuccessOcean', {
              fcl: d.fcl_rows,
              noPrice: d.skipped_no_price ?? 0,
              unresolved: d.skipped_unresolved ?? 0,
            }),
          );
        } else {
          message.success(
            t('rateSheet.commitSuccess', { tier: d.tier_rows ?? 0, skipped: d.skipped_weekly ?? 0 }),
          );
        }
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

  // 只读列：直接展示原值(不进 editedRows)，用于起运港/币种/编码等标识性字段
  const roCol = (title: string, field: keyof PreviewRow, width = 80) => ({
    title,
    key: field as string,
    width,
    render: (_: unknown, r: PreviewRow) => {
      const v = (r as Record<string, unknown>)[field as string];
      return v === null || v === undefined ? '' : String(v);
    },
  });

  // 动态列判定：该字段全表至少一行有非空值时才渲染对应列(与 air 档位列并集同思路)
  const seaHas = (field: string) =>
    rows.some((r) => {
      const v = (r as Record<string, unknown>)[field];
      return v !== null && v !== undefined && v !== '';
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

  // 起运港：联运商均沪发，默认 PVG/SHANGHAI；只读展示（不参与编辑），让客户一眼看清从哪发。
  const originCol = {
    title: t('rateSheet.colOrigin'),
    key: 'origin',
    width: 72,
    render: (_: unknown, r: PreviewRow) => r.origin ?? '',
  };
  // 海运动态列：起运港/目的港/备注恒显；其余按该批次是否有数据出现。
  // 价格列绑结构化 container_*(入库读这些)；via/commodity/生效日可编辑(needs_review 行纠正目标)；
  // 起运港/币种/编码只读(标识性字段)。
  const seaCols = [
    originCol,
    textCol(t('rateSheet.colDestination'), 'destination'),
    ...(seaHas('via') ? [textCol(t('rateSheet.colVia'), 'via')] : []),
    textCol(t('rateSheet.colCarrier'), 'carrier'),
    ...(seaHas('container_20gp') ? [numCol(t('rateSheet.colFreight20'), 'container_20gp')] : []),
    ...(seaHas('container_40gp') ? [numCol(t('rateSheet.col40gp'), 'container_40gp')] : []),
    ...(seaHas('container_40hq') ? [numCol(t('rateSheet.col40hq'), 'container_40hq')] : []),
    ...(seaHas('container_45') ? [numCol(t('rateSheet.col45'), 'container_45')] : []),
    ...(seaHas('currency') ? [roCol(t('rateSheet.colCurrency'), 'currency', 64)] : []),
    ...(seaHas('valid_from') ? [textCol(t('rateSheet.colValidFrom'), 'valid_from')] : []),
    ...(seaHas('valid_to') ? [textCol(t('rateSheet.colValidTo'), 'valid_to')] : []),
    ...(seaHas('commodity') ? [textCol(t('rateSheet.colCommodity'), 'commodity')] : []),
    ...(seaHas('rate_level') ? [roCol(t('rateSheet.colRateLevel'), 'rate_level', 72)] : []),
    ...(seaHas('lss_cic') ? [numCol(t('rateSheet.colLss'), 'lss_cic')] : []),
    ...(seaHas('baf') ? [numCol(t('rateSheet.colBaf'), 'baf')] : []),
    ...(seaHas('transit_days') ? [numCol(t('rateSheet.colTransit'), 'transit_days')] : []),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
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

  // 入库按钮显隐：海运(FCL) 或 空运重量档(tier) 都有 DB 落地表可入库；
  // 空运周报价(Market Price day1-7) 无落地表，保持只下载、不显示入库。
  const showCommit = templateType === 'sea' || tierColumns.length > 0;

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
          {showCommit && (
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
            style={{ marginLeft: showCommit ? 8 : 'auto' }}
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
                scroll={{ x: 'max-content' }}
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
