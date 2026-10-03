using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

// The windowed face of install.ps1 (the same template in every repo; setup.json says what is installed).
// It collects the choices, runs install.ps1 (embedded in this exe) hidden with <ENV>_DRIVER and shows the steps it
// reports in status.json. The install itself lives in one place: install.ps1, the same path as the one-line install.
//   Setup.exe                         the window
//   Setup.exe --shots <dir>           every page drawn to a PNG (nothing is installed)
//   Setup.exe --smoke <dir> [action]  CI: draws the pages, then runs install.ps1 through the window with no clicks
//                                     (action: uninstall, the default, changes nothing when the app is not installed;
//                                     install takes <ENV>_SOURCE from the environment) and exits 0 when it reported back
static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--shots") { SetupForm.Shots(args[1]); return 0; }
        try { SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch { }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        bool smoke = args.Length >= 2 && args[0] == "--smoke";
        if (smoke) SetupForm.Shots(args[1]);
        var form = new SetupForm();
        if (smoke) form.StartSmoke(args[1], args.Length >= 3 ? args[2] : "uninstall");
        Application.Run(form);
        return Environment.ExitCode;
    }

    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr value);
}

// what setup.json says about the app
sealed class AppInfo
{
    public string Name, Id, Publisher, Repo, Env, Accent, TaglineEn, TaglineTr, Mode, Key, Exe, Asset, Location, Command, PurgeEn, PurgeTr;
    public bool Admin, Launch, Path, Shortcut, Desktop, VersionFromExe;

    public static AppInfo Load()
    {
        string json;
        using (var res = typeof(Program).Assembly.GetManifestResourceStream("setup.json"))
        using (var sr = new StreamReader(res, System.Text.Encoding.UTF8)) json = sr.ReadToEnd();
        var d = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(json);
        Func<string, string> s = k => { object v; return d.TryGetValue(k, out v) && v != null ? Convert.ToString(v) : ""; };
        Func<string, bool> b = k => { object v; return d.TryGetValue(k, out v) && v is bool && (bool)v; };
        return new AppInfo
        {
            Name = s("name"), Id = s("id"), Publisher = s("publisher"), Repo = s("repo"), Env = s("env"), Accent = s("accent"),
            TaglineEn = s("taglineEn"), TaglineTr = s("taglineTr"), Mode = s("mode"), Key = s("key"), Exe = s("exe"), Asset = s("asset"),
            Location = s("location"), Command = s("command"), PurgeEn = s("purgeEn"), PurgeTr = s("purgeTr"),
            Admin = b("admin"), Launch = b("launch"), Path = b("path"), Shortcut = b("shortcut"), Desktop = b("desktop"), VersionFromExe = b("versionFromExe"),
        };
    }
}

sealed class SetupForm : Form
{
    readonly AppInfo app = AppInfo.Load();

    // ---------------------------------------------------------------- texts (Turkish / English)
    bool tr = System.Globalization.CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "tr";
    string T(string turkish, string english) { return tr ? turkish : english; }

    // ---------------------------------------------------------------- what is on this computer
    string installed, installDir, latest; // installed version, its folder, the release install.ps1 would pick
    bool latestChecked, latestFailed;

    // ---------------------------------------------------------------- choices
    enum Act { Install, Update, Repair, Uninstall }
    Act action = Act.Install;
    bool desktop, purge;

    // ---------------------------------------------------------------- install state
    enum Page { Welcome, Options, Progress, Result }
    Page page = Page.Welcome;
    string work, version = "", stepState = "running", exePath;
    string[] steps = new string[0], notes = new string[0];
    int percent = -1; long done, total;
    string resultKind, resultTitle, resultBody, resultLog; // ok / warn / error
    bool cancelRequested, launched;
    Process proc;
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer { Interval = 50 };
    int tick;
    DateTime slideStart = DateTime.UtcNow;
    string smokeDir, smokeAction; DateTime smokeStart;

    // ---------------------------------------------------------------- drawing
    float k = 1f; // DIPs -> pixels
    bool light;
    Color Bg, Surface, Surface2, Outline, Fg, Sub, Dim, Ok, Err, Warn, Accent, AccentInk;
    static readonly Color OnAccent = Hex("#1d1b20");
    readonly Dictionary<string, Font> fonts = new Dictionary<string, Font>();
    sealed class Hit { public RectangleF Rect; public string Id; public Action Click; }
    readonly List<Hit> hits = new List<Hit>();
    string hover;
    Bitmap logo;

    const float W = 760, H = 540;
    const double SlideMs = 220;

    public SetupForm()
    {
        Text = app.Name + " Setup";
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        DoubleBuffered = true;
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
        try { this.Icon = System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        try
        {
            using (var res = typeof(Program).Assembly.GetManifestResourceStream("logo.png")) logo = new Bitmap(res);
        }
        catch { }
        try { using (var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")) light = key != null && Convert.ToInt32(key.GetValue("AppsUseLightTheme", 0)) == 1; } catch { }
        SetTheme(light);
        Detect();
        timer.Tick += (s, e) => OnTick();
        timer.Start();
    }

    void SetTheme(bool isLight)
    {
        light = isLight;
        Accent = Hex(app.Accent.Length == 7 ? app.Accent : "#b69df8");
        if (light)
        {
            Bg = Hex("#fdf8fd"); Surface = Hex("#f3edf7"); Surface2 = Hex("#e8e0ec"); Outline = Hex("#cac4d0");
            Fg = Hex("#1d1b20"); Sub = Hex("#49454f"); Dim = Hex("#79747e"); Ok = Hex("#1e7a3d"); Err = Hex("#b3261e"); Warn = Hex("#9a5800");
            AccentInk = Mix(Accent, Color.Black, 0.45f);
        }
        else
        {
            Bg = Hex("#141218"); Surface = Hex("#1d1b20"); Surface2 = Hex("#2b2930"); Outline = Hex("#49454f");
            Fg = Hex("#e6e0e9"); Sub = Hex("#cac4d0"); Dim = Hex("#938f99"); Ok = Hex("#a8dab5"); Err = Hex("#f2b8b5"); Warn = Hex("#ffb77c");
            AccentInk = Accent;
        }
        BackColor = Bg;
    }

    protected override CreateParams CreateParams
    {
        get { var cp = base.CreateParams; cp.ClassStyle |= 0x20000; /* CS_DROPSHADOW */ return cp; }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        k = DeviceDpi / 96f;
        ClientSize = new Size((int)(W * k), (int)(H * k));
        // (the smoke test's window sits off screen: StartSmoke placed it before the handle existed; changing
        // ShowInTaskbar here would recreate the handle and land here again)
        if (smokeDir == null) CenterToScreen();
        // Windows 11: rounded corners and a frame that matches the theme; Windows 10 ignores both
        int round = 2, dark = light ? 0 : 1;
        DwmSetWindowAttribute(Handle, 33 /* DWMWA_WINDOW_CORNER_PREFERENCE */, ref round, 4);
        DwmSetWindowAttribute(Handle, 20 /* DWMWA_USE_IMMERSIVE_DARK_MODE */, ref dark, 4);
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == 0x02E0 /* WM_DPICHANGED */)
        {
            k = (m.WParam.ToInt32() & 0xFFFF) / 96f;
            ClearFonts();
            var r = (RECT)Marshal.PtrToStructure(m.LParam, typeof(RECT));
            SetBounds(r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top);
            Invalidate();
            return;
        }
        base.WndProc(ref m);
    }

    // ---------------------------------------------------------------- what is installed (the same places install.ps1 looks)

    static readonly bool Wow = !Environment.Is64BitProcess && Environment.Is64BitOperatingSystem;

    static string Expand(string path)
    {
        // a 32-bit setup on 64-bit Windows: %ProgramFiles% is the 64-bit folder, as install.ps1 sees it
        string pf = Environment.GetEnvironmentVariable("ProgramW6432");
        if (!string.IsNullOrEmpty(pf)) path = Regex.Replace(path, "%ProgramFiles%", pf.Replace("$", "$$"), RegexOptions.IgnoreCase);
        return Environment.ExpandEnvironmentVariables(path);
    }

    static RegistryKey OpenKey(RegistryHive hive, string path)
    {
        try { using (var root = RegistryKey.OpenBaseKey(hive, Environment.Is64BitOperatingSystem ? RegistryView.Registry64 : RegistryView.Default)) return root.OpenSubKey(path); }
        catch { return null; }
    }

    void Detect()
    {
        installed = null; installDir = null;
        string name = app.Mode == "setup" ? app.Key : app.Id;
        string[] roots = app.Mode == "setup"
            ? new[] { "HKLM:Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall", "HKLM:Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall", "HKCU:Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall" }
            : new[] { "HKCU:Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall" };
        foreach (var r in roots)
        {
            var hive = r.StartsWith("HKLM") ? RegistryHive.LocalMachine : RegistryHive.CurrentUser;
            using (var key = OpenKey(hive, r.Substring(5) + "\\" + name))
            {
                if (key == null) continue;
                installed = Convert.ToString(key.GetValue("DisplayVersion", "")) ?? "";
                string loc = Convert.ToString(key.GetValue("InstallLocation", "")) ?? "";
                string icon = Convert.ToString(key.GetValue("DisplayIcon", "")) ?? "";
                if (loc.Length > 0) installDir = loc.Trim('"').TrimEnd('\\');
                else if (icon.Length > 0) { try { installDir = Path.GetDirectoryName(icon.Split(',')[0].Trim('"')); } catch { } }
                break;
            }
        }
        // an install the Apps entry does not know about (AsenaPlug's own updater replaces only its exe)
        string probe = Expand(app.Location);
        if (installDir == null && app.Mode == "setup" && File.Exists(Path.Combine(probe, app.Exe))) installDir = probe;
        if (app.VersionFromExe && installDir != null)
        {
            try
            {
                var m = Regex.Match(FileVersionInfo.GetVersionInfo(Path.Combine(installDir, app.Exe)).ProductVersion ?? "", @"^\d+\.\d+\.\d+");
                if (m.Success) installed = m.Value;
            }
            catch { }
            if (installed == null) installed = "";
        }
        action = installed == null ? Act.Install : Act.Update;
        if (!offline) ThreadPool.QueueUserWorkItem(_ => CheckLatest());
    }

    // the newest release with the file install.ps1 downloads (the same choice install.ps1 makes)
    void CheckLatest()
    {
        string found = null; bool failed = false;
        try
        {
            ServicePointManager.SecurityProtocol |= (SecurityProtocolType)3072; // TLS 1.2
            var req = (HttpWebRequest)WebRequest.Create("https://api.github.com/repos/" + app.Repo + "/releases?per_page=40");
            req.UserAgent = app.Id + "-setup"; req.Accept = "application/vnd.github+json"; req.Timeout = 15000;
            string json;
            using (var res = req.GetResponse()) using (var sr = new StreamReader(res.GetResponseStream())) json = sr.ReadToEnd();
            var list = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.DeserializeObject(json) as object[];
            foreach (var o in list ?? new object[0])
            {
                var rel = o as Dictionary<string, object>;
                if (rel == null || true.Equals(rel["draft"]) || true.Equals(rel["prerelease"])) continue;
                var assets = rel["assets"] as object[];
                bool has = false;
                foreach (var a in assets ?? new object[0]) { var ad = a as Dictionary<string, object>; if (ad != null && Regex.IsMatch(Convert.ToString(ad["name"]), app.Asset, RegexOptions.IgnoreCase)) has = true; }
                if (!has) continue;
                found = Regex.Replace(Convert.ToString(rel["tag_name"]), "^v", "");
                break;
            }
        }
        catch { failed = true; }
        try
        {
            BeginInvoke((Action)(() =>
            {
                latest = found; latestFailed = failed || found == null; latestChecked = true;
                if (action == Act.Update && installed != null && latest != null && !Newer(latest, installed)) action = Act.Repair;
                Invalidate();
            }));
        }
        catch { } // the window closed first
    }

    static bool Newer(string a, string b)
    {
        Version va, vb;
        if (!Version.TryParse(a, out va) || !Version.TryParse(b, out vb)) return a != b;
        return va > vb;
    }

    // ---------------------------------------------------------------- pages

    protected override void OnPaint(PaintEventArgs e) { Render(e.Graphics); }

    void Render(Graphics g)
    {
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        g.Clear(Bg);
        hits.Clear();
        g.ScaleTransform(k, k);

        // header: the app's icon and name, step dots, theme, close
        if (logo != null) g.DrawImage(logo, new RectangleF(24, 18, 24, 24));
        else FillCircle(g, Accent, 36, 30, 7);
        Str(g, app.Name, F(15, true), Fg, 56, 19, 360, 24);
        int dot = page == Page.Welcome ? 0 : page == Page.Options ? 1 : page == Page.Progress ? 2 : 3;
        for (int i = 0; i < 4; i++) FillRound(g, i == dot ? Accent : Outline, W - 184 + i * 16 + (i > dot ? 14 : 0), 26, i == dot ? 22 : 8, 8, 4);
        var theme = new RectangleF(W - 92, 14, 36, 32);
        if (hover == "theme") FillRound(g, Surface2, theme.X, theme.Y, theme.Width, theme.Height, 10);
        Glyph(g, light ? "moon" : "sun", new RectangleF(theme.X + 8, theme.Y + 6, 20, 20), Sub);
        AddHit(theme, "theme", () => { SetTheme(!light); int dark = light ? 0 : 1; if (IsHandleCreated) DwmSetWindowAttribute(Handle, 20, ref dark, 4); Invalidate(); });
        var close = new RectangleF(W - 52, 14, 36, 32);
        if (hover == "close") FillRound(g, Surface2, close.X, close.Y, close.Width, close.Height, 10);
        Glyph(g, "close", close, Sub);
        AddHit(close, "close", CloseClicked);

        // the page slides in from the right
        float t = (float)Math.Min(1.0, (DateTime.UtcNow - slideStart).TotalMilliseconds / SlideMs);
        float off = 28 * (1 - t) * (1 - t);
        g.TranslateTransform(off, 0);
        if (page == Page.Welcome) PaintWelcome(g);
        else if (page == Page.Options) PaintOptions(g);
        else if (page == Page.Progress) PaintProgress(g);
        else PaintResult(g);
        g.ResetTransform();
    }

    string Tagline { get { return tr && app.TaglineTr.Length > 0 ? app.TaglineTr : app.TaglineEn; } }
    string Where { get { return installDir ?? Expand(app.Location); } }

    void PaintWelcome(Graphics g)
    {
        if (logo != null) g.DrawImage(logo, new RectangleF(40, 80, 64, 64));
        Str(g, app.Name, F(26, true), Fg, 124, 80, 560, 38);
        StrWrap(g, Tagline, F(13), Sub, 124, 120, 590, 40);

        // language
        Str(g, T("Dil", "Language"), F(12.5f, true), Dim, 40, 172, 120, 20);
        Chip(g, "lang:tr", "Türkçe", 120, 168, 92, tr, () => { tr = true; Invalidate(); });
        Chip(g, "lang:en", "English", 220, 168, 92, !tr, () => { tr = false; Invalidate(); });

        // what is on this computer
        FillRound(g, Surface, 40, 214, 680, 74, 18);
        string state = installed == null ? T("Bu bilgisayarda kurulu değil", "Not installed on this computer")
            : installed.Length > 0 ? T("Kurulu sürüm: ", "Installed: ") + installed : T("Kurulu", "Installed");
        Str(g, state, F(14, true), Fg, 60, 228, 640, 22);
        string rel = !latestChecked ? T("Son sürüm denetleniyor…", "Checking the latest release…")
            : latestFailed ? T("Son sürüm denetlenemedi; kurulum yine en yenisini indirir.", "Couldn't check the latest release; setup still downloads the newest one.")
            : installed != null && installed.Length > 0 && !Newer(latest, installed) ? T("Son sürüm: ", "Latest release: ") + latest + T("  ·  güncel", "  ·  up to date")
            : T("Son sürüm: ", "Latest release: ") + latest;
        Str(g, rel, F(12.5f), Sub, 60, 254, 640, 20);

        if (installed == null)
        {
            float y = 312;
            foreach (var line in Facts()) { FillCircle(g, Accent, 50, y + 10, 3); StrWrap(g, line, F(13), Sub, 64, y, 650, 40); y += 28; }
            Button(g, "next", T("Devam", "Next"), W - 40 - 140, H - 72, 140, true, () => Go(Page.Options));
        }
        else
        {
            bool canUpdate = !latestChecked || latestFailed || installed.Length == 0 || Newer(latest, installed);
            float x = 40;
            if (canUpdate) { ActCard(g, Act.Update, x, T("Güncelle", "Update"), latest != null && latestChecked && !latestFailed ? T("En yeni sürüme geç: ", "Move to ") + latest : T("En yeni sürüme geç", "Move to the newest release"), "update"); x += 232; }
            ActCard(g, Act.Repair, x, T("Onar", "Repair"), T("Aynı sürümü baştan kur; ayarların kalır.", "Install the same release again; your settings stay."), "repair"); x += 232;
            ActCard(g, Act.Uninstall, x, T("Kaldır", "Uninstall"), T("Bu bilgisayardan kaldır.", "Remove it from this computer."), "trash");
            if (!canUpdate && action == Act.Update) action = Act.Repair;
            Button(g, "next", T("Devam", "Next"), W - 40 - 140, H - 72, 140, true, () => Go(Page.Options));
        }
    }

    IEnumerable<string> Facts()
    {
        yield return app.Admin ? T("Windows bir kez yönetici izni isteyecek.", "Windows asks for administrator permission once.")
            : T("Yalnızca senin hesabına kurulur; yönetici izni gerekmez.", "Installs for your account only; no administrator permission needed.");
        if (app.Path) yield return T("'" + app.Command + "' komutu kullanıcı PATH'ine eklenir.", "The '" + app.Command + "' command is added to your user PATH.");
        else if (app.Shortcut) yield return T("Başlat menüsünde bir kısayol ve Ayarlar > Uygulamalar'da bir kayıt.", "A Start menu shortcut and an entry in Settings > Apps.");
        else yield return T("Ayarlar > Uygulamalar'da bir kayıt; oradan kaldırılabilir.", "An entry in Settings > Apps, where it can be removed.");
        yield return T("Bir şey ters giderse ya da vazgeçersen her şey eski haline döner.", "If something goes wrong or you cancel, everything goes back to how it was.");
        yield return T("Tek satırlık PowerShell kurulumuyla aynı kurulum; tekrar çalıştırınca günceller.", "The same install as the one-line PowerShell command; run it again to update.");
    }

    void ActCard(Graphics g, Act a, float x, string title, string body, string glyph)
    {
        string id = "act:" + a;
        var r = new RectangleF(x, 310, 216, 132);
        bool sel = action == a;
        FillRound(g, sel ? Mix(Surface2, Accent, 0.12f) : hover == id ? Surface2 : Surface, r.X, r.Y, r.Width, r.Height, 20);
        if (sel) DrawRound(g, Accent, 2, r.X + 1, r.Y + 1, r.Width - 2, r.Height - 2, 19);
        FillCircle(g, Mix(Surface, a == Act.Uninstall ? Err : Accent, 0.22f), x + 38, 348, 18);
        Glyph(g, glyph, new RectangleF(x + 28, 338, 20, 20), a == Act.Uninstall ? Err : AccentInk);
        Str(g, title, F(16, true), Fg, x + 66, 336, 140, 24);
        StrWrap(g, body, F(12.5f), Sub, x + 20, 378, 180, 56);
        AddHit(r, id, () => { action = a; Invalidate(); });
    }

    void PaintOptions(Graphics g)
    {
        if (action == Act.Uninstall)
        {
            Str(g, T(app.Name + " kaldırılsın mı?", "Remove " + app.Name + "?"), F(24, true), Fg, 40, 82, 680, 36);
            StrWrap(g, T("Program, kısayolları ve Ayarlar > Uygulamalar'daki kaydı kaldırılır.", "The program, its shortcuts and its entry in Settings > Apps are removed.") +
                (app.Admin ? T(" Windows bir kez yönetici izni isteyecek.", " Windows asks for administrator permission once.") : ""), F(13), Sub, 40, 126, 680, 60);
            Summary(g, 196, false);
            if (app.PurgeEn.Length > 0) Toggle(g, "purge", tr ? app.PurgeTr : app.PurgeEn, 40, 300, purge, () => { purge = !purge; Invalidate(); });
            Button(g, "back", T("Geri", "Back"), 40, H - 72, 120, false, () => Go(Page.Welcome));
            Button(g, "go", T("Kaldır", "Remove"), W - 40 - 160, H - 72, 160, true, StartAction, Err);
            return;
        }
        string title = action == Act.Update ? T("Güncellemeye hazır", "Ready to update") : action == Act.Repair ? T("Onarmaya hazır", "Ready to repair") : T("Kurmaya hazır", "Ready to install");
        Str(g, title, F(24, true), Fg, 40, 82, 680, 36);
        Str(g, T("Son sürüm GitHub'dan indirilir ve SHA-256 ile doğrulanır.", "The latest release is downloaded from GitHub and checked with its SHA-256."), F(13), Sub, 40, 122, 680, 22);
        float y = Summary(g, 164, true) + 20;
        if (app.Desktop)
        {
            Str(g, T("Seçenekler", "Options"), F(13, true), Sub, 40, y, 300, 20);
            Toggle(g, "desktop", T("Masaüstü kısayolu", "Desktop shortcut"), 40, y + 28, desktop, () => { desktop = !desktop; Invalidate(); });
        }
        string go = action == Act.Update ? T("Güncelle", "Update") : action == Act.Repair ? T("Onar", "Repair") : T("Kur", "Install");
        Button(g, "back", T("Geri", "Back"), 40, H - 72, 120, false, () => Go(Page.Welcome));
        Button(g, "go", go, W - 40 - 160, H - 72, 160, true, StartAction);
        if (app.Admin) Str(g, T("Windows bir kez yönetici izni isteyecek.", "Windows will ask for permission once."), F(12), Dim, 176, H - 60, 400, 20);
    }

    // version / location / permission rows; returns the bottom
    float Summary(Graphics g, float y, bool install)
    {
        var rows = new List<string[]>();
        if (install) rows.Add(new[] { T("Sürüm", "Version"), latestChecked && !latestFailed ? latest + (installed != null && installed.Length > 0 && installed != latest ? "   (" + T("kurulu: ", "installed: ") + installed + ")" : "") : T("en yenisi", "the newest") });
        else if (installed != null && installed.Length > 0) rows.Add(new[] { T("Sürüm", "Version"), installed });
        rows.Add(new[] { T("Konum", "Location"), Where });
        if (install && app.Path) rows.Add(new[] { T("Komut", "Command"), app.Command + T("  (kullanıcı PATH'inde)", "  (on your user PATH)") });
        if (install) rows.Add(new[] { T("İzin", "Permission"), app.Admin ? T("Yönetici (Windows bir kez sorar)", "Administrator (Windows asks once)") : T("Gerekmez, yalnızca senin hesabın", "None, your account only") });
        FillRound(g, Surface, 40, y, 680, 20 + rows.Count * 30, 18);
        for (int i = 0; i < rows.Count; i++)
        {
            Str(g, rows[i][0], F(12.5f), Dim, 60, y + 14 + i * 30, 110, 20);
            Str(g, rows[i][1], F(13), Fg, 170, y + 13 + i * 30, 530, 22);
        }
        return y + 20 + rows.Count * 30;
    }

    void PaintProgress(Graphics g)
    {
        string title = cancelRequested ? T("Geri alınıyor…", "Rolling back…")
            : action == Act.Uninstall ? T("Kaldırılıyor", "Removing") : action == Act.Update ? T("Güncelleniyor", "Updating")
            : action == Act.Repair ? T("Onarılıyor", "Repairing") : T("Kuruluyor", "Installing");
        Str(g, title, F(24, true), Fg, 40, 82, 600, 36);
        if (version.Length > 0) Str(g, app.Name + " " + version, F(13), Sub, 40, 120, 600, 22);
        float y = 160;
        if (steps.Length == 0) StepRow(g, y, T("Başlatılıyor", "Starting"), 1);
        int first = Math.Max(0, steps.Length - 9);
        for (int i = first; i < steps.Length; i++)
        {
            bool last = i == steps.Length - 1;
            int state = !last ? 2 : stepState == "done" ? 2 : stepState == "error" ? 3 : 1;
            StepRow(g, y, steps[i], state);
            if (last && state == 1 && percent >= 0)
            {
                ProgressBar(g, 76, y + 30, 420, percent / 100f);
                string mb = total > 0 ? string.Format("{0:0.0} / {1:0.0} MB", done / 1048576.0, total / 1048576.0) : "";
                Str(g, percent + "%   " + mb, F(12), Dim, 510, y + 22, 220, 20);
                y += 26;
            }
            y += 34;
        }
        if (!cancelRequested && action != Act.Uninstall) Button(g, "cancel", T("İptal", "Cancel"), W - 40 - 120, H - 72, 120, false, RequestCancel);
    }

    void PaintResult(Graphics g)
    {
        var mark = resultKind == "ok" ? Ok : resultKind == "warn" ? Warn : Err;
        FillCircle(g, Mix(Bg, mark, 0.18f), 72, 118, 32);
        Glyph(g, resultKind == "ok" ? "check" : resultKind == "warn" ? "bang" : "close", new RectangleF(52, 98, 40, 40), mark);
        StrWrap(g, resultTitle ?? "", F(22, true), Fg, 120, 100, 600, 64);
        float y = 176;
        if (!string.IsNullOrEmpty(resultBody)) y = StrWrap(g, resultBody, F(13), Sub, 40, y, 680, 230) + 14;
        if (notes.Length > 0)
        {
            float h = 0;
            foreach (var n in notes) h += g.MeasureString(n, F(12.5f), 640).Height + 6;
            FillRound(g, Mix(Surface, Warn, 0.12f), 40, y, 680, h + 20, 16);
            float ny = y + 10;
            foreach (var n in notes) ny = StrWrap(g, n, F(12.5f), Fg, 56, ny, 640, 80) + 6;
        }
        float bx = W - 40 - 140;
        Button(g, "done", T("Kapat", "Close"), bx, H - 72, 140, resultKind != "ok" || !CanLaunch, Close);
        if (CanLaunch && resultKind == "ok") { bx -= 160; Button(g, "launch", launched ? T("Açıldı", "Opened") : T("Aç", "Launch"), bx, H - 72, 150, true, Launch); }
        if (resultKind != "ok" && File.Exists(resultLog ?? "")) Button(g, "log", T("Günlüğü aç", "Open the log"), 40, H - 72, 170, false, () => { try { Process.Start("notepad.exe", "\"" + resultLog + "\""); } catch { } });
    }

    bool CanLaunch { get { return app.Launch && action != Act.Uninstall && !string.IsNullOrEmpty(exePath) && File.Exists(exePath); } }

    void Launch()
    {
        try { Process.Start(new ProcessStartInfo(exePath) { WorkingDirectory = Path.GetDirectoryName(exePath), UseShellExecute = true }); launched = true; Invalidate(); }
        catch (Exception ex) { resultBody = (resultBody ?? "") + "\n\n" + ex.Message; Invalidate(); }
    }

    // ---------------------------------------------------------------- controls (drawn)

    void Button(Graphics g, string id, string label, float x, float y, float w, bool primary, Action click, Color? tint = null)
    {
        bool hot = hover == id;
        var fill = tint ?? Accent;
        var bg = primary ? (hot ? Mix(fill, Color.White, 0.12f) : fill) : (hot ? Surface2 : Surface);
        FillRound(g, bg, x, y, w, 44, 22);
        StrCenter(g, label, F(14, true), primary ? (tint.HasValue && light ? Color.White : OnAccent) : Fg, new RectangleF(x, y, w, 44));
        AddHit(new RectangleF(x, y, w, 44), id, click);
    }

    void Chip(Graphics g, string id, string label, float x, float y, float w, bool on, Action click)
    {
        FillRound(g, on ? Mix(Surface, Accent, 0.28f) : hover == id ? Surface2 : Surface, x, y, w, 28, 14);
        if (on) DrawRound(g, Accent, 1.2f, x + 0.6f, y + 0.6f, w - 1.2f, 26.8f, 13.4f);
        StrCenter(g, label, F(12.5f), on ? Fg : Sub, new RectangleF(x, y, w, 28));
        AddHit(new RectangleF(x, y, w, 28), id, click);
    }

    void Toggle(Graphics g, string id, string label, float x, float y, bool on, Action click)
    {
        var row = new RectangleF(x, y, 680, 30);
        if (hover == id) FillRound(g, Surface, row.X - 8, row.Y - 2, row.Width + 16, row.Height + 4, 12);
        FillRound(g, on ? Accent : Surface2, x, y + 4, 40, 22, 11);
        if (!on) DrawRound(g, Outline, 1.2f, x + 0.6f, y + 4.6f, 38.8f, 20.8f, 10.4f);
        FillCircle(g, on ? OnAccent : Dim, on ? x + 29 : x + 11, y + 15, on ? 8 : 6);
        Str(g, label, F(13), on ? Fg : Sub, x + 54, y + 4, 600, 22);
        AddHit(row, id, click);
    }

    // state: 0 pending, 1 running, 2 done, 3 failed
    void StepRow(Graphics g, float y, string label, int state)
    {
        float cx = 56, cy = y + 11;
        if (state == 2) { FillCircle(g, Mix(Bg, Ok, 0.22f), cx, cy, 10); Glyph(g, "check", new RectangleF(cx - 8, cy - 8, 16, 16), Ok); }
        else if (state == 3) { FillCircle(g, Mix(Bg, Err, 0.22f), cx, cy, 10); Glyph(g, "close", new RectangleF(cx - 8, cy - 8, 16, 16), Err); }
        else if (state == 1)
        {
            using (var p = new Pen(Accent, 2.4f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                g.DrawArc(p, cx - 8, cy - 8, 16, 16, (tick * 18) % 360, 260);
        }
        else FillCircle(g, Outline, cx, cy, 3);
        Str(g, label, F(13, state == 1), state == 0 ? Dim : Fg, 76, y, 640, 22);
    }

    void ProgressBar(Graphics g, float x, float y, float w, float frac)
    {
        FillRound(g, Surface2, x, y, w, 6, 3);
        FillRound(g, Accent, x, y, Math.Max(6, w * Math.Max(0, Math.Min(1, frac))), 6, 3);
    }

    // ---------------------------------------------------------------- input

    void AddHit(RectangleF r, string id, Action click) { hits.Add(new Hit { Rect = r, Id = id, Click = click }); }

    Hit HitAt(Point p)
    {
        float x = p.X / k, y = p.Y / k;
        for (int i = hits.Count - 1; i >= 0; i--) if (hits[i].Rect.Contains(x, y)) return hits[i];
        return null;
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        var h = HitAt(e.Location);
        string id = h == null ? null : h.Id;
        Cursor = h == null ? Cursors.Default : Cursors.Hand;
        if (id != hover) { hover = id; Invalidate(); }
    }

    protected override void OnMouseLeave(EventArgs e) { if (hover != null) { hover = null; Invalidate(); } }

    protected override void OnMouseDown(MouseEventArgs e)
    {
        if (e.Button != MouseButtons.Left) return;
        var h = HitAt(e.Location);
        if (h != null) { h.Click(); return; }
        // anywhere else moves the window
        ReleaseCapture();
        SendMessage(Handle, 0xA1 /* WM_NCLBUTTONDOWN */, (IntPtr)2 /* HTCAPTION */, IntPtr.Zero);
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.Escape) { CloseClicked(); return true; }
        if (keyData == Keys.Enter)
        {
            if (page == Page.Welcome) Go(Page.Options);
            else if (page == Page.Options) StartAction();
            else if (page == Page.Result) Close();
            return true;
        }
        return base.ProcessCmdKey(ref msg, keyData);
    }

    void Go(Page p)
    {
        page = p;
        slideStart = DateTime.UtcNow;
        hover = null;
        StartFrames();
    }

    // The page slide is drawn on the compositor's frame clock: a 50 ms form timer gives it four or five frames and
    // Invalidate() waits behind every other message. Each frame paints at once (Refresh) and then waits for the next
    // composition pass (DwmFlush, the display's refresh); the message loop runs between frames, so input stays live.
    bool animating;
    void StartFrames()
    {
        if (animating || !IsHandleCreated) { Invalidate(); return; }
        animating = true;
        BeginInvoke((Action)Frame);
    }

    void Frame()
    {
        if (IsDisposed) return;
        Refresh();
        if ((DateTime.UtcNow - slideStart).TotalMilliseconds >= SlideMs + 20) { animating = false; return; }
        if (DwmFlush() != 0) Thread.Sleep(8); // composition off: about the same pace
        BeginInvoke((Action)Frame);
    }

    void CloseClicked()
    {
        if (page == Page.Progress) RequestCancel();
        else Close();
    }

    // ---------------------------------------------------------------- the install (install.ps1 does it all)

    static string PowerShellPath()
    {
        // a 32-bit setup on 64-bit Windows starts the 64-bit PowerShell, so install.ps1 sees the real Program Files and registry
        string root = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        string p = Path.Combine(root, Wow ? "Sysnative" : "System32", @"WindowsPowerShell\v1.0\powershell.exe");
        return File.Exists(p) ? p : "powershell.exe";
    }

    void StartAction()
    {
        if (page == Page.Progress || proc != null) return;
        try
        {
            work = Path.Combine(Path.GetTempPath(), app.Id + "-setup-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(work);
            string script = Path.Combine(work, "install.ps1");
            using (var res = typeof(Program).Assembly.GetManifestResourceStream("install.ps1"))
            using (var file = File.Create(script))
                res.CopyTo(file);
            var psi = new ProcessStartInfo(PowerShellPath(), "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = work,
            };
            string e = app.Env + "_";
            foreach (var name in new[] { "UNINSTALL", "PURGE", "FORCE", "DESKTOP", "DRIVER", "DEFAULTS", "LANGUAGE" }) psi.EnvironmentVariables.Remove(e + name);
            psi.EnvironmentVariables[e + "DRIVER"] = work;
            psi.EnvironmentVariables[e + "DEFAULTS"] = "1";
            psi.EnvironmentVariables[e + "LANGUAGE"] = tr ? "tr" : "en";
            if (action == Act.Repair) psi.EnvironmentVariables[e + "FORCE"] = "1";
            if (action == Act.Uninstall) psi.EnvironmentVariables[e + "UNINSTALL"] = "1";
            if (action == Act.Uninstall && purge) psi.EnvironmentVariables[e + "PURGE"] = "1";
            if (action != Act.Uninstall && desktop && app.Desktop) psi.EnvironmentVariables[e + "DESKTOP"] = "1";
            resultLog = Path.Combine(Path.GetTempPath(), app.Id + "-install.log");
            proc = Process.Start(psi);
            Go(Page.Progress);
        }
        catch (Exception ex)
        {
            Finish("error", T("Kurulum başlatılamadı", "Setup could not start"), ex.Message);
        }
    }

    void RequestCancel()
    {
        if (cancelRequested || work == null || action == Act.Uninstall) return;
        cancelRequested = true;
        try { File.WriteAllText(Path.Combine(work, "cancel"), ""); } catch { }
        Invalidate();
    }

    void OnTick()
    {
        tick++;
        if (page == Page.Progress && tick % 2 == 0) Poll();
        if (page == Page.Progress && !animating) Invalidate(); // the slide has its own frames (Frame)
        if (smokeDir != null && page != Page.Result && (DateTime.UtcNow - smokeStart).TotalMinutes > 15) EndSmoke(2, "timed out on page " + page);
    }

    Dictionary<string, object> status = new Dictionary<string, object>();

    void Poll()
    {
        var st = ReadJson(Path.Combine(work, "status.json"));
        if (st != null)
        {
            status = st;
            version = S(st, "version") ?? version;
            var s = Strings(st, "steps");
            if (s.Length > 0) steps = s;
            stepState = S(st, "state") ?? stepState;
            percent = Int(st, "percent", -1);
            done = Long(st, "done", 0);
            total = Long(st, "total", 0);
        }
        if (proc == null || !proc.HasExited) return;
        // install.ps1 has ended: its last word decides
        st = ReadJson(Path.Combine(work, "status.json")) ?? status;
        notes = Strings(st, "notes");
        exePath = S(st, "exe");
        string kind = S(st, "result"), say = S(st, "say");
        if (kind == "ok")
        {
            string body = !string.IsNullOrEmpty(app.Command)
                ? T("Yeni bir terminal aç ve '" + app.Command + "' yaz.", "Open a new terminal and type '" + app.Command + "'.")
                : app.Shortcut ? T("Başlat menüsünde: " + app.Name, "In the Start menu: " + app.Name) : "";
            body += (body.Length > 0 ? "\n" : "") + T("Güncellemek ya da kaldırmak için bu kurulumu yeniden çalıştır (ya da Ayarlar > Uygulamalar).",
                "To update or remove it later, run this setup again (or use Settings > Apps).");
            Finish("ok", S(st, "title"), body);
        }
        else if (kind == "warn" || kind == "error") Finish(kind, S(st, "title"), S(st, "body"));
        else if (say != null) Finish("ok", say, null); // removed / not installed / already up to date
        else Finish("error", T("Kurulum beklenmedik şekilde durdu", "Setup stopped unexpectedly"),
            T("PowerShell bir sonuç bildirmeden kapandı (çıkış kodu ", "PowerShell closed without reporting a result (exit code ") + proc.ExitCode + ").");
    }

    void Finish(string kind, string title, string body)
    {
        resultKind = kind;
        resultTitle = title ?? (kind == "ok" ? T("Tamamlandı", "Done") : T("Olmadı", "That didn't work"));
        resultBody = body;
        Go(Page.Result);
        if (smokeDir != null)
        {
            bool fromScript = status.ContainsKey("finished") || status.ContainsKey("say") || status.ContainsKey("result");
            bool good = smokeAction == "install" ? kind == "ok" && status.ContainsKey("exe") : fromScript && kind != "error";
            EndSmoke(good ? 0 : 1, kind + ": " + resultTitle + " | " + resultBody);
        }
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        // still running (closed from the taskbar): ask install.ps1 to roll back first
        if (page == Page.Progress && proc != null && !proc.HasExited && smokeDir == null)
        {
            RequestCancel();
            e.Cancel = true;
            return;
        }
        base.OnFormClosing(e);
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        timer.Stop();
        try { if (work != null && (proc == null || proc.HasExited)) Directory.Delete(work, true); } catch { }
        base.OnFormClosed(e);
    }

    // ---------------------------------------------------------------- CI

    public void StartSmoke(string dir, string act)
    {
        smokeDir = dir; smokeAction = act; smokeStart = DateTime.UtcNow;
        tr = false;
        ShowInTaskbar = false;
        StartPosition = FormStartPosition.Manual;
        Location = new Point(-6000, -6000);
        Shown += (s, e) =>
        {
            Go(Page.Options);
            action = act == "install" ? Act.Install : Act.Uninstall;
            var t = new System.Windows.Forms.Timer { Interval = 600 };
            t.Tick += (s2, e2) => { t.Stop(); StartAction(); };
            t.Start();
        };
    }

    void EndSmoke(int code, string message)
    {
        try
        {
            Directory.CreateDirectory(smokeDir);
            File.WriteAllText(Path.Combine(smokeDir, "smoke-" + (Environment.Is64BitProcess ? "x64" : "x86") + ".txt"),
                "exit " + code + "\n" + message + "\nstatus: " + new JavaScriptSerializer().Serialize(status) + "\n");
            using (var bmp = new Bitmap((int)W, (int)H))
            {
                k = 1; slideStart = DateTime.UtcNow.AddSeconds(-5);
                using (var g = Graphics.FromImage(bmp)) Render(g);
                bmp.Save(Path.Combine(smokeDir, "smoke-" + (Environment.Is64BitProcess ? "x64" : "x86") + ".png"), System.Drawing.Imaging.ImageFormat.Png);
            }
        }
        catch { }
        Environment.ExitCode = code;
        smokeDir = null;
        BeginInvoke((Action)Close);
    }

    static bool offline; // the screenshots need no network

    public static void Shots(string dir)
    {
        Directory.CreateDirectory(dir);
        offline = true;
        foreach (bool turkish in new[] { true, false })
        {
            string l = turkish ? "tr" : "en";
            Shot(dir, l + "-1-welcome", turkish, false, f => { f.installed = null; f.latest = "1.4.0"; f.latestChecked = true; f.latestFailed = false; f.action = Act.Install; });
            Shot(dir, l + "-1-welcome-installed", turkish, true, f => { f.installed = "1.3.2"; f.latest = "1.4.0"; f.latestChecked = true; f.latestFailed = false; f.action = Act.Update; });
            Shot(dir, l + "-2-options", turkish, false, f => { f.page = Page.Options; f.installed = null; f.latest = "1.4.0"; f.latestChecked = true; f.latestFailed = false; f.desktop = true; });
            Shot(dir, l + "-2-uninstall", turkish, false, f => { f.page = Page.Options; f.installed = "1.4.0"; f.action = Act.Uninstall; f.purge = true; });
            Shot(dir, l + "-3-download", turkish, false, f =>
            {
                f.page = Page.Progress; f.version = "1.4.0"; f.percent = 42; f.done = 14L << 20; f.total = 33L << 20;
                f.steps = turkish ? new[] { "Son sürüm aranıyor", "İndiriliyor " + f.app.Name + " 1.4.0" } : new[] { "Looking for the latest release", "Downloading " + f.app.Name + " 1.4.0" };
            });
            Shot(dir, l + "-4-done", turkish, false, f =>
            {
                f.page = Page.Result; f.resultKind = "ok";
                f.resultTitle = turkish ? "Hazır! " + f.app.Name + " 1.4.0 kuruldu" : "All set! " + f.app.Name + " 1.4.0 is installed";
                f.resultBody = turkish ? "Başlat menüsünde: " + f.app.Name : "In the Start menu: " + f.app.Name;
            });
            Shot(dir, l + "-5-error", turkish, true, f =>
            {
                f.page = Page.Result; f.resultKind = "error";
                f.resultTitle = turkish ? "Olmadı, ama merak etme" : "That didn't work, but don't worry";
                f.resultBody = turkish ? "Kurulum 'İndiriliyor' adımında takıldı. Bilgisayarında hiçbir şey yarım kalmadı." : "The install got stuck at 'Downloading'. Nothing was left half-done.";
            });
        }
        offline = false;
    }

    static void Shot(string dir, string name, bool turkish, bool isLight, Action<SetupForm> setup)
    {
        using (var f = new SetupForm())
        {
            f.timer.Stop();
            f.tr = turkish;
            f.SetTheme(isLight);
            f.slideStart = DateTime.UtcNow.AddSeconds(-5);
            f.tick = 7;
            setup(f);
            using (var bmp = new Bitmap((int)W, (int)H))
            {
                using (var g = Graphics.FromImage(bmp)) f.Render(g);
                bmp.Save(Path.Combine(dir, name + (isLight ? "-light" : "") + ".png"), System.Drawing.Imaging.ImageFormat.Png);
            }
        }
    }

    // ---------------------------------------------------------------- helpers

    static Dictionary<string, object> ReadJson(string path)
    {
        try
        {
            if (path == null || !File.Exists(path)) return null;
            string text;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (var sr = new StreamReader(fs, System.Text.Encoding.UTF8)) text = sr.ReadToEnd();
            return new JavaScriptSerializer().DeserializeObject(text) as Dictionary<string, object>;
        }
        catch { return null; }
    }

    static string S(Dictionary<string, object> d, string key) { object v; return d.TryGetValue(key, out v) && v != null ? Convert.ToString(v) : null; }
    static int Int(Dictionary<string, object> d, string key, int def) { object v; try { return d.TryGetValue(key, out v) && v != null ? Convert.ToInt32(v) : def; } catch { return def; } }
    static long Long(Dictionary<string, object> d, string key, long def) { object v; try { return d.TryGetValue(key, out v) && v != null ? Convert.ToInt64(v) : def; } catch { return def; } }
    static string[] Strings(Dictionary<string, object> d, string key)
    {
        object v;
        if (!d.TryGetValue(key, out v) || v == null) return new string[0];
        var arr = v as object[];
        if (arr == null) return new[] { Convert.ToString(v) }; // a one-item list can arrive as a plain string
        var list = new List<string>();
        foreach (var o in arr) if (o != null) list.Add(Convert.ToString(o));
        return list.ToArray();
    }

    Font F(float px, bool bold = false)
    {
        string key = px + (bold ? "b" : "");
        Font f;
        if (!fonts.TryGetValue(key, out f))
        {
            string family = FontExists("Segoe UI Variable Text") ? "Segoe UI Variable Text" : "Segoe UI";
            if (bold && FontExists("Segoe UI Variable Display")) family = "Segoe UI Variable Display";
            fonts[key] = f = new Font(family, px, bold ? FontStyle.Bold : FontStyle.Regular, GraphicsUnit.Pixel);
        }
        return f;
    }

    void ClearFonts() { foreach (var f in fonts.Values) f.Dispose(); fonts.Clear(); }

    static bool? hasVariable;
    static bool FontExists(string name)
    {
        if (name.StartsWith("Segoe UI Variable") && hasVariable.HasValue) return hasVariable.Value;
        using (var fam = new InstalledFontCollection())
            foreach (var f in fam.Families) if (f.Name == name) { if (name.StartsWith("Segoe UI Variable")) hasVariable = true; return true; }
        if (name.StartsWith("Segoe UI Variable")) hasVariable = false;
        return false;
    }

    static void Str(Graphics g, string s, Font f, Color c, float x, float y, float w, float h)
    {
        using (var b = new SolidBrush(c))
        using (var fmt = new StringFormat(StringFormatFlags.NoWrap) { Trimming = StringTrimming.EllipsisCharacter })
            g.DrawString(s ?? "", f, b, new RectangleF(x, y, w, h), fmt);
    }

    // centred in r (buttons, chips): no measuring, so nothing is cut
    static void StrCenter(Graphics g, string s, Font f, Color c, RectangleF r)
    {
        using (var b = new SolidBrush(c))
        using (var fmt = new StringFormat(StringFormatFlags.NoWrap) { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center, Trimming = StringTrimming.EllipsisCharacter })
            g.DrawString(s, f, b, r, fmt);
    }

    // wrapped text; returns the bottom
    static float StrWrap(Graphics g, string s, Font f, Color c, float x, float y, float w, float maxH)
    {
        s = s ?? "";
        var size = g.MeasureString(s, f, (int)w);
        using (var b = new SolidBrush(c)) g.DrawString(s, f, b, new RectangleF(x, y, w, Math.Min(maxH, size.Height + 2)));
        return y + Math.Min(maxH, size.Height);
    }

    // line glyphs (no icon font needed)
    static void Glyph(Graphics g, string name, RectangleF r, Color c)
    {
        using (var p = new Pen(c, Math.Max(1.5f, r.Width / 12f)) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round })
        {
            float x = r.X, y = r.Y, w = r.Width, h = r.Height;
            if (name == "check") g.DrawLines(p, new[] { new PointF(x + w * 0.24f, y + h * 0.52f), new PointF(x + w * 0.43f, y + h * 0.70f), new PointF(x + w * 0.78f, y + h * 0.32f) });
            else if (name == "close")
            {
                float a = w * 0.32f;
                g.DrawLine(p, x + a, y + a, x + w - a, y + h - a);
                g.DrawLine(p, x + w - a, y + a, x + a, y + h - a);
            }
            else if (name == "bang")
            {
                g.DrawLine(p, x + w / 2, y + h * 0.26f, x + w / 2, y + h * 0.56f);
                g.DrawLine(p, x + w / 2, y + h * 0.74f, x + w / 2, y + h * 0.75f);
            }
            else if (name == "update")
            {
                g.DrawLine(p, x + w / 2, y + h * 0.18f, x + w / 2, y + h * 0.70f);
                g.DrawLines(p, new[] { new PointF(x + w * 0.28f, y + h * 0.48f), new PointF(x + w / 2, y + h * 0.70f), new PointF(x + w * 0.72f, y + h * 0.48f) });
                g.DrawLine(p, x + w * 0.22f, y + h * 0.86f, x + w * 0.78f, y + h * 0.86f);
            }
            else if (name == "repair")
            {
                g.DrawArc(p, x + w * 0.16f, y + h * 0.16f, w * 0.68f, h * 0.68f, 40, 290);
                g.DrawLines(p, new[] { new PointF(x + w * 0.80f, y + h * 0.18f), new PointF(x + w * 0.80f, y + h * 0.40f), new PointF(x + w * 0.58f, y + h * 0.40f) });
            }
            else if (name == "trash")
            {
                g.DrawLine(p, x + w * 0.18f, y + h * 0.28f, x + w * 0.82f, y + h * 0.28f);
                g.DrawLine(p, x + w * 0.40f, y + h * 0.16f, x + w * 0.60f, y + h * 0.16f);
                g.DrawLines(p, new[] { new PointF(x + w * 0.28f, y + h * 0.28f), new PointF(x + w * 0.32f, y + h * 0.86f), new PointF(x + w * 0.68f, y + h * 0.86f), new PointF(x + w * 0.72f, y + h * 0.28f) });
            }
            else if (name == "sun")
            {
                g.DrawEllipse(p, x + w * 0.32f, y + h * 0.32f, w * 0.36f, h * 0.36f);
                for (int i = 0; i < 8; i++)
                {
                    double a = i * Math.PI / 4;
                    float cx = x + w / 2, cy = y + h / 2;
                    g.DrawLine(p, cx + (float)Math.Cos(a) * w * 0.32f, cy + (float)Math.Sin(a) * h * 0.32f, cx + (float)Math.Cos(a) * w * 0.44f, cy + (float)Math.Sin(a) * h * 0.44f);
                }
            }
            else if (name == "moon")
            {
                // a crescent: a disc with an offset disc cut out of it
                using (var disc = new GraphicsPath()) using (var cut = new GraphicsPath()) using (var b = new SolidBrush(c))
                {
                    disc.AddEllipse(x + w * 0.14f, y + h * 0.14f, w * 0.72f, h * 0.72f);
                    cut.AddEllipse(x + w * 0.38f, y + h * 0.02f, w * 0.62f, h * 0.62f);
                    using (var region = new Region(disc)) { region.Exclude(cut); g.FillRegion(b, region); }
                }
            }
        }
    }

    static GraphicsPath RoundPath(float x, float y, float w, float h, float r)
    {
        var path = new GraphicsPath();
        float d = Math.Min(r * 2, Math.Min(w, h));
        if (d <= 0.5f) { path.AddRectangle(new RectangleF(x, y, w, h)); return path; }
        path.AddArc(x, y, d, d, 180, 90);
        path.AddArc(x + w - d, y, d, d, 270, 90);
        path.AddArc(x + w - d, y + h - d, d, d, 0, 90);
        path.AddArc(x, y + h - d, d, d, 90, 90);
        path.CloseFigure();
        return path;
    }

    static void FillRound(Graphics g, Color c, float x, float y, float w, float h, float r)
    {
        using (var b = new SolidBrush(c)) using (var p = RoundPath(x, y, w, h, r)) g.FillPath(b, p);
    }

    static void DrawRound(Graphics g, Color c, float width, float x, float y, float w, float h, float r)
    {
        using (var pen = new Pen(c, width)) using (var p = RoundPath(x, y, w, h, r)) g.DrawPath(pen, p);
    }

    static void FillCircle(Graphics g, Color c, float cx, float cy, float r)
    {
        using (var b = new SolidBrush(c)) g.FillEllipse(b, cx - r, cy - r, r * 2, r * 2);
    }

    static Color Hex(string h)
    {
        int v = Convert.ToInt32(h.TrimStart('#'), 16);
        return Color.FromArgb(255, (v >> 16) & 255, (v >> 8) & 255, v & 255);
    }

    static Color Mix(Color a, Color b, float t)
    {
        return Color.FromArgb(255, (int)(a.R + (b.R - a.R) * t), (int)(a.G + (b.G - a.G) * t), (int)(a.B + (b.B - a.B) * t));
    }

    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    [DllImport("dwmapi.dll")] static extern int DwmFlush();
    [DllImport("user32.dll")] static extern bool ReleaseCapture();
    [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hwnd, int msg, IntPtr wp, IntPtr lp);
}
