import { useEffect, useState } from 'react';
import {
  Card,
  Segmented,
  Upload,
  Button,
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
  destination?: string;
  carrier?: string;
  freight_20?: number | string | null;
  freight_40?: number | string | null;
  service?: string;
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
          setRows((pv.data as { rows: PreviewRow[] }).rows);
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

  const handleDownload = () => {
    if (!sessionId) return;
    window.open(rateSheetApi.downloadUrl(sessionId), '_blank');
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
    { title: t('rateSheet.colRemark'), dataIndex: 'message', key: 'message' },
  ];

  const baseCols = [
    { title: t('rateSheet.colDestination'), dataIndex: 'destination', key: 'destination' },
    { title: t('rateSheet.colCarrier'), dataIndex: 'carrier', key: 'carrier' },
  ];
  const seaCols = [
    ...baseCols,
    { title: t('rateSheet.colFreight20'), dataIndex: 'freight_20', key: 'freight_20' },
    { title: t('rateSheet.colFreight40'), dataIndex: 'freight_40', key: 'freight_40' },
    { title: t('rateSheet.colRemark'), dataIndex: 'remark', key: 'remark' },
    {
      title: t('rateSheet.needsReview'),
      key: 'needs_review',
      render: (_: unknown, r: PreviewRow) =>
        r.needs_review ? <Tag color="orange">{t('rateSheet.needsReview')}</Tag> : null,
    },
  ];
  const airCols = [
    ...baseCols,
    { title: t('rateSheet.colService'), dataIndex: 'service', key: 'service' },
    { title: t('rateSheet.colRemark'), dataIndex: 'remark', key: 'remark' },
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
          <Button type="primary" disabled={!summary || summary.total_rows === 0} onClick={handleDownload}>
            {t('rateSheet.download')}
          </Button>
        }
      >
        {summary ? (
          <>
            <Row gutter={24} style={{ marginBottom: 16 }}>
              <Col>
                <Statistic title={t('rateSheet.summaryTotal')} value={summary.total_rows} />
              </Col>
              <Col>
                <Statistic
                  title={t('rateSheet.summaryReview')}
                  value={summary.needs_review}
                  valueStyle={{ color: summary.needs_review > 0 ? '#F79009' : undefined }}
                />
              </Col>
            </Row>
            <Table
              size="small"
              rowKey={(_, i) => String(i)}
              columns={previewCols}
              dataSource={rows}
              rowClassName={(r: PreviewRow) => (r.needs_review ? 'row-needs-review' : '')}
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
