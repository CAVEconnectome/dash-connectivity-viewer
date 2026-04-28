from typing import Any

import pandas as pd

from .keys import is_live
from .query_runner import run_query


_RESERVED_PARAMS = {"offset", "limit", "mat_version", "is_view",
                    "select_columns", "split_positions"}


def parse_filters(query_args: dict[str, str]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key, raw in query_args.items():
        if key in _RESERVED_PARAMS:
            continue
        if "," in raw:
            filters[key] = [_coerce(part) for part in raw.split(",") if part.strip()]
        else:
            filters[key] = _coerce(raw)
    return filters


def _coerce(value: str):
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


class TableQuery:
    def __init__(
        self,
        client,
        name: str,
        *,
        filters: dict[str, Any] | None = None,
        is_view: bool | None = None,
        mat_version: int | str | None = None,
    ):
        self.client = client
        self.name = name
        self.filters = filters or {}
        self.is_view = is_view if is_view is not None else self._detect_is_view()
        self._mgr = client.materialize.views if self.is_view else client.materialize.tables
        self.mat_version = mat_version
        if self.is_view and is_live(mat_version):
            raise ValueError(
                "Views are only available in materialized mode; "
                "pass an explicit mat_version to query a view."
            )

    def _detect_is_view(self) -> bool:
        # TableManager/ViewManager don't iterate as sequences of names; use the explicit accessors.
        try:
            if self.name in self.client.materialize.get_tables():
                return False
        except Exception:
            pass
        # Views are only available when a specific mat_version is set (not in live mode).
        try:
            if self.name in self.client.materialize.get_views():
                return True
        except Exception:
            pass
        return False  # default to table; query will surface a clear error if wrong

    def rows(
        self,
        *,
        offset: int = 0,
        limit: int = 500,
        split_positions: bool = True,
        select_columns: list[str] | None = None,
    ) -> pd.DataFrame:
        qf = self._mgr[self.name](**self.filters)
        kwargs: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
            "split_positions": split_positions,
        }
        if select_columns:
            kwargs["select_columns"] = select_columns
        # Views always use .query(); tables dispatch on live mode.
        live = (not self.is_view) and is_live(self.mat_version)
        return run_query(qf, live=live, **kwargs)
