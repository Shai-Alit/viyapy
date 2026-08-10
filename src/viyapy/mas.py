"""Operations on the SAS Micro Analytic Service (MAS)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from ._http import HttpClient
from ._pagination import iter_collection
from ._validation import (
    check_inputs_against_signature,
    optional_identifier,
    require_identifier,
    require_non_negative_int,
    require_positive_int,
)
from .dialects.base import DEFAULT_MAS_STEP, Dialect
from .exceptions import ViyaValidationError
from .models import ExecutionResult, MasModule, StepSignature, ValidationResult

DEFAULT_PAGE_SIZE = 100


def _build_metadata(client_id: str | None, transaction_id: str | None) -> dict[str, str] | None:
    """Build the request ``metadata`` object, or ``None`` if no ids were given.

    MAS reads correlation ids from snake_case ``client_id``/``transaction_id``
    keys inside a ``metadata`` object and echoes them on the response; omitted
    ids are left out entirely rather than sent as ``null``.
    """
    metadata: dict[str, str] = {}
    if client_id is not None:
        metadata["client_id"] = client_id
    if transaction_id is not None:
        metadata["transaction_id"] = transaction_id
    return metadata or None


class MASClient:
    """MAS module operations, accessed via ``ViyaClient.mas``."""

    def __init__(self, http: HttpClient, dialect: Dialect) -> None:
        self._http = http
        self._dialect = dialect

    def list(self, *, page_size: int = DEFAULT_PAGE_SIZE) -> Iterator[MasModule]:
        """Iterate the MAS modules on the deployment, one per yielded item.

        Pages are fetched lazily as the iterator is consumed (following the
        collection's ``next`` links), so a large deployment is streamed rather
        than buffered. ``page_size`` is validated eagerly, when this method is
        called, so a bad value fails fast at the call site rather than on the
        first iteration.

        Args:
            page_size: Number of modules requested per page. Larger pages mean
                fewer round trips; the server may cap the effective size.

        Returns:
            An iterator over each :class:`MasModule`, in server order.

        Raises:
            ViyaConfigError: ``page_size`` is not a positive integer.
            ViyaError: On any request failure while paging.
        """
        # Validate eagerly here (not in the generator below): a generator
        # function defers its whole body until first iteration, which would
        # postpone this check and defeat the fail-fast contract.
        require_positive_int(page_size, "page_size")
        return self._iter_modules(page_size)

    def _iter_modules(self, page_size: int) -> Iterator[MasModule]:
        """Lazily page through the MAS module collection (see :meth:`list`)."""
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

    def get_signature(
        self,
        module_id: str,
        step: str = DEFAULT_MAS_STEP,
        *,
        timeout: float | tuple[float, float] | None = None,
    ) -> StepSignature:
        """Fetch the input/output signature of a MAS module step.

        Use this to discover a step's expected inputs and outputs (names, types,
        dimensions) before calling :meth:`execute` — for example to validate a
        payload client-side or to build a form.

        Args:
            module_id: The module id.
            step: The step whose signature to fetch (defaults to ``"execute"``).
            timeout: Optional per-call timeout override for the signature request.

        Returns:
            The parsed :class:`StepSignature`.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: No such module or step exists.
            ViyaResponseError: The response was not a usable step signature.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        raw = self._http.request_json(
            "GET",
            self._dialect.mas_step_path(module_id, step),
            accept=self._dialect.mas_step_media_type,
            timeout=timeout,
        )
        return self._dialect.parse_step_signature(module_id, step, raw)

    def validate(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        timeout: float | tuple[float, float] | None = None,
    ) -> StepSignature:
        """Validate ``inputs`` against a step's signature, without executing it.

        Fetches the step signature and checks that the supplied input names match
        what the step declares, raising :class:`~viyapy.exceptions.ViyaValidationError`
        if a declared input is missing or an undeclared input was supplied. Only the
        set of names is checked, not values or types. Useful as a pre-flight before
        :meth:`execute`, or to validate a form the user is filling in.

        Args:
            module_id: The module id.
            inputs: Feature name/value mapping to validate.
            step: The step whose signature to validate against (defaults to
                ``"execute"``).
            timeout: Optional per-call timeout override for the signature request.

        Returns:
            The fetched :class:`StepSignature` (so the caller can reuse it).

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: No such module or step exists.
            ViyaResponseError: The response was not a usable step signature.
            ViyaValidationError: The inputs do not match the signature.
            ViyaError: On any other failure.
        """
        signature = self.get_signature(module_id, step=step, timeout=timeout)
        check_inputs_against_signature(signature, inputs, module_id=module_id, step=step)
        return signature

    def validate_remote(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        raise_on_invalid: bool = True,
        timeout: float | tuple[float, float] | None = None,
    ) -> ValidationResult:
        """Validate ``inputs`` against a step server-side, without executing it.

        Posts the inputs to the MAS validations endpoint so SAS Viya itself checks
        them against the step's signature — a stronger check than the client-side
        name comparison in :meth:`validate`, since the server also inspects types
        and constraints. A single round trip, no signature fetch.

        SAS reports an invalid payload as an HTTP 201 whose body says
        ``valid: false`` (not as a 4xx). By default that is surfaced as a
        :class:`~viyapy.exceptions.ViyaValidationError` carrying the server's
        messages; pass ``raise_on_invalid=False`` to instead return the
        :class:`~viyapy.models.ValidationResult` and inspect ``.valid`` yourself.

        Args:
            module_id: The module id.
            inputs: Feature name/value mapping to validate.
            step: The step to validate against (defaults to ``"execute"``).
            raise_on_invalid: When ``True`` (default), raise ``ViyaValidationError``
                if the server reports the inputs invalid. When ``False``, return the
                result regardless so the caller can branch on ``.valid``.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`~viyapy.models.ValidationResult`.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string.
            ViyaNotFoundError: No such module or step exists.
            ViyaResponseError: The response was not a usable validation result.
            ViyaValidationError: ``raise_on_invalid`` is set and the server reports
                the inputs invalid.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_validation_path(module_id, step),
            accept=self._dialect.mas_validation_media_type,
            content_type=self._dialect.mas_step_input_media_type,
            json_body=self._dialect.build_inputs(inputs),
            timeout=timeout,
        )
        result = self._dialect.parse_validation(module_id, step, raw)
        if raise_on_invalid and not result.valid:
            detail = (
                "; ".join(result.messages)
                if result.messages
                else "the server did not accept the inputs"
            )
            raise ViyaValidationError(
                f"MAS rejected the inputs for module {module_id!r} step {step!r}: {detail}",
                messages=result.messages,
                module_id=module_id,
                step=step,
                response_body=result.raw,
            )
        return result

    def execute(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        validate: bool = False,
        wait_time: int | None = None,
        client_id: str | None = None,
        transaction_id: str | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> ExecutionResult:
        """Execute a MAS module step against a mapping of inputs.

        ``wait_time`` selects the execution mode (it maps to the server's
        ``waitTime`` query parameter, in milliseconds):

        - ``None`` (default) — synchronous: wait until execution completes; the
          result carries the ``outputs`` and ``execution_state == "completed"``.
        - a positive integer — timed: wait up to that many milliseconds. If the
          run finishes in time the result is ``completed`` with ``outputs``;
          otherwise ``outputs`` is empty and ``execution_state == "timedOut"``
          (see :attr:`ExecutionResult.timed_out`).
        - ``0`` — fire-and-forget: return immediately after validation with empty
          ``outputs`` and ``execution_state == "submitted"``. See :meth:`submit`
          for a named shortcut.

        Binary inputs are passed as ``bytes`` (or ``bytearray``) values in
        ``inputs``: they are base64-encoded on the wire with ``encoding: "b64"``,
        which MAS accepts for ``binary``/``any``-typed variables. Binary outputs
        are decoded back into ``bytes`` on :attr:`ExecutionResult.outputs`.

        Args:
            module_id: The published module id (for a published decision this is
                the module name; the step defaults to ``"execute"``).
            inputs: Feature name/value mapping. Serialized as JSON — scalar values
                are passed through unchanged (no name-mangling); ``bytes``/
                ``bytearray`` values are sent as base64-encoded binary.
            step: The module step to execute.
            validate: When ``True``, fetch the step signature and validate the
                inputs against it before executing (an extra round trip), raising
                ``ViyaValidationError`` on a mismatch. Off by default so a normal
                execute stays a single request. Any ``timeout`` override applies
                to the signature request as well as the execute request.
            wait_time: Server-side wait budget in milliseconds selecting the
                execution mode (see above). Must be a non-negative integer when
                given. This is distinct from ``timeout``, which bounds the HTTP
                call itself.
            client_id: Optional correlation id sent in the request ``metadata`` and
                echoed on :attr:`ExecutionResult.client_id`. Must be a non-empty
                string when given.
            transaction_id: Optional correlation id sent in the request ``metadata``
                and echoed on :attr:`ExecutionResult.transaction_id`. Must be a
                non-empty string when given.
            timeout: Optional per-call timeout override (MAS execution may need a
                longer read timeout than a metadata GET).

        Returns:
            The parsed :class:`ExecutionResult`.

        Raises:
            ViyaConfigError: ``module_id``/``step`` is empty or not a string,
                ``wait_time`` is not a non-negative integer, or ``client_id``/
                ``transaction_id`` is given but not a non-empty string.
            ViyaNotFoundError: The module or step does not exist.
            ViyaResponseError: A completed response lacked an output list.
            ViyaValidationError: ``validate`` is set and the inputs do not match
                the step signature.
            ViyaError: On any other failure.
        """
        module_id = require_identifier(module_id, "module_id")
        step = require_identifier(step, "step")
        client_id = optional_identifier(client_id, "client_id")
        transaction_id = optional_identifier(transaction_id, "transaction_id")
        params: dict[str, Any] | None = None
        if wait_time is not None:
            params = {"waitTime": require_non_negative_int(wait_time, "wait_time")}
        if validate:
            self.validate(module_id, inputs, step=step, timeout=timeout)
        metadata = _build_metadata(client_id, transaction_id)
        raw = self._http.request_json(
            "POST",
            self._dialect.mas_execute_path(module_id, step),
            content_type="application/json",
            json_body=self._dialect.build_inputs(inputs, metadata=metadata),
            params=params,
            timeout=timeout,
        )
        return self._dialect.parse_execution(module_id, step, raw)

    def submit(
        self,
        module_id: str,
        inputs: Mapping[str, Any],
        *,
        step: str = DEFAULT_MAS_STEP,
        validate: bool = False,
        client_id: str | None = None,
        transaction_id: str | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> ExecutionResult:
        """Submit a MAS step for fire-and-forget execution, without waiting.

        A convenience for :meth:`execute` with ``wait_time=0``: the call returns
        as soon as the server accepts the inputs, so the result has empty
        ``outputs`` and ``execution_state == "submitted"`` (see
        :attr:`ExecutionResult.submitted`). Use this to kick off a run whose
        outputs you do not need in-band. MAS does not expose a per-execution
        result-polling endpoint, so the outputs are not retrievable afterward.

        Args:
            module_id: The published module id.
            inputs: Feature name/value mapping (``bytes`` values sent as binary).
            step: The module step to execute.
            validate: When ``True``, validate the inputs against the step
                signature before submitting (an extra round trip).
            client_id: Optional correlation id sent in the request ``metadata``.
            transaction_id: Optional correlation id sent in the request
                ``metadata``.
            timeout: Optional per-call timeout override.

        Returns:
            The parsed :class:`ExecutionResult`, with ``submitted`` set.

        Raises:
            ViyaConfigError: ``module_id`` or ``step`` is empty or not a string,
                or ``client_id``/``transaction_id`` is given but not a non-empty
                string.
            ViyaNotFoundError: The module or step does not exist.
            ViyaValidationError: ``validate`` is set and the inputs do not match
                the step signature.
            ViyaError: On any other failure.
        """
        return self.execute(
            module_id,
            inputs,
            step=step,
            validate=validate,
            wait_time=0,
            client_id=client_id,
            transaction_id=transaction_id,
            timeout=timeout,
        )
