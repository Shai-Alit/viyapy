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

## Managing modules

Beyond reading modules, `client.mas` can create, update, and delete them, and read
back a module's source.

### Create a module

[`create`][viyapy.mas.MASClient.create] compiles a module from source and returns
the resulting [`MasModule`][viyapy.MasModule]:

```python
module = client.mas.create(
    "scorer_1_0",
    ds2_source,               # the module source text
    language="ds2",           # "ds2" (default) or "python"
    scope="public",           # "public" (default) or "private"
    description="Scoring module",   # optional
)
module.id                     # "scorer_1_0"
module.step_ids               # the steps the compiled module exposes
```

`language` selects the source media type (`text/vnd.sas.source.ds2` or
`text/x-python`) and is matched case-insensitively. `module_id`, `source`, and
`scope` must be non-empty; an unsupported `language` or any blank argument raises
[`ViyaConfigError`][viyapy.ViyaConfigError] before a request is issued. A source
that fails to compile surfaces the server's error as a
[`ViyaAPIError`][viyapy.ViyaAPIError].

### Read a module's source

[`get_source`][viyapy.mas.MASClient.get_source] fetches the source subresource as
a typed [`ModuleSource`][viyapy.ModuleSource]:

```python
src = client.mas.get_source("scorer_1_0")
src.source        # the module source text
src.version       # the source revision, if reported
src.raw           # the raw source payload
```

It raises [`ViyaNotFoundError`][viyapy.ViyaNotFoundError] if the module doesn't
exist and [`ViyaResponseError`][viyapy.ViyaResponseError] if the response carries
no usable `source`.

### Update a module's source

[`update_source`][viyapy.mas.MASClient.update_source] replaces a module's source,
recompiling it in place. MAS guards the update with optimistic concurrency, so
`update_source` first fetches the module to read its current `ETag` and forwards it
verbatim as an `If-Match` header — without it the server responds `428 Precondition
Required`:

```python
src = client.mas.update_source("scorer_1_0", revised_source)   # reuses the module's language
src = client.mas.update_source("scorer_1_0", py_source, language="python")  # or override it
```

When `language` is omitted the module's current language is reused; pass it to
change the source type. An explicit unsupported `language` raises
[`ViyaConfigError`][viyapy.ViyaConfigError] before any request; if the server
reports no `ETag` or no resolvable language, `update_source` raises
[`ViyaResponseError`][viyapy.ViyaResponseError]. A concurrent modification (stale
`ETag`) surfaces as a [`ViyaAPIError`][viyapy.ViyaAPIError].

### Delete a module

[`delete`][viyapy.mas.MASClient.delete] removes a module (the server returns `204
No Content`):

```python
client.mas.delete("scorer_1_0")
```

It raises [`ViyaNotFoundError`][viyapy.ViyaNotFoundError] if the module doesn't
exist and [`ViyaConfigError`][viyapy.ViyaConfigError] for a blank `module_id`.

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
```

Pass `step=` to inspect a named step other than `execute`. `get_signature` raises
[`ViyaNotFoundError`][viyapy.ViyaNotFoundError] if the module or step doesn't
exist, [`ViyaConfigError`][viyapy.ViyaConfigError] for a blank `module_id`/`step`
(before any request), and [`ViyaResponseError`][viyapy.ViyaResponseError] if the
response isn't a usable signature.

## Validating inputs

Rather than compare names by hand, [`validate`][viyapy.mas.MASClient.validate]
fetches the signature and checks your inputs against it, raising
[`ViyaValidationError`][viyapy.ViyaValidationError] if a declared input is missing
or an undeclared one was supplied:

```python
try:
    client.mas.validate("api_tester1_0", {"input_string": "hi"})
except ViyaValidationError as err:
    err.missing      # names the step declares but you didn't supply
    err.unexpected   # names you supplied that the step doesn't declare
```

Only the *names* are checked, not the values or types — SAS Viya coerces numeric
types permissively, so a stricter type check would report false mismatches.
`validate` returns the fetched `StepSignature`, so you can reuse it. To validate
as part of executing (one call, at the cost of an extra round trip to fetch the
signature), pass `validate=True` to [`execute`](#execute-a-module):

```python
result = client.mas.execute("api_tester1_0", inputs, validate=True)
```

### Server-side validation

`validate` compares *names* locally. To have SAS Viya itself validate the payload
— including types and constraints — use
[`validate_remote`][viyapy.mas.MASClient.validate_remote], which POSTs the inputs
to the MAS validations endpoint and returns a typed
[`ValidationResult`][viyapy.ValidationResult]:

```python
result = client.mas.validate_remote("api_tester1_0", {"input_string": "hi"})
result.valid       # True — the server accepted the inputs
result.version     # the validation resource version, if reported
```

SAS reports an invalid payload as an HTTP 201 whose body says `valid: false` (not
as a 4xx error). By default `validate_remote` surfaces that as a
[`ViyaValidationError`][viyapy.ViyaValidationError] carrying the server's messages
on `.messages`. Pass `raise_on_invalid=False` to inspect the result yourself
instead:

```python
result = client.mas.validate_remote("api_tester1_0", inputs, raise_on_invalid=False)
if not result.valid:
    for message in result.messages:   # the server's violation messages
        print(message)
    result.error                      # the raw SAS error object, if present
```

Choose `validate` for a cheap, offline-ish name check (one signature fetch) and
`validate_remote` when you want the server's authoritative verdict (one POST, no
execution).

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

## Execution modes: synchronous, timed, and fire-and-forget

By default `execute` is **synchronous** — it waits for the run to finish and
returns the outputs. Passing `wait_time` (milliseconds) selects a different mode.
It maps to the server's `waitTime` and is distinct from `timeout`, which bounds
the HTTP call itself rather than the server-side wait:

```python
# Synchronous (default): wait for completion, get outputs.
result = client.mas.execute("api_tester1_0", inputs)
result.completed          # True

# Timed: wait up to 250 ms. If it finishes, you get outputs; if not, the run
# keeps going server-side but the call returns early with empty outputs.
result = client.mas.execute("api_tester1_0", inputs, wait_time=250)
if result.timed_out:
    ...                   # didn't finish in 250 ms; result.outputs is empty

# Fire-and-forget: return as soon as the inputs are accepted.
result = client.mas.submit("api_tester1_0", inputs)   # == execute(..., wait_time=0)
result.submitted          # True; result.outputs is empty
```

The three [`ExecutionResult`][viyapy.ExecutionResult] helpers — `completed`,
`timed_out`, and `submitted` — read the `execution_state` the server returned (`"completed"`, `"timedOut"`, `"submitted"`). Timed-out and
submitted responses legitimately carry no outputs, so those are parsed as an empty
mapping rather than an error.

`wait_time` must be a non-negative integer; anything else raises
[`ViyaConfigError`][viyapy.ViyaConfigError] before a request is issued. Note that
MAS has no per-execution result-polling endpoint, so a `submit` result's outputs
are not retrievable later — use fire-and-forget when you don't need them in-band.

## Inputs are built for you

Pass a plain `dict` of feature names to values. viyapy serializes it to the MAS
request body as JSON — values pass through unchanged, with **no** string
concatenation and **no** name-mangling (the 2.x helper's trailing-underscore bug
is gone). Quotes, newlines, and unicode in values are handled correctly.

## Binary inputs and outputs

Pass a `bytes` (or `bytearray`) value to send binary data. viyapy base64-encodes
it and marks the input with `encoding: "b64"` on the wire, which is how MAS
accepts binary — the target variable must be a `binary` or `any` type on the
server (a scalar type rejects a b64 value with a `400`). Binary **outputs** come
back the same way and are decoded for you back into `bytes`:

```python
result = client.mas.execute("image_scorer", {"photo": image_bytes})
result.outputs["thumbnail"]        # bytes — decoded from the server's base64
```

Scalar inputs and outputs alongside binary ones pass through unchanged. A binary
output whose value isn't valid base64 raises
[`ViyaResponseError`][viyapy.ViyaResponseError].

## Correlation metadata

Pass `client_id` and/or `transaction_id` to tag an execution for correlation
(e.g. tracing a request across systems, or grouping calls by client). They are
sent in the request's `metadata` object and echoed back on the result:

```python
result = client.mas.execute(
    "api_tester1_0", inputs, client_id="checkout-svc", transaction_id="order-42"
)
result.client_id        # "checkout-svc"
result.transaction_id   # "order-42"
```

Both are optional; when omitted, no `metadata` is sent. Each must be a non-empty
string when given, or [`ViyaConfigError`][viyapy.ViyaConfigError] is raised before
the request. `submit` accepts the same two arguments.

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
