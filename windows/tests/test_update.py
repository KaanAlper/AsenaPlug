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


# --- sha256 bütünlük ---
def test_sha256_file_matches_known(tmp_path):
    import hashlib
    p = tmp_path / "x.bin"
    data = b"AsenaPlug"
    p.write_bytes(data)
    assert u.sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_sha256_file_missing_is_none(tmp_path):
    assert u.sha256_file(tmp_path / "yok.bin") is None


def test_parse_sha256_formats():
    h = "a" * 64
    assert u.parse_sha256(h) == h
    assert u.parse_sha256(f"{h}  AsenaPlug.exe") == h      # 'hash  dosya' formatı
    assert u.parse_sha256(h.upper()) == h                  # küçük harfe indir
    assert u.parse_sha256("") is None
    assert u.parse_sha256("kısa") is None
    assert u.parse_sha256("z" * 64) is None                # hex değil


def test_verify_download_no_sha_url_is_permissive(tmp_path):
    # Eski release (sha asset yok) -> doğrulama atlanır, True (geriye uyumlu)
    p = tmp_path / "a.exe"
    p.write_bytes(b"x")
    assert u.verify_download(p, None) is True


def _patch_urlopen_raw(monkeypatch, data=b"", exc=None):
    class _Raw:
        def __init__(self, b):
            self._b = b
        def read(self, *a):
            return self._b
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    def fake(req, timeout=0):
        if exc:
            raise exc
        return _Raw(data)
    monkeypatch.setattr(u.urllib.request, "urlopen", fake)


def test_verify_download_sha_advertised_but_fetch_fails_is_fail_closed(tmp_path, monkeypatch):
    # sha REKLAM edildi (sha_url var) ama alınamadı (ağ düşmanı bloklamış olabilir)
    # -> imzayı atlama, çalıştırma (False).
    p = tmp_path / "a.exe"; p.write_bytes(b"x")
    _patch_urlopen_raw(monkeypatch, exc=OSError("blocked"))
    assert u.verify_download(p, "http://x/a.exe.sha256") is False


def test_verify_download_sha_match_is_true(tmp_path, monkeypatch):
    import hashlib
    p = tmp_path / "a.exe"; data = b"AsenaPlug"; p.write_bytes(data)
    h = hashlib.sha256(data).hexdigest()
    _patch_urlopen_raw(monkeypatch, data=f"{h}  AsenaPlug.exe".encode())
    assert u.verify_download(p, "http://x/a.exe.sha256") is True


def test_verify_download_sha_mismatch_is_false(tmp_path, monkeypatch):
    p = tmp_path / "a.exe"; p.write_bytes(b"tampered")
    _patch_urlopen_raw(monkeypatch, data=("a" * 64 + "  AsenaPlug.exe").encode())
    assert u.verify_download(p, "http://x/a.exe.sha256") is False


# --- check_latest (mock'lu ağ; None vs UP_TO_DATE vs tuple ayrımı) ---
class _FakeResp:
    def __init__(self, payload):
        import json as _j
        self._b = _j.dumps(payload).encode("utf-8")

    def read(self, *a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch, payload=None, exc=None):
    def fake(req, timeout=0):
        if exc:
            raise exc
        return _FakeResp(payload)
    monkeypatch.setattr(u.urllib.request, "urlopen", fake)


_EXE = {"name": "AsenaPlug.exe", "browser_download_url": "http://x/AsenaPlug.exe"}
_SHA = {"name": "AsenaPlug.exe.sha256", "browser_download_url": "http://x/AsenaPlug.exe.sha256"}


def test_check_latest_new_version_with_exe_and_sha(monkeypatch):
    monkeypatch.setattr(u, "APP_VERSION", "1.0.0")
    _patch_urlopen(monkeypatch, {"tag_name": "v1.0.5", "body": "notes", "assets": [_EXE, _SHA]})
    assert u.check_latest() == ("v1.0.5", "http://x/AsenaPlug.exe", "notes",
                                "http://x/AsenaPlug.exe.sha256")


def test_check_latest_new_version_without_sha(monkeypatch):
    monkeypatch.setattr(u, "APP_VERSION", "1.0.0")
    _patch_urlopen(monkeypatch, {"tag_name": "v1.0.5", "body": "", "assets": [_EXE]})
    res = u.check_latest()
    assert res[0] == "v1.0.5" and res[3] is None      # sha_url yok -> None


def test_check_latest_up_to_date(monkeypatch):
    monkeypatch.setattr(u, "APP_VERSION", "1.0.5")
    _patch_urlopen(monkeypatch, {"tag_name": "v1.0.5", "assets": [_EXE]})
    assert u.check_latest() == u.UP_TO_DATE


def test_check_latest_newer_but_no_exe_asset(monkeypatch):
    monkeypatch.setattr(u, "APP_VERSION", "1.0.0")
    _patch_urlopen(monkeypatch, {"tag_name": "v1.0.5", "assets": [_SHA]})
    assert u.check_latest() == u.UP_TO_DATE            # .exe yoksa güncelleme yok

def test_check_latest_network_error_is_none(monkeypatch):
    # Ağ hatası -> None ('denetlenemedi'), UP_TO_DATE ('güncelsin') DEĞİL
    _patch_urlopen(monkeypatch, exc=OSError("no net"))
    assert u.check_latest() is None
