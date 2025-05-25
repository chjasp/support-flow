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
    second = DummyResponse("<html><main><h1>Title</h1><p>Hello</p></main></html>")
    processor.session.get = MagicMock(side_effect=[first, second])

    result = processor.scrape_url("https://example.com")
    assert result["status"] == "success"
    assert result["title"] == "Title"
    assert "Hello" in result["content"]
