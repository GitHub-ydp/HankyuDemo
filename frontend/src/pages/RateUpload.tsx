import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  List,
  message,
  Result,
  Space,
  Spin,
  Steps,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd';
import {
  CloudDownloadOutlined,
  FileExcelOutlined,
  InboxOutlined,
  MailOutlined,
  PaperClipOutlined,
  PictureOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { aiParseApi, rateApi } from '../services/api';
import type { ParsePreviewRow } from '../types';

const { Dragger } = Upload;
const { TextArea } = Input;

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

  const handleParseSuccess = (res: any) => {
    if (res.code !== 0 && res.code !== undefined) {
      message.error(res.message || t('upload.parseFailed'));
      return;
    }

    const data = res.data || res;
    if (!data.total_rows || data.total_rows === 0) {
      message.warning(data.message || t('upload.noRatesExtracted'));
      if (data.warnings?.length) {
        message.warning(data.warnings[0]);
      }
      return;
    }

    setParseResult(data);
    setStep(1);
    message.success(t('upload.parseCompleted', { count: data.total_rows }));
  };

  const handleExcelUpload = async (file: File) => {
    setLoading(true);
    try {
      const res: any = await rateApi.uploadAndParse(file);
      handleParseSuccess(res);
    } catch (error: any) {
      message.error(error.message || t('upload.uploadFailed'));
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
      const res: any = await aiParseApi.parseEmailText(emailText);
      handleParseSuccess(res);
    } catch (error: any) {
      message.error(error.message || t('upload.aiParseFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleFetchInbox = async () => {
    setInboxLoading(true);
    try {
      const res: any = await aiParseApi.listInboxEmails({ limit: 20 });
      if (res.code !== 0 && res.code !== undefined) {
        message.error(res.message || t('upload.inboxFetchFailed'));
        return;
      }

      const data = res.data || res;
      setInboxEmails(data.emails || []);
      setInboxFetchedAt(new Date().toLocaleTimeString());
      if (!data.emails?.length) {
        message.info(t('upload.inboxEmpty'));
      } else {
        message.success(t('upload.inboxFetched', { count: data.emails.length }));
      }
    } catch (error: any) {
      message.error(error.message || t('upload.inboxFetchFailed'));
    } finally {
      setInboxLoading(false);
    }
  };

  const handleParseInboxEmail = async (item: InboxEmailItem) => {
    setParsingKey(item.cache_key);
    setLoading(true);
    try {
      const res: any = await aiParseApi.parseInboxEmail(item.cache_key);
      handleParseSuccess(res);
    } catch (error: any) {
      message.error(error.message || t('upload.parseInboxFailed'));
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
      const res: any = await aiParseApi.parseInboxAttachment(item.cache_key, image.index);
      handleParseSuccess(res);
    } catch (error: any) {
      message.error(error.message || t('upload.parseAttachmentFailed'));
    } finally {
      setLoading(false);
      setParsingAttachKey('');
    }
  };

  const handleMsgUpload = async (file: File) => {
    setMsgUploading(true);
    try {
      const res: any = await aiParseApi.uploadMsgFile(file);
      if (res.code !== 0 && res.code !== undefined) {
        message.error(res.message || t('upload.msgUploadFailed'));
        return;
      }
      const data = res.data || res;
      // 复用 InboxEmailItem 结构（后端已经按一致 shape 返回）
      setLocalMsgItem(data as InboxEmailItem);
      message.success(t('upload.msgUploadSuccess', { subject: data.subject || data.file_name || '' }));
    } catch (error: any) {
      message.error(error.message || t('upload.msgUploadFailed'));
    } finally {
      setMsgUploading(false);
    }
  };

  const handleImageUpload = async (file: File) => {
    setLoading(true);
    try {
      const res: any = await aiParseApi.parseWechatImage(file, imageContext);
      handleParseSuccess(res);
    } catch (error: any) {
      message.error(error.message || t('upload.parseImageFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!parseResult) {
      return;
    }

    setLoading(true);
    try {
      const isAiSource = ['email_text', 'wechat_image', 'inbox_email', 'inbox_attachment'].includes(parseResult.source_type);
      const confirmFn = isAiSource ? aiParseApi.confirmImport : rateApi.confirmImport;
      const res: any = await confirmFn(parseResult.batch_id);

      if (res.code !== 0 && res.code !== undefined) {
        message.error(res.message || t('upload.importFailed'));
        return;
      }

      const data = res.data || res;
      setImportResult(data);
      setStep(2);
      message.success(t('upload.importSuccess', { count: data.records_imported }));
    } catch (error: any) {
      message.error(error.message || t('upload.importFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setStep(0);
    setParseResult(null);
    setImportResult(null);
  };

  const previewColumns = [
    { title: t('rates.originPort'), dataIndex: 'origin_port', width: 140 },
    { title: t('rates.destinationPort'), dataIndex: 'destination_port', width: 140 },
    { title: t('rates.shippingLine'), dataIndex: 'carrier', width: 100 },
    { title: '20GP', dataIndex: 'container_20gp', width: 80, render: (value: string) => (value ? `$${value}` : '-') },
    { title: '40GP', dataIndex: 'container_40gp', width: 80, render: (value: string) => (value ? `$${value}` : '-') },
    { title: '40HQ', dataIndex: 'container_40hq', width: 80, render: (value: string) => (value ? `$${value}` : '-') },
    { title: '45ft', dataIndex: 'container_45', width: 80, render: (value: string) => (value ? `$${value}` : '-') },
    {
      title: 'BAF(20/40)',
      width: 100,
      render: (_: unknown, row: ParsePreviewRow) => {
        if (!row.baf_20 && !row.baf_40) {
          return '-';
        }
        return `${row.baf_20 || '0'}/${row.baf_40 || '0'}`;
      },
    },
    { title: t('rates.effectiveDate'), dataIndex: 'valid_from', width: 110 },
    {
      title: t('rates.transitDays'),
      dataIndex: 'transit_days',
      width: 90,
      render: (value: string) => (value ? t('common.days', { count: value }) : t('common.notAvailable')),
    },
    { title: t('rates.remarks'), dataIndex: 'remarks', ellipsis: true },
  ];

  const sourceTag = (type: string) => {
    const map: Record<string, { color: string; label: string }> = {
      excel: { color: 'green', label: t('rates.sources.excel') },
      email_text: { color: 'blue', label: t('rates.sources.email_text') },
      inbox_email: { color: 'geekblue', label: t('rates.sources.inbox_email') },
      wechat_image: { color: 'orange', label: t('rates.sources.wechat_image') },
      inbox_attachment: { color: 'purple', label: t('rates.sources.inbox_attachment') },
    };
    const current = map[type] || { color: 'default', label: type };
    return <Tag color={current.color}>{current.label}</Tag>;
  };

  const isAiTab = activeTab === 'email' || activeTab === 'wechat' || activeTab === 'inbox';

  return (
    <div>
      <Typography.Title level={3}>{t('upload.title')}</Typography.Title>

      <Steps
        current={step}
        style={{ marginBottom: 24 }}
        items={[
          { title: t('upload.stepSelectSource') },
          { title: t('upload.stepPreview') },
          { title: t('upload.stepDone') },
        ]}
      />

      <Spin spinning={loading} tip={isAiTab ? t('upload.aiParsing') : undefined}>
        {step === 0 && (
          <Card>
            <Tabs
              activeKey={activeTab}
              onChange={(key) => setActiveTab(key as SourceTab)}
              items={[
                {
                  key: 'excel',
                  label: <span><FileExcelOutlined /> {t('upload.tabExcel')}</span>,
                  children: (
                    <Dragger
                      accept=".xlsx,.xls,.csv"
                      showUploadList={false}
                      customRequest={({ file }) => handleExcelUpload(file as File)}
                    >
                      <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                      <p className="ant-upload-text">{t('upload.excelDragText')}</p>
                      <p className="ant-upload-hint">
                        {t('upload.excelHint')}
                        <br />
                        {t('upload.excelHint2')}
                      </p>
                    </Dragger>
                  ),
                },
                {
                  key: 'inbox',
                  label: <span><CloudDownloadOutlined /> {t('upload.tabInbox')}</span>,
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      <Alert
                        type="info"
                        showIcon
                        message={t('upload.inboxInfo')}
                        description={(
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {t('upload.inboxInfoDesc')}
                          </Typography.Text>
                        )}
                      />

                      <Space>
                        <Button
                          type="primary"
                          icon={<CloudDownloadOutlined />}
                          loading={inboxLoading}
                          onClick={handleFetchInbox}
                        >
                          {inboxEmails.length > 0 ? t('upload.refetchInbox') : t('upload.fetchInbox')}
                        </Button>
                        {inboxFetchedAt && (
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {t('upload.lastFetchTime', { time: inboxFetchedAt })}
                          </Typography.Text>
                        )}
                      </Space>

                      {inboxEmails.length === 0 ? (
                        <Empty description={inboxLoading ? t('upload.fetchingInbox') : t('upload.clickFetchInbox')} />
                      ) : (
                        <List<InboxEmailItem>
                          bordered
                          dataSource={inboxEmails}
                          rowKey={(item) => item.cache_key}
                          pagination={{ pageSize: 8, size: 'small' }}
                          renderItem={(item) => (
                            <List.Item
                              actions={[
                                <Button
                                  key="parse"
                                  type="primary"
                                  size="small"
                                  icon={<ThunderboltOutlined />}
                                  loading={parsingKey === item.cache_key}
                                  disabled={loading && parsingKey !== item.cache_key}
                                  onClick={() => handleParseInboxEmail(item)}
                                >
                                  {t('upload.parseBody')}
                                </Button>,
                              ]}
                            >
                              <List.Item.Meta
                                title={(
                                  <Space size="small" wrap>
                                    <strong>{item.subject || t('common.unknownSubject')}</strong>
                                    {item.has_attachment && (
                                      <Tag icon={<PaperClipOutlined />} color="orange">
                                        {t('upload.attachments', { count: item.attachment_names.length })}
                                      </Tag>
                                    )}
                                    {item.folder && <Tag>{item.folder}</Tag>}
                                  </Space>
                                )}
                                description={(
                                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                      <MailOutlined /> {item.from_name || item.from} | {(item.date || '').slice(0, 16).replace('T', ' ')}
                                    </Typography.Text>
                                    <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0, fontSize: 12 }}>
                                      {item.snippet || t('common.emptyContent')}
                                    </Typography.Paragraph>
                                    {item.image_attachments.length > 0 && (
                                      <Space size={6} wrap>
                                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                          <PictureOutlined /> {t('upload.imageAttachments')}
                                        </Typography.Text>
                                        {item.image_attachments.map((image) => {
                                          const key = `${item.cache_key}_${image.index}`;
                                          return (
                                            <Button
                                              key={key}
                                              size="small"
                                              icon={<ThunderboltOutlined />}
                                              loading={parsingAttachKey === key}
                                              disabled={loading && parsingAttachKey !== key}
                                              onClick={() => handleParseAttachment(item, image)}
                                            >
                                              {image.filename || `image-${image.index + 1}`}
                                              <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
                                                ({Math.round(image.size / 1024)}KB)
                                              </Typography.Text>
                                            </Button>
                                          );
                                        })}
                                      </Space>
                                    )}
                                  </Space>
                                )}
                              />
                            </List.Item>
                          )}
                        />
                      )}
                    </Space>
                  ),
                },
                {
                  key: 'email',
                  label: <span><MailOutlined /> {t('upload.tabEmailText')}</span>,
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      <Alert type="info" showIcon message={t('upload.emailTextInfo')} />

                      {/* === 离线 .msg 文件上传区 === */}
                      <Dragger
                        accept=".msg"
                        showUploadList={false}
                        disabled={msgUploading}
                        customRequest={({ file }) => handleMsgUpload(file as File)}
                      >
                        <p className="ant-upload-drag-icon"><MailOutlined /></p>
                        <p className="ant-upload-text">
                          {msgUploading ? t('upload.msgUploading') : t('upload.msgDragText')}
                        </p>
                        <p className="ant-upload-hint">{t('upload.msgHint')}</p>
                      </Dragger>

                      {localMsgItem && (
                        <List<InboxEmailItem>
                          bordered
                          dataSource={[localMsgItem]}
                          rowKey={(item) => item.cache_key}
                          renderItem={(item) => (
                            <List.Item
                              actions={[
                                <Button
                                  key="parse"
                                  type="primary"
                                  size="small"
                                  icon={<ThunderboltOutlined />}
                                  loading={parsingKey === item.cache_key}
                                  disabled={loading && parsingKey !== item.cache_key}
                                  onClick={() => handleParseInboxEmail(item)}
                                >
                                  {t('upload.parseBody')}
                                </Button>,
                                <Button
                                  key="clear"
                                  size="small"
                                  onClick={() => setLocalMsgItem(null)}
                                >
                                  {t('common.cancel')}
                                </Button>,
                              ]}
                            >
                              <List.Item.Meta
                                title={(
                                  <Space size="small" wrap>
                                    <strong>{item.subject || t('common.unknownSubject')}</strong>
                                    <Tag color="purple">.msg</Tag>
                                    {item.has_attachment && (
                                      <Tag icon={<PaperClipOutlined />} color="orange">
                                        {t('upload.attachments', { count: item.attachment_names.length })}
                                      </Tag>
                                    )}
                                  </Space>
                                )}
                                description={(
                                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                      <MailOutlined /> {item.from_name || item.from} | {(item.date || '').slice(0, 16).replace('T', ' ')}
                                    </Typography.Text>
                                    <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0, fontSize: 12 }}>
                                      {item.snippet || t('common.emptyContent')}
                                    </Typography.Paragraph>
                                    {item.image_attachments.length > 0 && (
                                      <Space size={6} wrap>
                                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                          <PictureOutlined /> {t('upload.imageAttachments')}
                                        </Typography.Text>
                                        {item.image_attachments.map((image) => {
                                          const key = `${item.cache_key}_${image.index}`;
                                          return (
                                            <Button
                                              key={key}
                                              size="small"
                                              icon={<ThunderboltOutlined />}
                                              loading={parsingAttachKey === key}
                                              disabled={loading && parsingAttachKey !== key}
                                              onClick={() => handleParseAttachment(item, image)}
                                            >
                                              {image.filename || `image-${image.index + 1}`}
                                              <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
                                                ({Math.round(image.size / 1024)}KB)
                                              </Typography.Text>
                                            </Button>
                                          );
                                        })}
                                      </Space>
                                    )}
                                  </Space>
                                )}
                              />
                            </List.Item>
                          )}
                        />
                      )}

                      {/* === 或粘贴邮件文本 === */}
                      <Typography.Text type="secondary">{t('upload.orPasteText')}</Typography.Text>
                      <TextArea
                        rows={10}
                        placeholder={t('upload.emailPlaceholder')}
                        value={emailText}
                        onChange={(event) => setEmailText(event.target.value)}
                      />
                      <Button
                        type="primary"
                        size="large"
                        onClick={handleEmailParse}
                        disabled={!emailText.trim()}
                        icon={<MailOutlined />}
                      >
                        {t('upload.parseEmailText')}
                      </Button>
                    </Space>
                  ),
                },
                {
                  key: 'wechat',
                  label: <span><PictureOutlined /> {t('upload.tabWechat')}</span>,
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      <Alert type="info" showIcon message={t('upload.wechatInfo')} />
                      <Input
                        placeholder={t('upload.wechatContextPlaceholder')}
                        value={imageContext}
                        onChange={(event) => setImageContext(event.target.value)}
                      />
                      <Dragger
                        accept=".png,.jpg,.jpeg,.gif,.webp,.bmp"
                        showUploadList={false}
                        customRequest={({ file }) => handleImageUpload(file as File)}
                      >
                        <p className="ant-upload-drag-icon"><PictureOutlined /></p>
                        <p className="ant-upload-text">{t('upload.imageDragText')}</p>
                        <p className="ant-upload-hint">
                          {t('upload.imageHint')}
                          <br />
                          {t('upload.imageHint2')}
                        </p>
                      </Dragger>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        )}

        {step === 1 && parseResult && (
          <Card>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Alert
                type="success"
                message={(
                  <Space>
                    {sourceTag(parseResult.source_type)}
                    <span>{t('upload.fileLabel')}: <strong>{parseResult.file_name}</strong></span>
                    {parseResult.carrier_code && <Tag color="blue">{parseResult.carrier_code}</Tag>}
                    <span>{t('upload.parsedRates', { count: parseResult.total_rows })}</span>
                    {parseResult.sheets && parseResult.sheets.length > 0 && (
                      <span>
                        ({parseResult.sheets.map((sheet) => t('upload.sheetSummary', { name: sheet.name, count: sheet.rows })).join(', ')})
                      </span>
                    )}
                  </Space>
                )}
              />

              {parseResult.warnings.length > 0 && (
                <Alert
                  type="warning"
                  message={t('upload.warnings', { count: parseResult.warnings.length })}
                  description={(
                    <ul style={{ margin: 0, paddingLeft: 20 }}>
                      {parseResult.warnings.slice(0, 10).map((warning, index) => (
                        <li key={index}>{warning}</li>
                      ))}
                      {parseResult.warnings.length > 10 && (
                        <li>{t('upload.moreWarnings', { count: parseResult.warnings.length - 10 })}</li>
                      )}
                    </ul>
                  )}
                />
              )}

              <Table<ParsePreviewRow>
                columns={previewColumns}
                dataSource={parseResult.preview_rows}
                rowKey={(_, index) => String(index)}
                size="small"
                scroll={{ x: 1200 }}
                pagination={{ pageSize: 20, showSizeChanger: true }}
              />

              <Space>
                <Button type="primary" size="large" onClick={handleConfirm}>
                  {t('upload.confirmImport', { count: parseResult.total_rows })}
                </Button>
                <Button size="large" onClick={handleReset}>
                  {t('common.cancel')}
                </Button>
              </Space>
            </Space>
          </Card>
        )}

        {step === 2 && importResult && (
          <Card>
            <Result
              status="success"
              title={t('upload.successTitle')}
              subTitle={t('upload.successSubtitle', {
                imported: importResult.records_imported,
                parsed: importResult.records_parsed,
              })}
              extra={[
                <Button type="primary" key="view" onClick={() => { window.location.href = '/rates'; }}>
                  {t('upload.viewRates')}
                </Button>,
                <Button key="continue" onClick={handleReset}>
                  {t('upload.continueImport')}
                </Button>,
              ]}
            />

            {importResult.errors.length > 0 && (
              <Alert
                type="error"
                message={t('upload.importErrors', { count: importResult.errors.length })}
                description={importResult.errors.join('\n')}
                style={{ marginTop: 16 }}
              />
            )}
          </Card>
        )}
      </Spin>
    </div>
  );
}
