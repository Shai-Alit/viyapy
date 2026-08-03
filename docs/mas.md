# Executing MAS Modules

The `client.mas` group ([`MASClient`][viyapy.mas.MASClient]) executes SAS Micro
Analytic Score (MAS) module steps.

## Execute a module

[`execute`][viyapy.mas.MASClient.execute] posts a feature mapping to a module's
step and returns a typed [`ExecutionResult`][viyapy.ExecutionResult]:

```python
result = client.mas.execute("api_tester1_0", {"input_string": "this is a test"})

result.outputs          # {name: value} — the flattened outputs
result.execution_state  # e.g. "completed", if reported
result.module_id        # the executed module id
result.raw              # the raw response payload
```

`ExecutionResult` also supports mapping-style access to its outputs:

```python
result["output_string"]           # KeyError if absent
result.get("maybe_missing", None) # default if absent
"output_string" in result
```

## Inputs are built for you

Pass a plain `dict` of feature names to values. viyapy serializes it to the MAS
request body as JSON — values pass through unchanged, with **no** string
concatenation and **no** name-mangling (the 2.x helper's trailing-underscore bug
is gone). Quotes, newlines, and unicode in values are handled correctly.

## The step id

The step defaults to `"execute"`, which is correct for a **published decision**
(its MAS module exposes a step literally named `execute`). For an arbitrary
module that exposes named steps, pass `step`:

```python
result = client.mas.execute("my_module", inputs, step="score")
```

## Retries and idempotency

MAS `execute` is a POST and is **not** assumed idempotent, so it is not retried
by default (to avoid double-executing a decision). If your call is safe to retry,
opt in at the client level with `retry_on_post=True`. A longer read timeout can
be set per call via `timeout=`.

## The `output` vs `outputs` shape

SAS returns synchronous execute results under `output` (singular) and
async/timeout results under `outputs` (plural), and this differs across Viya
generations. The dialect layer handles both, so `result.outputs` is always a
flat dict regardless of which shape the server returned. A 2xx response with no
output list at all raises [`ViyaResponseError`][viyapy.ViyaResponseError].
