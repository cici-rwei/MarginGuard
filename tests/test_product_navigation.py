"""Product navigation contracts; numerical engine checks stay in existing suites.

These tests inspect server-rendered HTML. Actual JavaScript parameter propagation,
hash navigation and responsive layout must also be exercised in the browser.
"""
from html.parser import HTMLParser
import unittest
from urllib.parse import urlsplit

from app import create_app


class Element:
    def __init__(self, tag, attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def elements(self, tag=None):
        result = []
        for child in self.children:
            if isinstance(child, Element):
                if tag is None or child.tag == tag:
                    result.append(child)
                result.extend(child.elements(tag))
        return result

    def text(self):
        return ' '.join(''.join(child.text() if isinstance(child, Element) else child
                                for child in self.children).split())


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element('document')
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs)
        self.stack[-1].children.append(element)
        if tag not in self.VOID:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Element(tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def nav(self, label):
        return [node for node in self.root.elements('nav')
                if node.attrs.get('aria-label') == label]


class ProductNavigationTests(unittest.TestCase):
    BUSINESS = [('/', 'Business Overview'), ('/forecasting', 'Demand Forecasting'),
                ('/inventory', 'Inventory & Risk'), ('/scenarios', 'Financial Decision Lab')]
    MARKET = [('/market#market-overview', 'Australian Retail Market Overview'),
              ('/market#industry', 'Industry Performance'),
              ('/market#states', 'State Comparison'),
              ('/market#financial', 'Retail Financial Indicators'),
              ('/market#dynamics', 'Business Dynamics')]

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return Document(response.get_data(as_text=True))

    def one_nav(self, document, label):
        matches = document.nav(label)
        self.assertEqual(len(matches), 1, label)
        return matches[0]

    def test_five_existing_page_routes_and_consistent_titles(self):
        page_routes = {rule.rule for rule in self.app.url_map.iter_rules()
                       if not rule.rule.startswith(('/api/', '/static/'))}
        self.assertEqual(page_routes, {'/', '/forecasting', '/inventory', '/scenarios', '/market'})
        for route, title in self.BUSINESS + [('/market', 'Australian Retail Market Overview')]:
            with self.subTest(route=route):
                doc = self.page(route)
                headings = doc.root.elements('h1')
                self.assertEqual(len(headings), 1)
                self.assertEqual(headings[0].text(), title)
                self.assertIn(title, doc.root.elements('title')[0].text())

    def test_workspaces_are_distinct_and_business_is_default(self):
        for route, _ in self.BUSINESS + [('/market', '')]:
            with self.subTest(route=route):
                links = self.one_nav(self.page(route), 'Workspaces').elements('a')
                self.assertEqual([node.text() for node in links], ['My Business', 'Market Intelligence'])
                self.assertEqual([urlsplit(node.attrs['href']).path for node in links], ['/', '/market'])
                current = [node for node in links if node.attrs.get('aria-current') == 'true']
                self.assertEqual(len(current), 1)
                self.assertEqual(current[0].text(), 'Market Intelligence' if route == '/market' else 'My Business')

    def test_business_navigation_has_four_pages_and_one_current_page(self):
        for route, _ in self.BUSINESS:
            with self.subTest(route=route):
                doc = self.page(route)
                links = self.one_nav(doc, 'My Business navigation').elements('a')
                self.assertEqual([urlsplit(node.attrs['href']).path for node in links],
                                 [path for path, _ in self.BUSINESS])
                for node, (_, label) in zip(links, self.BUSINESS):
                    self.assertIn(label, node.text())
                    self.assertIn('data-business-link', node.attrs)
                active = [node for node in links if node.attrs.get('aria-current') == 'page']
                self.assertEqual(len(active), 1)
                self.assertEqual(urlsplit(active[0].attrs['href']).path, route)
                self.assertEqual(doc.nav('Market Intelligence navigation'), [])

    def test_workflow_current_step_and_next_action_follow_existing_routes(self):
        labels = ['Overview', 'Forecast', 'Inventory', 'Decision Lab']
        actions = ['View demand forecast', 'Assess inventory risk',
                   'Compare financial strategies', 'Review business overview']
        for index, (route, _) in enumerate(self.BUSINESS):
            with self.subTest(route=route):
                doc = self.page(route)
                links = self.one_nav(doc, 'Business workflow').elements('a')
                self.assertEqual(len(links), 4)
                for link, label, (path, _) in zip(links, labels, self.BUSINESS):
                    self.assertIn(label, link.text())
                    self.assertEqual(urlsplit(link.attrs['href']).path, path)
                    self.assertIn('data-business-link', link.attrs)
                current = [link for link in links if link.attrs.get('aria-current') == 'step']
                self.assertEqual(len(current), 1)
                self.assertEqual(urlsplit(current[0].attrs['href']).path, route)
                next_links = [link for link in doc.root.elements('a')
                              if 'flow-next' in link.attrs.get('class', '').split()]
                self.assertEqual(len(next_links), 1)
                self.assertIn(actions[index], next_links[0].text())
                self.assertEqual(urlsplit(next_links[0].attrs['href']).path,
                                 self.BUSINESS[(index + 1) % 4][0])
                self.assertIn('data-business-link', next_links[0].attrs)

    def test_home_explains_demo_assumptions_and_historical_forecast_context(self):
        doc = self.page('/')
        text = doc.root.text()
        self.assertIn('Retail Risk & Financial Decision Intelligence', text)
        self.assertIn('Business data: Walmart M5 Demo', text)
        self.assertRegex(text, r'(?i)historical sales.{0,80}Walmart M5')
        self.assertRegex(text, r'(?i)(inventory|stock).{0,120}(assumption|hypothetical)')
        self.assertRegex(text, r'(?i)(no real business account|not connected to.{0,30}business account)')
        self.assertRegex(text, r'(?i)(forecast.{0,100}historical|historical.{0,100}forecast)')

    def test_market_has_five_group_links_and_keeps_all_seven_sections(self):
        doc = self.page('/market')
        links = self.one_nav(doc, 'Market Intelligence navigation').elements('a')
        self.assertEqual([(link.attrs['href'], link.text()) for link in links], self.MARKET)
        for link in links:
            self.assertNotIn('data-business-link', link.attrs)
        ids = {node.attrs.get('id') for node in doc.root.elements()}
        self.assertTrue({'market-overview', 'consumer', 'industry', 'states',
                         'financial', 'ratio', 'dynamics'}.issubset(ids))
        self.assertEqual(doc.nav('Market sections'), [])
        text = doc.root.text()
        for marker in ('Experimental', 'Seasonally Adjusted', 'AUD', 'Australian Bureau of Statistics'):
            self.assertIn(marker, text)

    def test_business_and_market_data_controls_are_separate(self):
        for route, _ in self.BUSINESS + [('/market', '')]:
            with self.subTest(route=route):
                doc = self.page(route)
                ids = {node.attrs.get('id') for node in doc.root.elements()}
                scripts = {node.attrs.get('src') for node in doc.root.elements('script')}
                if route == '/market':
                    self.assertFalse({'product', 'store', 'overview-kpis'} & ids)
                    self.assertEqual(doc.nav('Business workflow'), [])
                    self.assertIn('/static/js/market.js', scripts)
                    self.assertNotIn('/static/js/main.js', scripts)
                else:
                    self.assertTrue({'product', 'store'}.issubset(ids))
                    self.assertNotIn('market-kpis', ids)
                    self.assertIn('/static/js/main.js', scripts)
                    self.assertNotIn('/static/js/market.js', scripts)

    def test_existing_product_store_deep_links_remain_accessible(self):
        for route, title in self.BUSINESS:
            with self.subTest(route=route):
                doc = self.page(route + '?item_id=HOUSEHOLD_1_535&store_id=CA_1')
                self.assertEqual(doc.root.elements('h1')[0].text(), title)
                selections = {node.attrs.get('id') for node in doc.root.elements('select')}
                self.assertTrue({'product', 'store'}.issubset(selections))


if __name__ == '__main__':
    unittest.main()
