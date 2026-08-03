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
