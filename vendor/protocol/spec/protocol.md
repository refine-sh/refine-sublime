# Integration Protocol 1.0

Status: release candidate, not yet frozen as `v1.0.0`.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are to be interpreted as requirement levels. This document is
normative for framing, lexical JSON validity, state, ordering, semantics,
recovery, security, and limits. The JSON Schemas are normative for parsed JSON
shape, required members, primitive constraints, and discriminated unions.

## 1. Scope and roles

Integration Protocol 1.0 is the supported public wire between a writing-host
client and the Refine app. The client observes authoritative host source,
presents Refine-owned suggestions, forwards explicit actions, and performs an
atomic host mutation only when Refine sends an Apply request. Refine owns
writing-check policy, providers, prompts, scheduling, suggestions, entitlement,
and presentation settings.

The supported production profile is:

- macOS;
- one local OS user;
- Refine as the server and a writing host as the client;
- endpoint-descriptor schema 1 discovery;
- a Unix-domain stream socket (`AF_UNIX`); and
- Refine already running before discovery.

Network and loopback transports, cross-user access, sandbox escape mechanisms,
Windows, Linux, automatic Refine launch, and third-party production servers are
not supported. The MIT license does not prohibit experimental servers. The fake
server in this package is supported test tooling.

Integration Protocol version `1.0`, endpoint-descriptor schema `1`, Refine app
versions, client versions, and the internal suggestion identity namespace are
independent axes. Protocol 1.0 has no Protocol 2.5 alias and assigns no
compatible-minor meaning. A version pair other than exactly `1.0` is
incompatible.

## 2. Normative artifacts

- [`endpoint-descriptor.schema.json`](../schema/endpoint-descriptor.schema.json)
  governs discovery.
- [`handshake.schema.json`](../schema/handshake.schema.json) governs `hello`,
  `welcome`, and `rejected`.
- [`envelope.schema.json`](../schema/envelope.schema.json) governs connected
  command and event envelopes.
- [`command.schema.json`](../schema/command.schema.json),
  [`event.schema.json`](../schema/event.schema.json), and
  [`shared.schema.json`](../schema/shared.schema.json) govern payloads.
- [`capabilities.json`](../registry/capabilities.json) is the immutable base
  capability registry.

Unknown object members are deliberately accepted only after the complete value
passes the recursive portable JSON profile in Section 5. Unknown discriminators
and enum values are not. A conflict between prose, schema, or vectors is a
specification defect resolved as errata; vectors never override a normative
source and a tagged artifact is never silently changed.

## 3. Discovery and transport security

The descriptor path is:

```text
~/Library/Application Support/com.runjuu.refine/Integrations/endpoint.json
```

The containing directory MUST be owned by the current user and mode `0700`.
The ownership lock is the descriptor's sibling named exactly `owner.lock`. The
descriptor and `owner.lock` MUST exist, be regular files owned by that user, and
have mode exactly `0600`. Refine holds an exclusive advisory lock on
`owner.lock` while the descriptor is published, atomically replaces the
descriptor, and withdraws it before releasing ownership. A client MUST validate
the directory, `owner.lock`, and descriptor existence, file type, owner, and
mode before connecting. A client is not required to prove that Refine currently
holds the advisory lock; that fact is not a portable client-visible security
check.

The descriptor contains schema `version: 1`, an absolute `socketPath`, a
64-character uppercase hexadecimal `launchToken`, `serverEpoch`, exact
`protocolMajor: 1` and `protocolMinor: 0`, and `pid`. `protocolMinor` is
REQUIRED. PID is discovery metadata, not identity or authorization.

The socket MUST live in a random mode-`0700` runtime directory and be mode
`0600`. The server verifies the peer with `getpeereid`. The server validates the
peer UID and launch token before returning any typed diagnostic. A missing or
incorrect token closes silently.

These controls exclude other OS users and nonlocal peers. They do not defend
against another process already running as the same user. Client, host, and
frontend strings are self-reported labels and grant no authorization.

## 4. Framing

Each socket message is exactly one nonempty UTF-8 JSON object prefixed by a
four-byte unsigned big-endian payload length. The length counts only JSON
payload bytes and MUST be in `1...8_388_608`.

A zero-length frame, length over `8_388_608`, truncated payload, invalid UTF-8,
malformed JSON, or non-object root is invalid. Senders MUST serialize complete
frames. Receivers MAY read any number of bytes per system call and therefore
MUST buffer partial headers and payloads and MUST accept multiple frames in one
read.

Before `welcome`, an invalid frame closes silently unless an authenticated
version mismatch can be diagnosed. After `welcome`, the server sends a fatal
fault when it can safely frame and flush one; otherwise it closes. A client
receiving an invalid server frame closes because no reciprocal fault command
exists.

## 5. Portable JSON profile

JSON is interpreted with these additional REQUIRED rules. They are applied
recursively to the complete decoded value before schema validation and before
any unknown object member is ignored:

- object member order and insignificant whitespace are unrestricted;
- duplicate object keys at any depth are invalid;
- unknown object members are ignored only after their names and values pass
  this portable profile;
- unknown discriminators and enum values are invalid;
- required members must be present;
- `null` is invalid at every depth, including inside unknown members;
- strings contain Unicode scalar values and unpaired surrogate escapes are
  invalid;
- every numeric token uses nonnegative integer lexical form: a leading minus,
  fraction, or exponent is invalid even in an unknown member;
- every integer is in `0...9_007_199_254_740_991`, with schemas imposing
  narrower field limits; and
- no canonical serialization is required.

Optional values, including an unavailable Apply outcome's snapshot, are
represented by omitting the member rather than sending `null`.

Protocol versions are unsigned 16-bit integers. Connection sequences are
unsigned 32-bit integers. A JSON parser that normally loses duplicate-key or
numeric-token information MUST perform a lexical preflight before ordinary
decoding. The same profile applies to the endpoint descriptor.

## 6. Limits and identifiers

`welcome.limits` confirms fixed base limits; it does not negotiate them:

| Member | Exact value |
|---|---:|
| `maxFrameBytes` | `8_388_608` encoded JSON payload bytes |
| `maxSources` | `2` sources per snapshot |
| `maxSourceBytes` | `1_048_576` decoded UTF-8 bytes per source text |

Both source and frame limits apply. Two maximally escaped one-MiB sources are
not guaranteed to fit one frame. Connection, retained-run, TTL, queue, retry,
listener, scheduler, and shutdown bounds are implementation policy and MUST NOT
be inferred from this protocol.

A protocol identifier is a byte-exact, case-sensitive string of 1 through 128
bytes, with every byte in visible ASCII `0x21...0x7E`. It applies to client,
client-version, host, frontend, run, epoch, revision, source, check, suggestion,
command, action, transaction, cause/correlation, forced-language-tag, and
capability identifiers. Socket paths and human text are not identifiers.

The descriptor launch token has the stronger form `[0-9A-F]{64}`. Human source,
diff, explanation, display-name, and diagnostic text may use any valid Unicode
subject to field and frame limits.

Identity scopes are:

- `runId` is stable for one logical run across same-launch reconnects;
- command and action IDs are never reused during a run;
- check IDs are unique during a run;
- a revision names one immutable source state and is never rebound, including
  an A-B-A edit history;
- source IDs are unique in a snapshot and stable while the logical source
  exists;
- transaction IDs are generated by the server, unique during a run, and echoed
  by the corresponding receipt; and
- `serverEpoch` uniquely identifies one Refine launch.

## 7. Coordinates

Source and presentation coordinates are zero-based, half-open UTF-16 code-unit
ranges. `location + length` MUST be within the addressed source and MUST be
representable in the interoperable integer range. Each endpoint MUST fall on a
Unicode-scalar boundary; an endpoint MUST NOT split a surrogate pair. An
endpoint need not be an extended grapheme-cluster boundary.

Host adapters MAY expand visual selection or presentation to grapheme
boundaries. Coordinate conversion and Apply validation MUST accept every valid
scalar boundary.

## 8. Handshake

The client sends one `hello` within five seconds. Its required capability array
may be empty. The server first validates framing, UTF-8, object shape, duplicate
keys, and a bounded launch token. Only after authenticating the token does it
validate version, identity, host capabilities, run, and extension offers.

The server then sends one `welcome` or `rejected`. Opening the engine session
has its own five-second bound. `welcome.serverEpoch` MUST equal the descriptor
epoch. Both peers MUST report exact protocol `1.0`.

`welcome.runResumed` is true only when the same-launch coordinator and its
transaction deduplication state were retained. False is a normal first attach
or expired/evicted prior state.

An authenticated rejection has `reason`, machine-actionable `recovery`, and the
server's required `protocol`. `incompatibleProtocol` additionally includes the
client's `receivedProtocol` so diagnostics can report both exact pairs without
inferring update direction.

| Reason | Recovery | Meaning |
|---|---|---|
| `incompatibleProtocol` | `none` | Exact version pairs differ |
| `invalidClient` | `none` | Identity or declared host contract is invalid |
| `runUnavailable` | `newRun` | Retained state is bound to incompatible identity |
| `runUnavailable` | `retry` | Matching retained state is temporarily unavailable |
| `serverBusy` | `retry` | Authenticated admission capacity is unavailable |
| `engineUnavailable` | `retry` | An engine session cannot open yet |

Rejections contain no human message, token, client inventory, hidden limit, or
internal diagnostic. Same-UID failure, invalid token, malformed initial input,
or pre-authentication capacity exhaustion closes silently.

## 9. Capability negotiation

Extension `capabilities` differ from
`hostCapabilities.interceptableSuggestionActionKeys`, which describes required
base host behavior and is bound to retained run identity.

The `hello.capabilities` and `welcome.capabilities` negotiation arrays are
REQUIRED duplicate-free sets, order-insignificant, with at most 64 entries.
The published capability registry is append-only and has no 64-entry limit; its
IDs MUST be unique within a snapshot. `hello.capabilities` offers
client-supported extensions. Unknown offers are ignored. `welcome.capabilities`
is the subset present in the server's exact published registry snapshot,
implemented by the server, and offered by the client. A client MUST close if
the server activates an unoffered or unrecognized capability.

An empty activated set `[]` is complete Protocol 1.0 behavior. The current registry also offers the optional [suggestion shortcut capability](suggestion-shortcuts-v1.md). An
extension may add optional fields, messages, or behavior only after activation.
It cannot remove base messages, weaken validation or security, or make required behavior optional. Negotiated suggestion shortcuts may replace the standalone shortcut bindings as specified by suggestion-shortcuts.v1; all other base semantics remain unchanged. Registered identifiers use a
publisher-controlled reverse-domain namespace and end in `.vN`; Refine-owned
identifiers use `com.runjuu.refine.<feature>.vN`. Breaking semantics require a
new identifier.

## 10. Connected envelopes and sequencing

After `welcome`, clients send command envelopes and the server sends event
envelopes. Commands and events have independent connection-scoped sequences.
Each direction starts at 1 and increments by exactly 1 with no gap, duplicate,
zero, wrap, or reuse. Each event carries the current `serverEpoch`.

At sequence exhaustion the sender closes and reconnects instead of wrapping.
An invalid command sequence produces `fault(invalidSequence, fatal: true)` when
the server can write safely. An invalid event sequence makes the client close.

An event's optional `causeCommandId` correlates the event to a command; it is
not an acknowledgement and does not replace type-specific identity.

## 11. Document lifecycle and commands

A run has at most one open document. Legal client commands are:

- `openDocument`: opens an authoritative complete snapshot;
- `replaceDocument`: replaces it with a new authoritative complete snapshot;
- `updateAttention`: supplies advisory caret and visible ranges for a revision;
- `requestCheck`: requests a check, optionally scoped by source IDs or one
  selection and optionally forcing a language tag;
- `performAction`: explicitly requests Apply, Dismiss, Explain, or Report for a
  suggestion reference;
- `completeApply`: reports the host outcome for a server transaction; and
- `closeDocument`: closes document state.

Snapshots contain one or two unique sources with syntax `plainText`,
`markdownDocument`, `markdownDocumentHardLineBreaks`, or `latexDocument`. The
complete source is authoritative. Attention MAY reorder work that has not
started but MUST NOT narrow check coverage. `visibleRanges` is either empty or
contains nonempty ranges in ascending source-location order without overlap;
touching ranges are allowed. Selection coordinates address the full source, and
a check selection MUST be nonempty. A check intent MAY contain a nonempty
`sourceIds` set or one `selection`, but MUST NOT contain both. Omitting both
scopes the check to the complete snapshot. `forcedLanguageTag` is independent of
that scope.

A line ending is exactly U+000A, U+000D, or the U+000D U+000A pair. Every other
Unicode line or paragraph separator is an ordinary character under every source
syntax. Under `markdownDocument` and `latexDocument` the server MAY reflow
source line endings it has proven insignificant, so corrected text need not
preserve the original line layout.

`markdownDocumentHardLineBreaks` protects Markdown syntax exactly as
`markdownDocument` does, and parser-proven soft line endings remain logical
whitespace for checking, so prose wrapped across two source lines is still
checked as one logical paragraph. Its line endings are immovable: the server's
projection and Apply-plan materialization MUST reproduce every line ending at
the same source position, and MUST NOT remove one, introduce one, or place an
edit across one. A correction the server cannot materialize under that rule is
not published as a suggestion. The declaration is host-authoritative and per
source, and changing it changes the source revision even when the text is
unchanged.

Protocol 1.0 carries no feature discovery, so a client cannot ask whether a
server implements a declared syntax. A syntax the peer does not implement is an
unknown enum value, which is rejected at decode as a fatal `malformedMessage`
rather than degraded silently.

The server emits `documentAccepted` for an accepted revision or
`resyncRequired` with `documentNotOpen`, `conflictingRevision`,
`reusedRevision`, or `invalidDocument`. Resynchronization always uses a complete
snapshot.

Incremental changes, client-authored projections, and cross-launch sessions are
not part of Protocol 1.0.

## 12. Presentation, explanations, and actions

`presentationContentReplaced` replaces the complete presentation for its check.
Statuses are `pending`, `checking`, `complete`, `unavailable`, and `closed`.
Coverage is `full` or `partial`. Progress satisfies
`0 <= completedUnitCount <= totalUnitCount` and is present only while checking.

Suggestions carry source-local ranges, a complete diff, attribution, and the
currently available actions. Presentation appearance and interaction are owned
by Refine. Clients do not configure prompt, provider, model, language policy,
scheduling, appearance, interaction, or entitlement through the protocol.
Attribution language and model display names are nonempty strings.

`explanationReplaced` completely replaces explanation state with `started`,
`streaming`, `completed`, `stale`, or `unavailable`. An action ends with
`actionCompleted`, `actionRejected`, or the relevant explanation/apply flow.
Report is valid only as an explicit user action on a live suggestion and while
Refine feedback is enabled; it MUST NOT be submitted automatically.

## 13. Host-authoritative Apply

Apply is a two-message transaction:

1. Refine sends `applyRequested` with a server-generated transaction ID, exact
   expected revision, one source ID, and one or more edits.
2. The host validates the revision and every expected string, performs the
   whole source-local mutation atomically if possible, reads authoritative
   state back, and sends exactly one `completeApply` outcome.

Apply is whole-suggestion: no partial mutation is permitted. Edits MUST be
listed in strictly descending source-location order, without tied locations or
overlap, so applying them in listed order cannot shift a later edit's
coordinates. Every range endpoint MUST be scalar-boundary safe, and
`expectedText` MUST differ byte-for-byte from `replacement`; a no-op edit is
invalid. Outcomes are:

- `applied` with the authoritative resulting snapshot;
- `rejected` with `staleRevision` or `textMismatch` and a snapshot;
- `unsupported` with `readOnly` or `nonAtomic` and an optional snapshot;
- `unavailable` with an optional snapshot; or
- `indeterminate` with an optional snapshot.

The client deduplicates transaction IDs. A disconnect, timeout, or unknown
receipt MUST NEVER cause a host mutation to be retried.

## 14. Reconnect and receipt restoration

The server does not retain detached event bytes, expose a replay cursor, or
replay missed events. Both sequences restart at 1 after a new connection.

When `runResumed` is true, the client restores, in order:

1. pending Apply receipts under their original transaction IDs;
2. the newest complete source snapshot;
3. matching current attention; and
4. a still-pending explicit check bound to that snapshot.

When `runResumed` is false, the client discards receipts belonging to the lost
coordinator, accepts possible accounting undercount, and restores only snapshot,
attention, then pending check. It never turns a historical receipt into a new
transaction or acknowledged no-op.

`runUnavailable/newRun` causes the client to allocate a new run and clear lost
coordinator state. `runUnavailable/retry` retries the same run later.

## 15. Faults

After `welcome`, `fault.fatal` is authoritative. A fatal fault is best-effort
sequenced, flushed, and followed by close. A nonfatal fault leaves the session
usable. Clients MUST NOT infer severity from the code alone.

| Code | `fatal: false` | `fatal: true` |
|---|---|---|
| `invalidSequence` | never | gap, duplicate, zero, exhaustion, or reuse |
| `malformedMessage` | invalid reference when continuation is safe | schema, discriminator, or state violation |
| `resourceLimit` | one operation rejected safely | connection cannot continue within a mandatory bound |
| `internalError` | operation failed, state reliable | session state unreliable |
| `invalidDocument` | invalid revision, topology, range, or intent | never |
| `unsupportedSource` | unsupported syntax or language | never |
| `engineUnavailable` | recoverable engine/model outage | never |

`authenticationFailed` and `incompatibleProtocol` are not legal fault codes.
An unknown historical Apply receipt may use nonfatal `malformedMessage`; it
never causes another mutation. A client receiving an invalid event closes.

## 16. Identity, recognition, prompts, and entitlement

Third-party client IDs use a reverse-domain namespace. The `refine-*` namespace
is reserved for Refine-owned clients. These are contract and naming rules, not
authentication.

Refine may recognize an official self-reported tuple for product metadata.
Recognition is intentionally spoofable inside the same-user boundary and MUST
NOT authorize anything. A generic client receives the complete engine, global
custom prompts, generic display/activity, and the user's Refine entitlement and
provider configuration. It does not receive application-targeted prompt
matching, claimed-app foreground priority, or native-check conflict policy.

A client without a valid trial or license may remain connected but receives the
existing actionable `writingCheckEntitlementRequired` presentation state.

## 17. Privacy and compatibility

Complete source flows to Refine and may reach a configured cloud provider. A
local model keeps generation on the Mac. Credentials and raw Refine settings do
not cross the protocol.

Report may send original/revised snippets plus language, provider, model,
custom-instruction, Refine-version, and macOS-version context to Refine's
feedback service. That destination is separate from the writing-check provider.
The client owns disclosure and retention for its own processing.

Technical wire conformance, MIT permission, support eligibility, and the public
“Compatible with Refine Protocol 1.0” claim are distinct. Claim conditions are
defined in [`COMPATIBILITY-CLAIMS.md`](../COMPATIBILITY-CLAIMS.md).

## 18. Compatibility lifetime

Exact Protocol 1.0 is supported throughout Refine 1.x, with no additional
time-based guarantee. Tagged schemas and behavior are immutable. Nonbehavioral
errata may clarify the contract; behavior changes require a negotiated
capability or successor protocol.
