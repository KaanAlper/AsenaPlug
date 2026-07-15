"""endpoint modülü — seçim + config.json r/w testleri (ağsız, Linux'ta koşar).

measure_* (gerçek socket) hariç her şey deterministik test edilir.
"""
import json

from asenaplug import endpoint as ep


# --- candidates ---
def test_candidates_unique_and_nonempty():
    c = ep.candidates()
    assert c, "aday listesi boş olmamalı"
    assert len(c) == len(set(c)), "adaylar tekrarsız olmalı"
    # dokümante default h3 endpoint her zaman aday olmalı (bilinen-iyi)
    assert "162.159.198.1" in c


def test_candidates_are_valid_ipv4():
    import ipaddress
    for ip in ep.candidates():
        ipaddress.IPv4Address(ip)   # geçersizse ValueError atar


# --- pick_best (pure) ---
def test_pick_best_lowest_latency():
    res = [("1.1.1.1", 42.0), ("2.2.2.2", 12.5), ("3.3.3.3", 30.0)]
    assert ep.pick_best(res) == "2.2.2.2"


def test_pick_best_empty_is_none():
    assert ep.pick_best([]) is None


# --- apply / backup / restore (config.json round-trip) ---
_IDENTITY = {
    "private_key": "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----\n",
    "endpoint_v4": "162.159.198.1",
    "endpoint_h2_v4": "162.159.198.2",
    "endpoint_pub_key": "-----BEGIN PUBLIC KEY-----\nXYZ\n-----END PUBLIC KEY-----\n",
    "license": "SECRET",
    "id": "00000000-0000-0000-0000-000000000000",
    "ipv4": "172.16.0.2",
}


def _cfg(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(_IDENTITY, indent=2), encoding="utf-8")
    return p


def _redirect(monkeypatch, tmp_path):
    monkeypatch.setattr(ep, "BACKUP_FILE", tmp_path / "endpoint.bak")
    monkeypatch.setattr(ep, "APPLIED_FILE", tmp_path / "endpoint.applied")


def test_apply_changes_only_endpoint_v4(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    cfg = _cfg(tmp_path)
    assert ep.apply_endpoint("162.159.192.5", cfg)
    after = json.loads(cfg.read_text())
    assert after["endpoint_v4"] == "162.159.192.5"
    # geri kalan kimlik alanları AYNEN korunmalı (PEM/gizli anahtarlar dahil)
    for k, v in _IDENTITY.items():
        if k != "endpoint_v4":
            assert after[k] == v, f"{k} korunmadı"


def test_apply_writes_backup_and_applied(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    cfg = _cfg(tmp_path)
    ep.apply_endpoint("162.159.192.5", cfg)
    assert ep.was_applied()
    assert (tmp_path / "endpoint.bak").read_text().strip() == "162.159.198.1"


def test_apply_same_ip_is_noop(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    cfg = _cfg(tmp_path)
    assert ep.apply_endpoint("162.159.198.1", cfg)   # zaten seçili
    assert not ep.was_applied(), "no-op'ta işaret bırakılmamalı"


def test_backup_not_overwritten_on_second_apply(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    cfg = _cfg(tmp_path)
    ep.apply_endpoint("162.159.192.5", cfg)   # orijinal .198.1 yedeklenir
    ep.apply_endpoint("162.159.192.6", cfg)   # yedek .198.1 KALMALI (.192.5 değil)
    assert (tmp_path / "endpoint.bak").read_text().strip() == "162.159.198.1"


def test_restore_reverts_to_original_and_clears(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    cfg = _cfg(tmp_path)
    ep.apply_endpoint("162.159.192.5", cfg)
    assert ep.restore_endpoint(cfg)
    assert json.loads(cfg.read_text())["endpoint_v4"] == "162.159.198.1"
    assert not ep.was_applied(), "restore sonrası işaret temizlenmeli (döngü yok)"


def test_restore_without_backup_is_safe(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    cfg = _cfg(tmp_path)
    assert ep.restore_endpoint(cfg) is False   # yedek yok -> güvenli False
