# Security Policy

## Supported versions

viyapy is pre-1.0-of-the-3.x-line during development; security fixes target the
latest released version on the 3.x line.

| Version | Supported |
|---|---|
| 3.x (latest) | ✅ |
| 2.x and older | ❌ |

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately:

- Use GitHub's **[private vulnerability reporting](https://github.com/Shai-Alit/viyapy/security/advisories/new)**
  ("Report a vulnerability" under the repository's **Security** tab), or
- email **psuaerofighter@gmail.com** with details.

Please include a description of the issue, steps to reproduce, the affected
version, and any potential impact. You'll get an acknowledgement as soon as
possible, and we'll keep you informed as a fix is developed and released.

## Handling of secrets

viyapy never persists tokens and never writes the bearer token to its logs or
`repr`; a redaction filter scrubs `Bearer <token>` patterns from log records as a
backstop. If you find a path where a token could leak, please report it via the
private channels above.
