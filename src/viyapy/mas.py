"""Operations on the SAS Micro Analytic Service (MAS)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from ._http import HttpClient
from ._pagination import iter_collection
from ._validation import require_identifier, require_positive_int
from .dialects.base import DEFAULT_MAS_STEP, Dialect
from .models import ExecutionResult, MasModule

DEFAULT_PAGE_SIZE = 100


class MASClient:
    """MAS module operations, accessed via ``ViyaClient.mas``."""

    def __init__(self, http: HttpClient, dialect: Dialect) -> None:
        self._http = http
        self._dialect = dialect

    def list(self, *, page_size: int = DEFAULT_PAGE_SIZE) -> Iterator[MasModule]:
        """Iterate the MAS modules on the deployment, one per yielded item.

        Pages are fetched lazily as the iterator is consumed (following the
        collection's ``next`` links), so a large deployment is streamed rather
        than buffered.

        Args:
            page_size: Number of modules requested per page. Larger pages mean
                fewer round trips; the server may cap the effective size.

        Yields:
            Each :class:`MasModule`, in server order.

        Raises:
            ViyaConfigError: ``page_size`` is not a positive integer.
            ViyaError: On any request failure while paging.
        """
        require_positive_int(page_size, "page_size")
        items = iter_collection(
            self._http,
            self._dialect.mas_modules_path(),
            params={"limit": page_size},
        )
        for item in items:
            yield self._dialect.parse_module(item)

    def get(self, module_id: str) -> MasModule:
        """Fetch a single MAS module's metadata.

        Args:
            module_id: The module id.

        Returns:
            The parsed :class:`MasModule`.

        Raises:
            ViyaConfigError: ``module_id`` is empty or not a string.
            ViyaNotFoundError: No module with that id exists.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        raw = self._http.request_json(
            "GET",
            self._dialect.mas_module_path(module_id),
            accept=self._dialect.mas_module_media_type,
        )
        return self._dialect.parse_module(raw)

    def execute(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        timeout: float | tuple[float, float] | None = None,
    ) -> ExecutionResult:
        """Execute a MAS module step against a mapping of inputs.

        Args:
            module_id: The published module id (for a published decision this is
                the module name; the step defaults to ``"execute"``).
            inputs: Feature name/value mapping. Serialized as JSON — values are
                passed through unchanged (no name-mangling).
            step: The module step to execute.
            timeout: Optional per-call timeout override (MAS execution may need a
                longer read timeout than a metadata GET).

        Returns:
            The parsed :class:`ExecutionResult`.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: The module or step does not exist.
            ViyaResponseError: The response lacked an output list.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_execute_path(module_id, step),
            content_type="application/json",
            json_body=self._dialect.build_inputs(inputs),
            timeout=timeout,
        )
        return self._dialect.parse_execution(module_id, step, raw)
