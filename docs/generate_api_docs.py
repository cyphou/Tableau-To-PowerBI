"""
API documentation generator for the TableauToPowerBI project.

Generates HTML API documentation from Python docstrings using either
``pdoc`` (preferred) or a built-in lightweight generator that uses
``pydoc`` (standard library, no dependencies).

Usage:
    python docs/generate_api_docs.py                 # auto-detect
    python docs/generate_api_docs.py --engine pdoc   # force pdoc
    python docs/generate_api_docs.py --engine builtin # force builtin
    python docs/generate_api_docs.py --output docs/api/
"""

import argparse
import importlib
import os
import sys
import pydoc
import inspect
import html as html_module

# Modules to document
MODULES = [
    'tableau_export.dax_converter',
    'tableau_export.extract_tableau_data',
    'tableau_export.datasource_extractor',
    'tableau_export.m_query_builder',
    'tableau_export.prep_flow_parser',
    'powerbi_import.pbip_generator',
    'powerbi_import.tmdl_generator',
    'powerbi_import.visual_generator',
    'powerbi_import.validator',
    'powerbi_import.assessment',
    'powerbi_import.strategy_advisor',
    'powerbi_import.migration_report',
    'powerbi_import.incremental',
    'powerbi_import.m_query_generator',
    'powerbi_import.import_to_powerbi',
]


def generate_with_pdoc(output_dir):
    """Generate docs using pdoc (pip install pdoc)."""
    try:
        import pdoc
    except ImportError:
        print("pdoc not installed. Install with: pip install pdoc")
        return False

    os.makedirs(output_dir, exist_ok=True)

    # pdoc >=14 API
    if hasattr(pdoc, 'pdoc'):
        for mod_name in MODULES:
            try:
                html = pdoc.pdoc(mod_name)
                out_file = os.path.join(output_dir, f'{mod_name}.html')
                with open(out_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"  ✓ {mod_name} → {out_file}")
            except Exception as exc:
                print(f"  ✗ {mod_name}: {exc}")
    else:
        # Older pdoc versions
        print("pdoc version not supported; falling back to builtin")
        return False

    _write_index(output_dir)
    print(f"\nAPI docs generated in: {output_dir}")
    return True


def generate_with_builtin(output_dir):
    """Generate docs using pydoc (standard library)."""
    os.makedirs(output_dir, exist_ok=True)

    # Ensure project root is in path
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    for mod_name in MODULES:
        try:
            mod = importlib.import_module(mod_name)
            html_content = _module_to_html(mod, mod_name)
            out_file = os.path.join(output_dir, f'{mod_name}.html')
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"  ✓ {mod_name} → {out_file}")
        except Exception as exc:
            print(f"  ✗ {mod_name}: {exc}")

    _write_index(output_dir)
    print(f"\nAPI docs generated in: {output_dir}")
    return True


def _module_to_html(mod, mod_name):
    """Convert a module to a simple HTML documentation page."""
    parts = [
        '<!DOCTYPE html>',
        '<html><head>',
        f'<title>{mod_name} — API Reference</title>',
        '<meta charset="utf-8">',
        '<style>',
        'body { font-family: -apple-system, "Segoe UI", sans-serif; ',
        '       max-width: 900px; margin: 0 auto; padding: 20px; '
        '       line-height: 1.6; color: #333; }',
        'h1 { color: #0078D4; border-bottom: 2px solid #0078D4; padding-bottom: 8px; }',
        'h2 { color: #106EBE; margin-top: 2em; }',
        'h3 { color: #444; }',
        'pre { background: #f4f4f4; padding: 12px; border-radius: 4px; '
        '      overflow-x: auto; font-size: 14px; }',
        'code { background: #f0f0f0; padding: 2px 5px; border-radius: 3px; }',
        '.signature { color: #0078D4; font-weight: bold; }',
        '.docstring { margin-left: 20px; white-space: pre-wrap; }',
        'a { color: #0078D4; }',
        'nav a { margin-right: 12px; }',
        '</style>',
        '</head><body>',
        f'<nav><a href="index.html">← Index</a></nav>',
        f'<h1>{html_module.escape(mod_name)}</h1>',
    ]

    # Module docstring
    if mod.__doc__:
        parts.append(f'<pre class="docstring">{html_module.escape(mod.__doc__.strip())}</pre>')

    # Classes
    classes = inspect.getmembers(mod, inspect.isclass)
    for cls_name, cls_obj in classes:
        if cls_obj.__module__ != mod.__name__:
            continue
        parts.append(f'<h2>class {html_module.escape(cls_name)}</h2>')
        if cls_obj.__doc__:
            parts.append(f'<pre class="docstring">{html_module.escape(cls_obj.__doc__.strip())}</pre>')
        # Methods
        methods = inspect.getmembers(cls_obj, predicate=inspect.isfunction)
        for meth_name, meth_obj in methods:
            if meth_name.startswith('_') and meth_name != '__init__':
                continue
            try:
                sig = inspect.signature(meth_obj)
            except (ValueError, TypeError):
                sig = '(...)'
            parts.append(f'<h3><span class="signature">{html_module.escape(meth_name)}'
                         f'{html_module.escape(str(sig))}</span></h3>')
            if meth_obj.__doc__:
                parts.append(f'<pre class="docstring">{html_module.escape(meth_obj.__doc__.strip())}</pre>')

    # Module-level functions
    functions = inspect.getmembers(mod, inspect.isfunction)
    for func_name, func_obj in functions:
        if func_obj.__module__ != mod.__name__:
            continue
        if func_name.startswith('_'):
            continue
        try:
            sig = inspect.signature(func_obj)
        except (ValueError, TypeError):
            sig = '(...)'
        parts.append(f'<h2><span class="signature">{html_module.escape(func_name)}'
                     f'{html_module.escape(str(sig))}</span></h2>')
        if func_obj.__doc__:
            parts.append(f'<pre class="docstring">{html_module.escape(func_obj.__doc__.strip())}</pre>')

    parts.append('</body></html>')
    return '\n'.join(parts)


def _write_index(output_dir):
    """Write an index.html linking to all module docs."""
    parts = [
        '<!DOCTYPE html>',
        '<html><head>',
        '<title>TableauToPowerBI — API Reference</title>',
        '<meta charset="utf-8">',
        '<style>',
        'body { font-family: -apple-system, "Segoe UI", sans-serif; '
        '       max-width: 700px; margin: 0 auto; padding: 20px; }',
        'h1 { color: #0078D4; }',
        'ul { list-style: none; padding: 0; }',
        'li { margin: 8px 0; }',
        'a { color: #0078D4; text-decoration: none; }',
        'a:hover { text-decoration: underline; }',
        '.section { font-weight: bold; margin-top: 1.5em; color: #333; }',
        '</style>',
        '</head><body>',
        '<h1>TableauToPowerBI — API Reference</h1>',
        '<p>Auto-generated API documentation for all public modules.</p>',
        '<p class="section">Extraction (tableau_export/)</p><ul>',
    ]

    for mod_name in MODULES:
        if mod_name.startswith('powerbi_import') and 'tableau_export' in parts[-1]:
            parts.append('</ul><p class="section">Generation (powerbi_import/)</p><ul>')
        filename = f'{mod_name}.html'
        parts.append(f'<li><a href="{filename}">{mod_name}</a></li>')

    parts.extend(['</ul>', '</body></html>'])

    index_path = os.path.join(output_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))


def main():
    parser = argparse.ArgumentParser(description='Generate API documentation')
    parser.add_argument('--engine', choices=['pdoc', 'builtin', 'auto'],
                        default='auto', help='Documentation engine')
    parser.add_argument('--output', default='docs/api/',
                        help='Output directory for HTML docs')
    args = parser.parse_args()

    # Ensure project root is in path
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    print("Generating API documentation...")

    if args.engine == 'pdoc':
        success = generate_with_pdoc(args.output)
    elif args.engine == 'builtin':
        success = generate_with_builtin(args.output)
    else:
        # Auto: try pdoc first, fallback to builtin
        try:
            import pdoc
            success = generate_with_pdoc(args.output)
        except ImportError:
            success = generate_with_builtin(args.output)

    if not success:
        generate_with_builtin(args.output)


if __name__ == '__main__':
    main()
