import { Fragment, useEffect, useMemo, useState } from 'react';
import { Upload, Input, InputNumber, Table, Tooltip, message, Select, Spin, Modal } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
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

interface SeaSurcharge {
  code: string;
  amount_20?: number | null;
  amount_40?: number | null;
  currency?: string | null;
  payment?: string | null;
  included?: boolean;
  note?: string | null;
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
  cargo_class?: string | null;
  packing?: string | null;
  density?: string | null;
  day1?: number | string | null;
  day2?: number | string | null;
  day3?: number | string | null;
  day4?: number | string | null;
  day5?: number | string | null;
  day6?: number | string | null;
  day7?: number | string | null;
  // 档位源(EES/唯凯)：稀疏档位 dict(KG→价)。JSON 往返后键是字符串('45')。
  tier_prices?: Record<string, number | null>;
  surcharges?: SeaSurcharge[];
  remark?: string | null;
  needs_review?: boolean;
}

interface ApiLike {
  code: number;
  message?: string;
  data?: unknown;
}

// 单个文件解析超过这个行数即视为「超大输入」（典型为整本服务合约），
// 顶部给非阻断提示：做表为精选周运价表设计，合约建议走运价导入入库。
const LARGE_INPUT_THRESHOLD = 2000;

// 可编辑单元格：本地状态承接每次按键，仅在 onBlur 提交回父级 editedRows。
// 关键性能点——上万行时，受控 Input 每敲一键都 setState 父组件→antd 整表(12000+行)
// 重渲染(实测 ~150ms/键)，造成「打字到处卡」。改成单元格自管本地态后，敲键只重渲染
// 这一个格子，父组件与整表都不动，输入恒为即时；编辑值在失焦时一次性提交（下载/入库读 editedRows，行为不变）。
const EditableText = ({
  value,
  onCommit,
}: {
  value: string;
  onCommit: (v: string) => void;
}) => {
  const [local, setLocal] = useState(value);
  useEffect(() => {
    setLocal(value);
  }, [value]);
  return (
    <Input
      size="small"
      variant="outlined"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={() => {
        if (local !== value) onCommit(local);
      }}
    />
  );
};

const EditableNumber = ({
  value,
  onCommit,
}: {
  value: number | null | undefined;
  onCommit: (v: number | null) => void;
}) => {
  const [local, setLocal] = useState<number | null | undefined>(value);
  useEffect(() => {
    setLocal(value);
  }, [value]);
  return (
    <InputNumber
      size="small"
      variant="outlined"
      style={{ width: '100%' }}
      value={local}
      onChange={(v) => setLocal(v as number | null)}
      onBlur={() => {
        if (local !== value) onCommit(local ?? null);
      }}
    />
  );
};

export default function RateSheetBuilder() {
  const { t } = useTranslation();
  const [templateType, setTemplateType] = useState<string | null>('air');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [fileResults, setFileResults] = useState<FileResult[]>([]);
  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [summary, setSummary] = useState<{ total_rows: number; needs_review: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [specOpen, setSpecOpen] = useState(false);
  const [specFile, setSpecFile] = useState<File | null>(null);
  const [specDownloading, setSpecDownloading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [editedRows, setEditedRows] = useState<Record<number, Partial<PreviewRow>>>({});
  // air 做表会话级起运港 + 币种(默认 PVG/CNY；日本段选 NRT/JPY)。中国段默认不变。
  const [sessionOrigin, setSessionOrigin] = useState<string>('PVG');
  const [sessionCurrency, setSessionCurrency] = useState<string>('CNY');

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
  // 上传后 selectedRowKeys 会被全选（合约类文件可达上万条）。用 Set 做 O(1) 命中判断：
  // 否则 keptReview / buildFinalRows / rowClassName 里的 selectedRowKeys.includes() 套在
  // rows.filter() 上是 O(n²)，12744 行实测每次渲染 ~15ms(Chrome)。这只是次要项；
  // 真正的「打字到处卡」是受控单元格每键触发整表重渲染，已由 EditableText/EditableNumber 的
  // 本地态+失焦提交解决。两处一起改，渲染开销才回到可用区间。
  const selectedSet = useMemo(() => new Set(selectedRowKeys), [selectedRowKeys]);
  const keptReview = rows.filter(
    (r) => selectedSet.has(r._rid as number) && r.needs_review,
  ).length;

  // 超大输入（疑似服务合约）：取行数最多且超阈值的那个文件用于提示文案。
  const largeFile = fileResults
    .filter((f) => f.row_count > LARGE_INPUT_THRESHOLD)
    .sort((a, b) => b.row_count - a.row_count)[0];

  // 勾选保留 + 行内编辑后的最终行（下载与入库共用）
  const buildFinalRows = () =>
    rows
      .filter((r) => selectedSet.has(r._rid as number))
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
        // air：会话级起运港/币种盖到每行(commit_tier_rows 读行 origin/currency；手录 NRT/JPY 据此入库)。
        if (templateType === 'air') {
          merged.origin = sessionOrigin;
          merged.currency = sessionCurrency;
        }
        return merged;
      });

  const handleDownload = async () => {
    // 防重复点击：演示时客户连点会并发触发多次同步生成把后端拖死，进行中直接忽略后续点击
    if (!sessionId || downloading) return;
    setDownloading(true);
    try {
      const blob = await rateSheetApi.downloadFilled(sessionId, buildFinalRows());
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download =
        templateType === 'sea'
          ? 'ocean_sea_rate_sheet_filled.xlsx'
          : `${templateType ?? 'rate'}_rate_sheet_filled.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(t('rateSheet.downloadThenImportHint'));
    } catch {
      message.error(t('rateSheet.downloadFailed'));
    } finally {
      setDownloading(false);
    }
  };

  const handleSpecifiedDownload = async () => {
    if (!sessionId || !specFile || specDownloading) return;
    setSpecDownloading(true);
    try {
      const blob = await rateSheetApi.downloadIntoTemplate(
        sessionId,
        specFile,
        buildFinalRows(),
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${specFile.name.replace(/\.[^.]+$/, '')}_filled.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(t('rateSheet.specifiedDownloadDone'));
      setSpecOpen(false);
      setSpecFile(null);
    } catch {
      message.error(t('rateSheet.downloadFailed'));
    } finally {
      setSpecDownloading(false);
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

  const textCol = (title: string, field: keyof PreviewRow, width = 100) => ({
    title,
    key: field as string,
    width,
    render: (_: unknown, r: PreviewRow) => (
      <EditableText
        value={(valueOf(r, field) as string) ?? ''}
        onCommit={(v) => editCell(r._rid as number, field, v)}
      />
    ),
  });

  const numCol = (title: string, field: keyof PreviewRow) => ({
    title,
    key: field as string,
    width: 78,
    render: (_: unknown, r: PreviewRow) => (
      <EditableNumber
        value={valueOf(r, field) as number | null | undefined}
        onCommit={(v) => editCell(r._rid as number, field, v)}
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
    width: 74,
    render: (_: unknown, r: PreviewRow) => (
      <EditableNumber
        value={mergedTiers(r)[String(kg)] as number | null | undefined}
        onCommit={(v) => editTier(r, kg, v)}
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
    width: 40,
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
    width: 60,
    render: (_: unknown, r: PreviewRow) => r.origin ?? '',
  };
  // 海运动态列：起运港/目的港/备注恒显；其余按该批次是否有数据出现。
  // 价格列绑结构化 container_*(入库读这些)；via/commodity/生效日可编辑(needs_review 行纠正目标)；
  // 起运港/币种/编码只读(标识性字段)。
  // 海运结构化附加费 → 紧凑串：LSS 含 · EIS 150/300 到付 · 转运 稍等
  const fmtSurcharge = (s: SeaSurcharge): string => {
    if (s.included) return `${s.code} 含`;
    if (s.note) return `${s.code} ${s.note}`;
    const amt = [s.amount_20, s.amount_40].filter((v) => v !== null && v !== undefined).join('/');
    const pay = s.payment === 'collect' ? ' 到付' : s.payment === 'prepaid' ? ' 预付' : '';
    return amt ? `${s.code} ${amt}${pay}` : s.code;
  };
  // 任一行有非空 surcharges 数组才显该列（seaHas 对空数组会误判，单独判定）
  const seaHasSurcharges = rows.some((r) => Array.isArray(r.surcharges) && r.surcharges.length > 0);
  const surchargeCol = {
    title: t('rateSheet.colSurcharges'),
    key: 'surcharges',
    width: 190,
    render: (_: unknown, r: PreviewRow) => {
      const list = (r.surcharges ?? []) as SeaSurcharge[];
      if (!list.length) return '';
      const hasTbd = list.some((s) => !!s.note);
      return (
        <span style={hasTbd ? { color: '#d46b08' } : undefined}>
          {list.map(fmtSurcharge).join(' · ')}
        </span>
      );
    },
  };

  const seaCols = [
    originCol,
    textCol(t('rateSheet.colDestination'), 'destination', 96),
    ...(seaHas('via') ? [textCol(t('rateSheet.colVia'), 'via', 90)] : []),
    textCol(t('rateSheet.colCarrier'), 'carrier', 84),
    ...(seaHas('container_20gp') ? [numCol(t('rateSheet.colFreight20'), 'container_20gp')] : []),
    ...(seaHas('container_40gp') ? [numCol(t('rateSheet.col40gp'), 'container_40gp')] : []),
    ...(seaHas('container_40hq') ? [numCol(t('rateSheet.col40hq'), 'container_40hq')] : []),
    ...(seaHas('container_45') ? [numCol(t('rateSheet.col45'), 'container_45')] : []),
    ...(seaHas('currency') ? [roCol(t('rateSheet.colCurrency'), 'currency', 60)] : []),
    ...(seaHas('valid_from') ? [textCol(t('rateSheet.colValidFrom'), 'valid_from', 96)] : []),
    ...(seaHas('valid_to') ? [textCol(t('rateSheet.colValidTo'), 'valid_to', 96)] : []),
    ...(seaHas('commodity') ? [textCol(t('rateSheet.colCommodity'), 'commodity', 110)] : []),
    ...(seaHas('rate_level') ? [roCol(t('rateSheet.colRateLevel'), 'rate_level', 68)] : []),
    ...(seaHas('lss_cic') ? [numCol(t('rateSheet.colLss'), 'lss_cic')] : []),
    ...(seaHas('baf') ? [numCol(t('rateSheet.colBaf'), 'baf')] : []),
    ...(seaHasSurcharges ? [surchargeCol] : []),
    ...(seaHas('transit_days') ? [numCol(t('rateSheet.colTransit'), 'transit_days')] : []),
    textCol(t('rateSheet.colRemark'), 'remark', 150),
    reviewCol,
  ];
  const airDayCols = Array.from({ length: 7 }, (_, i) =>
    numCol(t('rateSheet.colDay', { n: i + 1 }), `day${i + 1}` as keyof PreviewRow),
  );
  const airCols = [
    // 严格按客户原件模板：不展示起运港列（起运港固定 PVG，由会话级设置写入行供入库；模板/下载也无此列）。
    textCol(t('rateSheet.colDestination'), 'destination', 96),
    // air 图片/文本多维列：该字段全表至少一行有值才显(seaHas 是泛型判定)；EES/周报行无 → 隐藏。
    ...(seaHas('carrier') ? [textCol(t('rateSheet.colCarrier'), 'carrier', 84)] : []),
    ...(seaHas('cargo_class') ? [textCol(t('rateSheet.colCargoClass'), 'cargo_class', 84)] : []),
    ...(seaHas('packing') ? [textCol(t('rateSheet.colPacking'), 'packing', 84)] : []),
    ...(seaHas('density') ? [textCol(t('rateSheet.colDensity'), 'density', 84)] : []),
    textCol(t('rateSheet.colService'), 'service', 130),
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
          {templateType === 'air' && (
            <div style={{ marginTop: 12, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <span>{t('rateSheet.colOrigin')}</span>
              <Select
                size="small"
                value={sessionOrigin}
                onChange={setSessionOrigin}
                style={{ width: 96 }}
                options={[{ value: 'PVG', label: 'PVG' }, { value: 'NRT', label: 'NRT' }]}
              />
              <span>{t('rateSheet.colCurrency')}</span>
              <Select
                size="small"
                value={sessionCurrency}
                onChange={setSessionCurrency}
                style={{ width: 96 }}
                options={[{ value: 'CNY', label: 'CNY' }, { value: 'JPY', label: 'JPY' }]}
              />
            </div>
          )}
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

          {uploading && (
            <div
              style={{
                marginTop: 14,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 16px',
                background: 'var(--fill-2, #f5f7fa)',
                border: '1px solid var(--border, #e5e8ee)',
                borderRadius: 8,
              }}
            >
              <Spin />
              <span style={{ color: 'var(--text-2, #555)' }}>{t('rateSheet.uploadingHint')}</span>
            </div>
          )}

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
          <button
            type="button"
            className="btn btn-primary btn-sm"
            style={{ marginLeft: 'auto', cursor: downloading ? 'wait' : undefined }}
            disabled={!summary || keptCount === 0 || downloading}
            onClick={handleDownload}
          >
            {downloading ? (
              <Spin indicator={<LoadingOutlined style={{ fontSize: 14, color: '#fff' }} spin />} />
            ) : (
              <Icon name="download" size={14} />
            )}
            {downloading ? t('rateSheet.downloading') : t('rateSheet.download')}
          </button>
          {templateType === 'sea' && (
            <button
              type="button"
              className="btn btn-sm"
              style={{ marginLeft: 8 }}
              disabled={!summary || keptCount === 0}
              onClick={() => setSpecOpen(true)}
            >
              <Icon name="download" size={14} />
              {t('rateSheet.specifiedDownload')}
            </button>
          )}
        </div>
        <div className="card-body">
          {summary || rows.length > 0 ? (
            <>
              {largeFile && (
                <div
                  style={{
                    marginBottom: 16,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                    padding: '10px 14px',
                    background: '#fff7e6',
                    border: '1px solid #ffd591',
                    borderRadius: 8,
                    color: '#ad6800',
                    lineHeight: 1.6,
                  }}
                >
                  <Icon name="review" size={16} />
                  <span>
                    {t('rateSheet.largeInputWarn', {
                      file: largeFile.name,
                      count: largeFile.row_count.toLocaleString(),
                    })}
                  </span>
                </div>
              )}
              <div
                className="kpi-grid"
                style={{ gridTemplateColumns: 'repeat(2, minmax(150px, 220px))', marginBottom: 18 }}
              >
                <div className="kpi">
                  <div className="kpi-label">
                    <span className="zh">{t('rateSheet.summaryTotal')}</span>
                  </div>
                  <div className="kpi-value">
                    {keptCount} <span style={{ color: 'var(--ink-400)', fontWeight: 400 }}>/ {summary?.total_rows || rows.length}</span>
                  </div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">
                    <span className="zh">{t('rateSheet.summaryReview')}</span>
                  </div>
                  <div className="kpi-value" style={{ color: keptReview > 0 ? 'var(--warn)' : undefined }}>
                    {keptReview} <span style={{ color: 'var(--ink-400)', fontWeight: 400 }}>/ {summary?.needs_review ?? 0}</span>
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
                tableLayout="fixed"
                rowKey={(r: PreviewRow) => r._rid as number}
                rowSelection={{
                  selectedRowKeys,
                  onChange: (keys) => setSelectedRowKeys(keys as number[]),
                  columnWidth: 36,
                }}
                columns={previewCols}
                dataSource={rows}
                rowClassName={(r: PreviewRow) =>
                  !selectedSet.has(r._rid as number)
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

      <Modal
        open={specOpen}
        title={t('rateSheet.specifiedDownload')}
        onCancel={() => {
          setSpecOpen(false);
          setSpecFile(null);
        }}
        onOk={handleSpecifiedDownload}
        okText={t('rateSheet.specifiedDownloadConfirm')}
        okButtonProps={{ disabled: !specFile, loading: specDownloading }}
        confirmLoading={specDownloading}
      >
        <p style={{ marginBottom: 12 }}>{t('rateSheet.specifiedDownloadHint')}</p>
        <Upload
          accept=".xlsx"
          maxCount={1}
          beforeUpload={(file) => {
            setSpecFile(file as unknown as File);
            return false;
          }}
          onRemove={() => setSpecFile(null)}
          fileList={
            specFile
              ? ([{ uid: '-1', name: specFile.name } as UploadFile])
              : []
          }
        >
          <button type="button" className="btn btn-sm">
            {t('rateSheet.specifiedDownloadPick')}
          </button>
        </Upload>
      </Modal>
    </div>
  );
}
