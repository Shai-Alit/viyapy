# TEMPORARY — reviewer smoke test. DO NOT MERGE.
#
# This file exists only to verify that both automated PR reviewers (Claude on
# Foundry + Codex on Foundry) fire on a same-repo PR and can post inline,
# line-anchored comments. It contains a few deliberate, minor issues that map to
# viyapy's own review rules so we can confirm the bots actually engage with the
# diff. Close this PR without merging once both reviews land.

import urllib.request


def fetch_status(url):
    # Deliberate issue 1: HTTP call with no timeout (viyapy requires timeouts).
    # Deliberate issue 2: missing type hints and docstring on a "public" helper.
    response = urllib.request.urlopen(url)
    return response.read()


def parse_count(payload):
    try:
        return int(payload["count"])
    except:  # Deliberate issue 3: bare except swallows everything.
        # Deliberate issue 4: returning None to signal failure.
        return None


def log_result(value):
    # Deliberate issue 5: print() instead of logging in library-style code.
    print("result:", value)
