import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../components/Icon';
import { carrierApi, rateApi } from '../services/api';
import type {
  AirSurchargeRate,
  AirWeeklyRate,
  Carrier,
  FreightRate,
  LclRate,
  PaginatedData,
  RateStatus,
  RateType,
} from '../types';

type ChipValue = 'all' | RateStatus;
const STATUS_CHIPS: { v: ChipValue; l: string }[] = [
  { v: 'all', l: '全部' },
  { v: 'active', l: '有效' },
  { v: 'draft', l: '待确认' },
  { v: 'expired', l: '已过期' },
];

const RATE_TYPE_TABS: RateType[] = [
  'ocean_fcl',
  'ocean_ngb',
  'air_weekly',
  'air_surcharge',
  'lcl',
];

const PAGE_SIZE = 15;

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

function statusTag(value: RateStatus) {
  if (value === 'active') return 'tag-success';
  if (value === 'draft') return 'tag-warn';
  return 'tag-muted';
}

function statusLabel(value: RateStatus, t: (key: string) => string) {
  if (value === 'active') return t('rates.statusActive');
  if (value === 'draft') return t('rates.statusDraft');
  return t('rates.statusExpired');
}

function RouteCell({ record }: { record: FreightRate }) {
  const origin = record.origin_port;
  const dest = record.destination_port;
  return (
    <div className="route">
      <div className="port">
        <div className="code">{origin?.un_locode || origin?.name_en || '—'}</div>
        <div className="name">{origin?.name_cn || origin?.name_en}</div>
      </div>
      <span className="arrow">———→</span>
      <div className="port">
        <div className="code">{dest?.un_locode || dest?.name_en || '—'}</div>
        <div className="name">{dest?.name_cn || dest?.name_en}</div>
      </div>
    </div>
  );
}

function RateDrawer({
  rate,
  onClose,
  onStatusChange,
}: {
  rate: FreightRate;
  onClose: () => void;
  onStatusChange: (id: number, status: RateStatus) => Promise<void>;
}) {
  const { t } = useTranslation();
  const nextStatus: RateStatus =
    rate.status === 'draft' ? 'active' : rate.status === 'active' ? 'expired' : 'active';

  const content = (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <h2>RT-{rate.id}</h2>
              <span className={`tag zh tag-dot ${statusTag(rate.status)}`}>
                {statusLabel(rate.status, t)}
              </span>
              <span className="tag zh tag-muted">
                {t(`rates.sources.${rate.source_type}`, rate.source_type)}
              </span>
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--ink-500)' }}>
              {rate.origin_port?.name_cn || rate.origin_port?.name_en} (
              {rate.origin_port?.un_locode}) → {rate.destination_port?.name_cn || rate.destination_port?.name_en}{' '}
              ({rate.destination_port?.un_locode}) · {rate.carrier?.name_cn || rate.carrier?.name_en} ·{' '}
              {rate.service_code || '—'}
            </div>
          </div>
          <button className="icon-btn" onClick={onClose}>
            <Icon name="close" size={16} />
          </button>
        </div>
        <div className="drawer-body">
          <div style={{ marginBottom: 18 }}>
            <div className="price-big">
              <span className="cur">{rate.currency || 'USD'}</span>
              {formatPrice(rate.container_40gp).replace('$', '')}
              <span className="u">/ 40&apos;</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--ink-500)', marginTop: 4 }}>
              基础海运费 · 不含 BAF / THC / CAF 附加费
            </div>
          </div>

          <div className="price-grid">
            <div className="col">
              <div className="l">20&apos; DC</div>
              <div className="v">{formatPrice(rate.container_20gp)}</div>
            </div>
            <div className="col">
              <div className="l">40&apos; DC</div>
              <div className="v">{formatPrice(rate.container_40gp)}</div>
            </div>
            <div className="col">
              <div className="l">40&apos; HC</div>
              <div className="v">{formatPrice(rate.container_40hq)}</div>
            </div>
          </div>

          <div className="rail-title">基本信息 · Rate Info</div>
          <dl className="kv-grid">
            <dt>运价编号</dt>
            <dd className="num">RT-{rate.id}</dd>
            <dt>航线</dt>
            <dd>
              {rate.origin_port?.name_cn || rate.origin_port?.name_en} →{' '}
              {rate.destination_port?.name_cn || rate.destination_port?.name_en}
            </dd>
            <dt>承运商</dt>
            <dd>
              {rate.carrier?.name_cn || rate.carrier?.name_en} ({rate.carrier?.code})
            </dd>
            <dt>航线代码</dt>
            <dd className="num">{rate.service_code || '—'}</dd>
            <dt>航程 (天)</dt>
            <dd className="num">{rate.transit_days ?? '—'}</dd>
            <dt>有效期</dt>
            <dd className="num">
              {rate.valid_from || '—'}
              {rate.valid_to ? ` → ${rate.valid_to}` : ''}
            </dd>
            <dt>更新时间</dt>
            <dd className="num">{rate.updated_at?.slice(0, 10)}</dd>
            <dt>数据来源</dt>
            <dd>{t(`rates.sources.${rate.source_type}`, rate.source_type)}</dd>
          </dl>

          {rate.remarks && (
            <>
              <div className="rail-title">备注 · Remarks</div>
              <div style={{ fontSize: 13, color: 'var(--ink-700)', lineHeight: 1.6 }}>{rate.remarks}</div>
            </>
          )}
        </div>
        <div className="drawer-foot">
          <button className="btn btn-ghost" onClick={onClose}>
            关闭
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              onStatusChange(rate.id, nextStatus);
            }}
          >
            切换为 {statusLabel(nextStatus, t)}
          </button>
        </div>
      </div>
    </>
  );
  return createPortal(content, document.body);
}

function OceanTable({
  items,
  loading,
  selectedId,
  onRowClick,
  t,
}: {
  items: FreightRate[];
  loading: boolean;
  selectedId: number | undefined;
  onRowClick: (r: FreightRate) => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  return (
    <table className="rtable" style={{ minWidth: 1180 }}>
      <thead>
        <tr>
          <th>运价编号</th>
          <th>航线</th>
          <th>承运商 / 航线</th>
          <th className="c-right">20&apos; DC</th>
          <th className="c-right">40&apos; DC</th>
          <th className="c-right">40&apos; HC</th>
          <th className="c-center">航程</th>
          <th>来源</th>
          <th>状态</th>
          <th>有效期</th>
        </tr>
      </thead>
      <tbody>
        {items.map((r) => {
          const carrierName = r.carrier?.name_en || r.carrier?.code || '—';
          return (
            <tr
              key={r.id}
              onClick={() => onRowClick(r)}
              className={selectedId === r.id ? 'sel' : ''}
            >
              <td>
                <span className="num" style={{ fontWeight: 500, color: 'var(--ink-900)' }}>
                  RT-{r.id}
                </span>
              </td>
              <td>
                <RouteCell record={r} />
              </td>
              <td>
                <div style={{ lineHeight: 1.3 }}>
                  <div style={{ fontWeight: 500, fontFamily: 'var(--font-en)' }}>{carrierName}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--ink-500)', fontFamily: 'var(--font-en)' }}>
                    {r.service_code || '—'}
                  </div>
                </div>
              </td>
              <td className="c-right num">{formatPrice(r.container_20gp)}</td>
              <td className="c-right num">
                <b style={{ color: 'var(--ink-900)' }}>{formatPrice(r.container_40gp)}</b>
              </td>
              <td className="c-right num">{formatPrice(r.container_40hq)}</td>
              <td className="c-center num" style={{ color: 'var(--ink-500)' }}>
                {r.transit_days ? `${r.transit_days}d` : '—'}
              </td>
              <td>
                <span className="tag zh tag-muted">
                  {t(`rates.sources.${r.source_type}`, { defaultValue: r.source_type })}
                </span>
              </td>
              <td>
                <span className={`tag zh tag-dot ${statusTag(r.status)}`}>
                  {statusLabel(r.status, t)}
                </span>
              </td>
              <td
                style={{
                  fontFamily: 'var(--font-en)',
                  fontSize: 11.5,
                  color: 'var(--ink-500)',
                  whiteSpace: 'nowrap',
                }}
              >
                {r.valid_to || '—'}
              </td>
            </tr>
          );
        })}
        {items.length === 0 && !loading && (
          <tr>
            <td colSpan={10} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
              <div style={{ fontWeight: 500 }}>{t('rates.empty.title')}</div>
              <div style={{ fontSize: 12, marginTop: 6 }}>{t('rates.empty.hint')}</div>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function AirWeeklyTable({
  items,
  loading,
  t,
}: {
  items: AirWeeklyRate[];
  loading: boolean;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  return (
    <table className="rtable" style={{ minWidth: 1320 }}>
      <thead>
        <tr>
          <th>ID</th>
          <th>{t('rates.cols.air_weekly.airline')}</th>
          <th>{t('rates.originText')}</th>
          <th>{t('rates.destinationText')}</th>
          <th>{t('rates.cols.air_weekly.service')}</th>
          <th>{t('rates.cols.air_weekly.weekFrom')}</th>
          <th>{t('rates.cols.air_weekly.weekTo')}</th>
          <th className="c-right">{t('rates.cols.air_weekly.day1')}</th>
          <th className="c-right">{t('rates.cols.air_weekly.day2')}</th>
          <th className="c-right">{t('rates.cols.air_weekly.day3')}</th>
          <th className="c-right">{t('rates.cols.air_weekly.day4')}</th>
          <th className="c-right">{t('rates.cols.air_weekly.day5')}</th>
          <th className="c-right">{t('rates.cols.air_weekly.day6')}</th>
          <th className="c-right">{t('rates.cols.air_weekly.day7')}</th>
          <th>{t('rates.currency')}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((r) => (
          <tr key={r.id}>
            <td className="num" style={{ color: 'var(--ink-700)' }}>A-{r.id}</td>
            <td style={{ fontFamily: 'var(--font-en)', fontWeight: 500 }}>{r.airline_code || '—'}</td>
            <td style={{ fontFamily: 'var(--font-en)' }}>{r.origin}</td>
            <td style={{ fontFamily: 'var(--font-en)' }}>{r.destination}</td>
            <td style={{ fontSize: 12, color: 'var(--ink-700)' }}>{r.service_desc || '—'}</td>
            <td className="num" style={{ color: 'var(--ink-500)' }}>{r.effective_week_start || '—'}</td>
            <td className="num" style={{ color: 'var(--ink-500)' }}>{r.effective_week_end || '—'}</td>
            <td className="c-right num">{formatNumber(r.price_day1)}</td>
            <td className="c-right num">{formatNumber(r.price_day2)}</td>
            <td className="c-right num">{formatNumber(r.price_day3)}</td>
            <td className="c-right num">{formatNumber(r.price_day4)}</td>
            <td className="c-right num">{formatNumber(r.price_day5)}</td>
            <td className="c-right num">{formatNumber(r.price_day6)}</td>
            <td className="c-right num">{formatNumber(r.price_day7)}</td>
            <td style={{ color: 'var(--ink-500)' }}>{r.currency}</td>
          </tr>
        ))}
        {items.length === 0 && !loading && (
          <tr>
            <td colSpan={15} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
              <div style={{ fontWeight: 500 }}>{t('rates.empty.title')}</div>
              <div style={{ fontSize: 12, marginTop: 6 }}>{t('rates.empty.hint')}</div>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function AirSurchargeTable({
  items,
  loading,
  t,
}: {
  items: AirSurchargeRate[];
  loading: boolean;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  return (
    <table className="rtable" style={{ minWidth: 1200 }}>
      <thead>
        <tr>
          <th>ID</th>
          <th>{t('rates.cols.air_surcharge.airline')}</th>
          <th>{t('rates.cols.air_surcharge.fromRegion')}</th>
          <th>{t('rates.cols.air_surcharge.area')}</th>
          <th>{t('rates.cols.air_surcharge.destScope')}</th>
          <th className="c-right">{t('rates.cols.air_surcharge.mycMin')}</th>
          <th className="c-right">{t('rates.cols.air_surcharge.mycPerKg')}</th>
          <th className="c-right">{t('rates.cols.air_surcharge.mscMin')}</th>
          <th className="c-right">{t('rates.cols.air_surcharge.mscPerKg')}</th>
          <th>{t('rates.cols.air_surcharge.effective')}</th>
          <th>{t('rates.currency')}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((r) => (
          <tr key={r.id}>
            <td className="num">S-{r.id}</td>
            <td style={{ fontFamily: 'var(--font-en)', fontWeight: 500 }}>{r.airline_code || '—'}</td>
            <td style={{ color: 'var(--ink-700)' }}>{r.from_region || '—'}</td>
            <td style={{ color: 'var(--ink-700)' }}>{r.area || '—'}</td>
            <td style={{ fontSize: 12, color: 'var(--ink-500)' }}>{r.destination_scope || '—'}</td>
            <td className="c-right num">{formatNumber(r.myc_min)}</td>
            <td className="c-right num">{formatNumber(r.myc_fee_per_kg)}</td>
            <td className="c-right num">{formatNumber(r.msc_min)}</td>
            <td className="c-right num">{formatNumber(r.msc_fee_per_kg)}</td>
            <td className="num" style={{ color: 'var(--ink-500)' }}>{r.effective_date || '—'}</td>
            <td style={{ color: 'var(--ink-500)' }}>{r.currency}</td>
          </tr>
        ))}
        {items.length === 0 && !loading && (
          <tr>
            <td colSpan={11} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
              <div style={{ fontWeight: 500 }}>{t('rates.empty.title')}</div>
              <div style={{ fontSize: 12, marginTop: 6 }}>{t('rates.empty.hint')}</div>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function LclTable({
  items,
  loading,
  t,
}: {
  items: LclRate[];
  loading: boolean;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  return (
    <table className="rtable" style={{ minWidth: 1280 }}>
      <thead>
        <tr>
          <th>ID</th>
          <th>{t('rates.originPort')}</th>
          <th>{t('rates.destinationPort')}</th>
          <th className="c-right">{t('rates.cols.lcl.perCbm')}</th>
          <th className="c-right">{t('rates.cols.lcl.perTon')}</th>
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
        {items.map((r) => (
          <tr key={r.id}>
            <td className="num">L-{r.id}</td>
            <td>{r.origin_port?.un_locode || r.origin_port?.name_en || '—'}</td>
            <td>{r.destination_port?.un_locode || r.destination_port?.name_en || '—'}</td>
            <td className="c-right num">{formatPrice(r.freight_per_cbm)}</td>
            <td className="c-right num">{formatPrice(r.freight_per_ton)}</td>
            <td style={{ color: 'var(--ink-700)' }}>{r.lss || '—'}</td>
            <td style={{ color: 'var(--ink-700)' }}>{r.ebs || '—'}</td>
            <td style={{ color: 'var(--ink-700)' }}>{r.cic || '—'}</td>
            <td style={{ color: 'var(--ink-700)' }}>{r.ams_aci_ens || '—'}</td>
            <td style={{ color: 'var(--ink-500)' }}>{r.sailing_day || '—'}</td>
            <td style={{ color: 'var(--ink-500)' }}>{r.via || '—'}</td>
            <td className="num" style={{ color: 'var(--ink-500)', fontSize: 11.5 }}>
              {r.valid_from || '—'}{r.valid_to ? ` → ${r.valid_to}` : ''}
            </td>
          </tr>
        ))}
        {items.length === 0 && !loading && (
          <tr>
            <td colSpan={12} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
              <div style={{ fontWeight: 500 }}>{t('rates.empty.title')}</div>
              <div style={{ fontSize: 12, marginTop: 6 }}>{t('rates.empty.hint')}</div>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

export default function RateList() {
  const { t } = useTranslation();
  const [rateType, setRateType] = useState<RateType>('ocean_fcl');
  const [data, setData] = useState<
    FreightRate[] | AirWeeklyRate[] | AirSurchargeRate[] | LclRate[]
  >([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [carriers, setCarriers] = useState<Carrier[]>([]);
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [carrierId, setCarrierId] = useState<number | ''>('');
  const [airlineCode, setAirlineCode] = useState('');
  const [status, setStatus] = useState<ChipValue>('all');
  const [selected, setSelected] = useState<FreightRate | null>(null);

  const isOcean = rateType === 'ocean_fcl' || rateType === 'ocean_ngb';
  const isAirWeekly = rateType === 'air_weekly';
  const isAirSurcharge = rateType === 'air_surcharge';
  const isLcl = rateType === 'lcl';

  useEffect(() => {
    carrierApi
      .list({ page_size: 50 })
      .then((res) => {
        const payload = (res as { data?: PaginatedData<Carrier> })?.data;
        if (payload?.items) setCarriers(payload.items);
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  const fetchRates = (nextPage = page) => {
    setLoading(true);
    const params: Record<string, unknown> = {
      rate_type: rateType,
      page: nextPage,
      page_size: PAGE_SIZE,
    };
    if (isOcean) {
      if (origin) params.origin = origin;
      if (destination) params.destination = destination;
      if (carrierId) params.carrier_id = carrierId;
      if (status !== 'all') params.status = status;
    } else if (isAirWeekly) {
      if (origin) params.origin_text = origin;
      if (destination) params.destination_text = destination;
      if (airlineCode) params.airline_code = airlineCode;
    } else if (isAirSurcharge) {
      if (airlineCode) params.airline_code = airlineCode;
    } else if (isLcl) {
      // LCL 目前只用 port_id 下拉，暂按 origin/destination 文本传入 port id 放弃，保留无筛选版本
    }

    rateApi
      .list(params)
      .then((res) => {
        const payload = (res as { data?: PaginatedData<unknown> })?.data;
        setData((payload?.items as typeof data) || []);
        setTotal(payload?.total || 0);
      })
      .catch(() => {
        setData([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchRates(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, status, rateType]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageNumbers = useMemo(() => {
    const arr: number[] = [];
    for (let i = 1; i <= Math.min(totalPages, 5); i += 1) arr.push(i);
    return arr;
  }, [totalPages]);

  const handleSearch = () => {
    setPage(1);
    fetchRates(1);
  };

  const reset = () => {
    setOrigin('');
    setDestination('');
    setCarrierId('');
    setAirlineCode('');
    setStatus('all');
    setPage(1);
    setTimeout(() => fetchRates(1), 0);
  };

  const handleTabChange = (next: RateType) => {
    if (next === rateType) return;
    setRateType(next);
    setPage(1);
    setOrigin('');
    setDestination('');
    setCarrierId('');
    setAirlineCode('');
    setStatus('all');
    setSelected(null);
  };

  const handleStatusChange = async (id: number, nextStatus: RateStatus) => {
    try {
      await rateApi.updateStatus(id, nextStatus);
      message.success(t('rates.statusUpdateSuccess'));
      fetchRates();
      setSelected((cur) => (cur && cur.id === id ? { ...cur, status: nextStatus } : cur));
    } catch {
      message.error(t('rates.statusUpdateFailed'));
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('rates.title')}</h1>
        <div className="sub">
          ALL RATES · {data.length} / {total}
        </div>
        <div className="actions">
          <button className="btn btn-secondary btn-sm" onClick={() => fetchRates()}>
            <Icon name="refresh" size={12} /> {t('dashboard.refresh')}
          </button>
          <button className="btn btn-secondary btn-sm">
            <Icon name="filter" size={12} /> {t('rates.advancedFilter')}
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: 'var(--ink-500)', marginRight: 4 }}>
          {t('rates.tabsLabel')}:
        </span>
        <div className="chip-group">
          {RATE_TYPE_TABS.map((v) => (
            <button
              key={v}
              type="button"
              className={`chip${rateType === v ? ' on' : ''}`}
              onClick={() => handleTabChange(v)}
            >
              {t(`rates.tabs.${v}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-bar">
        {isOcean && (
          <>
            <div className="field">
              <label>POL {t('rates.originPort')}</label>
              <input
                className="input"
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                placeholder="Shanghai / SHA"
              />
            </div>
            <div className="field">
              <label>POD {t('rates.destinationPort')}</label>
              <input
                className="input"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="Los Angeles / LAX"
              />
            </div>
            <div className="field">
              <label>{t('rates.shippingLine')}</label>
              <select
                className="select"
                value={carrierId}
                onChange={(e) => setCarrierId(e.target.value ? Number(e.target.value) : '')}
              >
                <option value="">全部</option>
                {carriers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} · {c.name_cn || c.name_en}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}
        {isAirWeekly && (
          <>
            <div className="field">
              <label>{t('rates.originText')}</label>
              <input
                className="input"
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                placeholder="PVG / HKG"
              />
            </div>
            <div className="field">
              <label>{t('rates.destinationText')}</label>
              <input
                className="input"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="LAX / ATL"
              />
            </div>
            <div className="field">
              <label>{t('rates.airlineCode')}</label>
              <input
                className="input"
                value={airlineCode}
                onChange={(e) => setAirlineCode(e.target.value)}
                placeholder="NH / CZ"
              />
            </div>
          </>
        )}
        {isAirSurcharge && (
          <div className="field">
            <label>{t('rates.airlineCode')}</label>
            <input
              className="input"
              value={airlineCode}
              onChange={(e) => setAirlineCode(e.target.value)}
              placeholder="NH"
            />
          </div>
        )}
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary btn-sm" onClick={handleSearch}>
          <Icon name="search" size={12} /> {t('common.search')}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={reset}>
          {t('common.reset')}
        </button>
      </div>

      {isOcean && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--ink-500)', marginRight: 4 }}>状态:</span>
          <div className="chip-group">
            {STATUS_CHIPS.map((c) => (
              <button
                key={c.v}
                type="button"
                className={`chip${status === c.v ? ' on' : ''}`}
                onClick={() => {
                  setStatus(c.v);
                  setPage(1);
                }}
              >
                {c.l}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden', opacity: loading ? 0.7 : 1 }}>
        <div className="table-scroll">
          {isOcean && (
            <OceanTable
              items={data as FreightRate[]}
              loading={loading}
              selectedId={selected?.id}
              onRowClick={(r) => setSelected(r)}
              t={t}
            />
          )}
          {isAirWeekly && (
            <AirWeeklyTable items={data as AirWeeklyRate[]} loading={loading} t={t} />
          )}
          {isAirSurcharge && (
            <AirSurchargeTable items={data as AirSurchargeRate[]} loading={loading} t={t} />
          )}
          {isLcl && <LclTable items={data as LclRate[]} loading={loading} t={t} />}
        </div>

        <div className="pager">
          <div className="pg-total">
            共 {total} 条 · 第 {page} / {totalPages} 页
          </div>
          <button disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            ‹
          </button>
          {pageNumbers.map((n) => (
            <button key={n} className={page === n ? 'on' : ''} onClick={() => setPage(n)}>
              {n}
            </button>
          ))}
          <button
            disabled={page === totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            ›
          </button>
        </div>
      </div>

      {selected && isOcean && (
        <RateDrawer
          rate={selected}
          onClose={() => setSelected(null)}
          onStatusChange={handleStatusChange}
        />
      )}
    </div>
  );
}
