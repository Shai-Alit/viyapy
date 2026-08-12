# Working with Decisions

The `client.decisions` group ([`DecisionsAPI`][viyapy.decisions.DecisionsAPI])
reads and authors SAS Intelligent Decisioning decision flows.

## Fetch a decision

[`get`][viyapy.decisions.DecisionsAPI.get] returns a typed
[`Decision`][viyapy.Decision]:

```python
decision = client.decisions.get("my-decision-id")

decision.id              # the decision id
decision.name            # the flow's name, if present
decision.models          # tuple[ModelStep, ...] — the model steps in the flow
decision.major_revision  # the current major revision number, if reported
decision.minor_revision  # the current minor revision number, if reported
decision.checkout        # whether the flow is checked out (locked), if reported
decision.raw             # the raw payload, as a dict, if you need an escape hatch
```

A plain `get` returns the flow's **current** revision; the
`major_revision`/`minor_revision` pair identifies which one that is, and
`checkout` reports whether it is checked out (locked) for editing. Each defaults
to `None` when the deployment does not report it.

Each entry in `decision.models` is a [`ModelStep`][viyapy.ModelStep]:

```python
for model in decision.models:
    print(model.name, model.modified_by, model.modified_timestamp)
```

Only model steps are surfaced in `decision.models`; other step types in the flow
(rule sets, branches, etc.) are ignored. The complete flow is always available on
`decision.raw`.

## List decision flows

[`list`][viyapy.decisions.DecisionsAPI.list] iterates every decision flow on the
deployment, yielding a lightweight [`DecisionSummary`][viyapy.DecisionSummary]
per flow. Pages are fetched lazily as you consume the iterator (following the
collection's `next` links), so a large deployment is streamed rather than
buffered into memory:

```python
for summary in client.decisions.list():
    print(summary.id, summary.name, summary.modified_timestamp)

summary.id                  # the decision id
summary.name                # the flow's name, if present
summary.description         # the description, if present
summary.type                # the object type (e.g. "decision")
summary.created_by          # audit metadata, if reported
summary.modified_by
summary.creation_timestamp
summary.modified_timestamp
summary.raw                 # the raw summary payload, as a dict
```

A `DecisionSummary` is the collection (`application/vnd.sas.summary`)
representation — it carries identity and audit metadata but **not** the flow
body. When you need the steps, pass its `id` to `get`:

```python
for summary in client.decisions.list():
    decision = client.decisions.get(summary.id)   # the full flow
```

`page_size` (default `100`) controls how many flows are requested per round trip;
the server may cap the effective size. It is validated eagerly, so a non-positive
value raises [`ViyaConfigError`][viyapy.ViyaConfigError] at the call site rather
than on first iteration:

```python
flows = list(client.decisions.list(page_size=500))
```

## Revision history

Every decision flow is versioned. [`revisions`][viyapy.decisions.DecisionsAPI.revisions]
iterates a flow's revision history, yielding a lightweight
[`Revision`][viyapy.Revision] per entry. Like `list`, it pages lazily as you
consume the iterator:

```python
for revision in client.decisions.revisions("my-decision-id"):
    print(revision.label, revision.checkout, revision.modified_timestamp)

revision.id                  # the revision id
revision.major_revision      # the major revision number, if reported
revision.minor_revision      # the minor revision number, if reported
revision.label               # a convenience "major.minor" string (e.g. "1.3"),
                             # or None if either component is missing
revision.description         # the revision's description, if present
revision.node_count          # nodes in the flow at this revision, if reported
revision.checkout            # whether this revision is checked out (locked)
revision.workflow_definition_id
revision.created_by          # audit metadata, if reported
revision.modified_by
revision.creation_timestamp
revision.modified_timestamp
revision.raw                 # the raw revision payload, as a dict
```

To load a flow's full content **at** a specific revision, pass the flow id and
the revision id to
[`get_revision`][viyapy.decisions.DecisionsAPI.get_revision]. It returns the same
typed [`Decision`][viyapy.Decision] as `get` (its `id` is the revision id):

```python
for revision in client.decisions.revisions("my-decision-id"):
    snapshot = client.decisions.get_revision("my-decision-id", revision.id)
    print(snapshot.name, [m.name for m in snapshot.models])
```

!!! note
    A plain `get("my-decision-id")` already returns the **current** revision, so
    there is no separate "current revision" call — read `major_revision` /
    `minor_revision` off the returned `Decision`.

`page_size` behaves exactly as for `list` (default `100`, validated eagerly).

## Generated code

A decision flow compiles to SAS **DS2** code.
[`get_code`][viyapy.decisions.DecisionsAPI.get_code] returns that generated
source for the flow's **current** revision, as a plain string (raw text, not
JSON):

```python
ds2 = client.decisions.get_code("my-decision-id")
print(ds2)              # the generated DS2 source, verbatim
```

To get the code **at** a specific historical revision, pass the flow id and a
revision id (see [Revision history](#revision-history) for the ids) to
[`get_revision_code`][viyapy.decisions.DecisionsAPI.get_revision_code]:

```python
for revision in client.decisions.revisions("my-decision-id"):
    ds2 = client.decisions.get_revision_code("my-decision-id", revision.id)
```

Both return the DS2 source verbatim. An empty or non-string id raises
[`ViyaConfigError`][viyapy.ViyaConfigError] before any request; a missing flow or
revision raises [`ViyaNotFoundError`][viyapy.ViyaNotFoundError].

!!! note
    This is the flow's *unmapped* generated code. The related SAS **mapped code**
    endpoint (which binds the flow to specific input/output tables) is a separate
    request and is not yet exposed by viyapy.

## External artifacts

A decision flow can reference resources that live **outside** the flow itself —
most commonly the analytic store backing a model step.
[`external_artifacts`][viyapy.decisions.DecisionsAPI.external_artifacts] returns
those dependencies for the flow's **current** revision. Unlike `list` and
`revisions`, this endpoint is **not** paginated — the server returns every
artifact in one response — so it eagerly returns a `tuple` rather than a lazy
iterator:

```python
for artifact in client.decisions.external_artifacts("my-decision-id"):
    artifact.name           # the artifact name
    artifact.artifact_type  # e.g. "analyticStore", if reported
    artifact.parent_uri     # the owning resource's URI, if reported
    artifact.properties     # a type-dependent dict (e.g. astore location keys)
    artifact.raw            # the raw artifact payload, as a dict
```

`properties` is left as a raw dict because its shape depends on
`artifact_type` (an `analyticStore`, for instance, carries astore name/key/URI
and file-location keys).

To get the artifacts **at** a specific historical revision, pass the flow id and
a revision id (see [Revision history](#revision-history) for the ids) to
[`revision_external_artifacts`][viyapy.decisions.DecisionsAPI.revision_external_artifacts]:

```python
for revision in client.decisions.revisions("my-decision-id"):
    artifacts = client.decisions.revision_external_artifacts(
        "my-decision-id", revision.id
    )
```

An empty or non-string id raises
[`ViyaConfigError`][viyapy.ViyaConfigError] before any request; a missing flow or
revision raises [`ViyaNotFoundError`][viyapy.ViyaNotFoundError]. A flow that
references no external artifacts yields an empty tuple.

## List just the models

If you only need the models, [`list_models`][viyapy.decisions.DecisionsAPI.list_models]
is a convenience wrapper:

```python
models = client.decisions.list_models("my-decision-id")
```

!!! note
    `list_models` issues its own fresh request each call and does not cache. If
    you need both the flow and its models, call `get` once and reuse the returned
    `Decision`.

## Authoring decision flows

Beyond reading, `client.decisions` can create, update, and delete flows.

[`create`][viyapy.decisions.DecisionsAPI.create] posts a new flow and returns the
server's [`Decision`][viyapy.Decision], with the id and revision numbers the
server assigns:

```python
decision = client.decisions.create(
    "My New Flow",
    {"steps": []},                     # the flow graph, as a raw dict
    description="created via viyapy",
)

decision.id              # the server-assigned id
decision.major_revision  # 1
decision.minor_revision  # 0
```

The flow graph can be passed through as a **raw dict** — an empty `{"steps": []}`
is a valid starting flow — and the optional `signature` and `properties` are
forwarded verbatim when given. Rather than hand-write the step JSON, though, you
can compose the graph with the [typed builder](#composing-flows-with-the-typed-builder)
described below.

[`update`][viyapy.decisions.DecisionsAPI.update] changes a flow's authorable
fields. Pass only what you want to change; unspecified fields are preserved:

```python
decision = client.decisions.update(
    "my-decision-id",
    description="a new description",   # name/flow/signature/properties untouched
)
```

Updates are guarded by optimistic concurrency: `update` first fetches the flow to
read its `ETag`, then sends the change back with an `If-Match` header. If the flow
changed on the server between those two steps, the update fails with a precondition
error ([`ViyaAPIError`][viyapy.ViyaAPIError], HTTP 412) rather than silently
overwriting the concurrent change — so retry against the fresh state.

[`delete`][viyapy.decisions.DecisionsAPI.delete] removes a flow:

```python
client.decisions.delete("my-decision-id")
```

## Composing flows with the typed builder

A decision flow's graph is a `{"steps": [...]}` mapping in which every step is a
small dict tagged by a SAS media-type string. Writing that by hand is easy to get
subtly wrong, so [`FlowBuilder`][viyapy.FlowBuilder] assembles it from typed,
validated calls. Each method appends one step and returns the builder, so calls
chain, and [`create`][viyapy.decisions.DecisionsAPI.create] and
[`update`][viyapy.decisions.DecisionsAPI.update] accept a `FlowBuilder` directly
(they call `build()` for you):

```python
from viyapy import FlowBuilder, TermMapping

flow = (
    FlowBuilder()
    .model(
        "9fadffa1-...",                          # a model's id
        mappings=[
            TermMapping.input("DEBTINC"),
            TermMapping.output("EM_CLASSIFICATION"),
        ],
    )
    .condition(
        "P_BAD1 < .2",                           # a SAS boolean expression
        on_true=FlowBuilder().ruleset("approve-ruleset-id"),
        on_false=FlowBuilder().ruleset("decline-ruleset-id"),
    )
)

decision = client.decisions.create("My Flow", flow)
```

The three step methods cover the common cases:

- [`model`][viyapy.FlowBuilder.model] references a registered model by id.
- [`ruleset`][viyapy.FlowBuilder.ruleset] references a business ruleset, with an
  optional pinned `version_id`/`version_name`.
- [`condition`][viyapy.FlowBuilder.condition] adds an if/else branch whose
  `on_true`/`on_false` arms are themselves `FlowBuilder` instances, so flows nest
  to any depth. Either arm may be omitted.

[`TermMapping`][viyapy.TermMapping] wires a step's own terms to the flow's
decision-level terms. Its `input`, `output`, and `in_out` constructors default the
step term to the decision term — the common matching-name case — so you name it
once; pass a second argument when the names differ.

The builder emits only the **authorable** subset of each step; the server assigns
ids, timestamps, and links on create. Step types the builder doesn't model yet
(custom-object, branch) can be appended verbatim with
[`add_step`][viyapy.FlowBuilder.add_step]. `build()` returns a fresh copy each
call, so a builder is reusable. The builder validates eagerly: an empty id or
expression, an unknown mapping direction, or a non-`TermMapping` mapping raises
[`ViyaConfigError`][viyapy.ViyaConfigError] before any request.

## Errors

An empty or non-string `decision_id` raises
[`ViyaConfigError`][viyapy.ViyaConfigError] before any request. A missing
decision raises [`ViyaNotFoundError`][viyapy.ViyaNotFoundError]. See
[Error Handling](error-handling.md).
