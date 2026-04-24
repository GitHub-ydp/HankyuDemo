import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../components/Icon';
import { portApi, rateApi } from '../services/api';
import type {
  AirWeeklyCompareItem,
  CompareRateItem,
  CompareRateType,
  CompareResult,
  LclCompareItem,
  PaginatedData,
  Port,
} from '../types';

const COMPARE_TABS: CompareRateType[] = ['ocean_fcl', 'ocean_ngb', 'air_weekly', 'lcl'];

function formatPrice(value?: string | null) {
  if (!value) return '—';
  const num = Number(value);
  if (!Number.isFinite(num) || num === 0) return '—';
  return `$${Math.round(num).toLocaleString()}`;
}

function formatNumber(value?: string | null) {
  if (!value) return '—';
  const num = Number(value);
  if (!Number.isFinite(num) || num === 0) return '—';
  return num.toLocaleString();
}

function statusTag(value?: string) {
  if (value === 'active') return 'tag-success';
  if (value === 'draft') return 'tag-warn';
  return 'tag-muted';
}

function isPort(value: Port | string | undefined): value is Port {
  return !!value && typeof value !== 'string' && 'un_locode' in value;
}

export default function RateCompare() {
  const { t } = useTranslation();
  const [rateType, setRateType] = useState<CompareRateType>('ocean_fcl');
  const [ports, setPorts] = useState<Port[]>([]);
  const [originId, setOriginId] = useState<number | ''>('');
  const [destId, setDestId] = useState<number | ''>('');
  const [originText, setOriginText] = useState('');
  const [destText, setDestText] = useState('');
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);

  const isAirWeekly = rateType === 'air_weekly';
  const isNgb = rateType === 'ocean_ngb';

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

  // 海运 FCL / NGB / LCL 通用最低价（20' 容器 / CBM 任意）
  const oceanMin20 = useMemo(() => {
    if (!result || isAirWeekly) return Infinity;
    const rates = result.rates as CompareRateItem[];
    return rates.reduce((m, r) => {
      const v = Number(r.container_20gp || 0);
      return v > 0 && v < m ? v : m;
    }, Infinity);
  }, [result, isAirWeekly]);
  const oceanMin40 = useMemo(() => {
    if (!result || isAirWeekly) return Infinity;
    const rates = result.rates as CompareRateItem[];
    return rates.reduce((m, r) => {
      const v = Number(r.container_40gp || 0);
      return v > 0 && v < m ? v : m;
    }, Infinity);
  }, [result, isAirWeekly]);

  // LCL 最低价（CBM / TON）
  const lclMinCbm = useMemo(() => {
    if (!result || rateType !== 'lcl') return Infinity;
    const rates = result.rates as LclCompareItem[];
    return rates.reduce((m, r) => {
      const v = Number(r.freight_per_cbm || 0);
      return v > 0 && v < m ? v : m;
    }, Infinity);
  }, [result, rateType]);
  const lclMinTon = useMemo(() => {
    if (!result || rateType !== 'lcl') return Infinity;
    const rates = result.rates as LclCompareItem[];
    return rates.reduce((m, r) => {
      const v = Number(r.freight_per_ton || 0);
      return v > 0 && v < m ? v : m;
    }, Infinity);
  }, [result, rateType]);

  // Air weekly 七日价各自最低
  const airMinDays = useMemo(() => {
    const empty = Array.from({ length: 7 }, () => Infinity);
    if (!result || !isAirWeekly) return empty;
    const rates = result.rates as AirWeeklyCompareItem[];
    return empty.map((_, i) => {
      const key = `price_day${i + 1}` as keyof AirWeeklyCompareItem;
      return rates.reduce((m, r) => {
        const v = Number(r[key] || 0);
        return v > 0 && v < m ? v : m;
      }, Infinity);
    });
  }, [result, isAirWeekly]);

  const handleTabChange = (next: CompareRateType) => {
    if (next === rateType) return;
    setRateType(next);
    setOriginId('');
    setDestId('');
    setOriginText('');
    setDestText('');
    setResult(null);
  };

  const handleCompare = async () => {
    if (isAirWeekly) {
      if (!originText || !destText) {
        message.warning(t('compare.missingAirports'));
        return;
      }
    } else {
      if (!originId || !destId) {
        message.warning(t('compare.missingPorts'));
        return;
      }
    }
    setLoading(true);
    try {
      const res = await rateApi.compare(
        isAirWeekly
          ? { rateType, originText, destinationText: destText }
          : {
              rateType,
              originPortId: Number(originId),
              destinationPortId: Number(destId),
            },
      );
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

      <div style={{ display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: 'var(--ink-500)', marginRight: 4 }}>
          {t('compare.tabsLabel')}:
        </span>
        <div className="chip-group">
          {COMPARE_TABS.map((v) => (
            <button
              key={v}
              type="button"
              className={`chip${rateType === v ? ' on' : ''}`}
              onClick={() => handleTabChange(v)}
            >
              {t(`compare.tabs.${v}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body" style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
          {isAirWeekly ? (
            <>
              <div className="field" style={{ flex: 1, minWidth: 260 }}>
                <label>{t('rates.originText')}</label>
                <input
                  className="input"
                  value={originText}
                  onChange={(e) => setOriginText(e.target.value.toUpperCase())}
                  placeholder={t('compare.airOriginPlaceholder')}
                  style={{ width: '100%' }}
                />
              </div>
              <div style={{ paddingBottom: 10, color: 'var(--teal-500)' }}>
                <Icon name="arrow-right" size={20} />
              </div>
              <div className="field" style={{ flex: 1, minWidth: 260 }}>
                <label>{t('rates.destinationText')}</label>
                <input
                  className="input"
                  value={destText}
                  onChange={(e) => setDestText(e.target.value.toUpperCase())}
                  placeholder={t('compare.airDestinationPlaceholder')}
                  style={{ width: '100%' }}
                />
              </div>
            </>
          ) : (
            <>
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
            </>
          )}
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
                {isPort(result.origin) ? result.origin.un_locode : (result.origin as string)} →{' '}
                {isPort(result.destination)
                  ? result.destination.un_locode
                  : (result.destination as string)}
              </h3>
              <span className="tag zh tag-teal">
                {t('compare.totalQuotes', { count: result.total })}
              </span>
              {isNgb && (
                <span className="tag zh tag-warn" style={{ marginLeft: 4 }}>
                  {t('compare.ngbTag')}
                </span>
              )}
            </div>
            <span className="sub right">
              {isPort(result.origin)
                ? result.origin.name_cn || result.origin.name_en
                : ''}{' '}
              {isPort(result.origin) && isPort(result.destination) ? '→' : ''}{' '}
              {isPort(result.destination)
                ? result.destination.name_cn || result.destination.name_en
                : ''}
            </span>
          </div>

          <div className="table-scroll">
            {!isAirWeekly && rateType !== 'lcl' && (
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
                  {(result.rates as CompareRateItem[]).map((r) => {
                    const price20 = Number(r.container_20gp || 0);
                    const price40 = Number(r.container_40gp || 0);
                    const best20 = price20 > 0 && price20 === oceanMin20;
                    const best40 = price40 > 0 && price40 === oceanMin40;
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
                            {r.source_type
                              ? t(`rates.sources.${r.source_type}`, { defaultValue: r.source_type })
                              : '—'}
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
            )}

            {isAirWeekly && (
              <table className="rtable" style={{ minWidth: 1280 }}>
                <thead>
                  <tr>
                    <th>{t('rates.cols.air_weekly.airline')}</th>
                    <th>{t('rates.cols.air_weekly.service')}</th>
                    <th>{t('rates.cols.air_weekly.weekFrom')}</th>
                    <th>{t('rates.cols.air_weekly.weekTo')}</th>
                    {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                      <th key={d} className="c-right">
                        {t(`rates.cols.air_weekly.day${d}`)}
                      </th>
                    ))}
                    <th>{t('rates.currency')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(result.rates as AirWeeklyCompareItem[]).map((r) => (
                    <tr key={r.rate_id}>
                      <td style={{ fontFamily: 'var(--font-en)', fontWeight: 500 }}>
                        {r.airline_code || '—'}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--ink-700)' }}>
                        {r.service_desc || '—'}
                      </td>
                      <td className="num" style={{ color: 'var(--ink-500)' }}>
                        {r.effective_week_start || '—'}
                      </td>
                      <td className="num" style={{ color: 'var(--ink-500)' }}>
                        {r.effective_week_end || '—'}
                      </td>
                      {[1, 2, 3, 4, 5, 6, 7].map((d, idx) => {
                        const key = `price_day${d}` as keyof AirWeeklyCompareItem;
                        const raw = r[key];
                        const v = Number(raw || 0);
                        const best = v > 0 && v === airMinDays[idx];
                        return (
                          <td
                            key={d}
                            className="c-right num"
                            style={{
                              color: best ? 'var(--success)' : 'var(--ink-900)',
                              fontWeight: best ? 600 : 500,
                            }}
                          >
                            {formatNumber(raw as string | null | undefined)}
                          </td>
                        );
                      })}
                      <td style={{ color: 'var(--ink-500)' }}>{r.currency}</td>
                    </tr>
                  ))}
                  {result.rates.length === 0 && (
                    <tr>
                      <td colSpan={12} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
                        {t('compare.noData')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}

            {rateType === 'lcl' && (
              <table className="rtable" style={{ minWidth: 1180 }}>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th className="c-right">{t('rates.cols.lcl.perCbm')}</th>
                    <th className="c-right">{t('rates.cols.lcl.perTon')}</th>
                    <th>{t('rates.currency')}</th>
                    <th>{t('rates.cols.lcl.lss')}</th>
                    <th>{t('rates.cols.lcl.ebs')}</th>
                    <th>{t('rates.cols.lcl.cic')}</th>
                    <th>{t('rates.cols.lcl.amsAciEns')}</th>
                    <th>{t('rates.cols.lcl.sailingDay')}</th>
                    <th>{t('rates.cols.lcl.via')}</th>
                    <th>{t('rates.cols.lcl.validity')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(result.rates as LclCompareItem[]).map((r) => {
                    const vCbm = Number(r.freight_per_cbm || 0);
                    const vTon = Number(r.freight_per_ton || 0);
                    const bestCbm = vCbm > 0 && vCbm === lclMinCbm;
                    const bestTon = vTon > 0 && vTon === lclMinTon;
                    return (
                      <tr key={r.rate_id}>
                        <td className="num">L-{r.rate_id}</td>
                        <td
                          className="c-right num"
                          style={{
                            color: bestCbm ? 'var(--success)' : 'var(--ink-900)',
                            fontWeight: bestCbm ? 600 : 500,
                          }}
                        >
                          {formatPrice(r.freight_per_cbm)}
                        </td>
                        <td
                          className="c-right num"
                          style={{
                            color: bestTon ? 'var(--success)' : 'var(--ink-900)',
                            fontWeight: bestTon ? 600 : 500,
                          }}
                        >
                          {formatPrice(r.freight_per_ton)}
                        </td>
                        <td style={{ color: 'var(--ink-500)' }}>{r.currency}</td>
                        <td>{r.lss || '—'}</td>
                        <td>{r.ebs || '—'}</td>
                        <td>{r.cic || '—'}</td>
                        <td>{r.ams_aci_ens || '—'}</td>
                        <td style={{ color: 'var(--ink-500)' }}>{r.sailing_day || '—'}</td>
                        <td style={{ color: 'var(--ink-500)' }}>{r.via || '—'}</td>
                        <td className="num" style={{ color: 'var(--ink-500)', fontSize: 11.5 }}>
                          {r.valid_from || '—'}{r.valid_to ? ` → ${r.valid_to}` : ''}
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
            )}
          </div>
        </div>
      )}
    </div>
  );
}
