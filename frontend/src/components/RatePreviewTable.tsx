import { useTranslation } from 'react-i18next';
import type { RateBatchPreviewRow } from '../types';

interface Props {
  rows: RateBatchPreviewRow[];
  minWidth?: number;
  fontSize?: number;
}

type Layout = 'air_weekly' | 'air_surcharge' | 'ocean';

function pickLayout(rows: RateBatchPreviewRow[]): Layout {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const k = String(r.record_kind || '');
    counts[k] = (counts[k] || 0) + 1;
  }
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0];
  if (top === 'air_weekly') return 'air_weekly';
  if (top === 'air_surcharge') return 'air_surcharge';
  return 'ocean';
}

export default function RatePreviewTable({ rows, minWidth = 720, fontSize = 12 }: Props) {
  const { t } = useTranslation();
  const layout = pickLayout(rows);

  return (
    <div className="table-scroll">
      <table className="rtable" style={{ minWidth, fontSize }}>
        {layout === 'air_weekly' && <AirWeeklyHead t={t} />}
        {layout === 'air_surcharge' && <AirSurchargeHead t={t} />}
        {layout === 'ocean' && <OceanHead t={t} />}
        <tbody>
          {rows.map((row) => {
            const kind = String(row.record_kind || '');
            if (layout === 'air_weekly' && kind === 'air_weekly') {
              return <AirWeeklyRow key={row.row_index} row={row} />;
            }
            if (layout === 'air_surcharge' && kind === 'air_surcharge') {
              return <AirSurchargeRow key={row.row_index} row={row} />;
            }
            if (layout === 'ocean' && (kind === '' || kind.startsWith('fcl') || kind.startsWith('ocean'))) {
              return <OceanRow key={row.row_index} row={row} />;
            }
            return <MismatchRow key={row.row_index} row={row} layout={layout} />;
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={12} style={{ textAlign: 'center', padding: 24, color: 'var(--ink-500)' }}>
                {t('common.noData')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

type TFn = ReturnType<typeof useTranslation>['t'];

function OceanHead({ t }: { t: TFn }) {
  return (
    <thead>
      <tr>
        <th style={{ width: 40 }}>#</th>
        <th>{t('batches.col.carrier')}</th>
        <th>{t('batches.col.origin')}</th>
        <th>{t('batches.col.destination')}</th>
        <th className="c-right">20&apos;</th>
        <th className="c-right">40&apos;</th>
        <th className="c-right">40&apos;HC</th>
        <th className="c-center">{t('batches.col.transit')}</th>
        <th>{t('batches.col.valid')}</th>
      </tr>
    </thead>
  );
}

function OceanRow({ row }: { row: RateBatchPreviewRow }) {
  return (
    <tr>
      <td className="num" style={{ color: 'var(--ink-500)' }}>{row.row_index}</td>
      <td>{row.carrier ? <span className="tag tag-teal">{row.carrier}</span> : '—'}</td>
      <td>{row.origin_port || '—'}</td>
      <td>{row.destination_port || '—'}</td>
      <td className="c-right num">{row.container_20gp || '—'}</td>
      <td className="c-right num"><b>{row.container_40gp || '—'}</b></td>
      <td className="c-right num">{row.container_40hq || '—'}</td>
      <td className="c-center num" style={{ color: 'var(--ink-500)' }}>
        {row.transit_days ? `${row.transit_days}d` : '—'}
      </td>
      <td className="num" style={{ color: 'var(--ink-500)', fontSize: 11 }}>
        {row.valid_from || '—'}
        {row.valid_to ? ` → ${row.valid_to}` : ''}
      </td>
    </tr>
  );
}

function AirWeeklyHead({ t }: { t: TFn }) {
  return (
    <thead>
      <tr>
        <th style={{ width: 40 }}>#</th>
        <th>{t('rates.cols.air_weekly.airline')}</th>
        <th>{t('batches.col.origin')}</th>
        <th>{t('batches.col.destination')}</th>
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
      </tr>
    </thead>
  );
}

function AirWeeklyRow({ row }: { row: RateBatchPreviewRow }) {
  return (
    <tr>
      <td className="num" style={{ color: 'var(--ink-500)' }}>{row.row_index}</td>
      <td>{row.airline_code ? <span className="tag tag-teal">{row.airline_code}</span> : '—'}</td>
      <td>{row.origin_port || '—'}</td>
      <td>{row.destination_port || '—'}</td>
      <td style={{ fontSize: 11.5, color: 'var(--ink-700)' }}>{row.service_desc || '—'}</td>
      <td className="num" style={{ fontSize: 11 }}>{row.effective_week_start || '—'}</td>
      <td className="num" style={{ fontSize: 11 }}>{row.effective_week_end || '—'}</td>
      <td className="c-right num">{row.price_day1 || '—'}</td>
      <td className="c-right num">{row.price_day2 || '—'}</td>
      <td className="c-right num">{row.price_day3 || '—'}</td>
      <td className="c-right num">{row.price_day4 || '—'}</td>
      <td className="c-right num">{row.price_day5 || '—'}</td>
      <td className="c-right num">{row.price_day6 || '—'}</td>
      <td className="c-right num">{row.price_day7 || '—'}</td>
    </tr>
  );
}

function AirSurchargeHead({ t }: { t: TFn }) {
  return (
    <thead>
      <tr>
        <th style={{ width: 40 }}>#</th>
        <th>{t('rates.cols.air_surcharge.airline')}</th>
        <th>{t('rates.cols.air_surcharge.area')}</th>
        <th>{t('rates.cols.air_surcharge.fromRegion')}</th>
        <th>{t('rates.cols.air_surcharge.effective')}</th>
        <th className="c-right">{t('rates.cols.air_surcharge.mycMin')}</th>
        <th className="c-right">{t('rates.cols.air_surcharge.mycPerKg')}</th>
        <th className="c-right">{t('rates.cols.air_surcharge.mscMin')}</th>
        <th className="c-right">{t('rates.cols.air_surcharge.mscPerKg')}</th>
        <th>{t('rates.cols.air_surcharge.destScope')}</th>
      </tr>
    </thead>
  );
}

function AirSurchargeRow({ row }: { row: RateBatchPreviewRow }) {
  return (
    <tr>
      <td className="num" style={{ color: 'var(--ink-500)' }}>{row.row_index}</td>
      <td>{row.airline_code ? <span className="tag tag-teal">{row.airline_code}</span> : '—'}</td>
      <td>{row.area || '—'}</td>
      <td>{row.from_region || '—'}</td>
      <td className="num" style={{ fontSize: 11 }}>{row.effective_date || '—'}</td>
      <td className="c-right num">{row.myc_min || '—'}</td>
      <td className="c-right num">{row.myc_fee_per_kg || '—'}</td>
      <td className="c-right num">{row.msc_min || '—'}</td>
      <td className="c-right num">{row.msc_fee_per_kg || '—'}</td>
      <td style={{ fontSize: 11.5, color: 'var(--ink-700)' }}>{row.destination_scope || '—'}</td>
    </tr>
  );
}

function MismatchRow({ row, layout }: { row: RateBatchPreviewRow; layout: Layout }) {
  const span =
    layout === 'air_weekly' ? 14 : layout === 'air_surcharge' ? 10 : 9;
  return (
    <tr>
      <td className="num" style={{ color: 'var(--ink-500)' }}>{row.row_index}</td>
      <td colSpan={span - 1} style={{ color: 'var(--ink-500)', fontSize: 11.5 }}>
        {row.record_kind || '—'}
      </td>
    </tr>
  );
}
