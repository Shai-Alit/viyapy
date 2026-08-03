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
    wait = exc.retry_after       # the server's Retry-After in seconds, or None
except ViyaError as exc:
    logger.error("Viya call failed: %s", exc)  # the base class catches everything
```

## What the error carries

API errors ([`ViyaAPIError`][viyapy.ViyaAPIError] and its subclasses) carry the
HTTP status, the SAS Viya error envelope (`errorCode`, `details`, and a
`remediation` hint when present), a correlation id from the response headers when
the server provides one, and the request URL/method — all as attributes
(`exc.status_code`, `exc.viya_error_code`, `exc.details`, `exc.remediation`,
`exc.correlation_id`, `exc.url`, `exc.method`). `str(exc)` includes the message,
status, error code, and correlation id; log the other attributes explicitly if
you need them in the line.

Local errors carry their own context instead:
[`ViyaConfigError`][viyapy.ViyaConfigError] for invalid arguments (raised before
any network call), and [`ViyaResponseError`][viyapy.ViyaResponseError] for a 2xx
body that couldn't be parsed (it attaches the raw body).

## Timeouts and retries

- **Timeouts are mandatory** — a default of `(connect=5s, read=30s)`, overridable
  per client (`timeout=`) and per call. No request is ever issued without one.
- **Retries** use a configurable budget (`max_retries`) with exponential backoff
  and jitter on connection errors and 429/5xx. The internal retry **sleep** honors
  `Retry-After` but is **bounded**, so a runaway server value can't hang the
  caller. Idempotent GETs use the retry budget; POSTs (MAS execute) are **not**
  retried by default — opt in with `retry_on_post=True`, accepting the risk of
  executing a decision twice. Note the raw server value exposed on
  `ViyaRateLimitError.retry_after` is *not* capped (it may also be `None`), so
  apply your own sanity limit before sleeping on it.

## Token redaction in logs

viyapy attaches a redacting filter to its logger that scrubs any `Bearer <token>`
pattern from log records (including nested mapping/sequence/set/bytes arguments)
before any application handler emits them — defense in depth on top of the fact
that the library does not log the token itself.
