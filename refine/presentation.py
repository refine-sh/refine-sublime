"""Escape all source/model text before rendering Sublime minihtml."""
from html import escape
from .markdown import render as render_markdown


def card(suggestion, content, explanation='', shortcuts=None, feedback=None, explanation_attribution=None):
    appearance = content['appearance']['diff']
    runs = []
    for run in suggestion['diff']:
        text = escape(run['text'])
        if appearance['showHiddenWhitespace'] and run['kind'] != 'unchanged':
            text = text.replace(' ', '·').replace('\t', '→').replace('\n', '↵\n')
        text = text.replace('\n', '<br>')
        if run['kind'] == 'insert':
            text = '<span style="color:{}">{}</span>'.format(appearance['additionColor'], text)
        elif run['kind'] == 'delete':
            text = '<span style="color:{};text-decoration:line-through">{}</span>'.format(appearance['deletionColor'], text)
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
            if shortcuts and action in ('apply', 'dismiss') and shortcuts.keys[action]:
                label += ' (' + shortcuts.labels[action] + ')'
            style = 'control primary' if action == 'apply' else 'control'
            controls[action] = '<a href="{}" class="{}">{}</a>'.format(action, style, escape(label))
    messages = ''
    for detail in feedback.values():
        if detail.get('message'):
            messages += '<p class="meta">' + escape(detail['message']) + '</p>'
    explanation_html = ''
    if explanation:
        detail = explanation_attribution or {}
        heading = 'Explanation'
        if detail:
            heading += ' · ' + detail['languageDisplayName'] + ' · ' + detail['modelDisplayName']
        direction = detail.get('textDirection', attribution['textDirection'])
        direction = direction if direction in ('ltr', 'rtl', 'auto') else 'auto'
        explanation_html = '<div class="explanation"><p class="meta">{}</p><div dir="{}">{}</div></div>'.format(
            escape(heading), direction, render_markdown(explanation))
    if shortcuts and shortcuts.messages:
        messages += '<p class="meta">{}</p>'.format(escape(' '.join(shortcuts.messages)))
    kind = {'grammar': 'Grammar', 'fluency': 'Fluency', 'mixed': 'Grammar & Fluency'}[suggestion['kind']]
    header = '<span class="meta">{} – {}</span> &nbsp; {}'.format(
        escape(kind), escape(attribution['languageDisplayName']), controls.get('explain', ''))
    footer = ' &nbsp; '.join(controls[action] for action in ('dismiss', 'report', 'apply') if action in controls)
    return ('''<body id="refine-suggestion"><style>
        body { margin: 0; font-family: system; }
        .card { padding: 0.7rem; }
        .meta { color: color(var(--foreground) alpha(0.65)); font-size: 0.85rem; }
        .diff { margin: 0.65rem 0; line-height: 1.4; }
        .control { display: inline-block; padding: 0.3rem 0.45rem; text-decoration: none; }
        a { color: var(--foreground); }
        .primary { background-color: color(var(--foreground) alpha(0.10));
                   border: 1px solid color(var(--foreground) alpha(0.18)); border-radius: 0.3rem; }
        .explanation { border-top: 1px solid color(var(--foreground) alpha(0.15)); margin-top: 0.6rem; }
        .actions { margin-top: 0.65rem; }
        </style><div class="card">''' + header
        + '<div class="diff" dir="{}">{}</div>'.format(attribution['textDirection'], ''.join(runs))
        + explanation_html + messages
        + '<div class="actions">' + footer + '</div>'
        + '<div class="meta">' + escape(attribution['checkModelDisplayName']) + '</div></div></body>')
