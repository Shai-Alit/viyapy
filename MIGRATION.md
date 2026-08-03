# Migrating from viyapy 2.x to 3.x

viyapy 3.x replaces the flat helper functions in `viyapy.viya_utils` with a
single, hardened `ViyaClient`. The client adds mandatory timeouts, retries with
backoff, a typed exception hierarchy, token redaction in logs/`repr`, and a
version/dialect layer that handles SAS Viya 3.5 vs Viya 4 differences (including
the MAS `output` vs `outputs` response-shape pitfall) for you.

## Deprecation timeline

- **3.x** — `viyapy.viya_utils` still works but emits a `DeprecationWarning` on
  import. `viyapy.compat` provides same-signature drop-ins that also warn and
  delegate to `ViyaClient`.
- **4.0** — `viyapy.viya_utils` and `viyapy.compat` are removed. Only the
  `ViyaClient` API remains.

Run your test suite with `-W error::DeprecationWarning` to surface every call
site that still uses the legacy API.

## The one behavior change to know about

The 2.x `gen_viya_inputs` appended a trailing underscore to every input name
(`{"name": "amount_", ...}`). That was a bug: it does not match the feature
names MAS expects. The 3.x `build_inputs` (and everything built on it) sends the
names **unchanged**. If any downstream module was silently relying on the
mangled names, update the module's input signature to the real names.

## Function-by-function mapping

Set up the client once and reuse it:

```python
from viyapy import ViyaClient

client = ViyaClient("https://viya.example.com", access_token, viya_version="4")
# viya_version defaults to "4"; pass "3.5" for a Viya 3.5 deployment.
```

### `get_decision_content(base_url, decision_id, token)`

```python
# 2.x
raw = get_decision_content(base_url, decision_id, token)

# 3.x — raw payload still available on .raw
decision = client.decisions.get(decision_id)
raw = decision.raw
# ...or use the typed object directly:
decision.name          # flow name
decision.models        # tuple[ModelStep, ...]
```

### `get_models(base_url, decision_id, token)`

```python
# 2.x — returned list of {"Model Name", "Modified By", "Modified Timestamp"}
models = get_models(base_url, decision_id, token)

# 3.x — typed ModelStep objects
for m in client.decisions.list_models(decision_id):
    m.name, m.modified_by, m.modified_timestamp
```

### `gen_viya_inputs(feature_dict)`

```python
# 2.x — returned a JSON string with mangled names
body = gen_viya_inputs({"amount": 1000})

# 3.x — usually unnecessary; mas.execute builds the body for you.
# If you need the body explicitly (note: a dict, not a string; no mangling):
from viyapy.dialects import Viya4Dialect
body = Viya4Dialect().build_inputs({"amount": 1000})
```

### `call_id_api(base_url, token, feature_dict, module_id)`

```python
# 2.x — returned the raw MAS response dict
resp = call_id_api(base_url, token, {"amount": 1000}, module_id)

# 3.x
result = client.mas.execute(module_id, {"amount": 1000})
result.outputs          # {name: value}, dialect-aware
result.execution_state
result.raw              # the raw response dict, if you still need it
```

### `unpack_viya_outputs(response)`

```python
# 2.x
outputs = unpack_viya_outputs(resp)

# 3.x — already flattened on the result
outputs = client.mas.execute(module_id, inputs).outputs
```

## Minimal-edit bridge

If you cannot refactor immediately, switch the import to `viyapy.compat`. The
signatures are identical, the return shapes match 2.x, and each call warns and
routes through the modern surface — `ViyaClient` for the HTTP-backed helpers,
and the dialect layer for the pure `gen_viya_inputs` body builder (so you get
the fixes, including no name-mangling):

```python
# from viyapy.viya_utils import get_models, call_id_api
from viyapy.compat import get_models, call_id_api
```

This is a stepping stone, not a destination — `viyapy.compat` is removed in 4.0
alongside `viyapy.viya_utils`.
