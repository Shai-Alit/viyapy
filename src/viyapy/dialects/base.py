"""The version/dialect abstraction.

A :class:`Dialect` localizes everything that differs between SAS Viya
generations — endpoint paths, media-type versions, and response shapes (notably
the MAS ``output`` vs ``outputs`` key) — so the rest of the library codes against
one stable interface instead of branching on version inline.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from ..exceptions import ViyaResponseError
from ..models import (
    EXECUTION_SUBMITTED,
    EXECUTION_TIMED_OUT,
    CompileJob,
    Decision,
    DecisionSummary,
    ExecutionResult,
    ExternalArtifact,
    MasModule,
    ModelStep,
    ModuleSource,
    Revision,
    StepSignature,
    ValidationResult,
    Variable,
)

MODEL_STEP_TYPE = "application/vnd.sas.decision.step.model"
DEFAULT_MAS_STEP = "execute"
MAS_MODULE_MEDIA_TYPE = "application/vnd.sas.microanalytic.module+json"
MAS_STEP_MEDIA_TYPE = "application/vnd.sas.microanalytic.module.step+json"
# Request body sent to the validations endpoint (same shape as an execute body).
MAS_STEP_INPUT_MEDIA_TYPE = "application/vnd.sas.microanalytic.module.step.input+json"
# Accept/response type of the validations endpoint.
MAS_VALIDATION_MEDIA_TYPE = "application/vnd.sas.validation+json"
# Content-Type accepted by the module-creation endpoint (POST /modules). Note the
# distinct `.definition+json` suffix — a plain `.module+json` create body 415s.
MAS_MODULE_DEFINITION_MEDIA_TYPE = "application/vnd.sas.microanalytic.module.definition+json"
# Accept/Content-Type of the module `/source` subresource (GET and PUT).
MAS_MODULE_SOURCE_MEDIA_TYPE = "application/vnd.sas.microanalytic.module.source+json"
# Accept/response type of an async compile job (`/microanalyticScore/jobs`). The
# job is *submitted* with the same `.module.definition+json` body as a synchronous
# create; only the response envelope differs (a `.job+json` resource).
MAS_JOB_MEDIA_TYPE = "application/vnd.sas.microanalytic.job+json"


def _coerce_int(value: Any) -> int | None:
    """Return ``value`` if it is a real ``int`` (``bool`` excluded), else ``None``."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _bool_or_none(value: Any) -> bool | None:
    """Return ``value`` if it is a real ``bool``, else ``None``."""
    return value if isinstance(value, bool) else None


def _prefer_str(value: Any, fallback: str) -> str:
    """Return ``value`` stripped if it is a non-empty string, else ``fallback``."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _str_or_none(value: Any) -> str | None:
    """Return ``value`` if it is a non-empty string, else ``None``."""
    if isinstance(value, str) and value.strip():
        return value
    return None


class Dialect:
    """Base dialect with Viya-4-shaped defaults; subclasses override what differs.

    Class attributes:
        name: Human-readable dialect name.
        decision_media_type: ``Accept`` value for fetching decision content.
        outputs_keys: Response keys to look for MAS outputs under, in priority
            order. Both generations are tolerated; the order encodes the shape a
            given generation returns first.
    """

    name: str
    decision_media_type: str = "application/vnd.sas.decision+json"
    decision_code_media_type: str = "text/vnd.sas.source.ds2"
    # A flow's external-artifacts endpoint is a (non-paginated) collection, so
    # it is read with the standard collection Accept.
    decision_external_artifacts_media_type: str = "application/vnd.sas.collection+json"
    mas_module_media_type: str = MAS_MODULE_MEDIA_TYPE
    mas_module_definition_media_type: str = MAS_MODULE_DEFINITION_MEDIA_TYPE
    mas_module_source_media_type: str = MAS_MODULE_SOURCE_MEDIA_TYPE
    mas_step_media_type: str = MAS_STEP_MEDIA_TYPE
    mas_step_input_media_type: str = MAS_STEP_INPUT_MEDIA_TYPE
    mas_validation_media_type: str = MAS_VALIDATION_MEDIA_TYPE
    mas_job_media_type: str = MAS_JOB_MEDIA_TYPE
    outputs_keys: tuple[str, ...] = ("outputs", "output")

    # -- endpoint paths -----------------------------------------------------

    def decision_path(self, decision_id: str) -> str:
        """Return the relative path for fetching a decision flow's content."""
        return f"/decisions/flows/{quote(decision_id, safe='')}"

    def decisions_flows_path(self) -> str:
        """Return the relative path for the decision-flows collection."""
        return "/decisions/flows"

    def decision_revisions_path(self, decision_id: str) -> str:
        """Return the relative path for a decision flow's revisions collection.

        A ``GET`` returns the ``/revisions`` subcollection of lightweight
        revision summaries. The id is percent-encoded for the same reason as
        :meth:`decision_path`.
        """
        return f"/decisions/flows/{quote(decision_id, safe='')}/revisions"

    def decision_revision_path(self, decision_id: str, revision_id: str) -> str:
        """Return the relative path for one revision of a decision flow.

        A ``GET`` (Accept ``application/vnd.sas.decision+json``) returns the full
        decision content *at that revision*. Both segments are percent-encoded.
        """
        return (
            f"/decisions/flows/{quote(decision_id, safe='')}"
            f"/revisions/{quote(revision_id, safe='')}"
        )

    def decision_code_path(self, decision_id: str) -> str:
        """Return the relative path for a decision flow's generated code.

        A ``GET`` (Accept ``text/vnd.sas.source.ds2``) returns the flow's
        generated DS2 source as raw text (not JSON), for the flow's current
        revision. The id is percent-encoded for the same reason as
        :meth:`decision_path`.
        """
        return f"/decisions/flows/{quote(decision_id, safe='')}/code"

    def decision_revision_code_path(self, decision_id: str, revision_id: str) -> str:
        """Return the relative path for the generated code of one flow revision.

        A ``GET`` (Accept ``text/vnd.sas.source.ds2``) returns the DS2 source as
        raw text *at that revision*. Both segments are percent-encoded.
        """
        return (
            f"/decisions/flows/{quote(decision_id, safe='')}"
            f"/revisions/{quote(revision_id, safe='')}/code"
        )

    def decision_external_artifacts_path(self, decision_id: str) -> str:
        """Return the relative path for a decision flow's external artifacts.

        A ``GET`` (Accept ``application/vnd.sas.collection+json``) returns every
        external artifact the flow references (analytic stores, etc.) in one
        response — the collection is not paginated. The id is percent-encoded for
        the same reason as :meth:`decision_path`.
        """
        return f"/decisions/flows/{quote(decision_id, safe='')}/externalArtifacts"

    def decision_revision_external_artifacts_path(self, decision_id: str, revision_id: str) -> str:
        """Return the relative path for one flow revision's external artifacts.

        As :meth:`decision_external_artifacts_path`, but scoped to a specific
        revision. Both segments are percent-encoded.
        """
        return (
            f"/decisions/flows/{quote(decision_id, safe='')}"
            f"/revisions/{quote(revision_id, safe='')}/externalArtifacts"
        )

    def mas_modules_path(self) -> str:
        """Return the relative path for the MAS modules collection."""
        return "/microanalyticScore/modules"

    def mas_module_path(self, module_id: str) -> str:
        """Return the relative path for a single MAS module's metadata."""
        return f"/microanalyticScore/modules/{quote(module_id, safe='')}"

    def mas_module_source_path(self, module_id: str) -> str:
        """Return the relative path for a MAS module's ``/source`` subresource.

        A ``GET`` returns the module's source code, a ``PUT`` replaces it (which
        requires an ``If-Match`` ETag). The id is percent-encoded for the same
        reason as :meth:`mas_execute_path`.
        """
        return f"/microanalyticScore/modules/{quote(module_id, safe='')}/source"

    def mas_jobs_path(self) -> str:
        """Return the relative path for the MAS async compile-job collection.

        A ``POST`` of a module definition here submits an asynchronous compile
        job (returning ``202`` with the job resource) instead of blocking on a
        synchronous ``POST /modules``.
        """
        return "/microanalyticScore/jobs"

    def mas_job_path(self, job_id: str) -> str:
        """Return the relative path for a single MAS compile job (poll target).

        The id is percent-encoded for the same reason as
        :meth:`mas_execute_path`, though the server assigns it as a UUID.
        """
        return f"/microanalyticScore/jobs/{quote(job_id, safe='')}"

    def mas_execute_path(self, module_id: str, step_id: str = DEFAULT_MAS_STEP) -> str:
        """Return the relative path for executing a MAS module step.

        ``step_id`` defaults to ``"execute"`` (correct for published decisions);
        pass another value for arbitrary modules exposing named steps.

        Both segments are percent-encoded so a reserved character (``/``, ``?``,
        ``#``, …) in an id can't alter the request path.
        """
        return (
            f"/microanalyticScore/modules/{quote(module_id, safe='')}"
            f"/steps/{quote(step_id, safe='')}"
        )

    def mas_step_path(self, module_id: str, step_id: str = DEFAULT_MAS_STEP) -> str:
        """Return the relative path for a MAS step's signature (metadata ``GET``).

        This is the same resource URL as :meth:`mas_execute_path` — a ``GET``
        returns the step's input/output signature, a ``POST`` executes it — so
        the same percent-encoding guarantees apply.
        """
        return self.mas_execute_path(module_id, step_id)

    def mas_validation_path(self, module_id: str, step_id: str = DEFAULT_MAS_STEP) -> str:
        """Return the relative path for validating a MAS step's inputs server-side.

        A ``POST`` of a step-input body to this resource asks SAS Viya to validate
        the payload against the step's signature. Both segments are percent-encoded
        for the same reason as :meth:`mas_execute_path`.
        """
        return (
            f"/microanalyticScore/commons/validations/modules/{quote(module_id, safe='')}"
            f"/steps/{quote(step_id, safe='')}"
        )

    # -- request building ---------------------------------------------------

    def build_inputs(
        self,
        features: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a MAS step-input request body from a feature mapping.

        Used both for executing a step (``POST /steps/{step}``) and for validating
        its inputs (``POST`` to the validations endpoint) — the two share the same
        ``{"inputs": [{"name", "value"}, ...]}`` body shape. Scalar values are
        passed through as-is and serialized as JSON by the HTTP layer (no string
        concatenation, no implicit name-mangling).

        A ``bytes``/``bytearray`` value is treated as *binary*: it is base64-encoded
        and its input object carries ``"encoding": "b64"``, which is how MAS accepts
        binary data (the target variable must be a ``binary``/``any`` type on the
        server). ``metadata``, when given, is attached as a sibling ``metadata``
        object for correlation (e.g. ``client_id``/``transaction_id``); MAS echoes
        it back on the response.
        """
        body: dict[str, Any] = {
            "inputs": [self._build_input(name, value) for name, value in features.items()]
        }
        if metadata:
            body["metadata"] = dict(metadata)
        return body

    def _build_input(self, name: str, value: Any) -> dict[str, Any]:
        """Build a single step-input entry, base64-encoding binary values."""
        if isinstance(value, (bytes, bytearray)):
            return {
                "name": name,
                "value": base64.b64encode(bytes(value)).decode("ascii"),
                "encoding": "b64",
            }
        return {"name": name, "value": value}

    def build_module_definition(
        self,
        module_id: str,
        source: str,
        *,
        source_type: str,
        scope: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Build the request body for creating a MAS module (``POST /modules``).

        ``source_type`` is the *source language* media type (e.g.
        ``text/vnd.sas.source.ds2`` or ``text/x-python``), not the ``.module`` or
        ``.definition+json`` envelope type. ``scope`` (e.g. ``"public"``) is
        required by the server; ``description`` is omitted when ``None`` rather
        than sent as ``null``.
        """
        body: dict[str, Any] = {
            "id": module_id,
            "type": source_type,
            "scope": scope,
            "source": source,
        }
        if description is not None:
            body["description"] = description
        return body

    def build_source_update(
        self, module_id: str, source: str, *, source_type: str
    ) -> dict[str, Any]:
        """Build the request body for a module source update (``PUT /source``).

        ``source_type`` is the source-language media type (see
        :meth:`build_module_definition`). The ``PUT`` additionally requires an
        ``If-Match`` header carrying the current ETag; that is a transport
        concern handled by the client, not part of this body.
        """
        return {"moduleId": module_id, "type": source_type, "source": source}

    def build_decision_definition(
        self,
        name: str,
        *,
        description: str | None = None,
        flow: Mapping[str, Any] | None = None,
        signature: Any | None = None,
        properties: Any | None = None,
    ) -> dict[str, Any]:
        """Build the request body for a decision flow (``POST``/``PUT`` flows).

        The authorable representation is a small subset of the full decision
        payload the server returns: ``name`` (required) plus the optional
        ``description``, ``flow`` (the raw step graph — for phase 5.4a this is
        passed through verbatim rather than assembled from a typed builder),
        ``signature``, and ``properties``. Absent fields are omitted rather than
        sent as ``null``, so a create can send just ``name`` and a ``flow`` and an
        update can carry a full round-tripped representation.
        """
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        if flow is not None:
            body["flow"] = dict(flow)
        if signature is not None:
            body["signature"] = signature
        if properties is not None:
            body["properties"] = properties
        return body

    # -- response parsing ---------------------------------------------------

    def parse_decision_summary(self, raw: Mapping[str, Any]) -> DecisionSummary:
        """Build a :class:`DecisionSummary` from one ``/decisions/flows`` item.

        Each collection item is an ``application/vnd.sas.summary`` carrying
        identity and audit metadata but not the flow body. The full payload is
        retained on :attr:`DecisionSummary.raw`.

        Raises:
            ViyaResponseError: The payload has no usable string ``id`` — without
                it the returned summary would have a false identity, so a
                malformed response fails loudly here.
        """
        decision_id = raw.get("id")
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ViyaResponseError(
                "decision summary payload has no usable 'id' field",
                response_body=dict(raw),
            )
        return DecisionSummary(
            id=decision_id.strip(),
            name=_str_or_none(raw.get("name")),
            description=_str_or_none(raw.get("description")),
            type=_str_or_none(raw.get("type")),
            created_by=_str_or_none(raw.get("createdBy")),
            modified_by=_str_or_none(raw.get("modifiedBy")),
            creation_timestamp=_str_or_none(raw.get("creationTimeStamp")),
            modified_timestamp=_str_or_none(raw.get("modifiedTimeStamp")),
            raw=dict(raw),
        )

    def parse_decision(self, decision_id: str, raw: Mapping[str, Any]) -> Decision:
        """Build a :class:`Decision` from a decision-flow payload.

        Extracts the model steps from ``flow.steps`` (ignoring non-model steps)
        and the revision/lock metadata (``majorRevision``, ``minorRevision``,
        ``checkout``), and retains the full payload on :attr:`Decision.raw`. The
        same shape is returned whether the payload is the current flow (from
        ``GET /decisions/flows/{id}``) or a specific historical revision (from
        ``GET /decisions/flows/{id}/revisions/{revisionId}``).
        """
        flow = raw.get("flow")
        steps = flow.get("steps", []) if isinstance(flow, Mapping) else []
        models = tuple(
            ModelStep(
                name=str((step.get("model") or {}).get("name", "")),
                modified_by=step.get("modifiedBy"),
                modified_timestamp=step.get("modifiedTimeStamp"),
                raw=dict(step),
            )
            for step in steps
            if isinstance(step, Mapping) and step.get("type") == MODEL_STEP_TYPE
        )
        return Decision(
            id=decision_id,
            name=raw.get("name"),
            models=models,
            major_revision=_coerce_int(raw.get("majorRevision")),
            minor_revision=_coerce_int(raw.get("minorRevision")),
            checkout=_bool_or_none(raw.get("checkout")),
            raw=dict(raw),
        )

    def parse_revision(self, raw: Mapping[str, Any]) -> Revision:
        """Build a :class:`Revision` from one ``/revisions`` collection item.

        Each item is a lightweight revision summary carrying the ``major.minor``
        version pair, the ``checkout`` lock indicator, and audit metadata. The
        full payload is retained on :attr:`Revision.raw`. This shape is shared
        across versioned resources (decision flows, business rulesets), so the
        parser lives on the base dialect rather than a per-resource override.

        Raises:
            ViyaResponseError: The payload has no usable string ``id`` — without
                it the returned revision would have a false identity, so a
                malformed response fails loudly here.
        """
        revision_id = raw.get("id")
        if not isinstance(revision_id, str) or not revision_id.strip():
            raise ViyaResponseError(
                "revision payload has no usable 'id' field",
                response_body=dict(raw),
            )
        return Revision(
            id=revision_id.strip(),
            major_revision=_coerce_int(raw.get("majorRevision")),
            minor_revision=_coerce_int(raw.get("minorRevision")),
            description=_str_or_none(raw.get("description")),
            node_count=_coerce_int(raw.get("nodeCount")),
            checkout=_bool_or_none(raw.get("checkout")),
            workflow_definition_id=_str_or_none(raw.get("workflowDefinitionId")),
            created_by=_str_or_none(raw.get("createdBy")),
            modified_by=_str_or_none(raw.get("modifiedBy")),
            creation_timestamp=_str_or_none(raw.get("creationTimeStamp")),
            modified_timestamp=_str_or_none(raw.get("modifiedTimeStamp")),
            raw=dict(raw),
        )

    def parse_external_artifact(self, raw: Mapping[str, Any]) -> ExternalArtifact:
        """Build an :class:`ExternalArtifact` from one ``externalArtifacts`` item.

        Each item names a resource the flow depends on (typically an analytic
        store) with a type-dependent ``artifactProperties`` map, kept verbatim on
        :attr:`ExternalArtifact.properties`. The full payload is retained on
        :attr:`ExternalArtifact.raw`.

        Raises:
            ViyaResponseError: The payload has no usable string ``name`` — without
                it the artifact would have a false identity, so a malformed
                response fails loudly here.
        """
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ViyaResponseError(
                "external artifact payload has no usable 'name' field",
                response_body=dict(raw),
            )
        properties = raw.get("artifactProperties")
        return ExternalArtifact(
            name=name.strip(),
            artifact_type=_str_or_none(raw.get("artifactType")),
            parent_uri=_str_or_none(raw.get("parentURI")),
            properties=dict(properties) if isinstance(properties, Mapping) else {},
            raw=dict(raw),
        )

    def parse_module(self, raw: Mapping[str, Any]) -> MasModule:
        """Build a :class:`MasModule` from a MAS module payload.

        Used for both a single-module ``GET`` and each item of the modules
        collection; the full payload is retained on :attr:`MasModule.raw`.

        Raises:
            ViyaResponseError: The payload has no usable string ``id`` — without
                it the returned model would have a false identity (e.g. the
                literal ``"None"``), so a malformed response fails loudly here.
        """
        module_id = raw.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            raise ViyaResponseError(
                "MAS module payload has no usable 'id' field",
                response_body=dict(raw),
            )
        step_ids = raw.get("stepIds")
        steps = tuple(str(s) for s in step_ids) if isinstance(step_ids, list) else ()
        revision = raw.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            revision = None
        return MasModule(
            id=module_id.strip(),
            name=raw.get("name"),
            description=raw.get("description"),
            revision=revision,
            scope=raw.get("scope"),
            step_ids=steps,
            created_by=raw.get("createdBy"),
            modified_by=raw.get("modifiedBy"),
            creation_timestamp=raw.get("creationTimeStamp"),
            modified_timestamp=raw.get("modifiedTimeStamp"),
            raw=dict(raw),
        )

    def parse_module_source(self, module_id: str, raw: Mapping[str, Any]) -> ModuleSource:
        """Build a :class:`ModuleSource` from a MAS ``/source`` payload.

        The module identity comes from the request (``module_id``); the payload's
        own ``moduleId`` is preferred when present. The full payload is retained
        on :attr:`ModuleSource.raw`.

        Raises:
            ViyaResponseError: The payload has no string ``source`` field — without
                the source code the result would be meaningless, so a malformed
                response fails loudly here.
        """
        source = raw.get("source")
        if not isinstance(source, str):
            raise ViyaResponseError(
                "MAS module source payload has no usable 'source' field",
                response_body=dict(raw),
            )
        return ModuleSource(
            module_id=_prefer_str(raw.get("moduleId"), module_id),
            source=source,
            version=_coerce_int(raw.get("version")),
            created_by=_str_or_none(raw.get("createdBy")),
            modified_by=_str_or_none(raw.get("modifiedBy")),
            creation_timestamp=_str_or_none(raw.get("creationTimeStamp")),
            modified_timestamp=_str_or_none(raw.get("modifiedTimeStamp")),
            raw=dict(raw),
        )

    def parse_compile_job(self, raw: Mapping[str, Any]) -> CompileJob:
        """Build a :class:`CompileJob` from a MAS ``/jobs`` payload.

        Used for both the ``POST`` submit response and each poll ``GET``; the full
        payload is retained on :attr:`CompileJob.raw`. The ``errors`` array (which
        a failed job populates with compiler messages) is normalized to a tuple of
        strings.

        Raises:
            ViyaResponseError: The payload has no usable string ``id`` — without a
                job id the result could not be polled, so a malformed response
                fails loudly here.
        """
        job_id = raw.get("id")
        if not isinstance(job_id, str) or not job_id.strip():
            raise ViyaResponseError(
                "MAS compile job payload has no usable 'id' field",
                response_body=dict(raw),
            )
        errors_raw = raw.get("errors")
        errors = tuple(str(item) for item in errors_raw) if isinstance(errors_raw, list) else ()
        return CompileJob(
            id=job_id.strip(),
            module_id=_str_or_none(raw.get("moduleId")),
            operation=_str_or_none(raw.get("operation")),
            state=_str_or_none(raw.get("state")),
            errors=errors,
            created_by=_str_or_none(raw.get("createdBy")),
            modified_by=_str_or_none(raw.get("modifiedBy")),
            creation_timestamp=_str_or_none(raw.get("creationTimeStamp")),
            modified_timestamp=_str_or_none(raw.get("modifiedTimeStamp")),
            raw=dict(raw),
        )

    def parse_step_signature(
        self, module_id: str, step_id: str, raw: Mapping[str, Any]
    ) -> StepSignature:
        """Build a :class:`StepSignature` from a MAS step payload.

        The step's identity comes from the request (``module_id``/``step_id``);
        the payload's own ``id``/``moduleId`` are preferred when present. Each
        entry of the ``inputs`` and ``outputs`` arrays becomes a :class:`Variable`;
        malformed or nameless entries are skipped rather than crashing the parse.

        Raises:
            ViyaResponseError: The payload carries neither an ``inputs`` nor an
                ``outputs`` list — without either it isn't a usable signature, so
                a malformed response fails loudly here rather than returning an
                empty shape that looks like a real (but signatureless) step.
        """
        inputs_raw = raw.get("inputs")
        outputs_raw = raw.get("outputs")
        if not isinstance(inputs_raw, list) and not isinstance(outputs_raw, list):
            raise ViyaResponseError(
                "MAS step signature payload has no 'inputs' or 'outputs' list",
                response_body=dict(raw),
            )
        return StepSignature(
            id=_prefer_str(raw.get("id"), step_id),
            module_id=_prefer_str(raw.get("moduleId"), module_id),
            inputs=self._parse_variables(inputs_raw),
            outputs=self._parse_variables(outputs_raw),
            raw=dict(raw),
        )

    def _parse_variables(self, items: Any) -> tuple[Variable, ...]:
        """Parse a signature's ``inputs``/``outputs`` array into :class:`Variable`s."""
        if not isinstance(items, list):
            return ()
        variables: list[Variable] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue  # a nameless entry can't be addressed; skip it
            var_type = item.get("type")
            variables.append(
                Variable(
                    name=name.strip(),
                    type=var_type if isinstance(var_type, str) else None,
                    dim=_coerce_int(item.get("dim")),
                    size=_coerce_int(item.get("size")),
                )
            )
        return tuple(variables)

    def parse_execution(
        self, module_id: str, step_id: str, raw: Mapping[str, Any]
    ) -> ExecutionResult:
        """Build an :class:`ExecutionResult` from a MAS execute payload.

        Flattens the generation's output list (``outputs`` or ``output``) into a
        ``{name: value}`` mapping. Raises :class:`ViyaResponseError` if a
        completed response carries no output list. The timed-out and submitted
        modes legitimately return no outputs, so those are parsed as an empty
        mapping rather than an error.

        A binary output (one MAS marks with ``encoding: "b64"``) has its base64
        string value decoded back into ``bytes``; scalar outputs pass through. Any
        correlation ``metadata`` the server echoes (``client_id``/``transaction_id``)
        is surfaced on the result.
        """
        state = raw.get("executionState")
        outputs = {
            name: self._output_value(item, raw)
            for item in self._raw_outputs(raw, state)
            if isinstance(item, Mapping) and isinstance(name := item.get("name"), str)
        }
        metadata = raw.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        return ExecutionResult(
            outputs=outputs,
            execution_state=state,
            module_id=raw.get("moduleId", module_id),
            step_id=raw.get("stepId", step_id),
            client_id=_str_or_none(metadata.get("client_id")),
            transaction_id=_str_or_none(metadata.get("transaction_id")),
            raw=dict(raw),
        )

    def _output_value(self, item: Mapping[str, Any], raw: Mapping[str, Any]) -> Any:
        """Return an output's value, decoding it from base64 if MAS marked it binary."""
        value = item.get("value")
        if item.get("encoding") != "b64":
            return value
        if not isinstance(value, str):
            raise ViyaResponseError(
                f"MAS output {item.get('name')!r} is marked encoding 'b64' but its "
                f"value is not a base64 string (got {type(value).__name__})",
                response_body=dict(raw),
            )
        try:
            return base64.b64decode(value, validate=True)
        except ValueError as exc:  # binascii.Error subclasses ValueError
            raise ViyaResponseError(
                f"MAS output {item.get('name')!r} is marked encoding 'b64' but its "
                "value is not valid base64",
                response_body=dict(raw),
            ) from exc

    def _raw_outputs(self, raw: Mapping[str, Any], state: Any = None) -> list[Any]:
        for key in self.outputs_keys:
            value = raw.get(key)
            if isinstance(value, list):
                return value
        # Fire-and-forget (submitted) and timed-out runs return no outputs by
        # design; only a completed/synchronous response is expected to have them.
        if state in (EXECUTION_SUBMITTED, EXECUTION_TIMED_OUT):
            return []
        raise ViyaResponseError(
            f"MAS response contains no output list (expected one of {self.outputs_keys!r})",
            response_body=dict(raw),
        )

    def parse_validation(
        self, module_id: str, step_id: str, raw: Mapping[str, Any]
    ) -> ValidationResult:
        """Build a :class:`ValidationResult` from a MAS validations payload.

        The endpoint returns ``valid`` (bool) and ``version``; an *invalid* payload
        is still an HTTP 201 whose body carries ``valid: false`` and a SAS error
        object, so the outcome is read from the body rather than the status. When
        invalid, the error object's messages (its own ``message``/``details`` plus
        any nested ``errors``) are flattened onto :attr:`ValidationResult.messages`.

        Raises:
            ViyaResponseError: The payload has no ``valid`` field — without it the
                response isn't a usable validation result, so a malformed body
                fails loudly here rather than being read as ``valid: false``.
        """
        if "valid" not in raw:
            raise ViyaResponseError(
                "MAS validation payload has no 'valid' field",
                response_body=dict(raw),
            )
        valid = bool(raw.get("valid"))
        error = raw.get("error")
        error_dict = dict(error) if isinstance(error, Mapping) else None
        messages = () if valid else self._validation_messages(error)
        return ValidationResult(
            valid=valid,
            version=_coerce_int(raw.get("version")),
            messages=messages,
            error=error_dict,
            module_id=module_id,
            step=step_id,
            raw=dict(raw),
        )

    def _validation_messages(self, error: Any) -> tuple[str, ...]:
        """Flatten a SAS error object into ordered, de-duplicated message strings."""
        messages: list[str] = []
        self._collect_error_messages(error, messages)
        # Preserve order while dropping duplicates (nested errors can repeat text).
        seen: set[str] = set()
        unique: list[str] = []
        for message in messages:
            if message not in seen:
                seen.add(message)
                unique.append(message)
        return tuple(unique)

    def _collect_error_messages(self, error: Any, acc: list[str]) -> None:
        """Recursively gather ``message``/``details`` text from a SAS error object."""
        if not isinstance(error, Mapping):
            return
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            acc.append(message.strip())
        details = error.get("details")
        if isinstance(details, list):
            acc.extend(d.strip() for d in details if isinstance(d, str) and d.strip())
        nested = error.get("errors")
        if isinstance(nested, list):
            for item in nested:
                self._collect_error_messages(item, acc)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"
