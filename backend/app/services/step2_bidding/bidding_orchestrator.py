"""T-B10 v0.1 bidding 编排器。

同步函数 run_auto_fill：identify → parse → match(全行) → fill×2 → token put。
全异常归口到 BiddingErrorCode 降级响应（200 body.ok=false）。
见架构任务单 §5.1 伪代码。
"""
from __future__ import annotations

import traceback
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from sqlalchemy.orm import Session

from app.schemas.bidding import (
    BiddingAutoFillResponse,
    BiddingErrorBlock,
    BiddingErrorCode,
    DownloadTokens,
    FillBlock,
    FillRowBlock,
    IdentifyBlock,
    ParseBlock,
    SampleRow,
)
from app.services.step2_bidding.customer_identifier import IdentifierResult, identify
from app.services.step2_bidding.customer_profiles.customer_a import (
    CustomerAProfile,
    default_markup_fn,
)
from app.services.step2_bidding.entities import (
    CostType,
    ParsedPkg,
    PerRowReport,
    PkgRow,
    QuoteCandidate,
    RowStatus,
)
from app.models.import_batch import ImportBatchFileType
from app.services.step2_bidding.rate_matcher import RateMatcher
from app.services.step2_bidding.rate_repository import Step1RateRepository
from app.services.step2_bidding import temp_files
from app.services.step2_bidding.token_store import TOKEN_STORE


_MARKUP_RATIO = Decimal("1.15")
_TOKEN_TTL_SECONDS = 3600
_ERROR_MESSAGE_KEYS: dict[BiddingErrorCode, str] = {
    BiddingErrorCode.F1_INVALID_XLSX: "bidding.errors.f1_invalid_xlsx",
    BiddingErrorCode.F2_UNSUPPORTED_CUSTOMER: "bidding.errors.f2_unsupported_customer",
    BiddingErrorCode.F3_PARSE_FAILED: "bidding.errors.f3_parse_failed",
    BiddingErrorCode.F4_FILL_FAILED: "bidding.errors.f4_fill_failed",
    BiddingErrorCode.F5_TOKEN_EXPIRED: "bidding.errors.f5_token_expired",
    BiddingErrorCode.F6_FILE_TOO_LARGE: "bidding.errors.f6_file_too_large",
    BiddingErrorCode.F7_WRONG_EXTENSION: "bidding.errors.f7_wrong_extension",
    BiddingErrorCode.F8_NETWORK_ERROR: "bidding.errors.f8_network_error",
}


def run_auto_fill(
    input_path: Path,
    bid_id: str,
    bid_dir: Path,
    db: Session,
    *,
    effective_on: date | None = None,
) -> BiddingAutoFillResponse:
    temp_files.cleanup_expired(ttl=_TOKEN_TTL_SECONDS)

    identify_result = identify(input_path)
    identify_block = _to_identify_block(identify_result)

    if identify_result.matched_customer == "unknown":
        code = _classify_unknown(identify_result.warnings)
        return _resp_error(
            bid_id=bid_id,
            identify=identify_block,
            code=code,
            detail=identify_result.unmatched_reason or "identify returned unknown",
        )

    profile = CustomerAProfile(markup_fn=default_markup_fn)

    try:
        parsed = profile.parse(input_path, bid_id=bid_id, period="")
    except Exception as e:
        return _resp_error(
            bid_id=bid_id,
            identify=identify_block,
            code=BiddingErrorCode.F3_PARSE_FAILED,
            detail=f"{type(e).__name__}: {e}",
        )

    parse_block = _to_parse_block(parsed, sample_limit=5)

    try:
        repo = Step1RateRepository(db)
        matcher = RateMatcher(repo)
        if effective_on is not None:
            eff_date = effective_on
        else:
            eff_date = repo.infer_default_effective_on(file_type=ImportBatchFileType.air)
        row_reports = _match_all_rows(parsed, matcher, eff_date)

        cost_path = bid_dir / f"cost_{input_path.stem}_{bid_id}.xlsx"
        sr_path = bid_dir / f"sr_{input_path.stem}_{bid_id}.xlsx"
        fr_cost = profile.fill(input_path, parsed, row_reports, "cost", cost_path)
        fr_sr = profile.fill(input_path, parsed, row_reports, "sr", sr_path)
    except Exception as e:
        return _resp_error(
            bid_id=bid_id,
            identify=identify_block,
            code=BiddingErrorCode.F4_FILL_FAILED,
            parse=parse_block,
            detail=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}",
        )

    fill_block = _to_fill_block(
        row_reports=row_reports,
        fr_warnings=list(fr_cost.global_warnings) + list(fr_sr.global_warnings),
        markup_ratio=_MARKUP_RATIO,
    )
    cost_token = TOKEN_STORE.put(cost_path, cost_path.name, ttl=_TOKEN_TTL_SECONDS)
    sr_token = TOKEN_STORE.put(sr_path, sr_path.name, ttl=_TOKEN_TTL_SECONDS)
    expires_at = datetime.utcnow() + timedelta(seconds=_TOKEN_TTL_SECONDS)

    return BiddingAutoFillResponse(
        bid_id=bid_id,
        ok=True,
        error=None,
        identify=identify_block,
        parse=parse_block,
        fill=fill_block,
        download=DownloadTokens(
            cost_token=cost_token,
            sr_token=sr_token,
            cost_filename=cost_path.name,
            sr_filename=sr_path.name,
            expires_at=expires_at,
            one_time_use=True,
        ),
    )


# ---------- internal helpers ----------


def _to_identify_block(result: IdentifierResult) -> IdentifyBlock:
    matched: str = result.matched_customer
    if matched not in ("customer_a", "unknown"):
        matched = "unknown"
    conf = result.confidence if result.confidence in ("high", "medium", "low") else "low"
    return IdentifyBlock(
        matched_customer=matched,  # type: ignore[arg-type]
        matched_dimensions=list(result.matched_dimensions),
        confidence=conf,  # type: ignore[arg-type]
        unmatched_reason=result.unmatched_reason,
        warnings=list(result.warnings),
    )


def _to_parse_block(parsed: ParsedPkg, *, sample_limit: int) -> ParseBlock:
    samples: list[SampleRow] = []
    for row in parsed.rows[:sample_limit]:
        samples.append(
            SampleRow(
                row_idx=row.row_idx,
                section_code=row.section_code,
                destination_text=row.destination_text_raw,
                cost_type=_cost_type_to_str(row.cost_type),
            )
        )
    return ParseBlock(
        period=parsed.period or "",
        sheet_name=parsed.sheet_name,
        section_count=len(parsed.sections),
        row_count=len(parsed.rows),
        sample_rows=samples,
        warnings=list(parsed.warnings),
    )


def _cost_type_to_str(ct: CostType) -> str:
    if ct == CostType.AIR_FREIGHT:
        return "air_freight"
    if ct == CostType.LOCAL_DELIVERY:
        return "local_delivery"
    return "unknown"


def _match_all_rows(
    parsed: ParsedPkg, matcher: RateMatcher, effective_on: date
) -> list[PerRowReport]:
    reports: list[PerRowReport] = []
    for row in parsed.rows:
        status, cands = matcher.match(row, effective_on=effective_on)
        reports.append(_row_report_from_match(row, status, cands))
    return reports


def _row_report_from_match(
    row: PkgRow, status: RowStatus, cands: Sequence[QuoteCandidate]
) -> PerRowReport:
    if status == RowStatus.FILLED and cands:
        top = cands[0]
        return PerRowReport(
            row_idx=row.row_idx,
            section_code=row.section_code,
            destination_code=row.destination_code,
            status=RowStatus.FILLED,
            cost_price=top.cost_price,
            sell_price=default_markup_fn(top.cost_price),
            markup_ratio=_MARKUP_RATIO,
            lead_time_text=(
                f"{top.base_price_day_index}天" if top.base_price_day_index else None
            ),
            carrier_text=(
                top.service_desc
                or (top.airline_codes[0] if top.airline_codes else None)
            ),
            remark_text=top.remarks_from_step1,
            selected_candidate=top,
            confidence=top.match_score,
        )
    return PerRowReport(
        row_idx=row.row_idx,
        section_code=row.section_code,
        destination_code=row.destination_code,
        status=status,
        cost_price=None,
        sell_price=None,
        markup_ratio=None,
        lead_time_text=None,
        carrier_text=None,
        remark_text=None,
        selected_candidate=None,
        confidence=0.0,
    )


def _to_fill_block(
    *,
    row_reports: Sequence[PerRowReport],
    fr_warnings: list[str],
    markup_ratio: Decimal,
) -> FillBlock:
    filled = sum(1 for r in row_reports if r.status == RowStatus.FILLED)
    no_rate = sum(1 for r in row_reports if r.status == RowStatus.NO_RATE)
    skipped = len(row_reports) - filled - no_rate

    rows_block: list[FillRowBlock] = []
    for r in row_reports:
        source_batch_id = (
            r.selected_candidate.source_batch_id if r.selected_candidate else None
        )
        rows_block.append(
            FillRowBlock(
                row_idx=r.row_idx,
                section_code=r.section_code,
                destination_code=r.destination_code,
                status=r.status.value,
                cost_price=str(r.cost_price) if r.cost_price is not None else None,
                sell_price=str(r.sell_price) if r.sell_price is not None else None,
                markup_ratio=(
                    str(r.markup_ratio) if r.markup_ratio is not None else None
                ),
                source_batch_id=source_batch_id,
                confidence=r.confidence,
            )
        )

    # 去重 warning（cost / sr 两轮 fill 会产生同样的段级警告）
    dedup: list[str] = []
    seen: set[str] = set()
    for w in fr_warnings:
        if w not in seen:
            seen.add(w)
            dedup.append(w)

    return FillBlock(
        filled_count=filled,
        no_rate_count=no_rate,
        skipped_count=skipped,
        global_warnings=dedup,
        rows=rows_block,
        markup_ratio=str(markup_ratio),
    )


def _classify_unknown(warnings: tuple[str, ...]) -> BiddingErrorCode:
    for w in warnings:
        if w.startswith("WBOPEN_FAIL"):
            return BiddingErrorCode.F1_INVALID_XLSX
    return BiddingErrorCode.F2_UNSUPPORTED_CUSTOMER


def _resp_error(
    *,
    bid_id: str,
    identify: IdentifyBlock,
    code: BiddingErrorCode,
    detail: str = "",
    parse: ParseBlock | None = None,
) -> BiddingAutoFillResponse:
    return BiddingAutoFillResponse(
        bid_id=bid_id,
        ok=False,
        error=BiddingErrorBlock(
            code=code,
            message_key=_ERROR_MESSAGE_KEYS[code],
            detail=detail,
        ),
        identify=identify,
        parse=parse,
        fill=None,
        download=None,
    )
