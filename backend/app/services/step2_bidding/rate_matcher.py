"""T-B5 RateMatcher — 单航线 → 候选费率列表。

见 docs/Step2_入札対応_T-B5_RateMatcher_架构任务单_20260423.md。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.step1_rates.entities import Step1RateRow
from app.services.step2_bidding.entities import (
    CostType,
    PkgRow,
    QuoteCandidate,
    RowStatus,
)
from app.services.step2_bidding.protocols import RateRepository


_LOCAL_SECTION_CODES: frozenset[str] = frozenset({"PVG"})
_DEFAULT_MAX_CANDIDATES = 5
_SCORE_DEST_EXACT = 0.4
_SCORE_CURRENCY_MATCH = 0.2
_SCORE_VALIDITY_COVER = 0.2
_SCORE_CARRIER_PREF = 0.1
_SCORE_NO_CONSTRAINT = 0.1
_NO_AIRLINE_PENALTY = 0.1
_CASE_BY_CASE_DAMP = 0.5
_ZERO = Decimal("0")


class RateMatcher:
    """单航线 → 候选费率列表。无副作用，无状态。"""

    def __init__(self, repo: RateRepository) -> None:
        self._repo = repo

    def match(
        self,
        row: PkgRow,
        *,
        effective_on: date,
        carrier_preference: list[str] | None = None,
        max_candidates: int = _DEFAULT_MAX_CANDIDATES,
    ) -> tuple[RowStatus, list[QuoteCandidate]]:
        # §5.1 预过滤
        if row.section_code not in _LOCAL_SECTION_CODES:
            return (RowStatus.NON_LOCAL_LEG, [])
        if row.is_example:
            return (RowStatus.EXAMPLE, [])
        if row.cost_type == CostType.LOCAL_DELIVERY:
            return (RowStatus.LOCAL_DELIVERY_MANUAL, [])
        if row.existing_price is not None and row.existing_price != _ZERO:
            return (RowStatus.ALREADY_FILLED, [])
        if row.destination_code == "UNKNOWN" or not row.destination_code:
            return (RowStatus.NO_RATE, [])
        if not row.origin_code:
            return (RowStatus.NO_RATE, [])

        # §5.2 调仓储
        weekly_rows = self._repo.query_air_weekly(
            origin=row.origin_code,
            destination=row.destination_code,
            effective_on=effective_on,
            currency=row.currency,
            airline_code_in=None,
        )
        if not weekly_rows:
            return (RowStatus.NO_RATE, [])

        # §5.3 展开候选
        candidates: list[QuoteCandidate] = []
        for weekly_row in weekly_rows:
            airline_codes = list(weekly_row.extras.get("airline_codes") or [])
            if not airline_codes:
                cand = self._build_candidate(
                    row=row,
                    weekly_row=weekly_row,
                    airline_code="",
                    surcharge_row=None,
                    effective_on=effective_on,
                    carrier_preference=carrier_preference,
                    no_airline=True,
                )
                if cand is not None:
                    candidates.append(cand)
                continue

            for ac in airline_codes:
                surcharges = self._repo.query_air_surcharges(
                    airline_code=ac,
                    effective_on=effective_on,
                    currency=row.currency,
                )
                surcharge: Step1RateRow | None
                if not surcharges:
                    surcharge = None
                else:
                    surcharge = next(
                        (s for s in surcharges if not s.extras.get("all_fees_dash")),
                        None,
                    )
                    if surcharge is None:
                        # 该航司当期 4 项费率全 "—"，跳过
                        continue
                cand = self._build_candidate(
                    row=row,
                    weekly_row=weekly_row,
                    airline_code=ac,
                    surcharge_row=surcharge,
                    effective_on=effective_on,
                    carrier_preference=carrier_preference,
                    no_airline=False,
                )
                if cand is not None:
                    candidates.append(cand)

        if not candidates:
            return (RowStatus.NO_RATE, [])

        # §5.4 carrier_preference 硬约束
        if carrier_preference is not None:
            in_pref = [c for c in candidates if c.airline_codes and c.airline_codes[0] in carrier_preference]
            if not in_pref:
                return (RowStatus.CONSTRAINT_BLOCK, [])
            candidates = in_pref

        # §5.6 排序 + 截断
        candidates.sort(key=lambda c: (c.cost_price, -c.match_score))
        candidates = candidates[:max_candidates]
        return (RowStatus.FILLED, candidates)

    def _build_candidate(
        self,
        *,
        row: PkgRow,
        weekly_row: Step1RateRow,
        airline_code: str,
        surcharge_row: Step1RateRow | None,
        effective_on: date,
        carrier_preference: list[str] | None,
        no_airline: bool,
    ) -> QuoteCandidate | None:
        price, day_index = self._pick_price_by_etd(weekly_row, effective_on)
        if price is None:
            return None

        myc_fee = (
            surcharge_row.extras.get("myc_fee_per_kg") if surcharge_row is not None else None
        )
        msc_fee = (
            surcharge_row.extras.get("msc_fee_per_kg") if surcharge_row is not None else None
        )
        myc_applied = surcharge_row is not None and myc_fee not in (None, _ZERO)
        msc_applied = surcharge_row is not None and msc_fee not in (None, _ZERO)

        cost_price = price
        if myc_applied:
            cost_price = cost_price + myc_fee  # type: ignore[operator]
        if msc_applied:
            cost_price = cost_price + msc_fee  # type: ignore[operator]

        step1_must_go = bool(weekly_row.extras.get("has_must_go"))
        step1_case_by_case = bool(weekly_row.extras.get("is_case_by_case"))

        remarks_parts = [
            weekly_row.remarks,
            surcharge_row.remarks if surcharge_row is not None else None,
        ]
        remarks_from_step1 = "\n".join(p for p in remarks_parts if p) or None

        dest_exact = bool(
            row.destination_code
            and weekly_row.destination_port_name
            and row.destination_code in weekly_row.destination_port_name
        )
        currency_match = (weekly_row.currency or "") == (row.currency or "")
        validity_cover = (
            weekly_row.effective_week_start is not None
            and weekly_row.effective_week_end is not None
            and weekly_row.effective_week_start <= effective_on <= weekly_row.effective_week_end
        )
        in_carrier_pref = bool(
            carrier_preference and airline_code and airline_code in carrier_preference
        )
        no_constraint = (not step1_must_go) and (not step1_case_by_case)

        score = self._calc_score(
            dest_exact=dest_exact,
            currency_match=currency_match,
            validity_cover=validity_cover,
            in_carrier_pref=in_carrier_pref,
            no_constraint=no_constraint,
            case_by_case=step1_case_by_case,
        )
        if no_airline:
            score = max(0.0, score - _NO_AIRLINE_PENALTY)

        airline_codes_field = [airline_code] if airline_code else []

        return QuoteCandidate(
            base_price=price,
            base_price_day_index=day_index,
            airline_codes=airline_codes_field,
            service_desc=weekly_row.service_desc or "",
            via=weekly_row.via,
            myc_fee_per_kg=myc_fee if myc_applied else None,
            msc_fee_per_kg=msc_fee if msc_applied else None,
            myc_applied=myc_applied,
            msc_applied=msc_applied,
            cost_price=cost_price,
            currency=weekly_row.currency or "",
            source_batch_id=weekly_row.upload_batch_id or "",
            source_weekly_record_id=int(weekly_row.extras.get("step2_record_id") or 0),
            source_surcharge_record_id=(
                int(surcharge_row.extras.get("step2_record_id"))
                if surcharge_row is not None and surcharge_row.extras.get("step2_record_id") is not None
                else None
            ),
            remarks_from_step1=remarks_from_step1,
            step1_must_go=step1_must_go,
            step1_case_by_case=step1_case_by_case,
            match_score=score,
        )

    @staticmethod
    def _pick_price_by_etd(
        weekly_row: Step1RateRow, effective_on: date
    ) -> tuple[Decimal | None, int | None]:
        """按 effective_on 在周内的 day offset 取对应 price_dayN。

        - effective_on 落在 [week_start..week_end]：取 (offset+1) 那一天
        - 该天为 None：退化为周内非 None 平均
        - 7 天全 None：返回 (None, None)
        """
        prices = [
            weekly_row.price_day1,
            weekly_row.price_day2,
            weekly_row.price_day3,
            weekly_row.price_day4,
            weekly_row.price_day5,
            weekly_row.price_day6,
            weekly_row.price_day7,
        ]
        non_none = [p for p in prices if p is not None]
        if not non_none:
            return (None, None)

        if (
            weekly_row.effective_week_start is not None
            and weekly_row.effective_week_end is not None
            and weekly_row.effective_week_start <= effective_on <= weekly_row.effective_week_end
        ):
            offset = (effective_on - weekly_row.effective_week_start).days
            if 0 <= offset < 7:
                day_n = offset + 1
                day_price = prices[offset]
                if day_price is not None:
                    return (day_price, day_n)
                # 该天为 None → 周内非 None 平均
                avg = sum(non_none, _ZERO) / Decimal(len(non_none))
                return (avg, day_n)

        # effective_on 不在周内（理论上 SQL 已过滤），退化平均
        avg = sum(non_none, _ZERO) / Decimal(len(non_none))
        return (avg, None)

    @staticmethod
    def _calc_score(
        *,
        dest_exact: bool,
        currency_match: bool,
        validity_cover: bool,
        in_carrier_pref: bool,
        no_constraint: bool,
        case_by_case: bool,
    ) -> float:
        score = 0.0
        if dest_exact:
            score += _SCORE_DEST_EXACT
        if currency_match:
            score += _SCORE_CURRENCY_MATCH
        if validity_cover:
            score += _SCORE_VALIDITY_COVER
        if in_carrier_pref:
            score += _SCORE_CARRIER_PREF
        if no_constraint:
            score += _SCORE_NO_CONSTRAINT
        if case_by_case:
            score *= _CASE_BY_CASE_DAMP
        return score
