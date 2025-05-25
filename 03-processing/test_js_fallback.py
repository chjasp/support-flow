import sys
import types
from unittest.mock import MagicMock

# Provide dummy modules to avoid network calls during import

dummy_tiktoken = types.ModuleType('tiktoken')
class DummyTokenizer:
    def encode(self, text):
        return list(range(len(text)))
    def decode(self, tokens):
        return 'x' * len(tokens)

def get_encoding(name):
    return DummyTokenizer()

dummy_tiktoken.get_encoding = get_encoding
sys.modules['tiktoken'] = dummy_tiktoken
dummy_vertexai = MagicMock()
sys.modules['vertexai'] = dummy_vertexai
sys.modules['vertexai.language_models'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sql_connector_mock = MagicMock()
sys.modules['google.cloud.sql'] = MagicMock()
sys.modules['google.cloud.sql.connector'] = MagicMock(Connector=MagicMock(return_value=MagicMock()))
dummy_requests = types.ModuleType('requests')
class DummyResp:
    def __init__(self):
        self.status_code = 200
        self._content = b''
    @property
    def content(self):
        return self._content
    def raise_for_status(self):
        pass
class DummySession:
    def __init__(self):
        self.headers = {}
    def get(self, url, timeout=30):
        return DummyResp()
dummy_requests.Response = DummyResp
dummy_requests.Session = DummySession
sys.modules['requests'] = dummy_requests
dummy_bs4 = types.ModuleType('bs4')
import re

class DummyNode:
    def __init__(self, text=""):
        self.text = text
    def decompose(self):
        pass
    def get_text(self, separator='\n', strip=True):
        cleaned = re.sub(r'<[^>]+>', '', self.text)
        return cleaned.strip()

class DummySoup(DummyNode):
    def __init__(self, html, parser=None):
        if isinstance(html, bytes):
            html = html.decode()
        super().__init__(html)
        self.html = html
    def find(self, tag, *args, **kwargs):
        m = re.search(fr'<{tag}[^>]*>(.*?)</{tag}>', self.html, re.S)
        if m:
            return DummyNode(m.group(1))
        return None
    def __call__(self, tags):
        return []
    @property
    def body(self):
        return DummyNode(self.html)

dummy_bs4.BeautifulSoup = DummySoup
sys.modules['bs4'] = dummy_bs4
sys.modules['numpy'] = MagicMock()
sys.modules['umap'] = MagicMock()
sys.modules['sklearn'] = MagicMock()
sys.modules['sklearn.preprocessing'] = MagicMock(StandardScaler=MagicMock())

dummy_requests_html = types.ModuleType('requests_html')
dummy_requests_html.HTMLSession = MagicMock(return_value=MagicMock())
dummy_requests_html.AsyncHTMLSession = MagicMock(return_value=MagicMock())
sys.modules['requests_html'] = dummy_requests_html

from scraper import WebDocumentProcessor

class DummyResponse:
    def __init__(self, text):
        self.content = text.encode()
        self.status_code = 200
    def raise_for_status(self):
        pass


def test_js_fallback():
    processor = WebDocumentProcessor()
    first = DummyResponse("Registry Please enable Javascript to use this application")
    processor.session.get = MagicMock(return_value=first)
    js_response = MagicMock()
    js_response.status_code = 200
    js_response.html = MagicMock()
    js_response.html.html = "<html><main><h1>Title</h1><p>Hello</p></main></html>"
    js_response.html.render = MagicMock()
    processor.js_session.get = MagicMock(return_value=js_response)

    result = processor.scrape_url("https://example.com")
    assert result["status"] == "success"
    assert result["title"] == "Title"
    assert "Hello" in result["content"]
