# Capability registry

[`capabilities.json`](capabilities.json) is the immutable registry snapshot for
this Protocol 1.0 release candidate. An activated capability set of `[]` is the
complete base protocol. Optional capabilities have separately hashed
specifications:

- [suggestion-shortcuts.v1](../spec/suggestion-shortcuts-v1.md) defines negotiated
  shortcut combinations;
- [suggestion-shortcuts.v2](../spec/suggestion-shortcuts-v2.md) adds modifier gestures;
- [standalone-modifier-shortcuts.v1](../spec/standalone-modifier-shortcuts-v1.md)
  defines the standalone modifier bridge;
- [check-diagnostics.v1](../spec/check-diagnostics-v1.md) identifies unchecked
  passages in partial results without carrying source text; and
- [wavy-underline-highlight.v1](../spec/wavy-underline-highlight-v1.md) adds the
  `wavyUnderline` highlight style, with an `underline` fallback for base clients.

Future entries are append-only, immutable, versioned identifiers in a
publisher-controlled reverse-domain namespace, ending in `.vN`; Refine-owned
entries use `com.runjuu.refine.<feature>.vN`. Every ID occurs at most once in a
registry snapshot and has a separately published, digest-bound specification.
The registry itself has no 64-entry limit; that limit applies to each
connection's negotiation arrays. An implementation activates only capabilities
in the exact registry snapshot it vendors and implements. Unknown or private
offers are ignored and never echoed.
