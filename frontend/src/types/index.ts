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

export interface CompareResult {
  origin: Port;
  destination: Port;
  rates: CompareRateItem[];
  total: number;
}
