"""Small, escaped Markdown subset for explanation minihtml; no raw HTML or URLs."""
from html import escape
import re


def inline(text):
    # Code is handled first so emphasis characters inside it remain literal.
    parts = re.split(r'(`[^`\n]+`)', text)
    result = []
    for part in parts:
        if part.startswith('`') and part.endswith('`') and len(part) > 2:
            result.append('<code>' + escape(part[1:-1]) + '</code>')
            continue
        part = escape(part)
        part = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', part)
        part = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', part)
        result.append(part)
    return ''.join(result)


def render(text):
    output, paragraph, code = [], [], []
    fenced = False
    list_kind = None

    def flush():
        if paragraph:
            output.append('<p>' + '<br>'.join(inline(line) for line in paragraph) + '</p>')
            paragraph.clear()

    def close_list():
        nonlocal list_kind
        if list_kind:
            output.append('</' + list_kind + '>')
            list_kind = None

    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            flush()
            close_list()
            if fenced:
                output.append('<pre><code>' + escape('\n'.join(code)) + '</code></pre>')
                code.clear()
            fenced = not fenced
        elif fenced:
            code.append(line)
        elif not line.strip():
            flush()
            close_list()
        else:
            item = re.match(r'^\s*(?:([-+*])|\d+\.)\s+(.+)$', line)
            heading = re.match(r'^#{1,6}\s+(.+)$', line)
            if item:
                flush()
                kind = 'ul' if item[1] else 'ol'
                if kind != list_kind:
                    close_list()
                    output.append('<' + kind + '>')
                    list_kind = kind
                output.append('<li>' + inline(item[2]) + '</li>')
            else:
                close_list()
                if heading:
                    flush()
                    output.append('<p><strong>' + inline(heading[1]) + '</strong></p>')
                else:
                    paragraph.append(line)
    flush()
    close_list()
    if fenced:
        output.append('<pre><code>' + escape('\n'.join(code)) + '</code></pre>')
    return ''.join(output)
