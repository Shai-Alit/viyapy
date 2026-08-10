# Getting Started

## Install

```bash
pip install viyapy
```

viyapy requires Python 3.10 or newer.

## Your first call

Create a [`ViyaClient`][viyapy.ViyaClient] with your deployment URL and an OAuth2
bearer token, then use the `decisions` and `mas` operation groups:

```python
import os

from viyapy import ViyaClient

my_token = os.environ["VIYA_TOKEN"]

with ViyaClient("https://viya.example.com", token=my_token) as client:
    # Inspect a decision flow and its models
    decision = client.decisions.get("my-decision-id")
    for model in decision.models:
        print(model.name, model.modified_by)

    # Execute a published decision's MAS module against a feature dict
    result = client.mas.execute("api_tester1_0", {"input_string": "this is a test"})
    print(result.outputs["output_string"])
```

Using the client as a context manager (`with ViyaClient(...) as client:`) closes
the underlying HTTP session on exit. You can also call `client.close()`.

## Choosing the Viya generation

The client targets **Viya 4** by default. For a **Viya 3.5** deployment, pass
`viya_version`:

```python
client = ViyaClient("https://viya.example.com", token=my_token, viya_version="3.5")
```

The dialect layer handles the endpoint, media-type, and response-shape
differences (including the MAS `output` vs `outputs` key) so your code stays the
same across generations. See [Authentication](authentication.md) next.
