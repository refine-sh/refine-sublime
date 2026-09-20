# Refine for Sublime Text

Grammar, spelling, and fluency suggestions in Sublime Text, powered by the
Refine app on your Mac. This is the development version (0.2.0).

## Requirements

- Sublime Text 4 on macOS (build 4107 or newer).
- Refine for Mac running and configured, with Integration Protocol 1.0 support.
- For exclusive ownership of native writing checks inside Sublime, use a Refine
  build containing the `refine-sublime` / `sublime` host registration.

The plugin uses Sublime's bundled Python. No pip packages, Node, helper executable,
or separately installed Python are needed to use it. Python 3 is needed only for
development commands below.

## Install from this checkout

In Sublime, choose **Preferences → Browse Packages…**. Create a `Refine` symlink
inside that Packages folder pointing to this checkout. For the standard macOS path:

```sh
mkdir -p "$HOME/Library/Application Support/Sublime Text/Packages"
ln -s "$HOME/code/refine-sublime" "$HOME/Library/Application Support/Sublime Text/Packages/Refine"
```

If `Refine` already exists there, inspect it before replacing it. Restart Sublime
if it was already running. Open Refine for Mac yourself; the plugin never launches
it automatically.

Alternatively, run `python3 scripts/package.py`, then copy
`dist/Refine.sublime-package` into Sublime's **Installed Packages** folder. Use
one installation method at a time. The ZIP package loads its bundled schemas
through Sublime's resource API and works without unpacking.

## Use

Open a Markdown or plain-text buffer. Only the active supported buffer is checked;
unsaved buffers work too. Refine controls automatic checks, models, and languages.
Changing text sends a complete snapshot to the local app. Selecting a different
supported buffer switches the integration to that buffer.

- Hover over marked text, or run **Refine: Show Suggestion** at the caret.
- Review the diff and choose **Apply**, **Dismiss**, or **Explain** when available.
  Busy actions cannot be submitted twice. Reports show confirmation, and failed
  actions show feedback with retry controls.
- Explanations show their own model, language, and reading direction. Headings,
  paragraphs, lists, bold/italic text, and code are formatted. Other Markdown
  remains plain text; raw HTML, images, and clickable links are not rendered.
- Run **Refine: Next Suggestion** / **Previous Suggestion** to navigate.
- Run **Refine: Check Writing** for a manual check. A single selection scopes the
  check; an empty selection checks the full buffer. Multiple selections are rejected.
- **Refine: Connection Status** shows the current state. **Refine: Reconnect**
  starts a fresh session if you need to reset it.

Apply validates the current revision and every expected string, then performs one
native, undoable buffer replacement. **Undo** restores the original text. Changes
made while a check is running invalidate its old suggestions. Markdown uses the
protocol's hard-line-break syntax to preserve source line layout.

The status bar shows connection state, progress, and suggestion count. A `selection`
label indicates partial coverage. Refine reconnects automatically after a restart.

## Keyboard bindings and appearance

Apply and Dismiss follow regular key combinations configured in Refine.
Standalone modifier keys (including Left Shift), modifier chords, and double-tap
gestures are unavailable; the popup explains this without substituting a key.
Choose a regular combination in Refine or use the popup/Command Palette actions.

The native modifier listener was removed after a crash in Sublime's bundled
ARM64 Python 3.8 when macOS invoked its ctypes callback. The plugin uses Sublime
key bindings and does not install native event callbacks.

Cursor activation highlights the active changes. The “Show Tip and Highlight”
setting also displays an inline shortcut tip; “Highlight Changes” omits the tip.

An open suggestion card owns Apply and Dismiss. Without a card, Quick Apply must
be enabled in Refine and the caret must be inside a current suggestion. In that
case Escape (or your configured Dismiss key) cancels the quick activation without
dismissing the suggestion. Move the caret to activate it again. Outside those
contexts keys retain their editor behavior. Autocomplete, overlays, and editor
panels take precedence over regular suggestion key bindings.

You can add explicit commands through **Preferences → Key Bindings**, for example:

```json
[
  { "keys": ["super+alt+g"], "command": "refine_check" },
  { "keys": ["super+alt+]"], "command": "refine_next" },
  { "keys": ["super+alt+["], "command": "refine_next", "args": { "forward": false } },
  { "keys": ["super+alt+enter"], "command": "refine_action", "args": { "kind": "apply" } }
]
```

Diff colors, hidden-whitespace display, and highlight style follow Refine's
presentation settings. Inline region colors use Sublime's theme scopes
`region.redish`, `region.bluish`, and `region.purplish`; exact custom Refine
highlight colors are not mapped to a generated color scheme in this version.
To disable this integration for a buffer or project, set `"refine_enabled": false`
in its settings and switch away from and back to that buffer.

## Privacy

The plugin sends the complete active supported buffer, including unsaved text,
to the running Refine app over an authenticated same-user Unix-domain socket.
It reads the endpoint descriptor and ownership metadata at
`~/Library/Application Support/com.runjuu.refine/Integrations/` and the socket's
metadata. The launch token is kept in memory. It sends no filenames or paths as
document identity.

With a downloaded local model, checking stays on your Mac. If you configure a
hosted provider in Refine, the app may send the source to that provider.

**Report** is available only when Refine offers it, and only an explicit click or
**Refine: Report Suggestion** command sends that action. Refine may then send
original/revised excerpts and language, model, provider, instruction, app-version,
and macOS context to its feedback service. Reports are never automatic.

The plugin makes no direct internet requests, sends no telemetry, and does not
persist source, suggestions, explanations, or credentials. In-memory document and
transaction state lasts for the active integration session. Sublime and other
plugins have their own persistence behavior, including unsaved-buffer recovery.

## Development

```sh
python3 scripts/verify.py
python3 scripts/package.py
```

Verification includes host-contract tests, the vendored positive/negative JSON
vectors, and nine base-protocol scenarios against the upstream fake server over
real temporary Unix sockets. These tests require permission to bind local sockets.
The socket adapter exercises the production transport; editor doubles exercise
revision handling, Apply, reconnect receipt ordering, and presentation separately.
They do not substitute for running Sublime itself.

Manual smoke test before release:

1. Install the plugin, start Refine, and open Markdown containing `😀 She go home.`.
2. Check writing; verify an underline, hover popup, readable diff, and status.
3. Apply a correction and undo it once; verify the entire correction is undone.
4. Edit while checking, then try an old popup; verify it cannot change the new text.
5. Request an explanation and navigate between suggestions with commands.
6. Switch tabs, open a clone in another group, and close views; verify marks belong
   to the active buffer and the Command Palette does not disconnect the session.
7. Restart Refine; verify reconnection, no repeated edit, and accurate status.
8. Disable automatic checks in Refine and verify typing alone does not request a
   manual check. Check a selection explicitly.
9. Try CRLF, emoji, combining characters, read-only buffers, and a buffer over 1 MiB.
10. Configure Left Shift for Apply and Escape for Dismiss. Verify the popup marks
    Left Shift unavailable, the Apply button still works, and Escape dismisses the
    open card. Then configure Option+Right for Apply and verify that combination.
11. With the companion Refine app change, verify Sublime's plugin owns its native
    checks while Obsidian and unrelated applications retain their own behavior.

The current scope excludes code-comment extraction, other operating systems,
background checking of all tabs, standalone modifiers, and modifier chords/double-tap gestures.

## Layout

- `Refine.py`: Sublime commands and event lifecycle.
- `refine/editor.py`: active-buffer session, UI, and native Apply transaction.
- `refine/document.py`: revision identity, UTF-16 coordinates, edit validation.
- `refine/shortcuts.py`: shortcut negotiation, mapping, and Quick Apply ownership.
- `refine/transport.py`: reconnecting background socket worker.
- `refine/protocol.py`: discovery, framing, handshake, and sequencing.
- `refine/validation.py`: MIT-licensed validator extracted from `refine-protocol`.
- `vendor/protocol`: pinned schemas, vectors, fake-server runner, and provenance.

MIT licensed. See [LICENSE](LICENSE) and the vendored protocol provenance.
