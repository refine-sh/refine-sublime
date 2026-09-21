# Changelog

## 0.2.0 — development

- Keep native modifier hints hidden while a new suggestion awaits confirmation,
  without flashing an unsupported warning. Request ownership immediately and
  distinguish pending readiness from unavailable keyboard monitoring.

- Support standalone Left/Right Shift, Option, and Control through Refine's native
  monitor when the optional modifier bridge capability is negotiated. Older apps
  retain regular shortcuts and explicit unsupported feedback.
- Keep native modifier ownership connection-local and reject stale triggers after
  source, selection, focus, suggestion, settings, or connection changes.

- Add busy action controls, duplicate-request guards, report confirmation, and
  inline failures with retry controls.
- Format explanation Markdown and display explanation model/language attribution
  and reading direction. Keep raw HTML and remote content inert.

- Render cursor activation highlights and inline shortcut tips on caret movement;
  clear them on cancellation, focus loss, and opening a suggestion card.

- Update an open Explain popup in place so its hide callback cannot discard
  incoming explanation updates. Show progress as soon as Explain is requested.

- Synchronize Apply/Dismiss shortcuts with Refine through negotiated v1/v2 settings.
- Support regular key combinations; standalone modifiers require the negotiated native bridge.
- Remove the native modifier callback that crashed Sublime’s ARM64 Python host
  on incoming modifier events; retain popup actions and regular shortcuts.
- Keep shortcut ownership local to live suggestions and distinguish card Dismiss
  from cancellation of cursor Quick Apply.
- Preserve native keys outside suggestion ownership and show shortcut conflicts
  or unsupported gestures explicitly.
- Reload internal modules when the installed plugin updates.

## 0.1.0 — development

- Check the active Markdown or plain-text buffer through Refine Protocol 1.0.
- Display inline marks, suggestion diffs, streamed explanations, and status.
- Offer explicit Apply, Dismiss, Explain, Report, and navigation commands.
- Validate source revisions and Unicode boundaries before one undoable Apply.
- Restore retained sessions and receipts without repeating host mutations.
- Include protocol vectors, real-socket verification, and standalone packaging.
