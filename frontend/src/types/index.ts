// 通用 API 响应
export interface ApiResponse<T = unknown> {
  code: number;
  data: T;
  message: string;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// 港口
export interface Port {
  id: number;
  un_locode: string;
  name_en: string;
  name_cn?: string;
  name_ja?: string;
  country?: string;
  region?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// 船司
export type CarrierType = 'shipping_line' | 'co_loader' | 'agent' | 'nvo';

export interface Carrier {
  id: number;
  code: string;
  name_en: string;
  name_cn?: string;
  name_ja?: string;
  carrier_type: CarrierType;
  country?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// 费率状态
export type RateStatus = 'draft' | 'active' | 'expired';
export type SourceType = 'excel' | 'pdf' | 'email_text' | 'wechat_image' | 'manual';

// 海运费率
export interface FreightRate {
  id: number;
  carrier_id: number;
  origin_port_id: number;
  destination_port_id: number;
  service_code?: string;
  container_20gp?: string;
  container_40gp?: string;
  container_40hq?: string;
  container_45?: string;
  baf_20?: string;
  baf_40?: string;
  lss_20?: string;
  lss_40?: string;
  currency: string;
  valid_from?: string;
  valid_to?: string;
  transit_days?: number;
  is_direct: boolean;
  remarks?: string;
  source_type: SourceType;
  source_file?: string;
  upload_batch_id?: string;
  status: RateStatus;
  created_at: string;
  updated_at: string;
  carrier?: Carrier;
  origin_port?: Port;
  destination_port?: Port;
}

// 上传解析预览
export interface ParsePreviewRow {
  origin_port: string;
  destination_port: string;
  carrier: string;
  container_20gp?: string;
  container_40gp?: string;
  container_40hq?: string;
  container_45?: string;
  baf_20?: string;
  baf_40?: string;
  lss_20?: string;
  lss_40?: string;
  valid_from?: string;
  valid_to?: string;
  transit_days?: string;
  remarks?: string;
  service_code?: string;
}

export interface ParseResult {
  batch_id: string;
  file_name: string;
  source_type: string;
  carrier_code: string;
  total_rows: number;
  preview_rows: ParsePreviewRow[];
  warnings: string[];
  sheets?: { name: string; rows: number }[];
}

export interface ImportResult {
  batch_id: string;
  records_parsed: number;
  records_imported: number;
  errors: string[];
}

// 费率统计
export interface RateStats {
  total_rates: number;
  active_rates: number;
  draft_rates: number;
  carriers_count: number;
  routes_count: number;
}

// 比价
export interface CompareRateItem {
  rate_id: number;
  carrier_code: string;
  carrier_name: string;
  container_20gp?: string;
  container_40gp?: string;
  container_40hq?: string;
  container_45?: string;
  baf_20?: string;
  baf_40?: string;
  lss_20?: string;
  lss_40?: string;
  currency: string;
  valid_from?: string;
  valid_to?: string;
  transit_days?: number;
  is_direct: boolean;
  source_type?: string;
  status?: string;
}

// 海运比价别名（与后端 OceanCompareItem 对齐）
export type OceanCompareItem = CompareRateItem;

// 5 tab 运价类型（列表）
export type RateType =
  | 'ocean_fcl'
  | 'ocean_ngb'
  | 'air_weekly'
  | 'air_surcharge'
  | 'lcl';

// 4 tab 比价类型（不含 air_surcharge）
export type CompareRateType = 'ocean_fcl' | 'ocean_ngb' | 'air_weekly' | 'lcl';

// 空运周价
export interface AirWeeklyRate {
  id: number;
  origin: string;
  destination: string;
  airline_code?: string | null;
  service_desc?: string | null;
  effective_week_start?: string | null;
  effective_week_end?: string | null;
  price_day1?: string | null;
  price_day2?: string | null;
  price_day3?: string | null;
  price_day4?: string | null;
  price_day5?: string | null;
  price_day6?: string | null;
  price_day7?: string | null;
  currency: string;
  remark?: string | null;
  batch_id: string;
}

// 空运附加费
export interface AirSurchargeRate {
  id: number;
  airline_code?: string | null;
  from_region?: string | null;
  area?: string | null;
  destination_scope?: string | null;
  myc_min?: string | null;
  myc_fee_per_kg?: string | null;
  msc_min?: string | null;
  msc_fee_per_kg?: string | null;
  effective_date?: string | null;
  currency: string;
  remarks?: string | null;
  batch_id: string;
}

// 拼箱
export interface LclRate {
  id: number;
  origin_port?: Port | null;
  destination_port?: Port | null;
  freight_per_cbm?: string | null;
  freight_per_ton?: string | null;
  currency: string;
  lss?: string | null;
  ebs?: string | null;
  cic?: string | null;
  ams_aci_ens?: string | null;
  sailing_day?: string | null;
  via?: string | null;
  transit_time_text?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  batch_id: string;
}

// 空运周价比价条目
export interface AirWeeklyCompareItem {
  rate_id: number;
  airline_code?: string | null;
  service_desc?: string | null;
  effective_week_start?: string | null;
  effective_week_end?: string | null;
  price_day1?: string | null;
  price_day2?: string | null;
  price_day3?: string | null;
  price_day4?: string | null;
  price_day5?: string | null;
  price_day6?: string | null;
  price_day7?: string | null;
  currency: string;
  remark?: string | null;
}

// 拼箱比价条目
export interface LclCompareItem {
  rate_id: number;
  freight_per_cbm?: string | null;
  freight_per_ton?: string | null;
  currency: string;
  lss?: string | null;
  ebs?: string | null;
  cic?: string | null;
  ams_aci_ens?: string | null;
  sailing_day?: string | null;
  via?: string | null;
  transit_time_text?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
}

export interface CompareResult {
  origin: Port | string;
  destination: Port | string;
  rates: OceanCompareItem[] | AirWeeklyCompareItem[] | LclCompareItem[];
  total: number;
  rate_type?: CompareRateType;
}

// ============ Step1 Rate Batches ============

export interface RateBatchSheetSummary {
  name: string;
  rows: number;
}

export interface RateBatchPreviewRow {
  row_index: number;
  carrier?: string | null;
  origin_port?: string | null;
  destination_port?: string | null;
  service_code?: string | null;
  currency?: string | null;
  container_20gp?: string | null;
  container_40gp?: string | null;
  container_40hq?: string | null;
  container_45?: string | null;
  baf_20?: string | null;
  baf_40?: string | null;
  lss_20?: string | null;
  lss_40?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  transit_days?: number | null;
  is_direct?: boolean | null;
  remarks?: string | null;
}

export interface RateBatchSummary {
  batch_id: string;
  file_name: string;
  source_type: string;
  batch_status: string;
  activation_status: string;
  adapter_key?: string | null;
  parser_hint?: string | null;
  carrier_code?: string | null;
  total_rows: number;
  preview_count: number;
  warnings: string[];
  sheets: RateBatchSheetSummary[];
  storage_mode: string;
  created_at: string;
  updated_at: string;
}

export interface RateBatchDetail extends RateBatchSummary {
  preview_rows: RateBatchPreviewRow[];
  preview_truncated: boolean;
  available_actions: string[];
}

export interface RateBatchDiffSummary {
  total_rows: number;
  new_rows: number;
  changed_rows: number;
  unchanged_rows: number;
  unmatched_rows: number;
}

export type RateBatchDiffStatus = 'new' | 'changed' | 'unchanged' | 'unmatched';

export interface RateBatchDiffItem {
  row_index: number;
  status: RateBatchDiffStatus;
  existing_rate_id?: number | null;
  reason?: string | null;
  changed_fields: string[];
  preview: RateBatchPreviewRow;
}

export interface RateBatchDiffResponse {
  batch_id: string;
  batch_status: string;
  diff_status: string;
  generated_at: string;
  summary: RateBatchDiffSummary;
  items: RateBatchDiffItem[];
  is_stub: boolean;
  message?: string | null;
}

export interface RateBatchActivationErrorItem {
  code: string;
  detail: string;
  row_index?: number | null;
  record_kind?: string | null;
}

export interface RateBatchActivateResponse {
  batch_id: string;
  batch_status: string;
  activation_status: string;
  activated: boolean;
  imported_rows: number;
  skipped_rows: number;
  generated_at: string;
  selected_rows: number;
  diff_summary: RateBatchDiffSummary;
  is_stub: boolean;
  message?: string | null;
  errors?: RateBatchActivationErrorItem[];
}

export type ParserHint = 'air' | 'ocean' | 'ocean_ngb';
