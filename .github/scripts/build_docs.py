"""Build static HTML documentation from Markdown files.

Usage::

    python .github/scripts/build_docs.py docs/ _site/

Each ``.md`` file in the source directory is converted to a minimal
HTML page and written to the output directory.  A sidebar index is
generated automatically.  No external dependencies are required.
"""

import os
import sys
import html
import re


_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       max-width: 960px; margin: 0 auto; padding: 2rem 1rem; line-height: 1.6; color: #24292e; }
nav { position: fixed; left: 0; top: 0; width: 220px; height: 100vh; overflow-y: auto;
      background: #f6f8fa; border-right: 1px solid #e1e4e8; padding: 1rem; }
nav a { display: block; padding: 4px 0; text-decoration: none; color: #0366d6; font-size: 0.9rem; }
nav a:hover { text-decoration: underline; }
main { margin-left: 240px; }
code, pre { background: #f6f8fa; border-radius: 3px; font-size: 0.9rem; }
pre { padding: 1rem; overflow-x: auto; }
code { padding: 2px 6px; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #e1e4e8; padding: 6px 13px; text-align: left; }
th { background: #f6f8fa; }
h1 { border-bottom: 1px solid #e1e4e8; padding-bottom: 0.3rem; }
h2 { border-bottom: 1px solid #eaecef; padding-bottom: 0.3rem; margin-top: 1.5rem; }
"""


def _md_to_html(md_text):
    """Minimal Markdown to HTML converter (stdlib only, no dependencies).

    Handles: headings, code blocks, inline code, bold, italic, links,
    unordered/ordered lists, tables, paragraphs.
    """
    lines = md_text.split('\n')
    out = []
    in_code = False
    in_table = False
    in_list = False
    list_tag = ''

    for line in lines:
        # Fenced code blocks
        if line.strip().startswith('```'):
            if in_code:
                out.append('</code></pre>')
                in_code = False
            else:
                lang = line.strip()[3:]
                out.append(f'<pre><code class="language-{html.escape(lang)}">')
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue

        # Tables
        if '|' in line and line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().split('|')[1:-1]]
            if all(re.match(r'^[-:]+$', c) for c in cells):
                continue  # separator row
            if not in_table:
                out.append('<table>')
                tag = 'th'
                in_table = True
            else:
                tag = 'td'
            out.append('<tr>' + ''.join(f'<{tag}>{_inline(c)}</{tag}>' for c in cells) + '</tr>')
            continue
        elif in_table:
            out.append('</table>')
            in_table = False

        stripped = line.strip()

        # Headings
        m = re.match(r'^(#{1,6})\s+(.*)', stripped)
        if m:
            if in_list:
                out.append(f'</{list_tag}>')
                in_list = False
            level = len(m.group(1))
            text = _inline(m.group(2))
            slug = re.sub(r'[^a-z0-9]+', '-', m.group(2).lower()).strip('-')
            out.append(f'<h{level} id="{slug}">{text}</h{level}>')
            continue

        # Unordered list
        m = re.match(r'^[-*+]\s+(.*)', stripped)
        if m:
            if not in_list or list_tag != 'ul':
                if in_list:
                    out.append(f'</{list_tag}>')
                out.append('<ul>')
                in_list = True
                list_tag = 'ul'
            out.append(f'<li>{_inline(m.group(1))}</li>')
            continue

        # Ordered list
        m = re.match(r'^\d+\.\s+(.*)', stripped)
        if m:
            if not in_list or list_tag != 'ol':
                if in_list:
                    out.append(f'</{list_tag}>')
                out.append('<ol>')
                in_list = True
                list_tag = 'ol'
            out.append(f'<li>{_inline(m.group(1))}</li>')
            continue

        # Close list if we hit a non-list line
        if in_list and stripped == '':
            out.append(f'</{list_tag}>')
            in_list = False

        # Blank line
        if stripped == '':
            continue

        # Paragraph
        out.append(f'<p>{_inline(stripped)}</p>')

    if in_code:
        out.append('</code></pre>')
    if in_table:
        out.append('</table>')
    if in_list:
        out.append(f'</{list_tag}>')

    return '\n'.join(out)


def _inline(text):
    """Convert inline Markdown to HTML."""
    text = html.escape(text)
    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text


def build(src_dir, out_dir):
    """Build HTML docs from Markdown files."""
    os.makedirs(out_dir, exist_ok=True)

    md_files = sorted(f for f in os.listdir(src_dir) if f.endswith('.md'))
    if not md_files:
        print(f"No .md files found in {src_dir}")
        return

    # Build sidebar
    nav_links = []
    for f in md_files:
        name = f.replace('.md', '')
        title = name.replace('_', ' ').replace('-', ' ').title()
        html_name = name + '.html'
        nav_links.append(f'<a href="{html_name}">{title}</a>')
    nav_html = '<nav>\n<h3>Documentation</h3>\n' + '\n'.join(nav_links) + '\n</nav>'

    for f in md_files:
        name = f.replace('.md', '')
        title = name.replace('_', ' ').replace('-', ' ').title()
        with open(os.path.join(src_dir, f), 'r', encoding='utf-8') as fh:
            md = fh.read()
        body = _md_to_html(md)
        page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} – Tableau to Power BI</title>
<style>{_CSS}</style>
</head>
<body>
{nav_html}
<main>
{body}
</main>
</body>
</html>"""
        out_path = os.path.join(out_dir, name + '.html')
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(page)
        print(f"  ✓ {f} → {name}.html")

    # Create index.html redirect to README
    if 'README.md' in md_files:
        idx = '<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url=README.html"></head></html>'
        with open(os.path.join(out_dir, 'index.html'), 'w') as fh:
            fh.write(idx)
        print("  ✓ index.html → README.html")

    print(f"\nBuilt {len(md_files)} pages in {out_dir}/")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <src_dir> <out_dir>")
        sys.exit(1)
    build(sys.argv[1], sys.argv[2])
