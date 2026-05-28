import { useEffect, useState } from 'react';
import {
  Card,
  Segmented,
  Upload,
  Button,
  Input,
  InputNumber,
  Table,
  Tag,
  message,
  Space,
  Row,
  Col,
  Statistic,
  Empty,
  Typography,
} from 'antd';
import type { UploadFile } from 'antd';
import { useTranslation } from 'react-i18next';
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

  const handleDownload = async () => {
    if (!sessionId) return;
    const finalRows = rows
      .filter((r) => selectedRowKeys.includes(r._rid as number))
      .map((r) => {
        const merged = { ...r, ...editedRows[r._rid as number] };
        delete (merged as { _rid?: number })._rid;
        return merged;
      });
    try {
      const blob = await rateSheetApi.downloadFilled(sessionId, finalRows);
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

  const statusTag = (status: string) => {
    const map: Record<string, { color: string; key: string }> = {
      parsed: { color: 'green', key: 'rateSheet.statusParsed' },
      skipped: { color: 'orange', key: 'rateSheet.statusSkipped' },
      error: { color: 'red', key: 'rateSheet.statusError' },
    };
    const m = map[status] || { color: 'default', key: status };
    return <Tag color={m.color}>{t(m.key)}</Tag>;
  };

  const fileColumns = [
    { title: t('rateSheet.fileName'), dataIndex: 'name', key: 'name' },
    { title: t('rateSheet.sourceType'), dataIndex: 'source_type', key: 'source_type' },
    { title: t('rateSheet.status'), dataIndex: 'status', key: 'status', render: statusTag },
    { title: t('rateSheet.rowCount'), dataIndex: 'row_count', key: 'row_count' },
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
        value={(valueOf(r, field) as string) ?? ''}
        onChange={(e) => editCell(r._rid as number, field, e.target.value)}
      />
    ),
  });

  const numCol = (title: string, field: keyof PreviewRow) => ({
    title,
    key: field as string,
    render: (_: unknown, r: PreviewRow) => (
      <InputNumber
        size="small"
        style={{ width: '100%' }}
        value={valueOf(r, field) as number | null | undefined}
        onChange={(v) => editCell(r._rid as number, field, v)}
      />
    ),
  });

  const reviewCol = {
    title: t('rateSheet.needsReview'),
    key: 'needs_review',
    render: (_: unknown, r: PreviewRow) =>
      r.needs_review ? <Tag color="orange">{t('rateSheet.needsReview')}</Tag> : null,
  };

  const seaCols = [
    textCol(t('rateSheet.colDestination'), 'destination'),
    textCol(t('rateSheet.colCarrier'), 'carrier'),
    numCol(t('rateSheet.colFreight20'), 'freight_20'),
    numCol(t('rateSheet.colFreight40'), 'freight_40'),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
  const airCols = [
    textCol(t('rateSheet.colDestination'), 'destination'),
    textCol(t('rateSheet.colService'), 'service'),
    ...Array.from({ length: 7 }, (_, i) =>
      numCol(t('rateSheet.colDay', { n: i + 1 }), `day${i + 1}` as keyof PreviewRow),
    ),
    textCol(t('rateSheet.colRemark'), 'remark'),
    reviewCol,
  ];
  const previewCols = templateType === 'air' ? airCols : seaCols;

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3} style={{ marginBottom: 4 }}>
        {t('rateSheet.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary">{t('rateSheet.subtitle')}</Typography.Paragraph>

      <Card title={t('rateSheet.step1')} style={{ marginBottom: 16 }}>
        <Segmented
          value={templateType ?? undefined}
          onChange={(v) => onSelectTemplate(String(v))}
          options={[
            { label: t('rateSheet.templateAir'), value: 'air' },
            { label: t('rateSheet.templateSea'), value: 'sea' },
          ]}
        />
        {!templateType && (
          <Typography.Text type="secondary" style={{ marginLeft: 16 }}>
            {t('rateSheet.selectTemplate')}
          </Typography.Text>
        )}
      </Card>

      <Card title={t('rateSheet.step2')} style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Upload
            multiple
            beforeUpload={() => false}
            fileList={fileList}
            onChange={({ fileList: fl }) => setFileList(fl)}
            disabled={!sessionId}
          >
            <Button disabled={!sessionId}>{t('rateSheet.uploadHint')}</Button>
          </Upload>
          <Button
            type="primary"
            loading={uploading}
            disabled={!sessionId || fileList.length === 0}
            onClick={handleUpload}
          >
            {t('rateSheet.uploadBtn')}
          </Button>
          {fileResults.length > 0 && (
            <Table
              size="small"
              rowKey={(_, i) => String(i)}
              columns={fileColumns}
              dataSource={fileResults}
              pagination={false}
            />
          )}
        </Space>
      </Card>

      <Card
        title={t('rateSheet.step3')}
        extra={
          <Button type="primary" disabled={!summary || keptCount === 0} onClick={handleDownload}>
            {t('rateSheet.download')}
          </Button>
        }
      >
        {summary ? (
          <>
            <Row gutter={24} style={{ marginBottom: 16 }}>
              <Col>
                <Statistic title={t('rateSheet.summaryTotal')} value={`${keptCount} / ${summary.total_rows}`} />
              </Col>
              <Col>
                <Statistic
                  title={t('rateSheet.summaryReview')}
                  value={`${keptReview} / ${summary.needs_review}`}
                  valueStyle={{ color: keptReview > 0 ? '#F79009' : undefined }}
                />
              </Col>
            </Row>
            <Table
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
          <Empty description={t('rateSheet.previewTitle')} />
        )}
      </Card>
    </div>
  );
}
