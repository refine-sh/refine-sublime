# Contributing

Run the commands below from the repository root. Development requires Python 3.
The installed plugin must remain compatible with Sublime’s bundled Python 3.8.

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
10. Configure Left Shift for Apply and Escape for Dismiss. With a compatible
    Refine app and Input Monitoring permission, verify Left Shift applies the
    active suggestion once and Right Shift does not. Verify normal shifted typing
    and selection outside suggestions. Test card and cursor Dismiss, rapid tab/app
    changes, read-only buffers, autocomplete, panels, plugin reload and reconnect.
    With an older Refine app or denied permission, verify Left Shift stays
    unavailable while the Apply button, Escape, and Option+Right still work.
11. With the companion Refine app change, verify Sublime's plugin owns its native
    checks while Obsidian and unrelated applications retain their own behavior.


## Installing a packaged build

After running `python3 scripts/package.py`, copy `dist/Refine.sublime-package`
into Sublime’s **Installed Packages** folder. Use either that package or a checkout
in **Packages**, not both. The package loads its schemas without unpacking.

## Layout

- `Refine.py`: Sublime commands and event lifecycle.
- `refine/editor.py`: active-buffer session, UI, and native Apply transaction.
- `refine/document.py`: revision identity, UTF-16 coordinates, edit validation.
- `refine/shortcuts.py`: shortcut negotiation, mapping, and Quick Apply ownership.
- `refine/transport.py`: reconnecting background socket worker.
- `refine/protocol.py`: discovery, framing, handshake, and sequencing.
- `refine/validation.py`: MIT-licensed validator extracted from `refine-protocol`.
- `vendor/protocol`: pinned schemas, vectors, fake-server runner, and provenance.

