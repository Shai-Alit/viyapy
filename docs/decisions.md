# Working with Decisions

The `client.decisions` group ([`DecisionsAPI`][viyapy.decisions.DecisionsAPI])
reads SAS Intelligent Decisioning decision flows.

## Fetch a decision

[`get`][viyapy.decisions.DecisionsAPI.get] returns a typed
[`Decision`][viyapy.Decision]:

```python
decision = client.decisions.get("my-decision-id")

decision.id        # the decision id
decision.name      # the flow's name, if present
decision.models    # tuple[ModelStep, ...] — the model steps in the flow
decision.raw       # the raw payload, as a dict, if you need an escape hatch
```

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

## Errors

An empty or non-string `decision_id` raises
[`ViyaConfigError`][viyapy.ViyaConfigError] before any request. A missing
decision raises [`ViyaNotFoundError`][viyapy.ViyaNotFoundError]. See
[Error Handling](error-handling.md).
