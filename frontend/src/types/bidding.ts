// T-B10 v0.1 bidding 类型定义，对齐 backend/app/schemas/bidding.py

export type BiddingErrorCode =
  | 'F1_INVALID_XLSX'
  | 'F2_UNSUPPORTED_CUSTOMER'
  | 'F3_PARSE_FAILED'
  | 'F4_FILL_FAILED'
  | 'F5_TOKEN_EXPIRED'
  | 'F6_FILE_TOO_LARGE'
  | 'F7_WRONG_EXTENSION'
  | 'F8_NETWORK_ERROR';

export interface BiddingErrorBlock {
  code: BiddingErrorCode;
  message_key: string;
  detail: string;
}

export type BiddingConfidence = 'high' | 'medium' | 'low';

export interface IdentifyBlock {
  matched_customer: 'customer_a' | 'unknown';
  matched_dimensions: string[];
  confidence: BiddingConfidence;
  unmatched_reason: string | null;
  warnings: string[];
}

export interface SampleRow {
  row_idx: number;
  section_code: string;
  destination_text: string;
  cost_type: 'air_freight' | 'local_delivery' | 'unknown';
}

export interface ParseBlock {
  period: string;
  sheet_name: string;
  section_count: number;
  row_count: number;
  sample_rows: SampleRow[];
  warnings: string[];
}

export type RowStatus =
  | 'filled'
  | 'no_rate'
  | 'already_filled'
  | 'example'
  | 'non_local_leg'
  | 'local_delivery_manual'
  | 'constraint_block'
  | 'overridden';

export interface FillRowBlock {
  row_idx: number;
  section_code: string;
  destination_code: string;
  status: RowStatus | string;
  cost_price: string | null;
  sell_price: string | null;
  markup_ratio: string | null;
  source_batch_id: string | null;
  confidence: number;
}

export interface FillBlock {
  filled_count: number;
  no_rate_count: number;
  skipped_count: number;
  global_warnings: string[];
  rows: FillRowBlock[];
  markup_ratio: string;
}

export interface DownloadTokens {
  cost_token: string;
  sr_token: string;
  cost_filename: string;
  sr_filename: string;
  expires_at: string;
  one_time_use: boolean;
}

export interface BiddingAutoFillResponse {
  bid_id: string;
  ok: boolean;
  error: BiddingErrorBlock | null;
  identify: IdentifyBlock;
  parse: ParseBlock | null;
  fill: FillBlock | null;
  download: DownloadTokens | null;
}

export type UiState =
  | { kind: 'idle' }
  | { kind: 'uploading'; progress: number }
  | { kind: 'processing' }
  | { kind: 'success'; resp: BiddingAutoFillResponse }
  | { kind: 'rejected'; resp: BiddingAutoFillResponse }
  | {
      kind: 'error';
      resp: BiddingAutoFillResponse | null;
      code: BiddingErrorCode;
      detail?: string;
    };
