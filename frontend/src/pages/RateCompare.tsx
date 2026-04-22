import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../components/Icon';
import { portApi, rateApi } from '../services/api';
import type { CompareRateItem, CompareResult, PaginatedData, Port } from '../types';

function formatPrice(value?: string) {
  if (!value) return '—';
  const num = Number(value);
  if (!Number.isFinite(num) || num === 0) return '—';
  return `$${Math.round(num).toLocaleString()}`;
}

function statusTag(value?: string) {
  if (value === 'active') return 'tag-success';
  if (value === 'draft') return 'tag-warn';
  return 'tag-muted';
}

export default function RateCompare() {
  const { t } = useTranslation();
  const [ports, setPorts] = useState<Port[]>([]);
  const [originId, setOriginId] = useState<number | ''>('');
  const [destId, setDestId] = useState<number | ''>('');
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    portApi
      .list({ page_size: 500 })
      .then((res) => {
        const payload = (res as { data?: PaginatedData<Port> }).data;
        if (payload?.items) setPorts(payload.items);
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  const minPrice20 = useMemo(() => {
    if (!result) return Infinity;
    return result.rates.reduce((m, r) => {
      const v = Number(r.container_20gp || 0);
      return v > 0 && v < m ? v : m;
    }, Infinity);
  }, [result]);

  const minPrice40 = useMemo(() => {
    if (!result) return Infinity;
    return result.rates.reduce((m, r) => {
      const v = Number(r.container_40gp || 0);
      return v > 0 && v < m ? v : m;
    }, Infinity);
  }, [result]);

  const handleCompare = async () => {
    if (!originId || !destId) {
      message.warning(t('compare.missingPorts'));
      return;
    }
    setLoading(true);
    try {
      const res = await rateApi.compare(Number(originId), Number(destId));
      const payload = res as { code?: number; message?: string; data?: CompareResult };
      if (payload.code !== 0 && payload.code !== undefined) {
        message.error(payload.message || t('common.error'));
        return;
      }
      const data = payload.data;
      if (!data) return;
      setResult(data);
      if (data.total === 0) message.info(t('compare.noData'));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('common.unknownError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('compare.title')}</h1>
        <div className="sub">RATE COMPARE</div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body" style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
          <div className="field" style={{ flex: 1, minWidth: 260 }}>
            <label>{t('compare.selectOrigin')}</label>
            <select
              className="select"
              value={originId}
              onChange={(e) => setOriginId(e.target.value ? Number(e.target.value) : '')}
              style={{ width: '100%' }}
            >
              <option value="">{t('compare.selectOrigin')}</option>
              {ports.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.un_locode} · {p.name_en}
                  {p.name_cn ? ` / ${p.name_cn}` : ''}
                </option>
              ))}
            </select>
          </div>
          <div style={{ paddingBottom: 10, color: 'var(--teal-500)' }}>
            <Icon name="arrow-right" size={20} />
          </div>
          <div className="field" style={{ flex: 1, minWidth: 260 }}>
            <label>{t('compare.selectDestination')}</label>
            <select
              className="select"
              value={destId}
              onChange={(e) => setDestId(e.target.value ? Number(e.target.value) : '')}
              style={{ width: '100%' }}
            >
              <option value="">{t('compare.selectDestination')}</option>
              {ports.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.un_locode} · {p.name_en}
                  {p.name_cn ? ` / ${p.name_cn}` : ''}
                </option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary" onClick={handleCompare} disabled={loading}>
            <Icon name="search" size={13} />
            {loading ? t('common.loading') : t('compare.compareBtn')}
          </button>
        </div>
      </div>

      {result && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="card-head">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ fontFamily: 'var(--font-en)' }}>
                {result.origin.un_locode} → {result.destination.un_locode}
              </h3>
              <span className="tag zh tag-teal">
                {t('compare.totalQuotes', { count: result.total })}
              </span>
            </div>
            <span className="sub right">
              {result.origin.name_cn || result.origin.name_en} → {result.destination.name_cn || result.destination.name_en}
            </span>
          </div>

          <div className="table-scroll">
            <table className="rtable" style={{ minWidth: 1100 }}>
              <thead>
                <tr>
                  <th>{t('rates.shippingLine')}</th>
                  <th className="c-right">20&apos; DC</th>
                  <th className="c-right">40&apos; DC</th>
                  <th className="c-right">40&apos; HC</th>
                  <th className="c-right">BAF 20/40</th>
                  <th>{t('rates.effectiveDate')}</th>
                  <th>{t('compare.expiryDate')}</th>
                  <th className="c-center">{t('rates.transitDays')}</th>
                  <th>{t('compare.direct')}</th>
                  <th>{t('rates.source')}</th>
                  <th>{t('rates.status')}</th>
                </tr>
              </thead>
              <tbody>
                {result.rates.map((r: CompareRateItem) => {
                  const price20 = Number(r.container_20gp || 0);
                  const price40 = Number(r.container_40gp || 0);
                  const best20 = price20 > 0 && price20 === minPrice20;
                  const best40 = price40 > 0 && price40 === minPrice40;
                  return (
                    <tr key={r.rate_id}>
                      <td>
                        <div style={{ lineHeight: 1.3 }}>
                          <div style={{ fontFamily: 'var(--font-en)', fontWeight: 500 }}>{r.carrier_code}</div>
                          <div style={{ fontSize: 11.5, color: 'var(--ink-500)' }}>{r.carrier_name}</div>
                        </div>
                      </td>
                      <td className="c-right num" style={{ color: best20 ? 'var(--success)' : 'var(--ink-800)', fontWeight: best20 ? 600 : 500 }}>
                        {formatPrice(r.container_20gp)}
                      </td>
                      <td className="c-right num" style={{ color: best40 ? 'var(--success)' : 'var(--ink-900)', fontWeight: best40 ? 600 : 500 }}>
                        {formatPrice(r.container_40gp)}
                      </td>
                      <td className="c-right num">{formatPrice(r.container_40hq)}</td>
                      <td className="c-right num" style={{ color: 'var(--ink-500)' }}>
                        {r.baf_20 || r.baf_40
                          ? `$${Number(r.baf_20 || 0).toFixed(0)}/$${Number(r.baf_40 || 0).toFixed(0)}`
                          : '—'}
                      </td>
                      <td className="num" style={{ color: 'var(--ink-500)' }}>{r.valid_from || '—'}</td>
                      <td className="num" style={{ color: 'var(--ink-500)' }}>{r.valid_to || '—'}</td>
                      <td className="c-center num" style={{ color: 'var(--ink-500)' }}>
                        {r.transit_days ? `${r.transit_days}d` : '—'}
                      </td>
                      <td>
                        <span className={`tag zh ${r.is_direct ? 'tag-success' : 'tag-muted'}`}>
                          {r.is_direct ? t('compare.direct') : t('compare.transshipment')}
                        </span>
                      </td>
                      <td>
                        <span className="tag zh tag-muted">
                          {r.source_type ? t(`rates.sources.${r.source_type}`, r.source_type) : '—'}
                        </span>
                      </td>
                      <td>
                        <span className={`tag zh tag-dot ${statusTag(r.status)}`}>
                          {r.status === 'active'
                            ? t('rates.statusActive')
                            : r.status === 'draft'
                              ? t('rates.statusDraft')
                              : t('rates.statusExpired')}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {result.rates.length === 0 && (
                  <tr>
                    <td colSpan={11} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
                      {t('compare.noData')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
