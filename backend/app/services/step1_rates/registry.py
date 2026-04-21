from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from app.services.step1_rates.entities import ParsedRateBatch, Step1FileType
from app.services.step1_rates.protocols import RateAdapter


class RateAdapterRegistry:
    """Step1 适配器注册表。"""

    def __init__(self, adapters: Iterable[RateAdapter] | None = None) -> None:
        self._adapters: list[RateAdapter] = []
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: RateAdapter) -> None:
        self._adapters.append(adapter)
        self._adapters.sort(key=lambda item: item.priority)

    def resolve(self, path: Path, *, file_type_hint: Step1FileType | None = None) -> RateAdapter:
        for adapter in self._adapters:
            if adapter.detect(path, file_type_hint=file_type_hint):
                return adapter

        raise LookupError(
            f"没有匹配的 Step1 adapter: path={path.name}, "
            f"file_type_hint={file_type_hint.value if file_type_hint else None}"
        )

    def parse(
        self,
        path: Path,
        db=None,
        *,
        file_type_hint: Step1FileType | None = None,
    ) -> ParsedRateBatch:
        adapter = self.resolve(path, file_type_hint=file_type_hint)
        return adapter.parse(path, db=db)

    def keys(self) -> list[str]:
        return [adapter.key for adapter in self._adapters]
