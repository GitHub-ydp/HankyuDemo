import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icon';
import { KPI_METAS, QUICK_ACTIONS } from '../data/mockData';
import type { KpiMeta } from '../data/mockData';
import { rateApi } from '../services/api';
import type { FreightRate, PaginatedData, RateStats, RateStatus } from '../types';

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

function KpiCard({ meta, value }: { meta: KpiMeta; value: number | null }) {
  return (
    <div className="kpi">
      <div className="kpi-label">
        <span className="zh">{meta.labelZh}</span>
        {meta.labelEn}
      </div>
      <div className="kpi-value">
        {value === null ? '—' : value.toLocaleString()}
        <span className="unit">{meta.unit}</span>
      </div>
    </div>
  );
}

interface Segment {
  v: number;
  color: string;
  label: string;
}

function Donut({ segments, size = 140 }: { segments: Segment[]; size?: number }) {
  const total = segments.reduce((s, seg) => s + seg.v, 0);
  const r = size / 2 - 14;
  const cx = size / 2;
  const cy = size / 2;
  const C = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg width={size} height={size}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--line)" strokeWidth={14} />
      {segments.map((seg, i) => {
        const len = total === 0 ? 0 : (seg.v / total) * C;
        const el = (
          <circle
            key={i}
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={seg.color}
            strokeWidth={14}
            strokeDasharray={`${len} ${C}`}
            strokeDashoffset={-offset}
            transform={`rotate(-90 ${cx} ${cy})`}
            strokeLinecap="butt"
          />
        );
        offset += len;
        return el;
      })}
      <text
        x={cx}
        y={cy - 2}
        textAnchor="middle"
        fontFamily="var(--font-en)"
        fontSize={22}
        fontWeight={500}
        fill="var(--ink-900)"
      >
        {total.toLocaleString()}
      </text>
      <text
        x={cx}
        y={cy + 18}
        textAnchor="middle"
        fontFamily="var(--font-zh)"
        fontSize={11}
        fill="var(--ink-500)"
      >
        运价总数
      </text>
    </svg>
  );
}

export default function Dashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [stats, setStats] = useState<RateStats | null>(null);
  const [recent, setRecent] = useState<FreightRate[]>([]);
  const [statsFailed, setStatsFailed] = useState(false);
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  useEffect(() => {
    rateApi
      .stats()
      .then((res) => {
        const data = (res as { data?: RateStats })?.data;
        if (data) setStats(data);
        else setStatsFailed(true);
      })
      .catch(() => setStatsFailed(true));

    rateApi
      .list({ page: 1, page_size: 5 })
      .then((res) => {
        const data = (res as { data?: PaginatedData<FreightRate> })?.data;
        if (data?.items) setRecent(data.items);
      })
      .catch(() => {
        /* ignore — the card will simply not render */
      });
  }, []);

  const kpiValue = (key: KpiMeta['key']): number | null => {
    if (!stats) return null;
    switch (key) {
      case 'total':
        return stats.total_rates;
      case 'active':
        return stats.active_rates;
      case 'draft':
        return stats.draft_rates;
      case 'lanes':
        return stats.routes_count;
      case 'carriers':
        return stats.carriers_count;
      default:
        return null;
    }
  };

  const segments: Segment[] | null = stats
    ? (() => {
        const other = Math.max(
          0,
          stats.total_rates - stats.active_rates - stats.draft_rates
        );
        const arr: Segment[] = [
          { v: stats.active_rates, color: '#1E6B74', label: t('rates.statusActive') },
          { v: stats.draft_rates, color: '#F79009', label: t('rates.statusDraft') },
        ];
        if (other > 0) {
          arr.push({ v: other, color: '#98A2B3', label: t('dashboard.otherStatus') });
        }
        return arr;
      })()
    : null;
  const segTotal = segments ? segments.reduce((s, seg) => s + seg.v, 0) : 0;

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('dashboard.title')}</h1>
        <div className="sub">OVERVIEW · {today}</div>
        <div className="actions">
          <button className="btn btn-secondary btn-sm" onClick={() => window.location.reload()}>
            <Icon name="refresh" size={12} /> {t('dashboard.refresh')}
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => navigate('/upload')}>
            <Icon name="plus" size={12} /> {t('dashboard.newRate')}
          </button>
        </div>
      </div>

      {statsFailed && (
        <div className="alert alert-warn" style={{ marginBottom: 16 }}>
          <div className="alert-icon">
            <Icon name="alert" size={16} />
          </div>
          <div className="alert-body">
            <div className="alert-title">{t('dashboard.statsLoadFailed')}</div>
            <div className="alert-desc">{t('dashboard.statsLoadFailedHint')}</div>
          </div>
        </div>
      )}

      <div className="kpi-grid">
        {KPI_METAS.map((meta) => (
          <KpiCard key={meta.key} meta={meta} value={kpiValue(meta.key)} />
        ))}
      </div>

      {segments && segTotal > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <h3>{t('dashboard.statusTitle')}</h3>
            <span className="sub right">STATUS MIX</span>
          </div>
          <div className="card-body" style={{ display: 'flex', alignItems: 'center', gap: 32, flexWrap: 'wrap' }}>
            <Donut segments={segments} />
            <div style={{ flex: 1, minWidth: 260 }}>
              {segments.map((seg, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '8px 0',
                    fontSize: 13,
                    borderBottom: i < segments.length - 1 ? '1px solid var(--line-2)' : 'none',
                  }}
                >
                  <span style={{ width: 10, height: 10, borderRadius: 3, background: seg.color }} />
                  <span style={{ flex: 1, color: 'var(--ink-800)' }}>{seg.label}</span>
                  <span className="num" style={{ color: 'var(--ink-900)', fontWeight: 500 }}>
                    {seg.v.toLocaleString()}
                  </span>
                  <span
                    className="num"
                    style={{ color: 'var(--ink-500)', fontSize: 11.5, minWidth: 48, textAlign: 'right' }}
                  >
                    {segTotal === 0 ? '—' : ((seg.v / segTotal) * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h3>{t('dashboard.quickActions')}</h3>
          <span className="sub right">QUICK ACTIONS</span>
        </div>
        <div className="card-body">
          <div className="qa-grid">
            {QUICK_ACTIONS.map((q) => (
              <button type="button" key={q.to} className="qa" onClick={() => navigate(q.to)}>
                <div className="qa-icon">
                  <Icon name={q.icon} size={16} />
                </div>
                <div className="qa-title">{q.titleZh}</div>
                <div className="qa-desc">{q.desc}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {recent.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="card-head">
            <h3>{t('dashboard.recentTitle')}</h3>
            <span className="sub right">RECENT · {recent.length}</span>
            <button
              className="btn btn-ghost btn-sm"
              style={{ marginLeft: 'auto' }}
              onClick={() => navigate('/rates')}
            >
              {t('dashboard.viewAll')} <Icon name="arrow-right" size={11} />
            </button>
          </div>
          <div className="table-scroll">
            <table className="rtable" style={{ minWidth: 820 }}>
              <thead>
                <tr>
                  <th>{t('rates.originPort')}</th>
                  <th>{t('rates.destinationPort')}</th>
                  <th>{t('rates.shippingLine')}</th>
                  <th className="c-right">40&apos; DC</th>
                  <th>{t('rates.source')}</th>
                  <th>{t('rates.status')}</th>
                  <th>{t('rates.effectiveDate')}</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.id} onClick={() => navigate('/rates')} style={{ cursor: 'pointer' }}>
                    <td style={{ fontSize: 12.5 }}>
                      {r.origin_port?.un_locode || r.origin_port?.name_en || '—'}
                      {r.origin_port?.name_cn && (
                        <span style={{ color: 'var(--ink-500)', marginLeft: 6, fontSize: 11.5 }}>
                          {r.origin_port.name_cn}
                        </span>
                      )}
                    </td>
                    <td style={{ fontSize: 12.5 }}>
                      {r.destination_port?.un_locode || r.destination_port?.name_en || '—'}
                      {r.destination_port?.name_cn && (
                        <span style={{ color: 'var(--ink-500)', marginLeft: 6, fontSize: 11.5 }}>
                          {r.destination_port.name_cn}
                        </span>
                      )}
                    </td>
                    <td>
                      <span className="tag tag-teal">{r.carrier?.code || '—'}</span>
                    </td>
                    <td className="c-right num" style={{ fontWeight: 500 }}>
                      {formatPrice(r.container_40gp)}
                    </td>
                    <td>
                      <span className="tag zh tag-muted">
                        {t(`rates.sources.${r.source_type}`, r.source_type)}
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
                    <td className="num" style={{ color: 'var(--ink-500)', fontSize: 12 }}>
                      {r.valid_from || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
