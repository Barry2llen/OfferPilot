# Native asynchronous chat runs

## Ownership

ChatRunManager owns one Task per active run and one FIFO queue per conversation.
At most one run writes a conversation checkpoint. SSE subscribers do not own the
Task. The application lifespan cancels and awaits chat runs before disposing DB
engines. InteractionBroker stores process-local Futures, registered before an
input event is published. Runtime tool injection carries the scoped interaction
port; a task-local context binding propagates the same port into child workflows.
Neither mechanism writes execution objects into graph state.

## HTTP contract

- POST `/ai/chat/runs`: existing JSON/multipart prompt fields; optional
  `Idempotency-Key` header (clients should always supply it); returns 202.
- GET `/ai/chat/runs?thread_id=...`: ordered submissions and pending inputs.
- GET `/ai/chat/runs/{run_id}`: current or persisted terminal state.
- GET `/ai/chat/runs/{run_id}/events?after=N`: SSE replay after N; zero or an
  expired watermark returns a `snapshot` with current events/pending inputs.
- POST `/ai/chat/runs/{run_id}/inputs/{request_id}`: `answer` object containing
  query `choice`/optional `note`, or error retry `type=retry`.
- POST `/ai/chat/runs/{run_id}/cancel`: idempotent cancellation; waits for cleanup.

An answer returns 200, including identical repeats. Conflicting repeats return
409; missing, expired or cancelled inputs return 410; invalid answers return 422.
Queue capacity returns 429. Legacy stream query/retry commands return 410.
All new public fields are documented in OpenAPI. User-facing known errors use
the request locale; a running interaction retains its submission locale.

## Events and frontend reconciliation

Events carry application `run_id`, `thread_id` and monotonic `event_id`. Tool
start/end/error carry `tool_call_id`; interaction events also carry an independent
`request_id`, supporting multiple questions per call and reverse-order answers.
A snapshot replaces the current display at its watermark, then live events with
higher IDs are applied. The human `message_id` separates committed history before
this run from its live projection. Tokens are coalesced in the display snapshot.
Slow subscribers are detached; replay is bounded by both bytes and event count.
Terminated in-memory runs expire after the configured retention; persisted status
and checkpoint history remain available. No credential fields enter run records.

## Queue, cancellation and restart

New submissions are accepted while another run waits. Success, failure and
cancellation start the next item after cleanup. Cancelling one item does not
cancel its successors; the UI offers a separate action for queued items.
User input has no default timeout; configured expiry fails the run, never
substitutes an answer. Waiting runs count against the active-run limit.

The graph's tool batch still checkpoints only after all tools finish. During
termination, the manager merges known completed results, inserts error results
for unfinished calls, and completes the Supervisor parent node to discard the
old child continuation. A failed finalization blocks that conversation and fails
its queue. The next submission must not replay the abandoned tool batch.

At startup, formerly running/waiting records become interrupted and queued
records become cancelled. Old checkpoint continuations are not resumed. When
new input arrives, unknown tool results are explicitly finalized as unknown;
existing messages remain visible. Persisting a run record does not restore a
Python coroutine. External side effects may already have happened and are not
rolled back. Multi-worker operation is unsupported.

## Validation

Python typing uses the root `pyrightconfig.json` with `typeCheckingMode: basic`
and Python 3.13. Pyright is installed by `uv sync` as a development dependency.
To check all currently modified/new Python files from root PowerShell:

```powershell
$files = @(git diff --name-only --diff-filter=ACMR -- '*.py') + @(git ls-files --others --exclude-standard -- '*.py')
uv run --project backend pyright -p pyrightconfig.json @files
```

Running the same command without file arguments checks the entire backend,
including existing modules and tests outside this change.

`test_chat_runs.py` covers Broker timing/idempotency, concurrent input, FIFO,
restart marking, disconnect/slow subscriber behavior, actual nested LangGraph
cancellation and real HTTP answer submission. Database tests cover SQLite and
PostgreSQL DDL compilation; a live PostgreSQL server requires separate testing.
