import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../components/Icon';
import { carrierApi, rateApi } from '../services/api';
import type { Carrier, FreightRate, PaginatedData, RateStatus } from '../types';

type ChipValue = 'all' | RateStatus;
const STATUS_CHIPS: { v: ChipValue; l: string }[] = [
  { v: 'all', l: '全部' },
  { v: 'active', l: '有效' },
  { v: 'draft', l: '待确认' },
  { v: 'expired', l: '已过期' },
];

const PAGE_SIZE = 15;

function formatPrice(value?: string) {
  if (!value) return '—';
  const num = Number(value);
  if (!Number.isFinite(num) || num === 0) return '—';
  return `$${Math.round(num).toLocaleString()}`;
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

export default function RateList() {
  const { t } = useTranslation();
  const [data, setData] = useState<FreightRate[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [carriers, setCarriers] = useState<Carrier[]>([]);
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [carrierId, setCarrierId] = useState<number | ''>('');
  const [status, setStatus] = useState<ChipValue>('all');
  const [selected, setSelected] = useState<FreightRate | null>(null);

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
      page: nextPage,
      page_size: PAGE_SIZE,
    };
    if (origin) params.origin = origin;
    if (destination) params.destination = destination;
    if (carrierId) params.carrier_id = carrierId;
    if (status !== 'all') params.status = status;

    rateApi
      .list(params)
      .then((res) => {
        const payload = (res as { data?: PaginatedData<FreightRate> })?.data;
        setData(payload?.items || []);
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
  }, [page, status]);

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
    setStatus('all');
    setPage(1);
    setTimeout(() => fetchRates(1), 0);
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

      <div className="filter-bar">
        <div className="field">
          <label>POL 起运港</label>
          <input
            className="input"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            placeholder="Shanghai / SHA"
          />
        </div>
        <div className="field">
          <label>POD 目的港</label>
          <input
            className="input"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="Los Angeles / LAX"
          />
        </div>
        <div className="field">
          <label>承运商</label>
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
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary btn-sm" onClick={handleSearch}>
          <Icon name="search" size={12} /> {t('common.search')}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={reset}>
          {t('common.reset')}
        </button>
      </div>

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

      <div className="card" style={{ padding: 0, overflow: 'hidden', opacity: loading ? 0.7 : 1 }}>
        <div className="table-scroll">
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
            {data.map((r) => {
              const carrierName = r.carrier?.name_en || r.carrier?.code || '—';
              return (
                <tr
                  key={r.id}
                  onClick={() => setSelected(r)}
                  className={selected?.id === r.id ? 'sel' : ''}
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
                      {t(`rates.sources.${r.source_type}`, r.source_type)}
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
            {data.length === 0 && !loading && (
              <tr>
                <td colSpan={10} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
                  {t('common.noData')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
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

      {selected && (
        <RateDrawer
          rate={selected}
          onClose={() => setSelected(null)}
          onStatusChange={handleStatusChange}
        />
      )}
    </div>
  );
}
