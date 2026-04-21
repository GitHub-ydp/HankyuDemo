import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Progress,
  Row,
  Space,
  Statistic,
  Steps,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  RocketOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { pkgApi } from '../services/api';

const { Title, Text } = Typography;

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

interface FillResultItem {
  row: number;
  origin: string;
  destination: string;
  cost_type: string;
  status: 'filled' | 'no_rate' | 'already_filled' | 'skipped';
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
  if (value === 'AIR_FREIGHT') {
    return t('pkg.costTypes.airFreight');
  }
  if (value === 'LOCAL_DELIVERY') {
    return t('pkg.costTypes.localDelivery');
  }
  return value;
};

const currencySymbol = (currency: string) => {
  const symbols: Record<string, string> = {
    JPY: '¥',
    CNY: '¥',
    USD: '$',
    EUR: '€',
  };
  return symbols[currency] || currency;
};

function renderStatusTag(status: FillResultItem['status'], confidence: number, t: (key: string, options?: Record<string, unknown>) => string) {
  if (status === 'filled') {
    const label = confidence >= 0.9
      ? t('pkg.highConfidence')
      : confidence >= 0.7
        ? t('pkg.mediumConfidence')
        : t('pkg.lowConfidence');
    const color = confidence >= 0.9 ? 'green' : confidence >= 0.7 ? 'blue' : 'orange';
    return (
      <Space>
        <Tag color={color}>{label}</Tag>
        <Text type="secondary" style={{ fontSize: 12 }}>{Math.round(confidence * 100)}%</Text>
      </Space>
    );
  }
  if (status === 'no_rate') {
    return <Tag color="red">{t('pkg.noMatchedRate')}</Tag>;
  }
  if (status === 'already_filled') {
    return <Tag color="purple">{t('pkg.alreadyFilled')}</Tag>;
  }
  return <Tag>{t('pkg.skipped')}</Tag>;
}

export default function PkgAutoFill() {
  const { t } = useTranslation();
  const [currentStep, setCurrentStep] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [filling, setFilling] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [fillSummary, setFillSummary] = useState<FillSummary | null>(null);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const res = await pkgApi.upload(file) as { data: { session_id: string; parse_result: ParseResult } };
      setSessionId(res.data.session_id);
      setParseResult(res.data.parse_result);
      setCurrentStep(1);
      message.success(t('pkg.parseSuccess', {
        sections: res.data.parse_result.total_sections,
        lanes: res.data.parse_result.total_lanes,
      }));
    } catch (error: unknown) {
      message.error(t('pkg.parseFailed', {
        message: error instanceof Error ? error.message : t('common.unknownError'),
      }));
    } finally {
      setUploading(false);
    }
  };

  const handleFill = async () => {
    if (!sessionId) {
      return;
    }

    setFilling(true);
    try {
      const res = await pkgApi.fill(sessionId) as { data: FillSummary };
      setFillSummary(res.data);
      setCurrentStep(2);
      message.success(t('pkg.fillSuccess', {
        filled: res.data.filled_count,
        total: res.data.total_lanes,
      }));
    } catch (error: unknown) {
      message.error(t('pkg.fillFailed', {
        message: error instanceof Error ? error.message : t('common.unknownError'),
      }));
    } finally {
      setFilling(false);
    }
  };

  const handleDownload = () => {
    if (sessionId) {
      window.open(pkgApi.downloadUrl(sessionId), '_blank');
    }
  };

  const handleReset = () => {
    setCurrentStep(0);
    setSessionId(null);
    setParseResult(null);
    setFillSummary(null);
  };

  const parseColumns = [
    { title: t('pkg.row'), dataIndex: 'row', width: 50 },
    {
      title: t('pkg.origin'),
      dataIndex: 'origin',
      width: 140,
      render: (value: string) => <Text style={{ fontSize: 13 }}>{value?.replace(/\n/g, ' ')}</Text>,
    },
    { title: t('pkg.destination'), dataIndex: 'destination', width: 180 },
    {
      title: t('pkg.type'),
      dataIndex: 'cost_type',
      width: 120,
      render: (value: string) => <Tag color={value === 'AIR_FREIGHT' ? 'blue' : 'cyan'}>{costTypeLabel(value, t)}</Tag>,
    },
    {
      title: t('pkg.currency'),
      dataIndex: 'currency',
      width: 70,
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: t('pkg.currentPrice'),
      dataIndex: 'unit_price',
      width: 110,
      render: (value: number | null, row: Lane) => (
        value !== null && value !== 0
          ? <Text strong>{currencySymbol(row.currency)}{value}</Text>
          : <Text type="secondary">{t('pkg.waitingFill')}</Text>
      ),
    },
    {
      title: t('pkg.leadTime'),
      dataIndex: 'lead_time',
      width: 90,
      render: (value: string | null) => value || <Text type="secondary">{t('common.notAvailable')}</Text>,
    },
  ];

  const fillColumns = [
    { title: t('pkg.row'), dataIndex: 'row', width: 50 },
    {
      title: t('pkg.origin'),
      dataIndex: 'origin',
      width: 130,
      render: (value: string) => <Text style={{ fontSize: 13 }}>{value?.replace(/\n/g, ' ')}</Text>,
    },
    { title: t('pkg.destination'), dataIndex: 'destination', width: 170 },
    {
      title: t('pkg.type'),
      dataIndex: 'cost_type',
      width: 110,
      render: (value: string) => (
        <Tag color={value === 'AIR_FREIGHT' ? 'blue' : 'cyan'} style={{ fontSize: 11 }}>
          {costTypeLabel(value, t)}
        </Tag>
      ),
    },
    {
      title: t('pkg.status'),
      dataIndex: 'status',
      width: 130,
      render: (_: unknown, row: FillResultItem) => renderStatusTag(row.status, row.confidence, t),
    },
    {
      title: t('pkg.originalValue'),
      dataIndex: 'original_price',
      width: 90,
      render: (value: number | null) => (
        value !== null && value !== 0
          ? <Text delete type="secondary">{value}</Text>
          : <Text type="secondary">{t('common.notAvailable')}</Text>
      ),
    },
    {
      title: t('pkg.filledValue'),
      dataIndex: 'unit_price',
      width: 90,
      render: (value: number | null, row: FillResultItem) => (
        row.status === 'filled' && value !== null
          ? <Text strong style={{ color: '#52c41a' }}>{value}</Text>
          : <Text type="secondary">{t('common.notAvailable')}</Text>
      ),
    },
    {
      title: t('pkg.leadTime'),
      dataIndex: 'lead_time',
      width: 90,
      render: (value: string | null, row: FillResultItem) => (
        row.status === 'filled' && value
          ? <Text>{value}</Text>
          : <Text type="secondary">{t('common.notAvailable')}</Text>
      ),
    },
    {
      title: t('pkg.carrierRoute'),
      dataIndex: 'carrier_route',
      ellipsis: true,
      render: (value: string | null, row: FillResultItem) => (
        row.status === 'filled' && value && value !== '－'
          ? <Tooltip title={value}><Text style={{ fontSize: 12 }}>{value}</Text></Tooltip>
          : <Text type="secondary">{t('common.notAvailable')}</Text>
      ),
    },
  ];

  const stats = useMemo(() => {
    if (!fillSummary) {
      return null;
    }

    const fillRate = fillSummary.total_lanes > 0
      ? Math.round((fillSummary.filled_count / fillSummary.total_lanes) * 100)
      : 0;
    const filledRows = fillSummary.results.filter((item) => item.status === 'filled');
    const avgConfidence = filledRows.length > 0
      ? Math.round((filledRows.reduce((sum, item) => sum + item.confidence, 0) / filledRows.length) * 100)
      : 0;

    return { fillRate, avgConfidence };
  }, [fillSummary]);

  return (
    <div>
      <Title level={4}>
        <RocketOutlined /> {t('pkg.title')}
      </Title>
      <Text type="secondary" style={{ marginBottom: 24, display: 'block' }}>
        {t('pkg.subtitle')}
      </Text>

      <Steps
        current={currentStep}
        style={{ marginBottom: 32 }}
        items={[
          { title: t('pkg.stepUpload'), description: t('pkg.stepUploadDesc') },
          { title: t('pkg.stepReview'), description: t('pkg.stepReviewDesc') },
          { title: t('pkg.stepDownload'), description: t('pkg.stepDownloadDesc') },
        ]}
      />

      {currentStep === 0 && (
        <Card>
          <Upload.Dragger
            accept=".xlsx,.xls"
            maxCount={1}
            showUploadList={false}
            beforeUpload={(file) => {
              handleUpload(file);
              return false;
            }}
            disabled={uploading}
          >
            <p className="ant-upload-drag-icon">
              <FileExcelOutlined style={{ fontSize: 48, color: '#52c41a' }} />
            </p>
            <p className="ant-upload-text">
              {uploading ? t('pkg.uploading') : t('pkg.uploadDragText')}
            </p>
            <p className="ant-upload-hint">{t('pkg.uploadHint')}</p>
          </Upload.Dragger>
        </Card>
      )}

      {currentStep === 1 && parseResult && (
        <div>
          <Alert
            message={t('pkg.parseDone', { filename: parseResult.filename })}
            description={t('pkg.parseSummary', {
              period: parseResult.period,
              sheet: parseResult.sheet_name,
              sections: parseResult.total_sections,
              lanes: parseResult.total_lanes,
            })}
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
          />

          <Collapse
            defaultActiveKey={parseResult.sections.map((_, index) => String(index))}
            style={{ marginBottom: 16 }}
            items={parseResult.sections.map((section, index) => ({
              key: String(index),
              label: (
                <Space>
                  <Tag color="blue">{section.origin_code}</Tag>
                  <Text strong>{section.origin.replace(/\n/g, ' ')}</Text>
                  <Text type="secondary">({section.currency_unit})</Text>
                  <Badge count={section.lanes.length} style={{ backgroundColor: '#1677ff' }} />
                </Space>
              ),
              children: (
                <Table
                  dataSource={section.lanes}
                  columns={parseColumns}
                  rowKey="row"
                  size="small"
                  pagination={false}
                />
              ),
            }))}
          />

          <Space style={{ marginTop: 16 }}>
            <Button
              type="primary"
              size="large"
              icon={<ThunderboltOutlined />}
              loading={filling}
              onClick={handleFill}
            >
              {t('pkg.filledAction')}
            </Button>
            <Button onClick={handleReset}>{t('pkg.reupload')}</Button>
          </Space>
        </div>
      )}

      {currentStep === 2 && fillSummary && stats && (
        <div>
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <Card>
                <Statistic title={t('pkg.totalLanes')} value={fillSummary.total_lanes} />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title={t('pkg.filledCount')}
                  value={fillSummary.filled_count}
                  valueStyle={{ color: '#3f8600' }}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic title={t('pkg.fillRate')} value={stats.fillRate} suffix="%" valueStyle={{ color: '#1677ff' }} />
                <Progress percent={stats.fillRate} showInfo={false} size="small" />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title={t('pkg.avgConfidence')}
                  value={stats.avgConfidence}
                  suffix="%"
                  valueStyle={{ color: stats.avgConfidence >= 80 ? '#3f8600' : '#cf1322' }}
                />
              </Card>
            </Col>
          </Row>

          {fillSummary.no_rate_count > 0 && (
            <Alert
              message={t('pkg.noRateWarning', { count: fillSummary.no_rate_count })}
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          <Card title={t('pkg.details')} style={{ marginBottom: 16 }}>
            <Table
              dataSource={fillSummary.results}
              columns={fillColumns}
              rowKey="row"
              size="small"
              pagination={false}
              scroll={{ x: 1100 }}
            />
          </Card>

          <Space size="large">
            <Button type="primary" size="large" icon={<DownloadOutlined />} onClick={handleDownload}>
              {t('pkg.downloadFile')}
            </Button>
            <Button size="large" onClick={handleReset}>
              {t('pkg.newFile')}
            </Button>
          </Space>
        </div>
      )}
    </div>
  );
}
