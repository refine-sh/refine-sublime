# Conformance runner

The runner is a dependency-free Python 3.9 CLI. Its public interface is:

```text
python3 runner/conformance.py [--root ARTIFACT] verify
python3 runner/conformance.py [--root ARTIFACT] socket \
  [--scenario SCENARIO_ID] --client COMMAND [ARGUMENT ...]
python3 runner/conformance.py [--root ARTIFACT] server \
  [--scenario SCENARIO_ID] --adapter COMMAND [ARGUMENT ...]
```

`--client` and `--adapter` consume the remainder of the command line so adapter
arguments may begin with `-`; either one MUST be the final runner option.
`socket --client` appends:

```text
--descriptor /absolute/path/to/endpoint.json --scenario SCENARIO_ID
```

For example, an editor adapter may be invoked as:

```sh
python3 runner/conformance.py socket --scenario golden-writing-session \
  --client nvim --clean --headless -u NONE -l path/to/adapter.lua
```

## Machine-readable output

On success, `verify` writes exactly one JSON object and a newline to standard
output:

```json
{"artifactDigest":"…","baseArtifactDigest":"…","capabilityRegistryDigest":"…","frameVectors":0,"jsonNegative":0,"jsonPositive":0,"protocol":{"major":1,"minor":0},"stateVectors":0,"status":"ok"}
```

The counts above are illustrative. On success, `socket` writes exactly:

```json
{"scenario":"SCENARIO_ID","status":"ok","transport":"AF_UNIX"}
```

Failures are nonzero and diagnostic text goes to standard error. Automation
MUST parse the JSON object rather than depend on object-member order.

A successful `server` invocation adds `"role":"server"` to the `socket`
result shape.

## Language-neutral scenario adapter

`socket` creates a private mode-`0700` directory and a real Unix-domain socket.
Beside the descriptor it creates a regular, current-user, mode-`0600`
`owner.lock` and holds an exclusive advisory lock for the test. The client MUST
validate the directory, lock, descriptor, and socket metadata required by the
protocol; client conformance does not require proving that another process
currently holds the advisory lock.

The selected `vectors/state/SCENARIO_ID.json` is the adapter script:

- one adapter process handles every `connections[]` entry in order, opening one
  fresh socket connection per entry;
- a step contains exactly one inline `message`, a `messageRef` into the vector's
  `messages` object, `rawFrameHex`, or `close: true`;
- `${launchToken}` and `${serverEpoch}` are replaced with that runner launch's
  descriptor values before exact message comparison;
- a `client` message is sent by the adapter and compared by the fake peer;
- a `server` message or `rawFrameHex` is sent by the fake peer and validated by
  the adapter;
- `invalid` on a server message requires the adapter to reject that typed
  envelope and close, just as `rawFrameHex` requires strict frame rejection;
- `{ "direction": "client", "close": true }` requires the adapter to close;
  the corresponding `server` form means the fake peer closes; and
- `expectedOutcome`, `sequenceStarts`, `exhaustsSequence`, and `restore` annotate
  the behavior the adapter must demonstrate; they are not wire members.

After satisfying every connection, the adapter MUST exit zero and its complete
standard output MUST be the single JSON value below, optionally followed by one
newline. Adapter diagnostics belong on standard error.

```json
{"status":"ok","scenario":"SCENARIO_ID"}
```

The socket-runnable scenarios are:

| Scenario | Required behavior |
|---|---|
| `base-handshake` | Discovery, authenticated welcome, one command/event exchange |
| `golden-writing-session` | Snapshot, attention, scoped check, actions, Report, Apply, receipt, close |
| `typed-rejections` | Every legal rejection reason/recovery union branch |
| `fatal-fault` | Fatal fault validation, flush, terminal close |
| `reconnect-resumed` | Retained-run receipt/snapshot/attention/check restoration |
| `reconnect-lost-state` | Lost-run snapshot/attention/check restoration without receipt replay |
| `sequence-exhaustion` | Send `UInt32.max`, close, reconnect, restart at one |
| `invalid-server-inputs` | Reject duplicate-key and zero-length frames and close |
| `markdown-hard-line-breaks` | Hard-line-break Markdown snapshot, check, Apply, receipt preserving every line ending |

The fake peer compares messages with the vector and fails on the first mismatch.
It never prints the launch token or source payloads. It is test tooling, not a
supported production Refine server.

## Production-server adapter

`server` is the language-neutral seam for an implementation repository's own
self-driving black-box harness:

```sh
python3 runner/conformance.py server --scenario golden-writing-session \
  --adapter /absolute/path/to/run-server-conformance --adapter-specific-flag
```

The runner validates the scenario, creates a current-user mode-`0700` temporary
descriptor directory, and appends these arguments to the adapter command:

```text
--scenario SCENARIO_ID --descriptor-dir /absolute/private/directory
```

The adapter MUST use that directory for endpoint publication, launch and stop
the production server, and drive its own real `AF_UNIX` client through the
selected state scenario. It owns deterministic engine/test configuration and
wire assertions because those are implementation-specific harness concerns.
Before success it MUST stop the server and remove every file it created inside
the runner-owned descriptor directory. It leaves the directory itself in
place.

The adapter exits nonzero on the first failure, writes diagnostics only to
standard error, and writes exactly one success JSON value to standard output:

```json
{"status":"ok","scenario":"SCENARIO_ID"}
```

The runner rejects extra result members, output noise, a mismatched scenario,
nonzero exit, timeout, or leftover descriptor artifacts. This mode complements
the runner-driven fake peer; it does not turn a production server into a public
third-party server profile.

## Artifact maintenance

`verify` checks manifest completeness and digests, strict JSON lexical rules,
schemas, semantic rules, framed-byte vectors, state transcripts, and the exact
manifest inventories of every vector/scenario ID. Run
`python3 runner/update_manifest.py` after intentionally changing a release
artifact. A digest change is reviewable protocol-package work; consumers should
vendor the resulting manifest and exact files.
