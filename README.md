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

Check grammar, spelling, and phrasing in Sublime Text with Refine. Download a
local model to check your writing offline, without leaving your editor.

Features:

- Private, offline writing checks powered by a local AI model on your Mac
- Underlined suggestions with cards that show what will change
- Explanations with formatting, language, and model details
- Undoable corrections and keyboard shortcuts for reviewing suggestions
- Support for Markdown and plain text, including unsaved documents

## Requirements

- Sublime Text 4 on macOS, build 4107 or newer
- [Refine for Mac](https://refine.sh?utm_source=refine-sublime&utm_medium=readme), running and configured with Integration Protocol 1.0 support

This plugin is a development version. Use a Refine build that recognizes the
Sublime Text plugin so Refine can hand writing checks over to it.

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

If a `Refine` folder already exists there, update that installation rather than
adding a second copy. Restart Sublime after installing.

To update, open a terminal in the `Refine` folder and run `git pull`, then restart
Sublime.

### 3. Start writing

Open a Markdown or plain-text document. With **Check Writing Automatically**
enabled in Refine, suggestions appear as you write.

1. Click within underlined text to open its suggestion card immediately, or hover over it.
2. Review the proposed changes, then choose **Apply**, **Dismiss**, or **Explain**.
3. Use Sublime's **Undo** to undo a correction.

Each card shows the suggestion type, language, and proposed changes. Choose
**Explain** for more detail, or use the buttons and shortcuts below the changes.
Hover cards stay open as you move toward them and close when you move away.
Sublime controls the hover delay; clicking opens the card without that wait.

For an immediate check, open the Command Palette and run **Refine: Check
Writing**. Select a single passage to check, or clear the selection to check the
whole document. Multiple selections are not supported.

Only the active Markdown or plain-text document is checked. Switching documents
moves writing checks to the new document. The plugin does not check an entire
project in the background.

## Keyboard shortcuts

**Apply** and **Dismiss** use the key combinations configured in Refine,
such as **Option+Right Arrow**. Move the caret into a suggestion to activate it.
Refine's **Show Tip and Highlight** setting adds an inline shortcut tip;
**Highlight Changes** shows only the active highlight.

With a suggestion card open, the configured **Dismiss** shortcut dismisses that
suggestion. Without a card, it deactivates the suggestion at the caret but keeps
it available for review. Move the caret to activate a suggestion again.
Outside an active suggestion, keys retain their normal editor behavior.

With a compatible Refine version and Input Monitoring permission, you can also
use **Left/Right Shift, Option, and Control** on their own. These shortcuts act
on the current suggestion in the focused editor. They trigger when you press the
key, including when you hold Shift to begin typing, rather than when you release it.

With older Refine versions, use regular key combinations or the buttons on the
suggestion card. The plugin detects shortcut support automatically and marks
standalone modifier shortcuts as unavailable when Refine does not support them.
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
| **Refine: Check Writing** | Check the current document or selection. |
| **Refine: Show Suggestion** | Open the suggestion at the caret. |
| **Refine: Next Suggestion** / **Previous Suggestion** | Move through suggestions and open their cards. |
| **Refine: Apply Suggestion** | Apply the open suggestion or the suggestion at the caret. |
| **Refine: Dismiss Suggestion** | Dismiss the current suggestion. |
| **Refine: Explain Suggestion** | Show an explanation for the current suggestion. |
| **Refine: Report Suggestion** | Send feedback when Refine offers Report. |
| **Refine: Connection Status** | Show the connection status. |
| **Refine: Reconnect** | Start a fresh connection to Refine. |

Cards indicate when an action is in progress, ask for confirmation before sending
a report, and show errors with retry controls.
Explanations support headings, paragraphs, lists, bold and italic text, and code.
Other Markdown remains plain text; images, raw HTML, and clickable links are not
rendered.

## Appearance and status

Configure automatic checks, models, languages, shortcuts, diff colors, and
highlight style in Refine. Inline highlight colors follow Sublime's theme;
exact custom Refine highlight colors are not yet supported.

Sublime's status bar shows connection state, checking progress, and suggestion
count. A `selection` label indicates that only part of the document was checked.
The plugin reconnects automatically when Refine restarts.

To disable Refine for a document or project, set `"refine_enabled": false` in its
settings, then switch away from and back to that document.

## Local AI and privacy

The plugin sends the full active Markdown or plain-text document, including
unsaved text, to the Refine app on your Mac. Checking a selection still sends
the full document; the selection controls what Refine checks.
With a downloaded local model, writing checks stay on your Mac and work offline.
If you configure a hosted provider, Refine may send your writing to that provider.

The connection uses a local Unix-domain socket and an authentication token that
changes each time Refine launches. The plugin keeps the token in memory. Other
computers and other user accounts on your Mac cannot use this connection. It
does not protect against another process running under your account.

Choosing **Report** sends feedback about a suggestion to Refine's feedback
service. That report may include original and revised excerpts, language, model,
provider, custom instructions,
and Refine and macOS version details. Reports are never automatic.

The plugin makes no direct internet requests, sends no telemetry, and does not
save document text, suggestions, explanations, or credentials to disk. It does
not send filenames or paths to identify documents. Sublime and other installed
plugins may save data separately, including for unsaved-document recovery.
App and model downloads, updates, hosted checks, and Report require internet
access.

Read [How Refine works](https://refine.sh/guides/how-refine-works?utm_source=refine-sublime&utm_medium=readme)
and the [privacy policy](https://refine.sh/privacy-policy?utm_source=refine-sublime&utm_medium=readme)
for more information.

## Troubleshooting

### No suggestions appear

Confirm that Refine is open and configured, and that Sublime's syntax is
**Markdown** or **Plain Text**. Run **Refine: Check Writing**, then check
**Refine: Connection Status**. Documents over 1 MiB are unsupported.

### Refine is disconnected

Open Refine, then run **Refine: Reconnect** if automatic reconnection has not
restored the session. Refine and the plugin must both support Integration
Protocol 1.0.

### A shortcut is unavailable

To use Shift, Option, or Control on its own, use a Refine version that supports
these shortcuts and grant it Input Monitoring permission. While Refine prepares the
shortcut for the active suggestion, the highlight stays visible and the shortcut
hint is hidden. If Refine cannot monitor key presses, the shortcut appears as
unavailable. Use a regular key combination such as **Option+Right Arrow** or the
suggestion card instead.

Autocomplete menus, overlays, editor panels, and snippet editing take precedence.
Standalone modifier shortcuts are disabled while a panel is open.

### A suggestion cannot be applied

The plugin checks each correction against your current text before applying it.
If you edited the text after checking, run another check. You cannot apply
corrections to read-only documents. Each correction can be undone in one step.

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
