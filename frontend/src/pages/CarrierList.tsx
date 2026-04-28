import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { message } from 'antd';
import Icon from '../components/Icon';
import { carrierApi } from '../services/api';
import type { Carrier, CarrierType, PaginatedData } from '../types';

const TYPE_TAG: Record<CarrierType, string> = {
  shipping_line: 'tag-info',
  co_loader: 'tag-warn',
  agent: 'tag-success',
  nvo: 'tag-teal',
};

const PAGE_SIZE = 20;

export default function CarrierList() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [data, setData] = useState<PaginatedData<Carrier>>({
    items: [],
    total: 0,
    page: 1,
    page_size: PAGE_SIZE,
    total_pages: 0,
  });

  const fetchData = async (page = 1) => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: PAGE_SIZE, only_used: true };
      if (keyword.trim()) params.keyword = keyword.trim();
      const res = await carrierApi.list(params);
      const payload = (res as { data?: PaginatedData<Carrier> }).data;
      if (payload) setData(payload);
    } catch {
      message.error(t('carrier.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const pageNumbers: number[] = [];
  for (let i = 1; i <= Math.min(totalPages, 5); i += 1) pageNumbers.push(i);

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t('carrier.title')}</h1>
        <div className="sub">
          CARRIERS · {data.items.length} / {data.total}
        </div>
        <div className="actions">
          <button className="btn btn-secondary btn-sm" onClick={() => fetchData(data.page)}>
            <Icon name="refresh" size={12} /> {t('dashboard.refresh')}
          </button>
        </div>
      </div>

      <div className="filter-bar">
        <div className="field" style={{ flex: 1 }}>
          <label>{t('common.search')}</label>
          <input
            className="input"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') fetchData(1);
            }}
            placeholder={t('carrier.searchPlaceholder')}
            style={{ minWidth: 280 }}
          />
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => fetchData(1)}>
          <Icon name="search" size={12} /> {t('common.search')}
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => {
            setKeyword('');
            setTimeout(() => fetchData(1), 0);
          }}
        >
          {t('common.reset')}
        </button>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden', opacity: loading ? 0.7 : 1 }}>
        <div className="table-scroll">
          <table className="rtable" style={{ minWidth: 780 }}>
            <thead>
              <tr>
                <th style={{ width: 64 }}>{t('carrier.id')}</th>
                <th style={{ width: 90 }}>{t('carrier.code')}</th>
                <th>{t('carrier.nameEn')}</th>
                <th>{t('carrier.nameCn')}</th>
                <th style={{ width: 130 }}>{t('carrier.type')}</th>
                <th style={{ width: 100 }}>{t('carrier.country')}</th>
                <th style={{ width: 100 }}>{t('carrier.status')}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id}>
                  <td className="num" style={{ color: 'var(--ink-500)' }}>{c.id}</td>
                  <td>
                    <span className="tag tag-teal">{c.code}</span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-en)', fontWeight: 500 }}>{c.name_en}</td>
                  <td style={{ color: 'var(--ink-700)' }}>{c.name_cn || '—'}</td>
                  <td>
                    <span className={`tag zh ${TYPE_TAG[c.carrier_type] || 'tag-muted'}`}>
                      {t(`carrier.types.${c.carrier_type}`, c.carrier_type)}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-en)' }}>{c.country || '—'}</td>
                  <td>
                    <span className={`tag zh tag-dot ${c.is_active ? 'tag-success' : 'tag-muted'}`}>
                      {c.is_active ? t('carrier.activeStatus') : t('carrier.inactiveStatus')}
                    </span>
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-500)' }}>
                    {t('common.noData')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <div className="pg-total">
            共 {data.total} 条 · 第 {data.page} / {totalPages} 页
          </div>
          <button disabled={data.page <= 1} onClick={() => fetchData(Math.max(1, data.page - 1))}>
            ‹
          </button>
          {pageNumbers.map((n) => (
            <button key={n} className={data.page === n ? 'on' : ''} onClick={() => fetchData(n)}>
              {n}
            </button>
          ))}
          <button
            disabled={data.page >= totalPages}
            onClick={() => fetchData(Math.min(totalPages, data.page + 1))}
          >
            ›
          </button>
        </div>
      </div>
    </div>
  );
}
