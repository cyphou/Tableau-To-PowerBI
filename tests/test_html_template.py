"""Tests for powerbi_import.html_template — shared HTML report template module.

Sprint 107: Validates all reusable components, CSS framework, JavaScript,
design tokens, dark mode, and HTML escaping.
"""

import unittest

from powerbi_import.html_template import (
    PBI_BLUE, PBI_DARK, PBI_DARK_BLUE, PBI_LIGHT_BLUE, PBI_GRAY,
    PBI_LIGHT_GRAY, PBI_BG, PBI_SURFACE,
    SUCCESS, SUCCESS_BG, WARN, WARN_BG, FAIL, FAIL_BG,
    PURPLE, TEAL, ORANGE,
    esc, get_report_css, get_report_js,
    html_open, html_close, stat_card, stat_grid,
    section_open, section_close,
    badge, fidelity_bar, donut_chart, bar_chart,
    data_table, tab_bar, tab_content, card,
    heatmap_table, flow_diagram, cmd_box,
)


# ═══════════════════════════════════════════════════════════════════════
#  1. Design Tokens
# ═══════════════════════════════════════════════════════════════════════

class TestDesignTokens(unittest.TestCase):
    """Verify design token constants are valid hex colors."""

    def test_all_tokens_are_hex(self):
        tokens = [
            PBI_BLUE, PBI_DARK, PBI_DARK_BLUE, PBI_LIGHT_BLUE,
            PBI_GRAY, PBI_LIGHT_GRAY, PBI_BG, PBI_SURFACE,
            SUCCESS, SUCCESS_BG, WARN, WARN_BG, FAIL, FAIL_BG,
            PURPLE, TEAL, ORANGE,
        ]
        for token in tokens:
            self.assertTrue(token.startswith('#'), f'{token} is not a hex color')
            self.assertGreaterEqual(len(token), 4)

    def test_primary_blue(self):
        self.assertEqual(PBI_BLUE, '#0078d4')


# ═══════════════════════════════════════════════════════════════════════
#  2. HTML Escaping
# ═══════════════════════════════════════════════════════════════════════

class TestEsc(unittest.TestCase):
    """Test the esc() HTML escaping function."""

    def test_basic_escaping(self):
        self.assertEqual(esc('<script>'), '&lt;script&gt;')

    def test_ampersand(self):
        self.assertEqual(esc('A & B'), 'A &amp; B')

    def test_quotes(self):
        self.assertEqual(esc('"hello"'), '&quot;hello&quot;')

    def test_passthrough(self):
        self.assertEqual(esc('plain text'), 'plain text')

    def test_non_string_input(self):
        self.assertEqual(esc(42), '42')
        self.assertEqual(esc(None), 'None')

    def test_combined(self):
        self.assertEqual(esc('<a href="x">&'), '&lt;a href=&quot;x&quot;&gt;&amp;')


# ═══════════════════════════════════════════════════════════════════════
#  3. CSS Framework
# ═══════════════════════════════════════════════════════════════════════

class TestCSSFramework(unittest.TestCase):
    """Verify get_report_css() returns valid CSS with required selectors."""

    def setUp(self):
        self.css = get_report_css()

    def test_returns_string(self):
        self.assertIsInstance(self.css, str)
        self.assertGreater(len(self.css), 1000)

    def test_css_custom_properties(self):
        self.assertIn(':root', self.css)
        self.assertIn('--pbi-blue', self.css)
        self.assertIn('--success', self.css)
        self.assertIn('--fail', self.css)

    def test_report_header(self):
        self.assertIn('.report-header', self.css)
        self.assertIn('linear-gradient', self.css)

    def test_stat_grid_and_card(self):
        self.assertIn('.stat-grid', self.css)
        self.assertIn('.stat-card', self.css)
        self.assertIn('.stat-value', self.css)
        self.assertIn('.stat-label', self.css)

    def test_section_header_and_body(self):
        self.assertIn('.section-header', self.css)
        self.assertIn('.section-body', self.css)
        self.assertIn('.toggle-arrow', self.css)

    def test_badges(self):
        self.assertIn('.badge', self.css)
        self.assertIn('.badge-green', self.css)
        self.assertIn('.badge-yellow', self.css)
        self.assertIn('.badge-red', self.css)

    def test_legacy_tags(self):
        self.assertIn('.connector-tag', self.css)
        self.assertIn('.success-tag', self.css)
        self.assertIn('.warn-tag', self.css)
        self.assertIn('.danger-tag', self.css)
        self.assertIn('.isolated-tag', self.css)

    def test_new_tags(self):
        self.assertIn('.tag-connector', self.css)
        self.assertIn('.tag-success', self.css)
        self.assertIn('.tag-warn', self.css)
        self.assertIn('.tag-danger', self.css)

    def test_fidelity_bar(self):
        self.assertIn('.fidelity-bar', self.css)
        self.assertIn('.fidelity-track', self.css)
        self.assertIn('.fidelity-fill', self.css)

    def test_tables(self):
        self.assertIn('thead th', self.css)
        self.assertIn('tbody td', self.css)
        self.assertIn('.sortable', self.css)

    def test_charts(self):
        self.assertIn('.donut', self.css)
        self.assertIn('.bar-chart', self.css)
        self.assertIn('.bar-fill', self.css)

    def test_tabs(self):
        self.assertIn('.tab-bar', self.css)
        self.assertIn('.tab-content', self.css)
        self.assertIn('.tab.active', self.css)

    def test_cards_and_flow(self):
        self.assertIn('.card', self.css)
        self.assertIn('.flow-box', self.css)
        self.assertIn('.flow-arrow', self.css)
        self.assertIn('.cmd-box', self.css)

    def test_print_media_query(self):
        self.assertIn('@media print', self.css)

    def test_responsive_media_query(self):
        self.assertIn('@media (max-width: 768px)', self.css)

    def test_dark_mode_media_query(self):
        self.assertIn('@media (prefers-color-scheme: dark)', self.css)

    def test_dark_mode_overrides_background(self):
        self.assertIn('--pbi-bg: #1b1a19', self.css)
        self.assertIn('--pbi-surface: #252423', self.css)

    def test_dark_mode_print_reset(self):
        self.assertIn('@media print and (prefers-color-scheme: dark)', self.css)


# ═══════════════════════════════════════════════════════════════════════
#  4. JavaScript
# ═══════════════════════════════════════════════════════════════════════

class TestJavaScript(unittest.TestCase):
    """Verify get_report_js() returns working JS functions."""

    def setUp(self):
        self.js = get_report_js()

    def test_returns_string(self):
        self.assertIsInstance(self.js, str)
        self.assertGreater(len(self.js), 100)

    def test_toggle_section(self):
        self.assertIn('toggleSection', self.js)

    def test_switch_tab(self):
        self.assertIn('switchTab', self.js)

    def test_filter_table(self):
        self.assertIn('filterTable', self.js)

    def test_sort_table(self):
        self.assertIn('sortTable', self.js)


# ═══════════════════════════════════════════════════════════════════════
#  5. html_open / html_close
# ═══════════════════════════════════════════════════════════════════════

class TestHtmlOpenClose(unittest.TestCase):
    """Test html_open() and html_close() document wrappers."""

    def test_html_open_basic(self):
        html = html_open('Test Report')
        self.assertIn('<!DOCTYPE html>', html)
        self.assertIn('<title>Test Report</title>', html)
        self.assertIn('report-header', html)
        self.assertIn('Test Report', html)

    def test_html_open_with_subtitle(self):
        html = html_open('Title', subtitle='Sub text')
        self.assertIn('Sub text', html)

    def test_html_open_escapes_title(self):
        html = html_open('<script>XSS</script>')
        self.assertNotIn('<script>XSS', html)
        self.assertIn('&lt;script&gt;', html)

    def test_html_close_basic(self):
        html = html_close()
        self.assertIn('report-footer', html)
        self.assertIn('</html>', html)
        self.assertIn('</body>', html)

    def test_html_close_with_version(self):
        html = html_close(version='27.1.0')
        self.assertIn('27.1.0', html)


# ═══════════════════════════════════════════════════════════════════════
#  6. Stat Cards
# ═══════════════════════════════════════════════════════════════════════

class TestStatCards(unittest.TestCase):
    """Test stat_card() and stat_grid()."""

    def test_stat_card_basic(self):
        html = stat_card('42', 'Total Items')
        self.assertIn('stat-card', html)
        self.assertIn('42', html)
        self.assertIn('Total Items', html)

    def test_stat_card_with_accent(self):
        html = stat_card('100%', 'Score', accent='success')
        self.assertIn('accent-success', html)

    def test_stat_card_with_color(self):
        html = stat_card('5', 'Errors', color='#ff0000')
        self.assertIn('#ff0000', html)

    def test_stat_grid(self):
        cards = stat_card('1', 'A') + stat_card('2', 'B')
        html = stat_grid(cards)
        self.assertIn('stat-grid', html)
        self.assertIn('A', html)
        self.assertIn('B', html)


# ═══════════════════════════════════════════════════════════════════════
#  7. Sections
# ═══════════════════════════════════════════════════════════════════════

class TestSections(unittest.TestCase):
    """Test section_open() and section_close()."""

    def test_section_open_basic(self):
        html = section_open('exec', 'Executive Summary')
        self.assertIn('section-header', html)
        self.assertIn('Executive Summary', html)
        self.assertIn('section-body', html)
        self.assertIn('toggle-arrow', html)

    def test_section_open_with_icon(self):
        html = section_open('stats', 'Statistics', icon='📊')
        self.assertIn('📊', html)

    def test_section_open_collapsed(self):
        html = section_open('detail', 'Details', collapsed=True)
        self.assertIn('collapsed', html)

    def test_section_close(self):
        html = section_close()
        self.assertIn('</div>', html)


# ═══════════════════════════════════════════════════════════════════════
#  8. Badge
# ═══════════════════════════════════════════════════════════════════════

class TestBadge(unittest.TestCase):
    """Test badge() function."""

    def test_badge_auto_green(self):
        html = badge('GREEN')
        self.assertIn('badge', html)
        self.assertIn('badge-green', html)
        self.assertIn('GREEN', html)

    def test_badge_auto_yellow(self):
        html = badge('YELLOW')
        self.assertIn('badge-yellow', html)

    def test_badge_auto_red(self):
        html = badge('RED')
        self.assertIn('badge-red', html)

    def test_badge_explicit_level(self):
        html = badge('CUSTOM', 'blue')
        self.assertIn('badge-blue', html)

    def test_badge_pass_keyword(self):
        html = badge('pass')
        self.assertIn('badge-green', html)

    def test_badge_fail_keyword(self):
        html = badge('fail')
        self.assertIn('badge-red', html)

    def test_badge_gray_fallback(self):
        html = badge('UNKNOWN')
        self.assertIn('badge-gray', html)

    def test_badge_escapes_content(self):
        html = badge('<script>')
        self.assertNotIn('<script>', html)


# ═══════════════════════════════════════════════════════════════════════
#  9. Fidelity Bar
# ═══════════════════════════════════════════════════════════════════════

class TestFidelityBar(unittest.TestCase):
    """Test fidelity_bar()."""

    def test_basic(self):
        html = fidelity_bar(75)
        self.assertIn('fidelity-bar', html)
        self.assertIn('75%', html)

    def test_zero(self):
        html = fidelity_bar(0)
        self.assertIn('0%', html)

    def test_hundred(self):
        html = fidelity_bar(100)
        self.assertIn('100%', html)
        self.assertIn('var(--success)', html)


# ═══════════════════════════════════════════════════════════════════════
#  10. Charts
# ═══════════════════════════════════════════════════════════════════════

class TestCharts(unittest.TestCase):
    """Test donut_chart() and bar_chart()."""

    def test_donut_chart(self):
        slices = [('Pass', 80, SUCCESS), ('Fail', 20, FAIL)]
        html = donut_chart(slices)
        self.assertIn('donut', html)
        self.assertIn('Pass', html)
        self.assertIn('Fail', html)

    def test_donut_chart_empty(self):
        html = donut_chart([])
        self.assertIn('donut', html)

    def test_bar_chart(self):
        bars = [('SQL Server', 50, PBI_BLUE), ('Postgres', 30, TEAL)]
        html = bar_chart(bars, max_value=50)
        self.assertIn('bar-chart', html)
        self.assertIn('SQL Server', html)
        self.assertIn('Postgres', html)

    def test_bar_chart_zero_max(self):
        bars = [('Empty', 0, PBI_BLUE)]
        html = bar_chart(bars, max_value=0)
        self.assertIn('bar-chart', html)


# ═══════════════════════════════════════════════════════════════════════
#  11. Data Table
# ═══════════════════════════════════════════════════════════════════════

class TestDataTable(unittest.TestCase):
    """Test data_table()."""

    def test_basic_table(self):
        headers = ['Name', 'Score']
        rows = [['Alice', '90'], ['Bob', '85']]
        html = data_table(headers, rows)
        self.assertIn('<table', html)
        self.assertIn('Alice', html)
        self.assertIn('90', html)
        self.assertIn('Name', html)

    def test_sortable(self):
        html = data_table(['A'], [['1']], sortable=True)
        self.assertIn('sortable', html)
        self.assertIn('sortTable', html)

    def test_searchable(self):
        html = data_table(['A'], [['1']], searchable=True)
        self.assertIn('table-search', html)
        self.assertIn('filterTable', html)

    def test_empty_rows(self):
        html = data_table(['X', 'Y'], [])
        self.assertIn('<table', html)
        self.assertIn('X', html)

    def test_passes_html_through(self):
        """data_table allows raw HTML in cells (callers control escaping)."""
        html = data_table(['H'], [['<b>bold</b>']])
        self.assertIn('<b>bold</b>', html)


# ═══════════════════════════════════════════════════════════════════════
#  12. Tabs
# ═══════════════════════════════════════════════════════════════════════

class TestTabs(unittest.TestCase):
    """Test tab_bar() and tab_content()."""

    def test_tab_bar(self):
        tabs = [('overview', 'Overview', True), ('detail', 'Detail', False)]
        html = tab_bar('grp', tabs)
        self.assertIn('tab-bar', html)
        self.assertIn('Overview', html)
        self.assertIn('Detail', html)

    def test_tab_content_active(self):
        html = tab_content('grp', 'overview', '<p>Body</p>', active=True)
        self.assertIn('tab-content active', html)
        self.assertIn('Body', html)

    def test_tab_content_inactive(self):
        html = tab_content('grp', 'detail', '<p>X</p>', active=False)
        self.assertIn('tab-content', html)
        self.assertNotIn('tab-content active', html)


# ═══════════════════════════════════════════════════════════════════════
#  13. Card
# ═══════════════════════════════════════════════════════════════════════

class TestCard(unittest.TestCase):
    """Test card()."""

    def test_card_basic(self):
        html = card('<p>Content</p>')
        self.assertIn('class="card"', html)
        self.assertIn('Content', html)

    def test_card_with_title(self):
        html = card('<p>Body</p>', title='My Card')
        self.assertIn('My Card', html)
        self.assertIn('<h3>', html)


# ═══════════════════════════════════════════════════════════════════════
#  14. Heatmap Table
# ═══════════════════════════════════════════════════════════════════════

class TestHeatmapTable(unittest.TestCase):
    """Test heatmap_table()."""

    def test_basic_heatmap(self):
        row_labels = ['A', 'B']
        col_labels = ['A', 'B']
        matrix = [[100, 50], [50, 100]]
        html = heatmap_table(row_labels, col_labels, matrix)
        self.assertIn('heatmap', html)
        self.assertIn('A', html)
        self.assertIn('B', html)

    def test_empty(self):
        html = heatmap_table([], [], [])
        self.assertIn('<table', html)


# ═══════════════════════════════════════════════════════════════════════
#  15. Flow Diagram
# ═══════════════════════════════════════════════════════════════════════

class TestFlowDiagram(unittest.TestCase):
    """Test flow_diagram()."""

    def test_basic_flow(self):
        steps = [('Extract', False), ('Generate', True), ('Deploy', False)]
        html = flow_diagram(steps)
        self.assertIn('flow-container', html)
        self.assertIn('Extract', html)
        self.assertIn('Generate', html)
        self.assertIn('Deploy', html)

    def test_accent_step(self):
        steps = [('Active', True)]
        html = flow_diagram(steps)
        self.assertIn('accent', html)


# ═══════════════════════════════════════════════════════════════════════
#  16. Command Box
# ═══════════════════════════════════════════════════════════════════════

class TestCmdBox(unittest.TestCase):
    """Test cmd_box()."""

    def test_basic(self):
        html = cmd_box('python migrate.py workbook.twbx')
        self.assertIn('cmd-box', html)
        self.assertIn('python migrate.py workbook.twbx', html)

    def test_escapes_html(self):
        html = cmd_box('echo <script>')
        self.assertNotIn('<script>', html)


# ═══════════════════════════════════════════════════════════════════════
#  17. Integration — Full Document Round-Trip
# ═══════════════════════════════════════════════════════════════════════

class TestFullDocumentRoundTrip(unittest.TestCase):
    """Build a complete report to verify component integration."""

    def test_full_report(self):
        parts = []
        parts.append(html_open('Integration Test', subtitle='v27.1.0'))
        parts.append(stat_grid(
            stat_card('10', 'Workbooks') +
            stat_card('100%', 'Fidelity', accent='success')
        ))
        parts.append(section_open('summary', 'Summary', icon='📊'))
        parts.append(data_table(['Name', 'Score'], [['WB1', '100%']]))
        parts.append(section_close())
        parts.append(html_close(version='27.1.0'))
        doc = ''.join(parts)
        self.assertIn('<!DOCTYPE html>', doc)
        self.assertIn('</html>', doc)
        self.assertIn('stat-grid', doc)
        self.assertIn('section-header', doc)
        self.assertIn('27.1.0', doc)
        self.assertIn('WB1', doc)

    def test_css_included(self):
        doc = html_open('Test')
        self.assertIn(get_report_css()[:50], doc)

    def test_js_included(self):
        doc = html_close()
        self.assertIn('toggleSection', doc)


if __name__ == '__main__':
    unittest.main()
