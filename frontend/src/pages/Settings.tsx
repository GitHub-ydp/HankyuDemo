import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useBlocker } from 'react-router-dom';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Select,
  Slider,
  Space,
  Switch,
  Tag,
  Tooltip,
  message,
} from 'antd';
import Icon from '../components/Icon';
import { settingsApi } from '../services/api';
import type {
  AIConfigResponse,
  AIProvider,
  MaskedSecret,
  TestConnectionResponse,
} from '../types';

type SecretEditState = 'preserve' | 'clear' | 'edit';

// dirtyFields 只保留用户在 UI 改过的字段；提交时把这些 + 敏感字段状态组装 payload
interface SecretDraft {
  state: SecretEditState;
  value: string;
}

const PRESET_VLLM_URLS = [
  { key: 'prodVllm', url: 'http://43.133.197.65:8000/v1' },
  { key: 'localVllm', url: 'http://localhost:8000/v1' },
  { key: 'bailianFallback', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
];

function sourceTag(source: 'db' | 'env', t: (k: string) => string) {
  return source === 'db' ? (
    <Tag color="cyan" style={{ marginLeft: 8, fontSize: 11 }}>
      {t('settings.source.db')}
    </Tag>
  ) : (
    <Tag style={{ marginLeft: 8, fontSize: 11 }}>{t('settings.source.env')}</Tag>
  );
}

interface ApiKeyFieldProps {
  masked: MaskedSecret;
  draft: SecretDraft;
  onDraftChange: (d: SecretDraft) => void;
  label: string;
}

function ApiKeyField({ masked, draft, onDraftChange, label }: ApiKeyFieldProps) {
  const { t } = useTranslation();

  const enterEdit = () =>
    onDraftChange({ state: 'edit', value: '' });
  const cancelEdit = () =>
    onDraftChange({ state: 'preserve', value: '' });
  const clearKey = () => {
    Modal.confirm({
      title: t('settings.confirm.clearApiKeyTitle'),
      content: t('settings.confirm.clearApiKey'),
      okText: t('settings.action.clearApiKey'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: () => onDraftChange({ state: 'clear', value: '' }),
    });
  };
  const undoClear = () => onDraftChange({ state: 'preserve', value: '' });

  if (draft.state === 'edit') {
    return (
      <Space.Compact style={{ width: '100%' }}>
        <Input.Password
          placeholder={t('settings.apiKey.placeholderEditing')}
          value={draft.value}
          autoFocus
          onChange={(e) => onDraftChange({ state: 'edit', value: e.target.value })}
        />
        <Button onClick={cancelEdit}>{t('settings.action.cancelEditApiKey')}</Button>
      </Space.Compact>
    );
  }

  if (draft.state === 'clear') {
    return (
      <Space.Compact style={{ width: '100%' }}>
        <Input
          readOnly
          value={t('settings.apiKey.cleared')}
          style={{ color: 'var(--danger)' }}
          aria-label={label}
        />
        <Button onClick={undoClear}>{t('common.cancel')}</Button>
      </Space.Compact>
    );
  }

  // preserve
  const display = masked.is_set ? masked.masked : t('settings.apiKey.notSet');
  return (
    <Space.Compact style={{ width: '100%' }}>
      <Input readOnly value={display} aria-label={label} />
      <Button onClick={enterEdit}>{t('settings.action.editApiKey')}</Button>
      <Button danger onClick={clearKey} disabled={!masked.is_set}>
        {t('settings.action.clearApiKey')}
      </Button>
    </Space.Compact>
  );
}

export default function SettingsPage() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [config, setConfig] = useState<AIConfigResponse | null>(null);

  // dirty 普通字段：field name → new value
  const [dirty, setDirty] = useState<Record<string, unknown>>({});
  // 敏感字段三态
  const [vllmKeyDraft, setVllmKeyDraft] = useState<SecretDraft>({ state: 'preserve', value: '' });
  const [anthKeyDraft, setAnthKeyDraft] = useState<SecretDraft>({ state: 'preserve', value: '' });

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res = (await settingsApi.getAIConfig()) as { data?: AIConfigResponse };
      if (res.data) setConfig(res.data);
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const isDirty = useMemo(() => {
    return (
      Object.keys(dirty).length > 0 ||
      vllmKeyDraft.state !== 'preserve' ||
      anthKeyDraft.state !== 'preserve'
    );
  }, [dirty, vllmKeyDraft, anthKeyDraft]);

  // beforeunload 拦截（关标签页 / 刷新）
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  // 路由切换拦截（左侧菜单点击 / 浏览器返回）— 业务需求 §9.9
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (blocker.state === 'blocked') {
      Modal.confirm({
        title: t('settings.confirm.leaveUnsavedTitle'),
        content: t('settings.confirm.leaveUnsaved'),
        okText: t('settings.confirm.leaveOk'),
        cancelText: t('common.cancel'),
        okButtonProps: { danger: true },
        onOk: () => blocker.proceed?.(),
        onCancel: () => blocker.reset?.(),
      });
    }
  }, [blocker, t]);

  const getVal = <T,>(key: keyof AIConfigResponse): T | undefined => {
    if (!config) return undefined;
    return (dirty[key as string] as T | undefined) ?? (config[key].value as T);
  };

  const setField = (key: string, value: unknown, original: unknown) => {
    setDirty((prev) => {
      const next = { ...prev };
      if (value === original) {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const discardChanges = () => {
    setDirty({});
    setVllmKeyDraft({ state: 'preserve', value: '' });
    setAnthKeyDraft({ state: 'preserve', value: '' });
  };

  const buildPayload = (): Record<string, unknown> => {
    const payload: Record<string, unknown> = { ...dirty };
    // 敏感字段
    if (vllmKeyDraft.state === 'clear') payload.vllm_api_key = null;
    else if (vllmKeyDraft.state === 'edit' && vllmKeyDraft.value.trim())
      payload.vllm_api_key = vllmKeyDraft.value.trim();
    if (anthKeyDraft.state === 'clear') payload.anthropic_api_key = null;
    else if (anthKeyDraft.state === 'edit' && anthKeyDraft.value.trim())
      payload.anthropic_api_key = anthKeyDraft.value.trim();
    return payload;
  };

  // base_url 前端 validate
  const currentBaseUrl = (getVal<string>('vllm_base_url') ?? '').trim();
  const baseUrlInvalid =
    dirty.vllm_base_url !== undefined &&
    currentBaseUrl.length > 0 &&
    !/^https?:\/\/.+/.test(currentBaseUrl);

  // max_tokens 前端 validate（default ≤ cap、extract ≤ cap）
  const valDefault = Number(getVal('ai_max_tokens_default') ?? 0);
  const valExtract = Number(getVal('ai_max_tokens_extract_json') ?? 0);
  const valCap = Number(getVal('ai_max_tokens_cap') ?? 0);
  const tokensInvalid = valCap > 0 && (valDefault > valCap || valExtract > valCap);

  const canSave = isDirty && !baseUrlInvalid && !tokensInvalid;

  const doSave = async () => {
    if (!config) return;
    const payload = buildPayload();
    if (Object.keys(payload).length === 0) return;

    // Provider 切换二次确认
    const oldProvider = config.ai_provider.value;
    const newProvider = payload.ai_provider as AIProvider | undefined;
    if (newProvider && newProvider !== oldProvider) {
      const targetKeyIsSet =
        newProvider === 'anthropic'
          ? config.anthropic_api_key.value.is_set
          : config.vllm_api_key.value.is_set;
      const content =
        t('settings.confirm.switchProvider', { target: newProvider }) +
        (targetKeyIsSet ? '' : ' ' + t('settings.confirm.switchProviderWarnKey'));
      const confirmed = await new Promise<boolean>((resolve) => {
        Modal.confirm({
          title: t('settings.confirm.switchProviderTitle'),
          content,
          okText: t('common.confirm'),
          cancelText: t('common.cancel'),
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        });
      });
      if (!confirmed) return;
    }

    // API Key 修改二次确认（edit 或 clear 都要）
    if (vllmKeyDraft.state === 'edit' || anthKeyDraft.state === 'edit') {
      const confirmed = await new Promise<boolean>((resolve) => {
        Modal.confirm({
          title: t('settings.confirm.editApiKeyTitle'),
          content: t('settings.confirm.editApiKey'),
          okText: t('common.confirm'),
          cancelText: t('common.cancel'),
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        });
      });
      if (!confirmed) return;
    }

    setSaving(true);
    try {
      const res = (await settingsApi.updateAIConfig(payload)) as { data?: AIConfigResponse };
      if (res.data) {
        setConfig(res.data);
        discardChanges();
        message.success(t('settings.toast.saved'));

        // 清空警告（针对敏感字段清空后）
        const clearedVllm = 'vllm_api_key' in payload && payload.vllm_api_key === null;
        const clearedAnth =
          'anthropic_api_key' in payload && payload.anthropic_api_key === null;
        if (clearedVllm || clearedAnth) {
          message.warning(t('settings.toast.apiKeyEmpty'));
        }
      }
    } catch (e) {
      message.error(
        t('settings.toast.saveFailed') + ' ' + (e instanceof Error ? e.message : '')
      );
    } finally {
      setSaving(false);
    }
  };

  const doTest = async () => {
    if (isDirty) {
      message.warning(t('settings.toast.testDirtyBlock'));
      return;
    }
    setTesting(true);
    try {
      const res = (await settingsApi.testConnection()) as { data?: TestConnectionResponse };
      const d = res.data;
      if (!d) return;
      if (d.ok) {
        message.success(
          t('settings.toast.testOk', { provider: d.provider, latency: d.latency_ms })
        );
      } else {
        message.error(t('settings.toast.testFailed', { detail: d.detail }));
      }
    } catch (e) {
      message.error(
        t('settings.toast.testFailed', { detail: e instanceof Error ? e.message : '' })
      );
    } finally {
      setTesting(false);
    }
  };

  const doReset = () => {
    Modal.confirm({
      title: t('settings.confirm.resetDefaultTitle'),
      content: t('settings.confirm.resetDefault'),
      okText: t('settings.action.resetDefault'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        setResetting(true);
        try {
          const res = (await settingsApi.resetAIConfig()) as { data?: AIConfigResponse };
          if (res.data) {
            setConfig(res.data);
            discardChanges();
            message.success(t('settings.toast.resetDone'));
          }
        } catch (e) {
          message.error(e instanceof Error ? e.message : t('common.error'));
        } finally {
          setResetting(false);
        }
      },
    });
  };

  if (loading && !config) {
    return (
      <div className="page">
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--ink-500)' }}>
          {t('common.loading')}
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="page">
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--ink-500)' }}>
          {t('common.error')}
        </div>
      </div>
    );
  }

  const currentProvider = (getVal<AIProvider>('ai_provider') ?? 'vllm') as AIProvider;

  return (
    <div className="page">
      <div className="page-head">
        <h1>
          {t('settings.title')}
          <Tag color="cyan" style={{ marginLeft: 12 }}>
            {t('settings.currentProviderTag', { provider: config.ai_provider.value })}
          </Tag>
        </h1>
        <div className="sub">{t('settings.subtitle')}</div>
        <div className="actions">
          <Button onClick={discardChanges} disabled={!isDirty || saving}>
            {t('settings.action.cancel')}
          </Button>
          <Button danger onClick={doReset} loading={resetting}>
            {t('settings.action.resetDefault')}
          </Button>
          <Button type="primary" onClick={doSave} disabled={!canSave} loading={saving}>
            {t('settings.action.save')}
          </Button>
        </div>
      </div>

      {/* Provider Section */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-head">
          <h3>{t('settings.section.provider')}</h3>
          <span className="sub right">PROVIDER</span>
        </div>
        <div className="card-body">
          <div style={{ color: 'var(--ink-500)', fontSize: 12, marginBottom: 16 }}>
            {t('settings.section.providerDesc')}
          </div>
          <Form layout="vertical" colon={false}>
            <Form.Item
              label={
                <span>
                  {t('settings.field.provider')} {sourceTag(config.ai_provider.source, t)}
                </span>
              }
            >
              <Radio.Group
                value={currentProvider}
                onChange={(e) =>
                  setField('ai_provider', e.target.value, config.ai_provider.value)
                }
              >
                <Radio value="vllm">vLLM</Radio>
                <Radio value="anthropic">Anthropic</Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.timeout')} {sourceTag(config.ai_timeout_seconds.source, t)}
                </span>
              }
            >
              <InputNumber
                min={10}
                max={600}
                value={getVal<number>('ai_timeout_seconds')}
                onChange={(v) =>
                  setField('ai_timeout_seconds', v, config.ai_timeout_seconds.value)
                }
                style={{ width: 180 }}
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.autoNoThink')}{' '}
                  <Tooltip title={t('settings.tooltip.autoNoThink')}>
                    <Icon name="help" size={13} />
                  </Tooltip>
                  {sourceTag(config.ai_auto_no_think.source, t)}
                </span>
              }
            >
              <Switch
                checked={getVal<boolean>('ai_auto_no_think')}
                onChange={(v) =>
                  setField('ai_auto_no_think', v, config.ai_auto_no_think.value)
                }
              />
            </Form.Item>
            <Form.Item>
              <Button onClick={doTest} loading={testing} disabled={isDirty}>
                <Icon name="check" size={13} /> {t('settings.action.testConnection')}
              </Button>
            </Form.Item>
          </Form>
        </div>
      </div>

      {/* vLLM Section */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-head">
          <h3>{t('settings.section.vllm')}</h3>
          <span className="sub right">VLLM</span>
        </div>
        <div className="card-body">
          <div style={{ color: 'var(--ink-500)', fontSize: 12, marginBottom: 16 }}>
            {t('settings.section.vllmDesc')}
          </div>
          <Form layout="vertical" colon={false}>
            <Form.Item
              label={
                <span>
                  {t('settings.field.baseUrl')} {sourceTag(config.vllm_base_url.source, t)}
                </span>
              }
              validateStatus={baseUrlInvalid ? 'error' : ''}
              help={baseUrlInvalid ? t('settings.toast.baseUrlInvalid') : undefined}
            >
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  value={getVal<string>('vllm_base_url')}
                  onChange={(e) =>
                    setField('vllm_base_url', e.target.value, config.vllm_base_url.value)
                  }
                  placeholder="http://host:port/v1"
                />
                <Select
                  placeholder={t('settings.preset.label')}
                  style={{ width: 220 }}
                  onChange={(v: string) => {
                    const preset = PRESET_VLLM_URLS.find((p) => p.key === v);
                    if (preset)
                      setField('vllm_base_url', preset.url, config.vllm_base_url.value);
                  }}
                  options={PRESET_VLLM_URLS.map((p) => ({
                    value: p.key,
                    label: t(`settings.preset.${p.key}`),
                  }))}
                />
              </Space.Compact>
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.apiKey')} {sourceTag(config.vllm_api_key.source, t)}
                </span>
              }
            >
              <ApiKeyField
                masked={config.vllm_api_key.value}
                draft={vllmKeyDraft}
                onDraftChange={setVllmKeyDraft}
                label={t('settings.field.apiKey')}
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.model')} {sourceTag(config.vllm_model.source, t)}
                </span>
              }
              extra={t('settings.modelHint')}
            >
              <Input
                value={getVal<string>('vllm_model')}
                onChange={(e) =>
                  setField('vllm_model', e.target.value, config.vllm_model.value)
                }
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.enableThinking')}{' '}
                  <Tooltip title={t('settings.tooltip.enableThinking')}>
                    <Icon name="help" size={13} />
                  </Tooltip>
                  {sourceTag(config.vllm_enable_thinking.source, t)}
                </span>
              }
            >
              <Switch
                checked={getVal<boolean>('vllm_enable_thinking')}
                onChange={(v) =>
                  setField('vllm_enable_thinking', v, config.vllm_enable_thinking.value)
                }
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.enableChatTemplateKwargs')}{' '}
                  <Tooltip title={t('settings.tooltip.enableChatTemplateKwargs')}>
                    <Icon name="help" size={13} />
                  </Tooltip>
                  {sourceTag(config.vllm_enable_chat_template_kwargs.source, t)}
                </span>
              }
            >
              <Switch
                checked={getVal<boolean>('vllm_enable_chat_template_kwargs')}
                onChange={(v) =>
                  setField(
                    'vllm_enable_chat_template_kwargs',
                    v,
                    config.vllm_enable_chat_template_kwargs.value
                  )
                }
              />
            </Form.Item>
          </Form>
        </div>
      </div>

      {/* Anthropic Section */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-head">
          <h3>{t('settings.section.anthropic')}</h3>
          <span className="sub right">ANTHROPIC</span>
        </div>
        <div className="card-body">
          <div style={{ color: 'var(--ink-500)', fontSize: 12, marginBottom: 16 }}>
            {t('settings.section.anthropicDesc')}
          </div>
          <Form layout="vertical" colon={false}>
            <Form.Item
              label={
                <span>
                  {t('settings.field.anthropicApiKey')}{' '}
                  {sourceTag(config.anthropic_api_key.source, t)}
                </span>
              }
            >
              <ApiKeyField
                masked={config.anthropic_api_key.value}
                draft={anthKeyDraft}
                onDraftChange={setAnthKeyDraft}
                label={t('settings.field.anthropicApiKey')}
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.anthropicModel')}{' '}
                  {sourceTag(config.anthropic_model.source, t)}
                </span>
              }
            >
              <Input
                value={getVal<string>('anthropic_model')}
                onChange={(e) =>
                  setField('anthropic_model', e.target.value, config.anthropic_model.value)
                }
              />
            </Form.Item>
          </Form>
        </div>
      </div>

      {/* Tokens Section */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-head">
          <h3>{t('settings.section.tokens')}</h3>
          <span className="sub right">TOKENS</span>
        </div>
        <div className="card-body">
          <div style={{ color: 'var(--ink-500)', fontSize: 12, marginBottom: 16 }}>
            {t('settings.section.tokensDesc')}
          </div>
          <Form layout="vertical" colon={false}>
            <Form.Item
              label={
                <span>
                  {t('settings.field.maxTokensDefault')}{' '}
                  {sourceTag(config.ai_max_tokens_default.source, t)}
                </span>
              }
              validateStatus={tokensInvalid && valDefault > valCap ? 'error' : ''}
            >
              <InputNumber
                min={64}
                max={8192}
                value={getVal<number>('ai_max_tokens_default')}
                onChange={(v) =>
                  setField('ai_max_tokens_default', v, config.ai_max_tokens_default.value)
                }
                style={{ width: 200 }}
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.maxTokensExtract')}{' '}
                  {sourceTag(config.ai_max_tokens_extract_json.source, t)}
                </span>
              }
              validateStatus={tokensInvalid && valExtract > valCap ? 'error' : ''}
            >
              <InputNumber
                min={64}
                max={8192}
                value={getVal<number>('ai_max_tokens_extract_json')}
                onChange={(v) =>
                  setField(
                    'ai_max_tokens_extract_json',
                    v,
                    config.ai_max_tokens_extract_json.value
                  )
                }
                style={{ width: 200 }}
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.maxTokensCap')}{' '}
                  {sourceTag(config.ai_max_tokens_cap.source, t)}
                </span>
              }
            >
              <InputNumber
                min={256}
                max={4096}
                value={getVal<number>('ai_max_tokens_cap')}
                onChange={(v) =>
                  setField('ai_max_tokens_cap', v, config.ai_max_tokens_cap.value)
                }
                style={{ width: 200 }}
              />
            </Form.Item>
          </Form>
        </div>
      </div>

      {/* Image Compression Section */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-head">
          <h3>{t('settings.section.image')}</h3>
          <span className="sub right">IMAGE</span>
        </div>
        <div className="card-body">
          <div style={{ color: 'var(--ink-500)', fontSize: 12, marginBottom: 16 }}>
            {t('settings.section.imageDesc')}
          </div>
          <Form layout="vertical" colon={false}>
            <Form.Item
              label={
                <span>
                  {t('settings.field.imageCompress')}{' '}
                  {sourceTag(config.ai_image_compress.source, t)}
                </span>
              }
            >
              <Switch
                checked={getVal<boolean>('ai_image_compress')}
                onChange={(v) =>
                  setField('ai_image_compress', v, config.ai_image_compress.value)
                }
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.imageMaxEdge')}{' '}
                  {sourceTag(config.ai_image_max_edge_px.source, t)}
                </span>
              }
            >
              <Slider
                min={640}
                max={2048}
                step={64}
                disabled={!getVal<boolean>('ai_image_compress')}
                value={getVal<number>('ai_image_max_edge_px')}
                onChange={(v) =>
                  setField('ai_image_max_edge_px', v, config.ai_image_max_edge_px.value)
                }
                marks={{ 640: '640', 1280: '1280', 2048: '2048' }}
              />
            </Form.Item>
            <Form.Item
              label={
                <span>
                  {t('settings.field.imageJpegQuality')}{' '}
                  {sourceTag(config.ai_image_jpeg_quality.source, t)}
                </span>
              }
            >
              <Slider
                min={60}
                max={95}
                step={5}
                disabled={!getVal<boolean>('ai_image_compress')}
                value={getVal<number>('ai_image_jpeg_quality')}
                onChange={(v) =>
                  setField('ai_image_jpeg_quality', v, config.ai_image_jpeg_quality.value)
                }
                marks={{ 60: '60', 85: '85', 95: '95' }}
              />
            </Form.Item>
          </Form>
        </div>
      </div>
    </div>
  );
}
