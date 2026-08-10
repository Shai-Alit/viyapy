# Executing MAS Modules

The `client.mas` group ([`MASClient`][viyapy.mas.MASClient]) inspects and executes
SAS Micro Analytic Score (MAS) module steps.

## Discovering modules

[`list`][viyapy.mas.MASClient.list] iterates the modules on the deployment,
yielding a typed [`MasModule`][viyapy.MasModule] for each. Pages are fetched
lazily as you consume the iterator, so a large deployment streams rather than
loads all at once:

```python
for module in client.mas.list():
    print(module.id, module.name, module.step_ids)

# Materialize if you need a list, or filter as you go:
public = [m for m in client.mas.list() if m.scope == "public"]
```

`list` requests 100 modules per page by default; tune it with `page_size=` (the
server may cap the effective size). [`get`][viyapy.mas.MASClient.get] fetches a
single module's metadata by id:

```python
module = client.mas.get("api_tester1_0")
module.name              # "api_tester"
module.step_ids          # ("execute",) — the steps you can pass to execute()
module.revision          # the module revision, if reported
module.raw               # the raw module payload
```

`get` raises [`ViyaNotFoundError`][viyapy.ViyaNotFoundError] if no module has that
id, and both methods raise [`ViyaConfigError`][viyapy.ViyaConfigError] for an
invalid `module_id` or `page_size` before any request is issued.

## Inspecting a step signature

Before executing a step, you can discover the inputs it expects and the outputs
it produces. [`get_signature`][viyapy.mas.MASClient.get_signature] returns a typed
[`StepSignature`][viyapy.StepSignature] whose `inputs` and `outputs` are tuples of
[`Variable`][viyapy.Variable] (`name`, `type`, `dim`, `size`):

```python
sig = client.mas.get_signature("api_tester1_0")   # step defaults to "execute"

sig.id                                  # "execute"
sig.module_id                           # "api_tester1_0"
[v.name for v in sig.inputs]            # ["input_string"]
sig.inputs[0].type                      # "string"
sig.outputs[0].name                     # "output_string"

# Handy for validating a payload before you execute:
expected = {v.name for v in sig.inputs}
missing = expected - payload.keys()
```

Pass `step=` to inspect a named step other than `execute`. `get_signature` raises
[`ViyaNotFoundError`][viyapy.ViyaNotFoundError] if the module or step doesn't
exist, [`ViyaConfigError`][viyapy.ViyaConfigError] for a blank `module_id`/`step`
(before any request), and [`ViyaResponseError`][viyapy.ViyaResponseError] if the
response isn't a usable signature.

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
