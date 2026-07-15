"""i18n modülü — çeviri bütünlüğü + davranış testleri.

En değerlisi test_language_key_parity: her dilde EN'deki TÜM key'ler olmalı,
fazlası olmamalı. Gelecekte string ekleyince eksik çeviriyi CI'da yakalar.
"""
from asenaplug import i18n
from asenaplug.i18n import t, TRANSLATIONS, LANGUAGES


def teardown_function(_):
    i18n.set_language("en")   # test izolasyonu (global aktif dil)


def test_language_key_parity():
    en_keys = set(TRANSLATIONS["en"])
    for code, _name in LANGUAGES:
        assert code in TRANSLATIONS, f"{code}: çeviri tablosu yok"
        keys = set(TRANSLATIONS[code])
        assert not (en_keys - keys), f"{code}: eksik key {en_keys - keys}"
        assert not (keys - en_keys), f"{code}: fazla key {keys - en_keys}"


def test_languages_and_translations_match():
    codes = {c for c, _ in LANGUAGES}
    assert codes == set(TRANSLATIONS), "LANGUAGES ile TRANSLATIONS kodları uyuşmuyor"


def test_active_language_switch():
    i18n.set_language("tr")
    assert t("connect") == "Bağlan"
    i18n.set_language("de")
    assert t("connect") == "Verbinden"
    i18n.set_language("fr")
    assert t("quit") == "Quitter"


def test_invalid_language_ignored():
    i18n.set_language("en")
    i18n.set_language("zz")            # geçersiz -> yok say
    assert i18n.get_language() == "en"


def test_missing_key_returns_key():
    i18n.set_language("en")
    assert t("__no_such_key__") == "__no_such_key__"


def test_format_params_substituted():
    i18n.set_language("en")
    assert t("notify_added", domain="x.com") == "x.com added. Use 'Reload DNS' to activate."
    assert "{" not in t("status_connected", detail="HTTP/2 · Everything")


def test_native_names():
    names = dict(LANGUAGES)
    assert names["tr"] == "Türkçe"
    assert names["de"] == "Deutsch"
    assert names["es"] == "Español"
    assert names["fr"] == "Français"
    assert names["en"] == "English"


def test_no_stray_format_placeholders_in_static_keys():
    # Parametresiz key'lerde süslü paren kalmamalı (yanlış {..} yakalar)
    static = ["connect", "disconnect", "quit", "hdr_transport", "hdr_routing",
              "scope_selective", "scope_full", "bl_edit", "bl_add", "bl_reload",
              "notify_disconnected", "notify_timeout", "status_disconnected"]
    for code, _ in LANGUAGES:
        i18n.set_language(code)
        for key in static:
            assert "{" not in t(key), f"{code}/{key} beklenmeyen placeholder"
