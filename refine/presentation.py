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
    controls = []
    busy_labels = {'apply': 'Applying…', 'dismiss': 'Dismissing…', 'explain': 'Explaining…', 'report': 'Reporting…'}
    for action in suggestion['availableActions']:
        state = feedback.get(action, {}).get('state')
        if state == 'busy' or (state == 'success' and action == 'report'):
            label = 'Reported' if state == 'success' else busy_labels[action]
            controls.append('<span class="meta">' + label + '</span>')
        else:
            label = 'Retry ' + action if state == 'error' else action.title()
            controls.append('<a href="{}">{}</a>'.format(action, label))
    actions = ' &nbsp; '.join(controls)
    for detail in feedback.values():
        if detail.get('message'):
            actions += '<p>' + escape(detail['message']) + '</p>'
    explanation_html = ''
    if explanation:
        detail = explanation_attribution or {}
        heading = 'Explanation'
        if detail:
            heading += ' · ' + detail['languageDisplayName'] + ' · ' + detail['modelDisplayName']
        direction = detail.get('textDirection', attribution['textDirection'])
        direction = direction if direction in ('ltr', 'rtl', 'auto') else 'auto'
        explanation_html = '<p class="meta">{}</p><div dir="{}">{}</div>'.format(
            escape(heading), direction, render_markdown(explanation))
    if shortcuts:
        labels = ' · '.join('{}: {}'.format(action.title(), shortcuts.labels[action]) for action in ('apply', 'dismiss') if shortcuts.keys[action])
        notices = ' '.join(shortcuts.messages)
        actions += '<p class="meta">{}</p>'.format(escape(' · '.join(part for part in (labels, notices) if part)))
    return ('<body><style>body {{ margin: 10px; }} .meta {{ opacity: 0.7; }} '
            '.diff {{ margin: 10px 0; }}</style>'
            '<div class="meta">Refine · {} · {}</div>'
            '<div class="diff" dir="{}">{}</div><div>{}</div>{}</body>').format(
                escape(attribution['languageDisplayName']), escape(attribution['checkModelDisplayName']),
                attribution['textDirection'], ''.join(runs), actions,
                explanation_html)
