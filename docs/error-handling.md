# Error Handling

viyapy never prints, never swallows exceptions, and never returns `None` to
signal failure. Every failure raises a typed [`ViyaError`][viyapy.ViyaError]
subclass, so you can catch as broadly or precisely as you like.

## The hierarchy

```
ViyaError                     # base — catch this to handle any library failure
├─ ViyaConfigError            # bad args (URL, token/auth, ids) — raised before any network call
├─ ViyaConnectionError        # DNS/refused/TLS failure
├─ ViyaTimeoutError           # connect or read timeout exhausted
├─ ViyaAPIError               # any non-2xx; carries status/code/details/correlation id
│  ├─ ViyaAuthError           # 401/403
│  ├─ ViyaNotFoundError       # 404
│  ├─ ViyaRateLimitError      # 429 — carries retry_after
│  └─ ViyaServerError         # 5xx
└─ ViyaResponseError          # 2xx but the body is malformed/unexpected
```

## Catching

```python
from viyapy import ViyaError, ViyaNotFoundError, ViyaRateLimitError

try:
    result = client.mas.execute("api_tester1_0", {"input_string": "x"})
except ViyaNotFoundError:
    ...  # the module or step does not exist
except ViyaRateLimitError as exc:
    wait = exc.retry_after       # seconds, normalized and bounded
except ViyaError as exc:
    logger.error("Viya call failed: %s", exc)  # the base class catches everything
```

## What the error carries

API errors ([`ViyaAPIError`][viyapy.ViyaAPIError] and its subclasses) carry the
HTTP status, the SAS Viya error envelope (`errorCode`, `details`, and a
`remediation` hint when present), a correlation id from the response headers when
the server provides one, and the request URL/method — so a single log line or bug
report is actionable without re-running.

Local errors carry their own context instead:
[`ViyaConfigError`][viyapy.ViyaConfigError] for invalid arguments (raised before
any network call), and [`ViyaResponseError`][viyapy.ViyaResponseError] for a 2xx
body that couldn't be parsed (it attaches the raw body).

## Timeouts and retries

- **Timeouts are mandatory** — a default of `(connect=5s, read=30s)`, overridable
  per client (`timeout=`) and per call. No request is ever issued without one.
- **Retries** use exponential backoff with jitter on connection errors and
  429/5xx, honoring a **bounded** `Retry-After` (a runaway server value can't
  hang the caller). GETs retry freely; POSTs (MAS execute) do not, unless you opt
  in with `retry_on_post=True`.

## Token redaction in logs

viyapy attaches a redacting filter to its logger that scrubs any `Bearer <token>`
pattern from log records (including nested mapping/sequence/set/bytes arguments)
before any application handler emits them — defense in depth on top of the fact
that the library does not log the token itself.
