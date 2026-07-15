"""update modülü — sürüm karşılaştırma (saf, ağsız) testleri."""
from asenaplug import update as u


def test_parse_version():
    assert u.parse_version("v1.2.3") == (1, 2, 3)
    assert u.parse_version("1.0.0") == (1, 0, 0)
    assert u.parse_version("v2.0") == (2, 0)
    assert u.parse_version("") == (0,)
    assert u.parse_version("garbage") == (0,)


def test_is_newer_basic():
    assert u.is_newer("v1.0.1", "1.0.0")
    assert u.is_newer("v2.0.0", "1.9.9")
    assert not u.is_newer("v1.0.0", "1.0.0")
    assert not u.is_newer("v0.9.9", "1.0.0")


def test_is_newer_numeric_not_lexical():
    # String karşılaştırmada "1.0.10" < "1.0.9" olurdu — tuple doğru sıralamalı
    assert u.is_newer("v1.0.10", "1.0.9")
    assert u.is_newer("v1.0.100", "1.0.99")
    assert not u.is_newer("v1.0.9", "1.0.10")


def test_auto_build_numbers_increase():
    # Workflow 1.0.<run_number> üretir; artan run_number hep yeni sayılmalı
    assert u.is_newer("v1.0.42", "1.0.41")
    assert u.is_newer("v1.0.1000", "1.0.999")
