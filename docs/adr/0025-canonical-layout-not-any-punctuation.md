# ADR-0025: Canonical document layout, not any punctuation, bypasses the check digits

**Status:** Accepted
**Date:** 2026-09-10
**Deciders:** Carla Cury (found by the ADR-0024 validation run: the first
report to correlate traces quarantined on its own client IP)
**Decision style:** Bug fix, same family as ADR-0004 and ADR-0017.
**Related:** [[0003-pii-gate-from-first-commit]],
[[0004-pan-gate-scans-common-card-lengths-only]],
[[0015-quarantine-is-a-tracked-state]],
[[0017-pii-gate-validates-documents-not-digit-shapes]],
[[0024-investigation-correlates-logs-and-classifies-noise]]

## Context

ADR-0017 established that a document is PII if its check digits are real
*or* if it carries punctuation, because punctuation is a declaration of
intent — nobody writes `529.982.247-25` by accident. The implementation
read that as "the match contains a `.`, `-` or `/`":

```python
formatted = bool(re.search(r"[.\-/]", match.group()))
if formatted or validator(raw):
```

An IPv4 address whose octets run 3/3/3/2 digits puts dots exactly where a
CPF puts dots. `179.185.106.22` matched `_CPF_CANDIDATE`, counted as
"formatted", skipped the check digits, and was reported as a CPF hit.

This surfaced on the first run of the ADR-0024 prompt: the investigation
now correlates the error's whole trace, and a trace's root span carries
`http.client_ip`. The report cited the sample request's client IP, the gate
read it as a CPF, and a completed `$0.6337` investigation went to
`reports/.quarantine/`. Measured against the gate directly:

| Input | Before | After |
|---|---|---|
| `179.185.106.22` | `['cpf']` | `[]` |
| `200.155.201.10` | `['cpf']` | `[]` |
| `192.168.100.11` | `['cpf']` | `[]` |
| `529.982.247-25` (valid CPF) | `['cpf']` | `['cpf']` |
| `529.982.247-26` (canonical, bad check digit) | `['cpf']` | `['cpf']` |
| `52998224725` (bare, valid) | `['cpf']` | `['cpf']` |

Client IPs are not incidental to the new investigation shape — they are
part of what trace correlation is for (which caller, from where). So this
is the common case, not a corner one, and left alone it would quarantine
routine investigations for the rest of the phase.

## Decision

"Canonical punctuation" means the layout the document is actually written
in, matched whole:

- CPF — `^\d{3}\.\d{3}\.\d{3}-\d{2}$`
- CNPJ — `^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$`

`_document_hit()` takes that pattern alongside the candidate pattern. A run
in the canonical layout is PII regardless of its check digits, exactly as
ADR-0017 intended. A run written any other way — bare, space-separated,
dotted quad — still has to pass the real check-digit algorithm.

## Consequences

The gate keeps failing closed on what it is for: a real CPF or CNPJ trips
whether it is punctuated, bare or space-separated, and a canonically
written document trips even when its digits are made up.

What it no longer does is quarantine on dotted decimals. IPv4 is the case
that was measured, and it is the one that matters here, but the class is
wider — any three-then-two dotted decimal grouping was affected.

A CPF whose last separator is a dot rather than a hyphen
(`529.982.247.25`) no longer bypasses the check digits. It is still caught
when the digits are real, which is the case that carries actual personal
data; a made-up number written that way now passes. That is the deliberate
trade — the alternative costs a quarantined paid report on every client IP.

The two documented gaps from ADR-0003 are untouched: a person's proper
name, and a PAN inside a 20+ digit run. The mitigating practice is the one
ADR-0024 restated in the prompt — reference the query, never the content.
