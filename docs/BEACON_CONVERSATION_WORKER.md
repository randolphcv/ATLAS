# Beacon Conversation Worker

Updated: 2026-07-24

Status: implemented on `worker_build`; activation against the live catalog is
blocked until the current 500-item catalog-analysis job is terminal.

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

Only loopback HTTP endpoints are accepted. The default adapter makes two
structured local-model calls:

1. choose zero to four short catalog search queries;
2. answer from bounded conversation history and the returned catalog evidence.

Beacon supplies at most 20 recent messages, 24,000 conversation characters,
four search queries, and eight catalog results. Responses must fit the existing
8,000-character Desk limit. The model receives no file bytes and no
consequential tools.

## Grounded result cards

Each result card is linked to a permanent asset UUID and includes:

- display title and filename;
- current preferred catalog path;
- `atlas://asset/<uuid>` identity;
- the literal catalog query that matched it;
- current local-availability state;
- optional existing thumbnail.

**Inspect** opens the asset record in Library. It does not open, copy, or move
the source file. A future file-collection feature requires a separate typed,
checksum-verified retrieval job.

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

## Live activation gate

Do not launch source Beacon 0.17 or this worker against the live database until
the current analysis job is terminal. Then:

1. verify the job has no pending/running items;
2. confirm SQLite integrity and foreign keys;
3. create and hash a verified schema-13 online backup;
4. migrate the live database to schema 14;
5. run one synthetic/custom-catalog packaged smoke test;
6. queue one bounded live question and run the worker once;
7. inspect the response, result cards, run record, and audit event;
8. only then enable the watch loop.
