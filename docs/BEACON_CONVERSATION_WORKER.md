# Beacon Conversation Worker

Updated: 2026-07-24

Status: Beacon 0.18.0/schema 15 is live.

## Purpose

The conversation worker consumes durable `queued_for_beacon` Desk threads,
uses a separately managed local Ollama model, performs bounded read-only catalog
search, and appends a grounded Beacon response. It never receives a generic
filesystem tool and cannot copy, move, rename, delete, upload, or share files.

## Durable lifecycle

Schema 14 adds:

- `beacon_worker_runs` for worker identity, model/endpoint provenance, durable
  claims, lease expiry, success, and failure;
- `beacon_message_assets` for ranked asset IDs, match reasons, and the path
  observed when a grounded result was produced.

Claims use an immediate SQLite transaction. A second worker cannot claim the
same thread while the first lease is active. Failed runs leave the thread
queued and receive a five-minute durable retry backoff. Expired leases can be
recovered by another worker.

The worker pauses before migration or claim whenever a live catalog-analysis
job is running. This prevents the new schema or conversation inference from
interfering with an older packaged runner.

## Local model boundary

Only loopback HTTP endpoints are accepted. Beacon no longer routes
conversation through fixed search-trigger phrases. Qwen first formalizes the
active human goal from conversation context: catalog need, count, media type,
constraints, and whether the turn corrects an earlier misunderstanding. That
model-authored goal remains stable during a bounded agent loop.

Qwen can then choose among two read-only tools:

1. `search_catalog`, with model-selected literal queries, media type,
   any/all matching, and candidate depth;
2. `inspect_assets`, for richer metadata, accepted contextual analysis, and
   checksum-bound transcript/music context on assets already observed.

Qwen may search, inspect, broaden, narrow, or ask a focused question. A final
focused Qwen pass selects the exact observed asset IDs and writes the response.
Code does not reinterpret ordinary language or substitute a prewritten answer.
It enforces only the model-authored count/media goal and hard safety/grounding
rules.

For exploratory `any` searches, query buckets and likely filename series are
interleaved. `potential_series_hint` warns Qwen about adjacent captures; it is
evidence for the model, not an automatic duplicate decision. Perceptual
near-duplicate detection remains a future analysis capability.

Beacon supplies at most 20 recent messages, 20,000 conversation characters,
six search queries, sixteen candidates, eight inspections/result cards, and
six agent steps. Local inference uses a 16K context window with one retry for
malformed structured output. Responses must fit the existing 8,000-character
Desk limit.

The hard boundaries remain:

- no non-loopback model endpoint;
- no generic filesystem, cloud, or mutation tool;
- no result card for an asset Qwen did not first observe through a catalog
  tool;
- no ordinary result from known live test/sandbox paths;
- no conversation inference while catalog analysis owns the local model lane.

## Grounded result cards

Each result card is linked to a permanent asset UUID and includes:

- display title and filename;
- current preferred catalog path;
- `atlas://asset/<uuid>` identity;
- the literal catalog query that matched it;
- current local-availability state;
- optional existing thumbnail.

The final Qwen composition identifies the permanent asset IDs it actually
used. Only previously observed IDs become durable cards; unused candidates and
invented IDs are rejected.

**Inspect** opens the asset record in Library. It does not open, copy, or move
the source file. A future file-collection feature requires a separate typed,
checksum-verified retrieval job.

## Correction memory

Qwen decides whether the latest human turn actually corrects the immediately
preceding Beacon response. When it does, schema 15 retains that human wording
with both message identities. The most recent thread corrections remain
available even after ordinary bounded history would drop the original
exchange.

Correction memory is deliberately thread-scoped. Beacon does not promote one
misunderstanding into a global search rule, rewrite catalog metadata, or train
model weights automatically. A later reviewed-policy feature can promote
repeated corrections explicitly.

## Native and CLI entry points

The expanded shell exposes **Run Beacon** for one queued thread when:

- the local model is available;
- a thread is queued;
- no conversation worker is active;
- catalog analysis is not running.

For a deliberate foreground worker after schema-14 activation:

```powershell
.\.venv\Scripts\python.exe -m beacon.cli conversation-worker `
  --db C:\ProgramData\ATLAS\Beacon\beacon.db `
  --model qwen2.5vl:7b `
  --watch
```

The watch loop polls every five seconds by default and remains inference-idle
when no conversation is queued.

## Live activation result

Beacon 0.18.0 activation completed on 2026-07-24:

1. job `d020d54c-b39a-42eb-b9d9-6b8cb800b29f` finished 500/500;
2. schema-13 integrity and foreign keys passed;
3. a verified, SHA-256-hashed schema-13 online backup was retained;
4. the live catalog migrated once to schema 14;
5. all 87 acceptance tests and the isolated packaged smoke test passed;
6. real-Qwen isolated acceptance passed exact person retrieval, explicit
   no-search conversation, and three distinct food-image selection;
7. the live 0.18.0 worker returned three distinct series/scenes with exactly
   three cards, then the acceptance thread was resolved;
8. model goal/tool steps, worker run, message/card links, and audit events
   persisted;
9. post-run integrity remained `ok` with zero foreign-key errors.
