"""Hafif i18n — dict tabanlı, bağımlılıksız, RUNTIME dil değişimli.

Neden Qt'nin QTranslator/.ts/.qm değil: onlar lupdate/lrelease derleme + binary
gömme ister (PyInstaller'da zahmet). Burada tek Python dict = sıfır derleme,
çeviri eklemek trivial, yeniden başlatmadan dil değişir.

Kullanım:
    from .i18n import t
    t("connect")                      -> aktif dile göre "Connect"/"Bağlan"/...
    t("notify_added", domain="x.com") -> parametreli (.format)

- Eksik çeviri EN'e, o da yoksa key'in kendisine düşer (asla patlamaz).
- Aktif dil kalıcı: CONFIG_DIR/lang. init(os_lang) ilk kurulumda OS dilini seçer
  (listede yoksa 'en'), sonrakinde kayıttan okur.
- HTTP/2 · HTTP/3 teknik etiketler ÇEVRİLMEZ (tray.py'de sabit).
"""
from .paths import CONFIG_DIR

LANG_FILE = CONFIG_DIR / "lang"

# (kod, yerel isim) — dil menüsünde bu sırayla, kendi dilinde gösterilir.
LANGUAGES = [
    ("en", "English"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("fr", "Français"),
    ("tr", "Türkçe"),
]

TRANSLATIONS = {
    "en": {
        "connect": "Connect",
        "disconnect": "Disconnect",
        "status_connected": "Status: Connected — {detail}",
        "status_disconnected": "Status: Not connected",
        "hdr_transport": "Transport",
        "hdr_routing": "Routing",
        "scope_selective": "Blacklist only",
        "scope_full": "Everything",
        "killswitch": "Kill-switch (cut traffic if tunnel drops)",
        "blacklist_menu": "Blacklist",
        "language": "Language",
        "quit": "Quit",
        "bl_count": "{n} domains saved",
        "bl_full_note": "(in Everything mode all traffic already uses Asena)",
        "bl_edit": "Edit…",
        "bl_add": "Add domain…",
        "bl_reload": "Reload DNS",
        "dlg_add_title": "Blacklist — Add domain",
        "dlg_add_label": "Domain:",
        "notify_added": "{domain} added. Use 'Reload DNS' to activate.",
        "notify_not_added": "Not added (empty or already exists).",
        "notify_dns_reloading": "Reloading DNS…",
        "notify_connected": "Connected ({detail})",
        "notify_disconnected": "Disconnected",
        "notify_timeout": "Operation timed out — try again.",
        "tip_connected": "{app}: Connected ({detail})",
        "tip_disconnected": "{app}: Disconnected",
        "notify_title_blacklist": "Blacklist",
        "check_updates": "Check for updates",
        "upd_checking": "Checking for updates…",
        "upd_none": "You're on the latest version.",
        "upd_available_title": "Update available",
        "upd_available": "New version {ver} — download and install?",
        "upd_toast_header": "Updating AsenaPlug",
        "upd_downloading": "Downloading…",
        "upd_installing": "Installing, restarting…",
        "upd_fail": "Update failed. Try again.",
        "upd_check_fail": "Couldn't check (connection?).",
        "setup_running": "Setting up…",
        "setup_done": "Ready — in the system tray.",
        "notify_apply_on_connect": "Asena is off — changes apply automatically when you connect.",
        "notify_added_offline": "{domain} added — active automatically when you connect.",
        "registering": "Registering device (one-time setup)…",
        "register_fail": "Device registration failed — check your connection and try again.",
        "optimize_endpoint": "Speed up connection",
        "opt_scanning": "Finding the fastest server…",
        "opt_fail": "Couldn't reach any server (connection?).",
        "opt_done": "Fastest server selected: {ip} ({ms} ms).",
        "opt_done_reconnect": "Fastest server: {ip} ({ms} ms) — reconnect to apply.",
        "opt_reverted": "Server didn't respond — reverted to the default.",
        "notify_transport_fallback": "HTTP/3 unavailable on this network — switched to {got}.",
        "notify_net_reapply": "Network changed — refreshing the tunnel…",
    },
    "de": {
        "connect": "Verbinden",
        "disconnect": "Trennen",
        "status_connected": "Status: Verbunden — {detail}",
        "status_disconnected": "Status: Nicht verbunden",
        "hdr_transport": "Transport",
        "hdr_routing": "Routing",
        "scope_selective": "Nur Blacklist",
        "scope_full": "Alles",
        "killswitch": "Kill-Switch (Verkehr kappen, wenn Tunnel ausfällt)",
        "blacklist_menu": "Blacklist",
        "language": "Sprache",
        "quit": "Beenden",
        "bl_count": "{n} Domains gespeichert",
        "bl_full_note": "(im Modus Alles läuft bereits alles über Asena)",
        "bl_edit": "Bearbeiten…",
        "bl_add": "Domain hinzufügen…",
        "bl_reload": "DNS neu laden",
        "dlg_add_title": "Blacklist — Domain hinzufügen",
        "dlg_add_label": "Domain:",
        "notify_added": "{domain} hinzugefügt. Mit 'DNS neu laden' aktivieren.",
        "notify_not_added": "Nicht hinzugefügt (leer oder bereits vorhanden).",
        "notify_dns_reloading": "DNS wird neu geladen…",
        "notify_connected": "Verbunden ({detail})",
        "notify_disconnected": "Getrennt",
        "notify_timeout": "Zeitüberschreitung — bitte erneut versuchen.",
        "tip_connected": "{app}: Verbunden ({detail})",
        "tip_disconnected": "{app}: Getrennt",
        "notify_title_blacklist": "Blacklist",
        "check_updates": "Nach Updates suchen",
        "upd_checking": "Suche nach Updates…",
        "upd_none": "Du hast die neueste Version.",
        "upd_available_title": "Update verfügbar",
        "upd_available": "Neue Version {ver} — herunterladen und installieren?",
        "upd_toast_header": "AsenaPlug wird aktualisiert",
        "upd_downloading": "Wird heruntergeladen…",
        "upd_installing": "Installation, Neustart…",
        "upd_fail": "Update fehlgeschlagen. Erneut versuchen.",
        "upd_check_fail": "Prüfung fehlgeschlagen (Verbindung?).",
        "setup_running": "Wird eingerichtet…",
        "setup_done": "Bereit — im Infobereich.",
        "notify_apply_on_connect": "Asena ist aus — Änderungen werden beim Verbinden übernommen.",
        "notify_added_offline": "{domain} hinzugefügt — beim Verbinden automatisch aktiv.",
        "registering": "Gerät wird registriert (einmalige Einrichtung)…",
        "register_fail": "Geräteregistrierung fehlgeschlagen — Verbindung prüfen und erneut versuchen.",
        "optimize_endpoint": "Verbindung beschleunigen",
        "opt_scanning": "Schnellsten Server suchen…",
        "opt_fail": "Kein Server erreichbar (Verbindung?).",
        "opt_done": "Schnellster Server gewählt: {ip} ({ms} ms).",
        "opt_done_reconnect": "Schnellster Server: {ip} ({ms} ms) — zum Übernehmen neu verbinden.",
        "opt_reverted": "Server antwortete nicht — Standard wiederhergestellt.",
        "notify_transport_fallback": "HTTP/3 in diesem Netz nicht verfügbar — auf {got} umgeschaltet.",
        "notify_net_reapply": "Netzwerk gewechselt — Tunnel wird aufgefrischt…",
    },
    "es": {
        "connect": "Conectar",
        "disconnect": "Desconectar",
        "status_connected": "Estado: Conectado — {detail}",
        "status_disconnected": "Estado: No conectado",
        "hdr_transport": "Transporte",
        "hdr_routing": "Enrutamiento",
        "scope_selective": "Solo lista negra",
        "scope_full": "Todo",
        "killswitch": "Kill-switch (cortar tráfico si cae el túnel)",
        "blacklist_menu": "Lista negra",
        "language": "Idioma",
        "quit": "Salir",
        "bl_count": "{n} dominios guardados",
        "bl_full_note": "(en modo Todo, todo el tráfico ya pasa por Asena)",
        "bl_edit": "Editar…",
        "bl_add": "Añadir dominio…",
        "bl_reload": "Recargar DNS",
        "dlg_add_title": "Lista negra — Añadir dominio",
        "dlg_add_label": "Dominio:",
        "notify_added": "{domain} añadido. Usa 'Recargar DNS' para activar.",
        "notify_not_added": "No añadido (vacío o ya existe).",
        "notify_dns_reloading": "Recargando DNS…",
        "notify_connected": "Conectado ({detail})",
        "notify_disconnected": "Desconectado",
        "notify_timeout": "Se agotó el tiempo — inténtalo de nuevo.",
        "tip_connected": "{app}: Conectado ({detail})",
        "tip_disconnected": "{app}: Desconectado",
        "notify_title_blacklist": "Lista negra",
        "check_updates": "Buscar actualizaciones",
        "upd_checking": "Buscando actualizaciones…",
        "upd_none": "Ya tienes la última versión.",
        "upd_available_title": "Actualización disponible",
        "upd_available": "Nueva versión {ver} — ¿descargar e instalar?",
        "upd_toast_header": "Actualizando AsenaPlug",
        "upd_downloading": "Descargando…",
        "upd_installing": "Instalando, reiniciando…",
        "upd_fail": "Actualización fallida. Inténtalo de nuevo.",
        "upd_check_fail": "No se pudo comprobar (¿conexión?).",
        "setup_running": "Configurando…",
        "setup_done": "Listo — en la bandeja.",
        "notify_apply_on_connect": "Asena está apagado — los cambios se aplican al conectar.",
        "notify_added_offline": "{domain} añadido — activo automáticamente al conectar.",
        "registering": "Registrando el dispositivo (configuración única)…",
        "register_fail": "Falló el registro del dispositivo — comprueba la conexión e inténtalo de nuevo.",
        "optimize_endpoint": "Acelerar la conexión",
        "opt_scanning": "Buscando el servidor más rápido…",
        "opt_fail": "No se pudo contactar ningún servidor (¿conexión?).",
        "opt_done": "Servidor más rápido elegido: {ip} ({ms} ms).",
        "opt_done_reconnect": "Servidor más rápido: {ip} ({ms} ms) — reconéctate para aplicar.",
        "opt_reverted": "El servidor no respondió — se restauró el predeterminado.",
        "notify_transport_fallback": "HTTP/3 no disponible en esta red — se cambió a {got}.",
        "notify_net_reapply": "La red cambió — actualizando el túnel…",
    },
    "fr": {
        "connect": "Se connecter",
        "disconnect": "Se déconnecter",
        "status_connected": "État : Connecté — {detail}",
        "status_disconnected": "État : Non connecté",
        "hdr_transport": "Transport",
        "hdr_routing": "Routage",
        "scope_selective": "Liste noire uniquement",
        "scope_full": "Tout",
        "killswitch": "Kill-switch (couper le trafic si le tunnel tombe)",
        "blacklist_menu": "Liste noire",
        "language": "Langue",
        "quit": "Quitter",
        "bl_count": "{n} domaines enregistrés",
        "bl_full_note": "(en mode Tout, tout le trafic passe déjà par Asena)",
        "bl_edit": "Modifier…",
        "bl_add": "Ajouter un domaine…",
        "bl_reload": "Recharger le DNS",
        "dlg_add_title": "Liste noire — Ajouter un domaine",
        "dlg_add_label": "Domaine :",
        "notify_added": "{domain} ajouté. Utilisez « Recharger le DNS » pour activer.",
        "notify_not_added": "Non ajouté (vide ou déjà présent).",
        "notify_dns_reloading": "Rechargement du DNS…",
        "notify_connected": "Connecté ({detail})",
        "notify_disconnected": "Déconnecté",
        "notify_timeout": "Délai dépassé — réessayez.",
        "tip_connected": "{app} : Connecté ({detail})",
        "tip_disconnected": "{app} : Déconnecté",
        "notify_title_blacklist": "Liste noire",
        "check_updates": "Rechercher des mises à jour",
        "upd_checking": "Recherche de mises à jour…",
        "upd_none": "Vous avez la dernière version.",
        "upd_available_title": "Mise à jour disponible",
        "upd_available": "Nouvelle version {ver} — télécharger et installer ?",
        "upd_toast_header": "Mise à jour d'AsenaPlug",
        "upd_downloading": "Téléchargement…",
        "upd_installing": "Installation, redémarrage…",
        "upd_fail": "Échec de la mise à jour. Réessayez.",
        "upd_check_fail": "Vérification impossible (connexion ?).",
        "setup_running": "Installation…",
        "setup_done": "Prêt — dans la barre d'état.",
        "notify_apply_on_connect": "Asena est éteint — les changements s'appliquent à la connexion.",
        "notify_added_offline": "{domain} ajouté — actif automatiquement à la connexion.",
        "registering": "Enregistrement de l'appareil (configuration unique)…",
        "register_fail": "Échec de l'enregistrement de l'appareil — vérifiez la connexion et réessayez.",
        "optimize_endpoint": "Accélérer la connexion",
        "opt_scanning": "Recherche du serveur le plus rapide…",
        "opt_fail": "Aucun serveur joignable (connexion ?).",
        "opt_done": "Serveur le plus rapide choisi : {ip} ({ms} ms).",
        "opt_done_reconnect": "Serveur le plus rapide : {ip} ({ms} ms) — reconnectez-vous pour appliquer.",
        "opt_reverted": "Le serveur n'a pas répondu — valeur par défaut restaurée.",
        "notify_transport_fallback": "HTTP/3 indisponible sur ce réseau — basculé sur {got}.",
        "notify_net_reapply": "Réseau changé — actualisation du tunnel…",
    },
    "tr": {
        "connect": "Bağlan",
        "disconnect": "Bağlantıyı kes",
        "status_connected": "Durum: Bağlı — {detail}",
        "status_disconnected": "Durum: Bağlı değil",
        "hdr_transport": "Transport",
        "hdr_routing": "Yönlendirme",
        "scope_selective": "Sadece blacklist",
        "scope_full": "Her şey",
        "killswitch": "Kill-switch (tünel düşerse trafiği kes)",
        "blacklist_menu": "Blacklist",
        "language": "Dil",
        "quit": "Çıkış",
        "bl_count": "{n} domain kayıtlı",
        "bl_full_note": "(full modda hepsi zaten Asena'tan geçer)",
        "bl_edit": "Düzenle…",
        "bl_add": "Domain ekle…",
        "bl_reload": "DNS yenile",
        "dlg_add_title": "Blacklist — Domain ekle",
        "dlg_add_label": "Domain:",
        "notify_added": "{domain} eklendi. 'DNS yenile' ile aktif et.",
        "notify_not_added": "Eklenmedi (boş veya zaten mevcut).",
        "notify_dns_reloading": "DNS yenileniyor…",
        "notify_connected": "Bağlandı ({detail})",
        "notify_disconnected": "Bağlantı kesildi",
        "notify_timeout": "İşlem zaman aşımına uğradı — tekrar dene.",
        "tip_connected": "{app}: Bağlı ({detail})",
        "tip_disconnected": "{app}: Bağlı değil",
        "notify_title_blacklist": "Blacklist",
        "check_updates": "Güncellemeleri denetle",
        "upd_checking": "Güncellemeler denetleniyor…",
        "upd_none": "Zaten en güncel sürümdesin.",
        "upd_available_title": "Güncelleme mevcut",
        "upd_available": "Yeni sürüm {ver} — indirilip kurulsun mu?",
        "upd_toast_header": "AsenaPlug güncelleniyor",
        "upd_downloading": "İndiriliyor…",
        "upd_installing": "Kuruluyor, yeniden başlatılıyor…",
        "upd_fail": "Güncelleme başarısız. Tekrar dene.",
        "upd_check_fail": "Denetlenemedi (bağlantı?).",
        "setup_running": "Kuruluyor…",
        "setup_done": "Hazır — sistem tepsisinde.",
        "notify_apply_on_connect": "Asena kapalı — değişiklikler bağlanınca otomatik uygulanır.",
        "notify_added_offline": "{domain} eklendi — bağlanınca otomatik aktif olur.",
        "registering": "Cihaz kaydı yapılıyor (tek seferlik kurulum)…",
        "register_fail": "Cihaz kaydı başarısız — bağlantını kontrol edip tekrar dene.",
        "optimize_endpoint": "Bağlantıyı hızlandır",
        "opt_scanning": "En hızlı sunucu aranıyor…",
        "opt_fail": "Hiçbir sunucuya ulaşılamadı (bağlantı?).",
        "opt_done": "En hızlı sunucu seçildi: {ip} ({ms} ms).",
        "opt_done_reconnect": "En hızlı sunucu: {ip} ({ms} ms) — etkinleşmesi için yeniden bağlan.",
        "opt_reverted": "Sunucu yanıt vermedi — varsayılana dönüldü.",
        "notify_transport_fallback": "Bu ağda HTTP/3 yok — {got}'ye geçildi.",
        "notify_net_reapply": "Ağ değişti — tünel tazeleniyor…",
    },
}

_current = "en"


def available():
    """[(kod, yerel isim)] — dil menüsü için."""
    return LANGUAGES


def get_language() -> str:
    return _current


def set_language(code: str):
    global _current
    if code in TRANSLATIONS:
        _current = code


def t(key: str, **kw) -> str:
    """Aktif dilde çeviri; eksikse EN; o da yoksa key. Parametreler .format ile."""
    s = TRANSLATIONS.get(_current, {}).get(key)
    if s is None:
        s = TRANSLATIONS["en"].get(key, key)
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return s


def load_saved():
    """Kayıtlı dil kodu (geçerliyse), yoksa None."""
    try:
        code = LANG_FILE.read_text(encoding="utf-8").strip()
        return code if code in TRANSLATIONS else None
    except OSError:
        return None


def save(code: str):
    try:
        LANG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LANG_FILE.write_text(code, encoding="utf-8")
    except OSError:
        pass


def init(os_lang: str = "en") -> str:
    """Kayıtlı dil varsa onu kullan; yoksa OS dilini (listede yoksa 'en') seç ve
    KAYDET (ilk kurulum davranışı). Aktif dil kodunu döner."""
    saved = load_saved()
    if saved:
        set_language(saved)
    else:
        code = os_lang if os_lang in TRANSLATIONS else "en"
        set_language(code)
        save(code)
    return _current
