"""Escape all source/model text before rendering Sublime minihtml."""
from html import escape
from unicodedata import category
from .markdown import render as render_markdown


def _strike(text):
    # Decorate display text only, before HTML escaping. Keep accents attached
    # to their base character; leave whitespace, controls, and emoji alone.
    result = []
    pending = False
    for char in text:
        kind = category(char)[0]
        if kind != 'M':
            if pending:
                result.append('\u0336')
            pending = kind in ('L', 'N', 'P')
        result.append(char)
    if pending:
        result.append('\u0336')
    return ''.join(result)


def _section_heading(title, metadata):
    text = title + ' · ' + metadata if metadata else title
    return '<div class="section-heading meta">{}</div>'.format(escape(text))



def card(suggestion, content, explanation='', shortcuts=None, feedback=None, explanation_attribution=None):
    appearance = content['appearance']['diff']
    runs = []
    for run in suggestion['diff']:
        text = run['text']
        if appearance['showHiddenWhitespace'] and run['kind'] != 'unchanged':
            text = text.replace(' ', '·').replace('\t', '→').replace('\n', '↵\n')
        if run['kind'] == 'delete':
            text = _strike(text)
        text = escape(text).replace('\n', '<br>')
        if run['kind'] == 'insert':
            text = '<span style="color:{}">{}</span>'.format(appearance['additionColor'], text)
        elif run['kind'] == 'delete':
            text = '<span style="color:{}">{}</span>'.format(appearance['deletionColor'], text)
        runs.append(text)
    attribution = suggestion['attribution']
    feedback = feedback or {}
    controls = {}
    busy_labels = {'apply': 'Applying…', 'dismiss': 'Dismissing…', 'explain': 'Explaining…', 'report': 'Reporting…'}
    for action in ('explain', 'dismiss', 'report', 'apply'):
        if action not in suggestion['availableActions']:
            continue
        state = feedback.get(action, {}).get('state')
        if state == 'busy' or (state == 'success' and action == 'report'):
            label = 'Reported' if state == 'success' else busy_labels[action]
            controls[action] = '<span class="control meta">' + label + '</span>'
        else:
            label = 'Retry ' + action if state == 'error' else action.title()
            if shortcuts and action in ('apply', 'dismiss'):
                if shortcuts.keys[action]:
                    label += ' (' + shortcuts.labels[action] + ')'
                elif action in shortcuts.unavailable:
                    label += ' (' + shortcuts.labels[action] + ' · unavailable)'
                elif action not in shortcuts.pending and not shortcuts.has_conflict:
                    label += ' (' + shortcuts.labels[action] + ' · unsupported)'
            style = 'control primary' if action == 'apply' else 'control'
            controls[action] = '<a href="{}" class="{}">{}</a>'.format(action, style, escape(label))
    messages = ''
    for detail in feedback.values():
        if detail.get('message'):
            messages += '<p class="meta">' + escape(detail['message']) + '</p>'
    explanation_html = ''
    if explanation:
        detail = explanation_attribution or {}
        metadata = ''
        if detail:
            metadata = detail['languageDisplayName'] + ' · ' + detail['modelDisplayName']
        direction = detail.get('textDirection', attribution['textDirection'])
        direction = direction if direction in ('ltr', 'rtl', 'auto') else 'auto'
        explanation_html = ('<div class="explanation">'
                            + _section_heading('Explanation', metadata)
                            + '<div class="explanation-body" dir="{}">{}</div></div>'.format(
                                direction, render_markdown(explanation)))
    shortcut_note = ''
    if shortcuts and (shortcuts.has_conflict or shortcuts.unavailable):
        shortcut_note = '<div class="shortcut-note meta">{}</div>'.format(
            '<br>'.join(escape(message) for message in shortcuts.messages))
    kind = {'grammar': 'Grammar', 'fluency': 'Fluency', 'mixed': 'Grammar & Fluency'}[suggestion['kind']]
    header = _section_heading(
        kind, attribution['languageDisplayName'] + ' · ' + attribution['checkModelDisplayName'])
    footer = ' &nbsp; '.join(controls[action] for action in ('apply', 'dismiss', 'explain', 'report') if action in controls)
    diff = '<div class="diff" dir="{}">{}</div>'.format(
        attribution['textDirection'], ''.join(runs))
    return ('''<body id="refine-suggestion"><style>
        body { margin: 0; font-family: system; font-size: 1rem; line-height: 1.5em; }
        .card { padding: 0.75rem 1rem; }
        .section-heading { line-height: 1.5em; white-space: nowrap; }
        .meta { color: color(var(--foreground) alpha(0.65)); font-size: 0.85rem; font-weight: normal; }
        .diff { margin-top: 0.25rem; padding: 0; line-height: 1.5em; white-space: pre-wrap; }
        .control { font-size: 0.85rem; text-decoration: none; }
        a.control { color: color(var(--foreground) alpha(0.8)); }
        a.primary { color: var(--foreground); font-weight: normal; }
        .explanation { border-top: 1px solid color(var(--foreground) alpha(0.15));
                       margin-top: 0.5rem; padding-top: 0.5rem; }
        .explanation-body p, .explanation-body ul, .explanation-body ol, .explanation-body pre {
            margin: 0.5rem 0 0; padding: 0; }
        .explanation-body ul, .explanation-body ol { padding-left: 1rem; }
        .explanation-body li { display: list-item; margin: 0; padding: 0; }
        .actions { text-align: right; border-top: 1px solid color(var(--foreground) alpha(0.15));
                   margin-top: 0.5rem; padding: 0.5rem 0 0; line-height: 1.5em; }
        p.meta { margin: 0.5rem 0 0; }
        .shortcut-note { padding-top: 0.5rem; font-size: 1rem; line-height: 1.5em; }
        </style><div class="card">''' + header + diff
        + explanation_html + messages
        + '<div class="actions">' + footer + '</div>'
        + shortcut_note + '</div></body>')
