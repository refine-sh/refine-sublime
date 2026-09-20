"""Sublime Text entry point. Commands and callbacks stay on the main thread."""
import sublime
import sublime_plugin

# Sublime reloads the entry module alone; refresh dependencies after stopping the
# old session so a linked checkout/package update cannot retain stale classes.
if '_session' in globals():
    import importlib
    import sys
    for _name in ('shortcuts', 'protocol', 'transport', 'markdown', 'presentation', 'editor'):
        _module = __package__ + '.refine.' + _name
        if _module in sys.modules:
            importlib.reload(sys.modules[_module])

from .refine.editor import Session, syntax_for
from .refine.protocol import make_store

_session = None
_store = None


def activate(view):
    global _session
    if _store is None or sublime.platform() != 'osx' or not view or not view.is_valid():
        return None
    if view.settings().get('is_widget'):
        return _session
    syntax = syntax_for(view)
    if _session and (_session.closed or not syntax or _session.view.buffer_id() != view.buffer_id()):
        _session.close()
        _session = None
    if not syntax:
        return None
    if _session:
        _session.has_focus = True
        _session.input_epoch += 1
        _session.attach_view(view)
    else:
        try:
            _session = Session(view, _store)
        except (ValueError, UnicodeError):
            view.set_status('refine', 'Refine: buffer exceeds 1 MiB or contains invalid Unicode')
    return _session


def plugin_loaded():
    global _store
    package = __package__.split('.')[0]
    _store = make_store(lambda path: sublime.load_resource('Packages/' + package + '/' + path))
    window = sublime.active_window()
    if window:
        activate(window.active_view())


def plugin_unloaded():
    global _session, _store
    if _session:
        _session.close()
    _session = None
    _store = None


class RefineEvents(sublime_plugin.EventListener):
    def on_activated(self, view):
        activate(view)

    def on_query_context(self, view, key, operator, operand, match_all):
        if key != 'refine_shortcut':
            return None
        if operator != sublime.OP_EQUAL or not isinstance(operand, str):
            return False
        return bool(_session and view.id() == _session.view.id()
                    and _session.shortcut_action(operand))

    def on_deactivated(self, view):
        if _session and view.id() == _session.view.id():
            _session.has_focus = False
            _session.input_epoch += 1
            _session.activation.cancel()
            _session.render_activation()

    def on_load(self, view):
        if view.window() and view.window().active_view() == view:
            activate(view)

    def on_modified(self, view):
        if _session and view.buffer_id() == _session.view.buffer_id():
            _session.modified()

    def on_selection_modified(self, view):
        if _session and view.id() == _session.view.id():
            _session.selection_modified()

    def on_post_text_command(self, view, command_name, args):
        if (_session and view.id() == _session.view.id()
                and command_name == 'drag_select'):
            _session.show_clicked_suggestion()

    def on_hover(self, view, point, hover_zone):
        if _session and view.id() == _session.view.id() and hover_zone == sublime.HOVER_TEXT:
            _session.refresh()
            suggestion_id = _session.at(point)
            if suggestion_id:
                _session.show(suggestion_id, hover=True)

    def on_close(self, view):
        global _session
        if _session and view.id() == _session.view.id():
            _session.close()
            _session = None


class RefineCheckCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        session = activate(self.view)
        if session:
            session.check()
        else:
            sublime.status_message('Refine supports Markdown and plain text on macOS')


class RefineShowCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if _session and self.view.id() == _session.view.id():
            _session.show()


class RefineNextCommand(sublime_plugin.TextCommand):
    def run(self, edit, forward=True):
        if _session and self.view.id() == _session.view.id():
            _session.navigate(forward)


class RefineActionCommand(sublime_plugin.TextCommand):
    def run(self, edit, kind):
        if _session and self.view.id() == _session.view.id():
            _session.action(kind)


class RefineCommitCommand(sublime_plugin.TextCommand):
    def run(self, edit, transaction):
        if _session and self.view.id() == _session.view.id():
            _session.commit(edit, transaction)


class RefineStatusCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        sublime.status_message(_session.status if _session else 'Refine: open a Markdown or plain-text buffer')


class RefineReconnectCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global _session
        if _session:
            _session.close()
            _session = None
        activate(self.view)


class RefineShortcutCommand(sublime_plugin.TextCommand):
    def run(self, edit, key):
        if _session and self.view.id() == _session.view.id():
            _session.perform_shortcut(key)

