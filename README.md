<div align="center">
  <a href="https://refine.sh?utm_source=refine-sublime&utm_medium=readme">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://refine.sh/icon-dark.png">
      <img src="https://refine.sh/icon.png" width="128" alt="Refine icon">
    </picture>
  </a>
  <h1>Refine for Sublime Text</h1>
  <p><strong>A local-first AI grammar checker and writing assistant for Sublime Text, powered by <a href="https://refine.sh?utm_source=refine-sublime&utm_medium=readme">Refine</a>.</strong></p>
  <p>
    <a href="https://www.sublimetext.com/"><img src="https://img.shields.io/badge/Sublime_Text-4-FF9800?logo=sublimetext&logoColor=white" alt="Sublime Text 4"></a>
    <img src="https://img.shields.io/badge/platform-macOS-111111?logo=apple" alt="macOS">
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
  </p>
</div>

Refine brings contextual grammar, spelling, and fluency suggestions to Sublime
Text. With a downloaded local model, you can check your writing entirely offline
without leaving your editor.

Features:

- Private, offline writing checks powered by a local LLM on your Mac
- Inline highlights and suggestion cards with readable diffs
- Explanations with formatting, language, and model details
- Undoable corrections and keyboard shortcuts for reviewing suggestions
- Markdown and plain text, including unsaved buffers

## Requirements

- Sublime Text 4 on macOS, build 4107 or newer
- [Refine for Mac](https://refine.sh?utm_source=refine-sublime&utm_medium=readme), running and configured with Integration Protocol 1.0 support

This plugin is currently a development version. To let the plugin take over
writing checks in Sublime from Refine's native integration, use a Refine build
that includes the Sublime Text host registration.

The plugin uses Sublime's bundled Python. You do not need to install Python,
Node.js, or additional packages to use it.

## Quick start

### 1. Set up Refine

[Download Refine for Mac](https://refine.sh?utm_source=refine-sublime&utm_medium=readme),
open it, and complete setup. Download a local model for offline checks, or
configure a hosted provider in Refine.

Keep Refine running while you write. This plugin does not launch the app
automatically.

### 2. Install the plugin

In Sublime, choose **Preferences → Browse Packages…**. Clone this repository
into a folder named `Refine` inside that Packages folder. For the standard macOS
installation:

```sh
git clone https://github.com/refine-sh/refine-sublime.git \
  "$HOME/Library/Application Support/Sublime Text/Packages/Refine"
```

If you already have a checkout at `~/code/refine-sublime`, link it instead:

```sh
ln -s "$HOME/code/refine-sublime" \
  "$HOME/Library/Application Support/Sublime Text/Packages/Refine"
```

Choose one method. If a `Refine` folder already exists there, use that installation
rather than adding a second copy. Restart Sublime after installing.

To update a Git installation, run `git pull` in its checkout. For packaging a
`.sublime-package` file, see [Contributing](CONTRIBUTING.md).

### 3. Start writing

Open a Markdown or plain-text buffer. With **Check Writing Automatically**
enabled in Refine, suggestions appear as you write.

1. Click within a suggestion to open its card immediately, or hover over underlined text.
2. Review the diff, then choose **Apply**, **Dismiss**, or **Explain**.
3. Use Sublime's **Undo** to undo a correction.

Cards follow Refine's layout, with the suggestion type and language above the
diff, Explain in the header, and action buttons with available shortcuts below.
Hover cards stay open as you move toward them and close when you move away.
Sublime controls the hover delay; clicking opens the card without that wait.
Selecting text and keyboard Quick Apply keep their existing behavior.

For an immediate check, open the Command Palette and run **Refine: Check
Writing**. Select one range first to scope the check, or clear the selection to
check the whole buffer. Multiple selections are not supported.

Only the active supported buffer is checked. Switching buffers moves the
integration to the new buffer; it does not check an entire project in the
background.

## Keyboard shortcuts

Apply and Dismiss follow the regular key combinations configured in Refine,
such as **Option+Right Arrow**. Move the caret into a suggestion to activate it.
Refine's **Show Tip and Highlight** setting adds an inline shortcut tip;
**Highlight Changes** shows only the active highlight.

With a suggestion card open, the configured Dismiss key dismisses that suggestion.
Without a card, it cancels cursor activation and leaves the suggestion in place.
Move the caret to activate a suggestion again. Outside an active suggestion,
keys retain their normal editor behavior.

With a compatible Refine version and Input Monitoring permission, standalone
**Left/Right Shift, Option, and Control** also work. Refine observes the physical
press and the plugin applies it only to the current suggestion in the focused
editor. Standalone modifiers fire on press, including when beginning shifted
text; they are not tap-on-release gestures.

Older Refine versions retain the existing behavior: regular combinations work,
standalone modifiers are marked unavailable, and suggestion-card actions remain
usable. Support is negotiated automatically; there is no version setting.
Modifier-only chords, double-taps, and some non-Latin layout shortcuts remain
unsupported. The plugin never silently substitutes another shortcut.

You can also add your own bindings through **Preferences → Key Bindings**:

```json
[
  { "keys": ["super+alt+g"], "command": "refine_check" },
  { "keys": ["super+alt+]"], "command": "refine_next" },
  { "keys": ["super+alt+["], "command": "refine_next", "args": { "forward": false } },
  { "keys": ["super+alt+enter"], "command": "refine_action", "args": { "kind": "apply" } }
]
```

## Commands

These commands are available in Sublime's Command Palette:

| Command | Action |
| --- | --- |
| **Refine: Check Writing** | Check the current buffer or selection. |
| **Refine: Show Suggestion** | Open the suggestion at the caret. |
| **Refine: Next Suggestion** / **Previous Suggestion** | Move through suggestions and open their cards. |
| **Refine: Apply Suggestion** | Apply the open suggestion or the suggestion at the caret. |
| **Refine: Dismiss Suggestion** | Dismiss the current suggestion. |
| **Refine: Explain Suggestion** | Show an explanation for the current suggestion. |
| **Refine: Report Suggestion** | Explicitly send feedback when Refine offers Report. |
| **Refine: Connection Status** | Show the integration's current status. |
| **Refine: Reconnect** | Start a fresh connection to Refine. |

Cards show busy actions, Report confirmation, and errors with retry controls.
Explanations support headings, paragraphs, lists, bold and italic text, and code.
Other Markdown remains plain text; images, raw HTML, and clickable links are not
rendered.

## Appearance and status

Configure automatic checks, models, languages, shortcuts, diff colors, and
highlight style in Refine. Inline highlight colors follow Sublime's theme;
exact custom Refine highlight colors are not yet supported.

Sublime's status bar shows connection state, checking progress, and suggestion
count. A `selection` label indicates partial coverage. The plugin reconnects
automatically when Refine restarts.

To disable Refine for a buffer or project, set `"refine_enabled": false` in its
settings, then switch away from and back to that buffer.

## Local AI and privacy

The plugin sends the complete active supported buffer, including unsaved text,
to the local Refine app over a same-user Unix-domain socket. A selected check
still sends the complete buffer; the selection controls what Refine checks.
With a downloaded local model, writing checks stay on your Mac and work offline.
If you configure a hosted provider, Refine may send your writing to that provider.

To discover Refine, the plugin reads endpoint and ownership metadata under
`~/Library/Application Support/com.runjuu.refine/Integrations/`. It uses a
per-launch token and keeps that token in memory. This connection excludes
network clients and other OS users; it does not protect against another process
already running as you.

**Report is a separate, explicit action.** Only choosing Report can send feedback
about a live suggestion to Refine's feedback service. That report may include
original and revised excerpts, language, model, provider, custom instructions,
and Refine and macOS version details. Reports are never automatic.

The plugin makes no direct internet requests, sends no telemetry, and does not
persist source, suggestions, explanations, or credentials. It sends no filenames
or paths as document identity. Sublime and other installed plugins have their own
persistence behavior, including unsaved-buffer recovery. App and model downloads,
updates, hosted checks, and Report require internet access.

Read [How Refine works](https://refine.sh/guides/how-refine-works?utm_source=refine-sublime&utm_medium=readme)
and the [privacy policy](https://refine.sh/privacy-policy?utm_source=refine-sublime&utm_medium=readme)
for more information.

## Troubleshooting

### No suggestions appear

Confirm that Refine is open and configured, and that Sublime's syntax is
**Markdown** or **Plain Text**. Run **Refine: Check Writing**, then check
**Refine: Connection Status**. Buffers over 1 MiB are unsupported.

### Refine is disconnected

Open Refine, then run **Refine: Reconnect** if automatic reconnection has not
restored the session. The plugin requires exact Integration Protocol 1.0
compatibility between Refine and the plugin.

### A shortcut is unavailable

Standalone modifiers require a Refine version supporting the native modifier
bridge and Refine's Input Monitoring permission. While Refine confirms readiness
for the active suggestion, the highlight stays visible and the shortcut hint is
hidden. A monitoring failure is reported as unavailable; pending confirmation is
never reported as unsupported. Older versions can use a regular combination such
as Option+Right Arrow or the suggestion card.
Autocomplete menus, overlays, editor panels, and snippet editing take precedence.
Native modifier shortcuts are conservatively disabled while a panel is open.

### A suggestion cannot be applied

Corrections are checked against the current text before changing the buffer.
If you edited the text after checking, run another check. Read-only buffers
cannot be changed. Each successful correction is one undoable operation.

### Sublime reports that its plugin host exited

Update the plugin, save your work, and restart Sublime. An earlier development
version's standalone-modifier listener could crash the plugin host; that listener
has been removed.

## Support and development

For bugs and feature requests, [open an issue](https://github.com/refine-sh/refine-sublime/issues).
For help with Refine for Mac, email [support@refine.sh](mailto:support@refine.sh).

- [Contributing](CONTRIBUTING.md): development, tests, packaging, and manual checks
- [Changelog](CHANGELOG.md): user-visible changes
- [Protocol specification](vendor/protocol/spec/protocol.md): the local integration contract

## License

[MIT](LICENSE)
