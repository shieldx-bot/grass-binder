# ============================================================
# GRASS DESKTOP — FULL CODE + HOTFIX 12
# Deepnote / Clusy: không cần dpkg, cách ly glibc 2.39 khỏi Xvfb
#
# HOTFIX 10 (so với 9z-17):
#  1. fix crash "bash: symbol lookup error ... __tunable_is_initialized
#     GLIBC_PRIVATE": KHÔNG còn đưa glibc239 vào LD_LIBRARY_PATH của
#     bash/tiến trình con (host ld.so cũ + libc 2.39 = crash). glibc239
#     chỉ đi qua rpath của ELF đã patch / --library-path của ld 2.39.
#  2. patch interpreter luôn cho WebKitWebProcess/WebKitNetworkProcess
#     trong LIBROOT (trước đây chỉ vá APP_ROOT -> helper chết sau đó).
#  3. extract_deb_py: fallback zstd nhiều tầng (zstandard -> stdlib py3.14
#     -> pip cài lại -> CLI zstd) — hết lỗi "No module named 'zstandard'".
#  4. rootless apt: sources.list + lists + cache đặt trong LIBROOT (ghi
#     được) và chạy `apt-get update` trước -> hết lỗi "rootless OK: 0 gói,
#     lỗi: 22" trên máy không có dpkg/list (vd /hex).
#  5. HOTFIX 11: fallback tải .deb TRỰC TIẾP qua HTTPS — tự tải index
#     Packages.gz của Ubuntu, tự giải closure deps, không cần apt chút nào
#     (dùng khi apt-get/apt-cache tê liệt hoàn toàn, vd /hex).
#  6. HOTFIX 11: cấm extract libc6/libc-bin vào LIBROOT — nếu libc 2.39 lọt
#     vào LD_LIBRARY_PATH qua LIBROOT thì mọi binary host crash
#     GLIBC_PRIVATE ở lần chạy thứ 2+ (điểm mù của 9z-17 và hotfix 10).
#  7. HOTFIX 12: app được Popen THẲNG argv (không bash/sh) -> trả lại
#     glibc239 ĐẦU LD_LIBRARY_PATH của app: libresolv/libm/libpthread...
#     phải là bản 2.39 khớp libc 2.39, không được lấy từ host (host
#     libresolv yêu cầu version node GLIBC_ABI_DT_X86_64_PLT mà libc 2.39
#     Ubuntu không export -> "version not found" trên /hex).
#  8. HOTFIX 12: filter extract mới — symlink tuyệt đối (tzdata localtime,
#     fontconfig conf.d...) bị BỎ QUA thay vì làm hỏng cả deb.
#  9. HOTFIX 12: zstd — thử CLI zstd TRƯỚC pip; pip chỉ thử 1 lần
#     (venv không có pip gây spam "No module named pip"); bỏ qua hẳn
#     glibc239 nếu host đã >= 2.39.
# 10. HOTFIX 13: SESSION_FILE nhận URL (Google Drive) — tự tải session
#     tgz về SESSION_DIR, nạp store.json/token TRƯỚC khi app mở
#     (WebKit chỉ đọc session lúc khởi động). Có phiên thật -> bỏ qua
#     auto_login gõ tay (dễ dính reCAPTCHA, như log "asking the host
#     who is signed in" lặp vô hạn khi chưa đăng nhập).
# 11. HOTFIX 13: vòng health tự chữa — nếu phát hiện guest/empty mà có
#     file phiên THẬT -> restore + restart app tự động.
# 12. HOTFIX 13: pip mss thêm --break-system-packages (PEP 668).
# 13. HOTFIX 14: nhận diện distro từ /etc/os-release — Debian (Clusy trixie)
#     dùng deb.debian.org, Ubuntu dùng archive.ubuntu.com. Hết lỗi 404
#     "dists/trixie" (Ubuntu không có trixie).
# 14. HOTFIX 14: alias tên gói — Debian 13/Ubuntu 24.04 đổi libgtk-3-0 ->
#     libgtk-3-0t64, libappindicator3-1 -> libayatana-appindicator3-1.
#     Hết panic "Failed to load ayatana-appindicator3" lúc mở app.
# 15. HOTFIX 15: Deepnote (root + apt) — app dùng webkit HỆ THỐNG, helper
#     spawn từ /usr/lib/... kế thừa LD_LIBRARY_PATH glibc239 -> "symbol
#     lookup error". Copy helpers về LIBROOT + vá cả libwebkit2gtk hệ
#     thống trỏ helper sang $BASE/wk; vá interpreter cho helpers mới copy.
# 16. HOTFIX 16: earning_status() — đọc log engine chấm ĐANG KIẾM ĐIỂM /
#     ĐANG NGHỈ (bridge tunnel, sharing paused, device registered, TCP);
#     fix take_screenshot (lỗi "local variable 'mss'").
# ============================================================

import sys, os, re, time, json, shutil, subprocess, glob, tarfile, urllib.request, io

ON_COLAB  = "google.colab" in sys.modules
_kaggle_dir = os.path.isdir("/kaggle/working")
_kaggle_env = "KAGGLE_KERNEL_RUN_TYPE" in os.environ
if _kaggle_env and not _kaggle_dir:
    print(f"[env] bỏ qua tín hiệu Kaggle giả: KAGGLE_KERNEL_RUN_TYPE={os.environ.get('KAGGLE_KERNEL_RUN_TYPE')!r}")
ON_KAGGLE = _kaggle_dir
ON_REMOTE = True

def _usable_dir(p):
    try:
        return os.path.isdir(p) and os.access(p, os.R_OK | os.W_OK | os.X_OK)
    except Exception:
        return False

def _pick_base():
    try:
        cands = (["/kaggle/working"] if _kaggle_dir else []) + ["/content", os.getcwd(), "/tmp"]
        for c in cands:
            if _usable_dir(c):
                return c
    except Exception:
        pass
    return "/tmp"

BASE = _pick_base()
try:
    os.makedirs(BASE, exist_ok=True)
    _wt = os.path.join(BASE, ".grass_write_test")
    with open(_wt, "w") as _f:
        _f.write("ok")
    os.remove(_wt)
except Exception:
    print(f"[env] {BASE} không ghi được -> dùng /tmp")
    BASE = "/tmp"

print(f"ENV: colab={ON_COLAB} kaggle={ON_KAGGLE} base={BASE}")
print("[hotfix] GRASS HOTFIX 16 — earning_status() + fix screenshot mss")
print("[hotfix] nếu không thấy dòng này trong log = bạn đang chạy cell CŨ!")

# ---------- CONFIG ----------
MANIFEST_URL = "https://files.grass.io/file/grass-extension-upgrades/desktop-installer-latest.json"

# HOTFIX 16 (bản repo công khai): KHÔNG còn chứa email/mật khẩu.
# Điền thông tin trong notebook TRƯỚC khi gọi main(), ví dụ:
#   import os
#   os.environ["GRASS_EMAIL"] = "ban@gmail.com"
#   os.environ["GRASS_PASSWORD"] = "..."      # hoặc chỉ dùng session URL bên dưới
EMAIL = os.environ.get("GRASS_EMAIL", "")
PASSWORD = os.environ.get("GRASS_PASSWORD", "")

CONNECT_XY = (176, 352)
# HOTFIX 13: nhận cả URL (Drive). File "grass_desktop_session (4).tgz"
# chứa accessToken hết hạn 2027-10-26 / refreshToken hết hạn 2026-12-30.
# Dán URL session Drive của BẠN vào notebook (KHÔNG commit lên GitHub!):
#   os.environ["GRASS_SESSION_URL"] = "https://drive.google.com/uc?export=download&id=<FILE_ID>"
SESSION_FILE = os.environ.get("GRASS_SESSION_URL", "")
SKIP_WEBKIT_CACHE = True
GOOGLE_LOGIN_URL = "https://api.grass.io/auth/google?redirectUrl=grass%3A%2F%2Flocalhost"
MY_USER_ID = ""
GRASS_ENFORCE_ACCOUNT = False

HF_STATUS_REPO = "shieldX-Adam/grass-control"
HF_TOKEN_SECRET = "HF_TOKEN"
HF_PUSH_EVERY = 3

TABS_BEFORE_EMAIL = 0
TABS_BEFORE_PASSWORD = 1

SLEEP_SECONDS = 600
MAX_LOOPS = None
RUN_MODE = True
AUTO_UPDATE = True
DEVICE_NAME = ""
AUTO_SAVE_SESSION = True
SHOW_SHOT_IN_LOOP = False

SESSION_DIR = f"{BASE}/grass_desktop_session"
APP_ROOT = f"{BASE}/grass_app"
LIBROOT = f"{BASE}/grass_libs"
DEB_PATH = f"{BASE}/grass-desktop.deb"
APP_BIN = f"{APP_ROOT}/usr/bin/grass-desktop"
APP_LOG = f"{BASE}/grass_app.log"
VERSION_FILE = f"{APP_ROOT}/.installed_version"
DISPLAY_NUM = 99
HOME = os.path.expanduser("~")

# ---------- CLEAN SYSTEM ENV ----------
def _clean_system_env():
    """
    Env cho Xvfb, xdotool, dbus, python, openbox...
    Không được để glibc239 trong LD_LIBRARY_PATH.
    """
    env = dict(os.environ)
    lp = env.get("LD_LIBRARY_PATH", "")
    parts = []
    for p in lp.split(":"):
        if not p:
            continue
        if "/glibc239/" in p:
            continue
        parts.append(p)
    if parts:
        env["LD_LIBRARY_PATH"] = ":".join(parts)
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env

# làm sạch env hiện tại ngay
_os_clean = _clean_system_env()
if _os_clean.get("LD_LIBRARY_PATH"):
    os.environ["LD_LIBRARY_PATH"] = _os_clean["LD_LIBRARY_PATH"]
else:
    os.environ.pop("LD_LIBRARY_PATH", None)

# ---------- UTILS ----------
def _have_cmd(cmd):
    return shutil.which(cmd) is not None

def _check_internet():
    try:
        urllib.request.urlopen("https://pypi.org", timeout=10)
        return True
    except Exception:
        return False

if not _check_internet():
    print("[!] internet yếu — vẫn tiếp tục, health-check sẽ tự khởi động lại khi cần.")

_PIP_ZSTD_DEAD = False

def _zstd_decompress_blob(blob):
    """
    Giải nén zstd với nhiều tầng fallback (deb Ubuntu 24.04 nén bằng zstd).
    Thứ tự: module zstandard -> stdlib (py>=3.14) -> pip cài lại -> CLI zstd.
    """
    # 1) module zstandard
    try:
        import zstandard as zstd
        return zstd.ZstdDecompressor().decompress(blob, max_output_size=2 * 1024 * 1024 * 1024)
    except ImportError:
        pass

    # 2) stdlib compression.zstd (Python >= 3.14)
    try:
        from compression import zstd as _cz
        return _cz.decompress(blob)
    except Exception:
        pass

    # 3) CLI zstd — NHANH và KHÔNG cần pip (trên /hex pip không có,
    #    nhưng CLI zstd có sẵn; thử CLI trước để khỏi spam pip)
    zb = shutil.which("zstd")
    if not zb:
        for cand in (glob.glob(f"{LIBROOT}/usr/bin/zstd*") + glob.glob("/usr/bin/zstd*")
                     + glob.glob("/bin/zstd*")):
            if os.path.isfile(cand):
                zb = cand
                break
    if zb:
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                fin = os.path.join(td, "in.zst")
                fout = os.path.join(td, "out.tar")
                open(fin, "wb").write(blob)
                r = subprocess.run([zb, "-d", "-f", fin, "-o", fout],
                                   capture_output=True, timeout=120)
                if r.returncode == 0 and os.path.exists(fout) and os.path.getsize(fout) > 0:
                    return open(fout, "rb").read()
                print("[zstd] CLI zstd lỗi:", (r.stderr or b"").decode(errors="ignore")[:200])
        except Exception as e:
            print("[zstd] CLI zstd lỗi:", str(e)[:200])

    # 4) pip cài zstandard — CHỈ thử 1 lần (venv không pip sẽ spam 500 dòng)
    global _PIP_ZSTD_DEAD
    if _PIP_ZSTD_DEAD:
        raise RuntimeError("không giải nén được zstd (pip + CLI zstd đều không dùng được)")
    _PIP_ZSTD_DEAD = True
    try:
        for extra in ([], ["--break-system-packages"]):
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                 "-q", *extra, "zstandard"],
                capture_output=True, text=True, timeout=180
            )
            if r.returncode == 0:
                import zstandard as zstd
                return zstd.ZstdDecompressor().decompress(blob, max_output_size=2 * 1024 * 1024 * 1024)
        print("[zstd] pip zstandard lỗi:",
              ((r.stderr or "") + (r.stdout or "")).strip()[-300:])
    except Exception as e:
        print("[zstd] pip zstandard lỗi:", str(e)[:200])

    raise RuntimeError("không giải nén được zstd — cần pip zstandard hoặc CLI zstd")

def _deb_member_filter(m, path):
    """
    HOTFIX 12: filter extract — symlink tuyệt đối (vd
    './usr/share/zoneinfo/localtime' -> '/etc/localtime', fontconfig
    conf.d...) bị BỎ QUA thay vì làm HỎNG CẢ deb (trước đây 1 symlink
    lỗi -> cả package không được extract gì cả).
    """
    try:
        return tarfile.data_filter(m, path)
    except tarfile.TarError:
        if m.issym() or m.islnk():
            return None  # bỏ qua member lỗi, vẫn extract phần còn lại
        raise

def extract_deb_py(deb_path, dest):
    """
    Giải nén .deb không cần dpkg/ar.
    """
    if not os.path.isfile(deb_path):
        raise RuntimeError(f"Không tìm thấy deb: {deb_path}")
    if os.path.getsize(deb_path) < 100:
        raise RuntimeError(f"Deb quá nhỏ, có thể tải lỗi: {deb_path}")

    os.makedirs(dest, exist_ok=True)

    with open(deb_path, "rb") as f:
        magic = f.read(8)
        if magic != b"!<arch>\n":
            raise RuntimeError(f"Không phải deb/ar hợp lệ: {deb_path}")

        data_blob = None
        data_name = ""

        while True:
            hdr = f.read(60)
            if len(hdr) < 60:
                break

            name = hdr[0:16].decode("utf-8", "ignore").strip().strip("/")
            try:
                size = int(hdr[48:58].decode("ascii", "ignore").strip() or "0")
            except Exception:
                size = 0

            blob = f.read(size)
            if size % 2:
                f.read(1)

            if name.startswith("data.tar"):
                data_blob = blob
                data_name = name
                break

        if data_blob is None:
            raise RuntimeError(f"Không tìm thấy data.tar trong {deb_path}")

    tf = None
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data_blob), mode="r:*")
    except Exception as e:
        if data_name.endswith(".zst"):
            raw = _zstd_decompress_blob(data_blob)
            tf = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
        else:
            raise e

    with tf:
        try:
            tf.extractall(dest, filter=_deb_member_filter)
        except TypeError:
            tf.extractall(dest)

    return True

# ---------- APT / DEPS ----------
def _sudo_prefix():
    try:
        if os.geteuid() == 0:
            return []
    except Exception:
        pass
    return ["sudo", "-n"] if _have_cmd("sudo") else []

def _repair_dpkg():
    if not _have_cmd("dpkg"):
        return
    env = dict(_clean_system_env(), DEBIAN_FRONTEND="noninteractive")
    for _ in range(30):
        if not subprocess.getoutput("pgrep -x 'apt|apt-get|dpkg' || true").strip():
            break
        time.sleep(2)
    print("[fix] dpkg bị ngắt -> 'dpkg --configure -a' ...")
    pre = _sudo_prefix()
    subprocess.run(pre + ["dpkg", "--configure", "-a", "--force-confdef", "--force-confold"],
                   capture_output=True, text=True, env=env)
    subprocess.run(pre + ["apt-get", "-f", "install", "-y"],
                   capture_output=True, text=True, env=env)

def _apt(*args):
    if not _have_cmd("apt-get"):
        return subprocess.CompletedProcess(["apt-get"] + list(args), 127, "", "apt-get missing")
    env = dict(_clean_system_env(), DEBIAN_FRONTEND="noninteractive")
    pre = _sudo_prefix()
    r = subprocess.run(pre + ["apt-get", "-o", "DPkg::Lock::Timeout=180", *args],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0 and "dpkg was interrupted" in ((r.stderr or "") + (r.stdout or "")):
        _repair_dpkg()
        r = subprocess.run(pre + ["apt-get", *args], capture_output=True, text=True, env=env)
    return r

PKG_GROUPS = [
    ["libwebkit2gtk-4.1-0"],
    ["libgtk-3-0"],
    ["libappindicator3-1", "libayatana-appindicator3-1"],
    ["xvfb"],
    ["xdotool"],
    ["wmctrl"],
    ["fonts-liberation"],
    ["xembedsniproxy", "stalonetray", "trayer"],
    ["python3-dbus"],
    ["openbox"],
    ["x11-xserver-utils"],
    ["dbus"],
    ["iproute2"],
    ["curl"],
    ["wget"],
]

def _lib_env():
    """
    LD_LIBRARY_PATH cho app/libs rootless.
    QUAN TRỌNG: không đưa glibc239 vào đây.
    """
    libs = ":".join([
        f"{LIBROOT}/usr/lib/x86_64-linux-gnu",
        f"{LIBROOT}/lib/x86_64-linux-gnu",
        f"{LIBROOT}/usr/lib",
        f"{LIBROOT}/lib",
    ])

    lp = os.environ.get("LD_LIBRARY_PATH", "")
    lp_parts = [p for p in lp.split(":") if p and "/glibc239/" not in p]

    for p in libs.split(":"):
        if p and p not in lp_parts:
            lp_parts.insert(0, p)

    if lp_parts:
        os.environ["LD_LIBRARY_PATH"] = ":".join(lp_parts)
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)

    xdd = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    if LIBROOT + "/usr/share" not in xdd:
        os.environ["XDG_DATA_DIRS"] = f"{LIBROOT}/usr/share:" + xdd

    if os.path.isdir(f"{LIBROOT}/usr/bin"):
        pb = f"{LIBROOT}/usr/bin"
        if pb not in os.environ.get("PATH", ""):
            os.environ["PATH"] = pb + ":" + os.environ.get("PATH", "")

    pd = f"{LIBROOT}/usr/lib/python3/dist-packages"
    if os.path.isdir(pd):
        pp = os.environ.get("PYTHONPATH", "")
        if pd not in pp:
            os.environ["PYTHONPATH"] = pd + ((":" + pp) if pp else "")

def _dpkg_installed(pkg):
    if not _have_cmd("dpkg"):
        return False
    try:
        return subprocess.run(["dpkg", "-s", pkg.split(":")[0]],
                              capture_output=True, env=_clean_system_env()).returncode == 0
    except Exception:
        return False

def _patch_webkit_paths():
    sys_dir = "/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1"
    src_dir = f"{LIBROOT}/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1"

    # HOTFIX 15: máy ROOT cài deps qua apt (Deepnote) -> LIBROOT trống,
    # app dùng webkit HỆ THỐNG -> helper spawn từ /usr/lib/... kế thừa
    # LD_LIBRARY_PATH chứa glibc239 -> "symbol lookup error" chết ngay.
    # Giải pháp: copy helpers về LIBROOT (bản riêng để vá interpreter
    # glibc239-safe) rồi vá cả libwebkit2gtk hệ thống trỏ sang $BASE/wk.
    if not os.path.isdir(src_dir) and os.path.isdir(sys_dir):
        try:
            os.makedirs(os.path.dirname(src_dir), exist_ok=True)
            shutil.copytree(sys_dir, src_dir, symlinks=True, dirs_exist_ok=True)
            print("[patch] đã copy WebKit helpers hệ thống -> LIBROOT (sẽ vá interpreter)")
        except Exception as e:
            print("[patch] copy helpers lỗi:", str(e)[:120])

    if not os.path.isdir(src_dir):
        return

    link = f"{BASE}/wk"
    try:
        if os.path.islink(link):
            os.remove(link)
        elif os.path.exists(link):
            shutil.rmtree(link)
        os.symlink(src_dir, link)
    except Exception:
        return

    oldp = b"/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1"
    newp = link.encode()

    targets = (
        glob.glob(f"{LIBROOT}/usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.1.so.*")
        + glob.glob(f"{LIBROOT}/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1/*")
        + glob.glob(f"{LIBROOT}/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1/injected-bundle/*")
    )

    # HOTFIX 15: vá cả libwebkit2gtk HỆ THỐNG — app (root + apt) đang load
    # webkit hệ thống nên helper bị spawn từ path host -> crash glibc239
    for _sys_so in (glob.glob("/usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.1.so.*"),
                    glob.glob("/usr/lib64/libwebkit2gtk-4.1.so.*")):
        targets += _sys_so
    _patched_sys = bool(glob.glob("/usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.1.so.*")
                        or glob.glob("/usr/lib64/libwebkit2gtk-4.1.so.*"))

    patched = 0
    for f in targets:
        if not os.path.isfile(f):
            continue
        try:
            data = open(f, "rb").read()
        except Exception:
            continue
        if oldp not in data:
            continue

        out = bytearray()
        i = 0
        while True:
            j = data.find(oldp, i)
            if j < 0:
                out += data[i:]
                break
            k = data.find(b"\x00", j)
            if k < 0:
                out += data[i:]
                break
            full = data[j:k]
            if full == oldp:
                new = newp
            elif full.startswith(oldp + b"/"):
                new = newp + full[len(oldp):]
            else:
                out += data[i:k]
                i = k
                continue

            if len(new) <= len(full):
                out += data[i:j] + new + b"\x00" * (len(full) - len(new))
                patched += 1
            else:
                out += data[i:k]
            i = k

        try:
            open(f, "wb").write(bytes(out))
        except Exception as e:
            if _patched_sys and f.startswith("/usr/"):
                print(f"[patch] ⚠️ không ghi được file hệ thống {f}: {str(e)[:80]}")

    if patched:
        print(f"[patch] đã vá {patched} đường dẫn libexec WebKit -> {link}")
    else:
        print(f"[patch] không có đường dẫn nào cần vá (helpers -> {link})")

_APT_USER_READY = False

# Gói hệ thống cốt lõi — TUYỆT ĐỐI không tải/extract vào LIBROOT:
# libc 2.39 lọt vào LD_LIBRARY_PATH (qua LIBROOT) sẽ làm CRASH mọi binary
# của host ("symbol lookup error ... GLIBC_PRIVATE"). Host đã có sẵn chúng.
_ESSENTIAL_SKIP = {
    "libc6", "libc-bin", "libc6-dev", "libgcc-s1", "libstdc++6", "gcc-14-base",
    "gcc-13-base", "base-files", "base-passwd", "dpkg", "debconf", "perl-base",
    "grep", "sed", "tar", "gzip", "bash", "dash", "coreutils", "util-linux",
    "mount", "passwd", "hostname", "adduser", "init-system-helpers",
    "libselinux1", "libpcre2-8-0", "libsystemd0", "libcap2", "libcap-ng0",
}

def _distro_info():
    """HOTFIX 14: nhận diện distro -> (id, codename).
    Clusy là Debian trixie (glibc 2.41) nhưng script cũ ép mọi thứ về
    Ubuntu archive -> dists/trixie 404 -> apt + direct-HTTPS đều tê liệt."""
    did = codename = ""
    try:
        for ln in open("/etc/os-release"):
            ln = ln.strip()
            if ln.startswith("ID=") and not did:
                did = ln.split("=", 1)[1].strip().strip('"')
            elif ln.startswith("VERSION_CODENAME="):
                codename = ln.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return (did or "ubuntu", codename or "noble")

def _apt_mirrors():
    did, _ = _distro_info()
    if did == "debian":
        return ["https://deb.debian.org/debian", "http://deb.debian.org/debian"]
    return ["https://archive.ubuntu.com/ubuntu", "http://archive.ubuntu.com/ubuntu"]

def _apt_components():
    did, _ = _distro_info()
    return ("main",) if did == "debian" else ("main", "universe")

def _ubuntu_codename():
    return _distro_info()[1]

# HOTFIX 14: tên gói cũ -> tên mới (Ubuntu 24.04+/Debian 13 đổi đuôi t64,
# appindicator3 bị thay bằng ayatana). Thử theo thứ tự.
_PKG_ALIASES = {
    "libgtk-3-0":           ("libgtk-3-0t64",),
    "libappindicator3-1":   ("libayatana-appindicator3-1",),
    "libayatana-appindicator3-1": ("libayatana-appindicator3-1",),
    "libdbusmenu-gtk3-4":   ("libdbusmenu-gtk3-4",),
}

def _resolve_pkg(p):
    """Trả về tên gói có thật trong index (ưu tiên alias), hoặc p nguyên gốc."""
    for a in _PKG_ALIASES.get(p, (p,)):
        try:
            if a in _load_apt_index():
                return a
        except Exception:
            pass
    return p

_DIRECT_INDEX = {}

def _load_apt_index(max_age=6 * 3600):
    """
    HOTFIX 11: tự tải index Packages.gz (main + universe, binary-amd64) của
    Ubuntu qua HTTPS bằng urllib — KHÔNG cần apt. Parse thành
    {tên_gói: (filename_trong_pool, chuỗi_depends, essential)}.
    """
    if _DIRECT_INDEX:
        return _DIRECT_INDEX

    import gzip
    did, codename = _distro_info()
    idx_dir = f"{LIBROOT}/apt/direct"
    os.makedirs(idx_dir, exist_ok=True)

    mirrors = _apt_mirrors()
    for comp in _apt_components():
        gz = f"{idx_dir}/Packages_{comp}.gz"
        need = not (os.path.exists(gz)
                    and time.time() - os.path.getmtime(gz) < max_age
                    and os.path.getsize(gz) > 1000)
        if need:
            last_err = ""
            for mir in mirrors:
                url = f"{mir}/dists/{codename}/{comp}/binary-amd64/Packages.gz"
                try:
                    _download(url, gz + ".tmp")
                    os.replace(gz + ".tmp", gz)
                    last_err = ""
                    break
                except Exception as e:
                    last_err = str(e)[:140]
            if last_err:
                print(f"[direct] không tải được index {comp}: {last_err}")
                continue
        try:
            text = gzip.open(gz, "rt", encoding="utf-8", errors="ignore").read()
        except Exception as e:
            print(f"[direct] đọc index {comp} lỗi:", str(e)[:140])
            continue

        for stanza in text.split("\n\n"):
            if not stanza.startswith("Package:"):
                continue
            m = re.search(r"^Package: (\S+)$", stanza, re.M)
            f = re.search(r"^Filename: (\S+)$", stanza, re.M)
            if not m or not f:
                continue
            d = re.search(r"^Depends: (.*)$", stanza, re.M)
            ess = bool(re.search(r"^Essential: yes$", stanza, re.M))
            _DIRECT_INDEX[m.group(1)] = (f.group(1), d.group(1) if d else "", ess)

    print(f"[direct] index {did} {codename}: {len(_DIRECT_INDEX)} gói")
    return _DIRECT_INDEX

def _direct_fetch(names):
    """
    HOTFIX 11: tải .deb trực tiếp từ pool Ubuntu qua HTTPS cho `names` +
    closure phụ thuộc (đọc từ index). Bỏ qua gói essential/libc6 để bảo vệ
    LIBROOT. Chỉ TẢI — việc extract do vòng lặp trong _rootless_download lo.
    """
    idx = _load_apt_index()
    if not idx:
        print("[direct] không có index -> không tải trực tiếp được")
        return 0

    debs_dir = f"{LIBROOT}/debs"
    os.makedirs(debs_dir, exist_ok=True)
    mirror = _apt_mirrors()[0]

    todo = [n.split(":")[0].strip() for n in names]
    seen = set()
    got = 0
    while todo:
        p = todo.pop(0).strip()
        if not p or p in seen:
            continue
        seen.add(p)
        ent = idx.get(p)
        if not ent:
            # HOTFIX 14: tên cũ -> tên mới (t64 / ayatana)
            alt = _resolve_pkg(p)
            if alt != p and alt in idx:
                p = alt
                ent = idx.get(p)
        if not ent:
            continue  # gói ảo / không có trong index -> bỏ qua
        fn, deps, ess = ent
        if ess or p in _ESSENTIAL_SKIP:
            continue  # host đã có sẵn; extract vào LIBROOT = tự sát

        deb_path = os.path.join(debs_dir, os.path.basename(fn))
        if not os.path.exists(deb_path) and not glob.glob(f"{debs_dir}/{p}_*.deb"):
            try:
                print(f"[direct] tải {p} ...")
                _download(f"{mirror}/{fn}", deb_path)
                got += 1
            except Exception as e:
                print(f"[direct] lỗi {p}: {str(e)[:140]}")
                continue

        for grp in deps.split(","):
            first = grp.split("|")[0].strip().split(":")[0].strip()
            parts = first.split()
            first = parts[0] if parts else ""
            if first and first not in seen and first in idx:
                todo.append(first)

    print(f"[direct] đã tải thêm {got} .deb (closure {len(seen)} gói xét qua)")
    return got

def _user_apt_opts(force_refresh=False):
    """
    apt rootless: sources.list + lists + cache đặt hết trong LIBROOT (ghi được),
    thay vì /var/lib/apt của hệ thống (không root / không ghi -> luôn fail).
    Trả về list option -o để nhét vào apt-get / apt-cache.
    """
    global _APT_USER_READY
    d = f"{LIBROOT}/apt"
    lists = f"{d}/lists"
    etc = f"{d}/etc"
    for p in (lists, f"{d}/cache/archives/partial", etc):
        os.makedirs(p, exist_ok=True)

    codename = ""
    try:
        for ln in open("/etc/os-release"):
            if ln.startswith("VERSION_CODENAME="):
                codename = ln.split("=", 1)[1].strip().strip('"')
                break
    except Exception:
        pass
    if not codename:
        codename = "noble"

    did = _distro_info()[0]
    mirror = _apt_mirrors()[0]
    src = f"{etc}/sources.list"
    if did == "debian":
        # HOTFIX 14: Debian (vd Clusy trixie) KHÔNG tồn tại trên
        # archive.ubuntu.com — phải dùng deb.debian.org
        content = (f"deb [trusted=yes] {mirror} {codename} main\n"
                   f"deb [trusted=yes] {mirror} {codename}-updates main\n")
    else:
        content = (f"deb [trusted=yes] {mirror} {codename} main universe\n"
                   f"deb [trusted=yes] {mirror} {codename}-updates main universe\n")
    if not os.path.exists(src) or open(src).read() != content:
        open(src, "w").write(content)
        _APT_USER_READY = False

    opts = [
        "-o", f"Dir::Etc::SourceList={src}",
        "-o", "Dir::Etc::SourceParts=-",
        "-o", f"Dir::State::Lists={lists}",
        "-o", f"Dir::Cache={d}/cache",
        "-o", "Debug::NoLocking=1",
        "-o", "APT::Get::List-Cleanup=0",
    ]

    if not _APT_USER_READY or force_refresh:
        try:
            r = subprocess.run(["apt-get", *opts, "update"],
                               capture_output=True, text=True,
                               env=_clean_system_env(), timeout=300)
            if r.returncode != 0:
                print("[deps] apt-get update (rootless) lỗi:",
                      ((r.stderr or "") + (r.stdout or "")).strip()[-250:])
        except Exception as e:
            print("[deps] apt-get update (rootless) lỗi:", str(e)[:200])
        _APT_USER_READY = True

    return opts

def _rootless_download(pkgs):
    os.makedirs(f"{LIBROOT}/debs", exist_ok=True)
    _lib_env()

    opts = []
    if _have_cmd("apt-get") and not _APT_USER_READY:
        try:
            opts = _user_apt_opts()
        except Exception:
            opts = []

    universe = []
    if _have_cmd("apt-cache"):
        try:
            if not opts:
                opts = _user_apt_opts()
            uni = subprocess.getoutput(
                "apt-cache " + " ".join(opts) +
                " depends --recurse --no-recommends --no-suggests --no-conflicts "
                "--no-breaks --no-replaces --no-enhances " + " ".join(pkgs) +
                " 2>/dev/null | grep -E '^[a-zA-Z0-9]' | sort -u"
            ).split()
            for p in uni:
                p = p.split(":")[0].strip()
                if p and p not in universe:
                    universe.append(p)
        except Exception:
            universe = []

    if not universe:
        universe = list(dict.fromkeys(pkgs))
        print("[deps] apt-cache không hoạt động -> dùng danh sách gói tối thiểu")

    out = []
    for p in universe:
        if not _dpkg_installed(p):
            out.append(p)

    # HOTFIX 14: map tên cũ -> tên mới trước khi tải (libgtk-3-0 -> t64,
    # libappindicator3-1 -> libayatana-appindicator3-1 ...)
    _resolved = []
    for p in out:
        r = _resolve_pkg(p)
        if r != p:
            print(f"[deps] alias: {p} -> {r}")
        if r and r not in _resolved:
            _resolved.append(r)
    out = _resolved

    print(f"[deps] rootless: closure {len(universe)} gói, cần tải {len(out)} gói")

    ok = fail = 0
    for p in out:
        if glob.glob(f"{LIBROOT}/debs/{p}_*.deb"):
            ok += 1
            continue

        if not _have_cmd("apt-get"):
            fail += 1
            continue

        r = subprocess.run(["apt-get", *opts, "download", p],
                           cwd=f"{LIBROOT}/debs",
                           capture_output=True, text=True,
                           env=_clean_system_env())
        if r.returncode == 0:
            ok += 1
        else:
            fail += 1
            msg = (r.stderr or r.stdout or "").strip()
            print(f"[deps] bỏ qua {p}: {msg[:120]}")

    # HOTFIX 11: apt tê liệt -> tải trực tiếp .deb qua HTTPS (tự giải deps)
    if fail:
        print(f"[deps] {fail} gói apt không tải được -> fallback direct-HTTPS ...")
        try:
            n2 = _direct_fetch(out)
            ok += n2
            fail = max(0, fail - n2)
        except Exception as e:
            print("[deps] direct-HTTPS lỗi:", str(e)[:160])

    for deb in glob.glob(f"{LIBROOT}/debs/*.deb"):
        # HOTFIX 11: libc6 (deb dùng cho glibc239) KHÔNG được extract vào
        # LIBROOT — libc 2.39 lọt LD_LIBRARY_PATH sẽ crash binary host.
        if os.path.basename(deb).startswith(("libc6_", "libc-bin_")):
            print(f"[deps] bỏ qua extract {os.path.basename(deb)} (bảo vệ LIBROOT)")
            continue
        try:
            extract_deb_py(deb, LIBROOT)
        except Exception as e:
            print(f"[deps] lỗi giải nén {deb}: {e}")

    _lib_env()

    try:
        qb = shutil.which("gdk-pixbuf-query-loaders")
        if qb:
            ldr = subprocess.getoutput(
                f"ls {LIBROOT}/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders/*.so 2>/dev/null"
            ).split()
            r = subprocess.run([qb] + ldr, capture_output=True, text=True, env=_clean_system_env())
            if r.returncode == 0 and r.stdout.startswith("#"):
                open(f"{LIBROOT}/pixbuf.loaders", "w").write(r.stdout)
                os.environ["GDK_PIXBUF_MODULE_FILE"] = f"{LIBROOT}/pixbuf.loaders"
    except Exception:
        pass

    print(f"[deps] rootless OK: {ok} gói, lỗi: {fail}")
    _patch_webkit_paths()
    return True

def install_deps():
    _lib_env()

    _root = False
    try:
        _root = os.geteuid() == 0
    except Exception:
        pass

    # Chỉ apt install khi thật sự có apt-get + dpkg.
    if _root and _have_cmd("apt-get") and _have_cmd("dpkg"):
        _apt("update", "-qq")
        for group in PKG_GROUPS:
            done = False
            for pkg in group:
                r = _apt("install", "-y", "-qq", pkg)
                if r.returncode == 0:
                    done = True
                    break
            if not done:
                print(f"[warn] không cài được: {' hoặc '.join(group)}")
        # HOTFIX 15: máy root dùng webkit hệ thống — vẫn phải vá helper path
        _patch_webkit_paths()
        return

    print("[deps] không dùng apt install (thiếu dpkg hoặc không root) -> rootless")

    _fast = (
        (bool(glob.glob(f"{LIBROOT}/usr/bin/Xvfb")) or _have_cmd("Xvfb") or os.path.exists("/usr/bin/Xvfb"))
        and (bool(glob.glob(f"{LIBROOT}/usr/bin/xkbcomp")) or _have_cmd("xkbcomp") or os.path.exists("/usr/bin/xkbcomp"))
        and (os.path.isdir(f"{LIBROOT}/usr/share/X11/xkb/rules") or os.path.isdir("/usr/share/X11/xkb/rules"))
        and (os.path.exists(f"{LIBROOT}/usr/bin/xdotool") or _have_cmd("xdotool"))
        and (os.path.exists(f"{LIBROOT}/usr/bin/openbox") or _have_cmd("openbox"))
        and bool(glob.glob(f"{LIBROOT}/usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.1.so.*"))
        and bool(glob.glob(f"{LIBROOT}/usr/lib/x86_64-linux-gnu/libgtk-3.so.*"))
        and (
            bool(glob.glob(f"{LIBROOT}/usr/lib/x86_64-linux-gnu/libayatana-appindicator3.so.*"))
            or bool(glob.glob(f"{LIBROOT}/usr/lib/x86_64-linux-gnu/libappindicator3.so.*"))
        )
    )

    if _fast and (not os.path.exists(APP_BIN) or not missing_libs()):
        print("[deps] đủ libs cache — bỏ qua tải/giải nén lại")
        _patch_webkit_paths()
        return

    _rootless_download([
        "libwebkit2gtk-4.1-0", "libgtk-3-0", "libgdk-pixbuf-2.0-0", "libsoup-3.0-0",
        "libjavascriptcoregtk-4.1-0", "libgdk-pixbuf2.0-bin", "xdotool", "openbox",
        "x11-xserver-utils", "fonts-liberation", "dbus-bin", "dbus",
        "python3-dbus", "python3-gi", "bubblewrap",
        "xvfb", "x11-xkb-utils", "xkb-data",
        "libayatana-appindicator3-1", "libappindicator3-1", "libdbusmenu-glib4", "libdbusmenu-gtk3-4",
    ])

# ---------- APP DOWNLOAD / MANIFEST ----------
def fetch_manifest():
    req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def installed_version():
    try:
        return open(VERSION_FILE, encoding="utf-8").read().strip()
    except Exception:
        return None

def _download(url, dest):
    d = os.path.dirname(os.path.abspath(dest)) or "."
    os.makedirs(d, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return os.path.getsize(dest)

def _chmod_tree(root):
    for dp, _, fns in os.walk(root):
        for fn in fns:
            try:
                os.chmod(os.path.join(dp, fn), 0o755)
            except Exception:
                pass

def missing_libs():
    if not os.path.exists(APP_BIN):
        return []
    _lib_env()
    try:
        out = subprocess.getoutput(f"ldd {APP_BIN} 2>&1 | grep 'not found'")
        return sorted(set(re.findall(r"(\S+)\s+=>\s+not found", out)))
    except Exception:
        return []

_LIB2PKG = {
    "libwebkit2gtk-4.1.so.0": ["libwebkit2gtk-4.1-0"],
    "libsoup-3.0.so.0": ["libsoup-3.0-0"],
    "libjavascriptcoregtk-4.1.so.0": ["libjavascriptcoregtk-4.1-0"],
    "libgtk-3.so.0": ["libgtk-3-0"],
    "libgdk-3.so.0": ["libgtk-3-0"],
    "libgdk_pixbuf-2.0.so.0": ["libgdk-pixbuf-2.0-0"],
    "libEGL.so.1": [],
    "libGL.so.1": [],
}

# ---------- GLIBC 2.39 + PATCHELF ----------
def _find_glibc_ld():
    gdir = f"{LIBROOT}/glibc239"
    for root, dirs, files in os.walk(gdir):
        for f in files:
            if f == "ld-linux-x86-64.so.2":
                return os.path.join(root, f)
    return None

def _host_glibc_ver():
    """HOTFIX 12: version glibc của host, vd (2, 36)."""
    try:
        v = os.confstr("CS_GNU_LIBC_VERSION") or ""
        m = re.search(r"(\d+)\.(\d+)", v)
        return (int(m.group(1)), int(m.group(2))) if m else None
    except Exception:
        return None

def ensure_glibc239():
    glibc_dir = f"{LIBROOT}/glibc239"
    os.makedirs(f"{LIBROOT}/debs", exist_ok=True)

    ld = _find_glibc_ld()
    if ld:
        return ld

    # HOTFIX 12: host đã đủ mới (>= 2.39) thì khỏi cần glibc239 —
    # trừ khi binary đã bị patch interpreter ở lần chạy trước (phải có
    # glibc239 để /tmp/ld-grass còn hoạt động).
    hv = _host_glibc_ver()
    already_patched = False
    try:
        already_patched = b"/tmp/ld-grass" in open(APP_BIN, "rb").read()
    except Exception:
        pass
    if hv and hv >= (2, 39) and not already_patched:
        print(f"[fix-glibc] host đã có glibc {hv[0]}.{hv[1]} >= 2.39 -> bỏ qua glibc239")
        return None

    urls = [
        "https://archive.ubuntu.com/ubuntu/pool/main/g/glibc/libc6_2.39-0ubuntu8.9_amd64.deb",
        "https://archive.ubuntu.com/ubuntu/pool/main/g/glibc/libc6_2.39-0ubuntu8_amd64.deb",
        "https://security.ubuntu.com/ubuntu/pool/main/g/glibc/libc6_2.39-0ubuntu8.9_amd64.deb",
        "http://archive.ubuntu.com/ubuntu/pool/main/g/glibc/libc6_2.39-0ubuntu8.9_amd64.deb",
    ]

    deb_path = f"{LIBROOT}/debs/libc6_2.39_amd64.deb"

    print("[fix-glibc] tải glibc 2.39 ...")
    ok = False
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r, open(deb_path, "wb") as f:
                shutil.copyfileobj(r, f)
            if os.path.getsize(deb_path) > 1_000_000:
                print("[fix-glibc] tải OK:", u)
                ok = True
                break
        except Exception as e:
            print("[fix-glibc] mirror lỗi:", u, str(e)[:120])

    if not ok:
        print("[fix-glibc] ❌ không tải được glibc")
        return None

    os.makedirs(glibc_dir, exist_ok=True)
    try:
        extract_deb_py(deb_path, glibc_dir)
    except Exception as e:
        print("[fix-glibc] lỗi giải nén glibc:", e)
        return None

    ld = _find_glibc_ld()
    if ld:
        print("[fix-glibc] ✅ linker:", ld)
        return ld

    print("[fix-glibc] ❌ không tìm thấy ld-linux-x86-64.so.2")
    return None

def _find_patchelf_in(base):
    try:
        for root, dirs, files in os.walk(base):
            if "patchelf" in files:
                p = os.path.join(root, "patchelf")
                if os.path.isfile(p):
                    return p
    except Exception:
        pass
    return None

def get_patchelf():
    p = shutil.which("patchelf")
    if p:
        return p

    local = f"{LIBROOT}/patchelf/usr/bin/patchelf"
    if os.path.exists(local):
        return local

    # 1) pip
    try:
        print("[fix-glibc] thử pip install patchelf ...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "patchelf"],
            env=_clean_system_env(),
            capture_output=True,
            timeout=180
        )
        p = shutil.which("patchelf")
        if p:
            return p

        for base in [sys.prefix, os.path.expanduser("~/.local"), LIBROOT]:
            p2 = _find_patchelf_in(base)
            if p2:
                os.makedirs(os.path.dirname(local), exist_ok=True)
                try:
                    shutil.copy2(p2, local)
                    os.chmod(local, 0o755)
                    return local
                except Exception:
                    return p2
    except Exception as e:
        print("[fix-glibc] pip patchelf lỗi:", str(e)[:120])

    # 2) apt-get download
    try:
        if _have_cmd("apt-get"):
            os.makedirs(f"{LIBROOT}/patchelf_deb", exist_ok=True)
            r = subprocess.run(
                ["apt-get", "download", "patchelf"],
                cwd=f"{LIBROOT}/patchelf_deb",
                env=_clean_system_env(),
                capture_output=True,
                text=True,
                timeout=120
            )
            if r.returncode == 0:
                debs = glob.glob(f"{LIBROOT}/patchelf_deb/*.deb")
                if debs:
                    extract_deb_py(debs[0], f"{LIBROOT}/patchelf")
                    if os.path.exists(local):
                        return local
    except Exception as e:
        print("[fix-glibc] apt patchelf lỗi:", str(e)[:120])

    # 3) GitHub
    try:
        print("[fix-glibc] thử tải patchelf GitHub ...")
        tar_path = f"{LIBROOT}/patchelf.tar.gz"
        url = "https://github.com/NixOS/patchelf/releases/download/0.18.0/patchelf-0.18.0-x86_64.tar.gz"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as r, open(tar_path, "wb") as f:
            shutil.copyfileobj(r, f)

        with tarfile.open(tar_path, "r:gz") as tf:
            try:
                tf.extractall(LIBROOT, filter="data")
            except TypeError:
                tf.extractall(LIBROOT)

        p2 = _find_patchelf_in(LIBROOT)
        if p2:
            os.makedirs(os.path.dirname(local), exist_ok=True)
            try:
                shutil.copy2(p2, local)
                os.chmod(local, 0o755)
            except Exception:
                pass
            return p2
    except Exception as e:
        print("[fix-glibc] GitHub patchelf lỗi:", str(e)[:120])

    return None

def patch_app_binaries(ld_linux=None):
    ld_linux = ld_linux or ensure_glibc239()
    if not ld_linux:
        return False

    short_link = "/tmp/ld-grass"
    try:
        if os.path.islink(short_link) or os.path.exists(short_link):
            os.remove(short_link)
        os.symlink(ld_linux, short_link)
        print("[fix-glibc] symlink:", short_link, "->", ld_linux)
    except Exception as e:
        print("[fix-glibc] không tạo được /tmp/ld-grass:", e)
        short_link = ld_linux

    pe = get_patchelf()
    if not pe:
        print("[fix-glibc] ⚠️ không có patchelf -> sẽ dùng linker wrapper cho process chính")
        return False

    glibc_lib = os.path.dirname(ld_linux)
    rpath = ":".join([
        glibc_lib,
        f"{LIBROOT}/usr/lib/x86_64-linux-gnu",
        f"{LIBROOT}/lib/x86_64-linux-gnu",
        f"{LIBROOT}/usr/lib",
        f"{LIBROOT}/lib",
        "/lib/x86_64-linux-gnu",
        "/usr/lib/x86_64-linux-gnu",
        "/lib64",
        "/usr/lib",
        "/lib",
    ])

    print("[fix-glibc] vá ELF interpreter trong APP_ROOT + webkit helpers ...")
    patched = 0
    errors = []

    # Quan trọng: WebKitWebProcess / WebKitNetworkProcess nằm trong LIBROOT,
    # không phải APP_ROOT — nếu không vá thì app lên được nhưng helper chết sau.
    _walk = list(os.walk(APP_ROOT))
    for _wk in (f"{LIBROOT}/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1",
                f"{LIBROOT}/usr/lib64/webkit2gtk-4.1"):
        if os.path.isdir(_wk):
            _walk += list(os.walk(_wk))

    for root, dirs, files in _walk:
        for fn in files:
            fp = os.path.join(root, fn)
            try:
                with open(fp, "rb") as f:
                    if f.read(4) != b"\x7fELF":
                        continue

                pr = subprocess.run([pe, "--print-interpreter", fp],
                                    capture_output=True, text=True, env=_clean_system_env())
                if pr.returncode != 0:
                    continue

                r1 = subprocess.run([pe, "--set-interpreter", short_link, fp],
                                    capture_output=True, text=True, env=_clean_system_env())
                r2 = subprocess.run([pe, "--set-rpath", rpath, fp],
                                    capture_output=True, text=True, env=_clean_system_env())

                if r1.returncode == 0:
                    patched += 1
                else:
                    errors.append((fp, r1.stderr or r1.stdout))
            except Exception as e:
                errors.append((fp, str(e)))

    print(f"[fix-glibc] patched ELF: {patched}")
    for fp, er in errors[:3]:
        print("[fix-glibc] patch warn:", fp, str(er)[:160])

    return patched > 0

def ensure_app(force_download=False):
    m = fetch_manifest()
    ver = m.get("version", "?")
    plat = (m.get("platforms") or {}).get("linux-x86_64") or {}
    url = plat.get("url")
    if not url:
        raise RuntimeError(f"Manifest không có linux-x86_64: {json.dumps(m)[:300]}")

    cur = installed_version()

    if os.path.exists(APP_BIN) and cur == ver and not missing_libs() and not force_download:
        print(f"✅ grass-desktop {cur} đã sẵn sàng ({APP_BIN})")
    else:
        print(f"⬇️ Tải grass-desktop {ver} ...")
        n = _download(url, DEB_PATH)
        print(f"   đã tải {n / 1e6:.1f} MB -> {DEB_PATH}")
        shutil.rmtree(APP_ROOT, ignore_errors=True)
        os.makedirs(APP_ROOT, exist_ok=True)
        extract_deb_py(DEB_PATH, APP_ROOT)
        _chmod_tree(APP_ROOT)
        open(VERSION_FILE, "w").write(ver)

    _lib_env()
    ld = ensure_glibc239()
    # HOTFIX 15: vá paths (có thể copy helpers hệ thống về LIBROOT) TRƯỚC,
    # để patch_app_binaries kịp vá interpreter cho helpers mới copy
    _patch_webkit_paths()
    patch_app_binaries(ld)
    _patch_webkit_paths()  # lần 2: nhẹ, chỉ bảo đảm symlink/patch còn nguyên

    miss = missing_libs()
    if miss:
        print("[fix] thiếu thư viện:", ", ".join(miss))
        pkgs = []
        for lib in miss:
            pkgs += _LIB2PKG.get(lib, [])
        if pkgs:
            _rootless_download(list(dict.fromkeys(pkgs)))

    print(f"✅ grass-desktop {ver} sẵn sàng")
    return True

def maybe_update():
    try:
        m = fetch_manifest()
        ver = m.get("version")
        if ver and ver != installed_version():
            print(f"[update] có bản mới {ver} (đang {installed_version()}) -> nâng cấp")
            if ensure_app(force_download=True):
                launch_app(force=True)
                return True
    except Exception as e:
        print("[update] bỏ qua:", e)
    return False

# ---------- XVFB ----------
_XVFB_PROC = None
_XKB_BIN_DIR = "/tmp/xb"

def _patch_xvfb_for_xkbcomp():
    xvfb_src = shutil.which("Xvfb") or f"{LIBROOT}/usr/bin/Xvfb"
    if not os.path.exists(xvfb_src):
        _ub = sorted(os.listdir(f"{LIBROOT}/usr/bin"))[:40] if os.path.isdir(f"{LIBROOT}/usr/bin") else []
        raise RuntimeError(
            "Không thấy Xvfb — deps chưa tải đủ. "
            f"Đã tìm: {xvfb_src} | {LIBROOT}/usr/bin: {_ub or '(trống/không có)'} | "
            "Xem các dòng [deps]/[direct] phía trên để biết vì sao tải thất bại."
        )

    xc = f"{LIBROOT}/usr/bin/xkbcomp"
    if not os.path.exists(xc) and not os.path.exists("/usr/bin/xkbcomp"):
        raise RuntimeError("Không thấy xkbcomp — chạy lại deps (gói x11-xkb-utils)")

    dstdir = f"{BASE}/xvfbrun"
    dst = f"{dstdir}/Xvfb"
    os.makedirs(dstdir, exist_ok=True)

    try:
        need = True
        if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(xvfb_src):
            need = open(dst, "rb").read().count(b"/tmp/xb") == 0

        if need:
            data = bytearray(open(xvfb_src, "rb").read())
            old = b"/usr/bin"
            new = _XKB_BIN_DIR.encode() + b"\x00" * (len(old) - len(_XKB_BIN_DIR))
            i = 0
            while True:
                i = data.find(old, i)
                if i < 0:
                    break
                data[i:i + len(old)] = new
                i += len(old)
            open(dst, "wb").write(bytes(data))
            os.chmod(dst, 0o755)
            print(f"[fix-xkb] đã vá Xvfb: '/usr/bin' -> '{_XKB_BIN_DIR}' ({dst})")
        else:
            print("[fix-xkb] Xvfb (đã vá) dùng lại")
    except Exception as e:
        print("[fix-xkb] vá binary lỗi:", e)
        if os.path.exists("/usr/bin/xkbcomp"):
            return xvfb_src
        raise

    os.makedirs(_XKB_BIN_DIR, exist_ok=True)
    src_xc = xc if os.path.exists(xc) else "/usr/bin/xkbcomp"
    shutil.copy2(src_xc, f"{_XKB_BIN_DIR}/xkbcomp")
    os.chmod(f"{_XKB_BIN_DIR}/xkbcomp", 0o755)
    return dst

def _xvfb_pids():
    out = []
    for s in glob.glob("/proc/[0-9]*/comm"):
        try:
            pid = int(s.split("/")[2])
            c = open(s, "rb").read().decode(errors="ignore").strip()
        except Exception:
            continue
        if c != "Xvfb" and not c.startswith("Xvfb."):
            continue
        try:
            st = open(f"/proc/{pid}/stat", "rb").read().decode(errors="ignore")
            if st.rsplit(")", 1)[1].split()[0] == "Z":
                continue
        except Exception:
            pass
        out.append(pid)
    return out

def xserver_alive():
    lock_file = f"/tmp/.X{DISPLAY_NUM}-lock"
    if os.path.exists(lock_file):
        try:
            lpid = int(open(lock_file).read().strip())
            if os.path.exists(f"/proc/{lpid}"):
                return True
        except Exception:
            pass

    sock_file = f"/tmp/.X11-unix/X{DISPLAY_NUM}"
    if os.path.exists(sock_file):
        if _have_cmd("fuser"):
            try:
                r = subprocess.run(["fuser", sock_file],
                                   capture_output=True, text=True,
                                   env=_clean_system_env())
                if r.returncode == 0 and r.stdout.strip():
                    return True
            except Exception:
                pass

    import socket as _s
    for addr in (f"/tmp/.X11-unix/X{DISPLAY_NUM}", f"\0/tmp/.X11-unix/X{DISPLAY_NUM}"):
        try:
            c = _s.socket(_s.AF_UNIX, _s.SOCK_STREAM)
            c.settimeout(2)
            c.connect(addr.encode() if addr.startswith("\0") else addr)
            c.close()
            return True
        except OSError:
            pass

    xdt = shutil.which("xdotool") or (f"{LIBROOT}/usr/bin/xdotool"
                                      if os.path.exists(f"{LIBROOT}/usr/bin/xdotool") else "")
    if xdt:
        try:
            env = dict(_clean_system_env(), DISPLAY=f":{DISPLAY_NUM}")
            r = subprocess.run([xdt, "getdisplaygeometry"],
                               env=env, capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and (r.stdout or "").strip():
                return True
        except Exception:
            pass

    return False

def _kill_all_xvfb():
    global _XVFB_PROC
    if _XVFB_PROC and _XVFB_PROC.poll() is None:
        try:
            _XVFB_PROC.kill()
        except Exception:
            pass

    lock_file = f"/tmp/.X{DISPLAY_NUM}-lock"
    if os.path.exists(lock_file):
        try:
            lpid = int(open(lock_file).read().strip())
            if os.path.exists(f"/proc/{lpid}"):
                os.kill(lpid, 9)
        except Exception:
            pass

    for p in _xvfb_pids():
        try:
            os.kill(p, 9)
        except Exception:
            pass

    subprocess.run("pkill -9 -x Xvfb; pkill -9 -x Xvfb.patched; pkill -9 -x openbox",
                   shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env=_clean_system_env())

    _XVFB_PROC = None

    for _ in range(20):
        alive = False
        if os.path.exists(lock_file):
            try:
                lpid = int(open(lock_file).read().strip())
                if os.path.exists(f"/proc/{lpid}"):
                    alive = True
            except Exception:
                pass
        if _xvfb_pids():
            alive = True
        if not alive:
            break
        time.sleep(0.25)

def setup_display():
    global _XVFB_PROC, DISPLAY_NUM

    for _try in range(3):
        _kill_all_xvfb()
        for stale in (f"/tmp/.X{DISPLAY_NUM}-lock", f"/tmp/.X11-unix/X{DISPLAY_NUM}"):
            try:
                os.remove(stale)
            except FileNotFoundError:
                pass
            except Exception:
                subprocess.run(["rm", "-f", stale], capture_output=True, env=_clean_system_env())
                time.sleep(0.3)

        os.makedirs("/tmp/.X11-unix", exist_ok=True)
        if not xserver_alive():
            break

        print(f"[display] :{DISPLAY_NUM} vẫn bị chiếm -> chuyển sang :{DISPLAY_NUM + 1}")
        DISPLAY_NUM += 1

    os.environ["DISPLAY"] = f":{DISPLAY_NUM}"
    xvfb_bin = _patch_xvfb_for_xkbcomp()

    xkbdir = ""
    for cand in (f"{LIBROOT}/usr/share/X11/xkb", "/usr/share/X11/xkb"):
        if os.path.isdir(f"{cand}/rules"):
            xkbdir = cand
            break
    if not xkbdir:
        raise RuntimeError("Không thấy keymap XKB")

    cmd = [
        xvfb_bin, f":{DISPLAY_NUM}",
        "-screen", "0", "1400x900x24",
        "-nolisten", "tcp",
        "-ac",
        "-noreset",
        "-xkbdir", xkbdir
    ]

    xlog = open("/tmp/xvfb.log", "w")
    _XVFB_PROC = subprocess.Popen(
        cmd,
        stdout=xlog,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=_clean_system_env()
    )

    ok = False
    for _ in range(80):
        if _XVFB_PROC.poll() is not None:
            break
        if xserver_alive():
            ok = True
            break
        time.sleep(0.25)

    if not ok:
        try:
            print(open("/tmp/xvfb.log", errors="ignore").read()[-4000:])
        except Exception:
            pass
        raise RuntimeError(f"Xvfb :{DISPLAY_NUM} không sống được")

    if shutil.which("openbox"):
        subprocess.Popen("openbox >/dev/null 2>&1 &", shell=True, env=_clean_system_env())

    if shutil.which("xsetroot"):
        subprocess.run(f"xsetroot -display :{DISPLAY_NUM} -solid '#16202e'",
                       shell=True, capture_output=True, env=_clean_system_env())

    print(f"[display] Xvfb :{DISPLAY_NUM} OK pid={_XVFB_PROC.pid}")

# ---------- SESSION ----------
def _grass_config_dirs():
    out = subprocess.getoutput(f"find {HOME} -maxdepth 4 -iname '*grass*' 2>/dev/null").splitlines()
    keep = []
    for p in out:
        if os.path.isdir(p) and not p.startswith(BASE + "/") and "/grass_app" not in p:
            keep.append(p)
    return sorted(set(keep))

def _jwt_payload(tok):
    try:
        import base64
        p = (tok or "").split(".")[1]
        p += "=" * (-len(p) % 4)
        d = json.loads(base64.urlsafe_b64decode(p))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _session_token_info():
    try:
        st = json.load(open(os.path.join(HOME, ".local/share/io.getgrass.desktop/store.json")))
        tok = (st.get("accessToken") or "").strip('"')
        if not tok:
            return None
        import datetime
        p = _jwt_payload(tok)
        return {
            "user_id": str(st.get("wynd:user_id", "?")).strip('"'),
            "email": p.get("email", "?"),
            "exp": datetime.datetime.fromtimestamp(p["exp"]).strftime("%Y-%m-%d %H:%M")
        }
    except Exception:
        return None

def _is_guest_email(em):
    em = (em or "").strip().lower()
    return em.endswith("@mail.com") and not em.endswith("@gmail.com")

def _session_quality():
    try:
        st = json.load(open(os.path.join(HOME, ".local/share/io.getgrass.desktop/store.json"),
                            encoding="utf-8"))
    except Exception:
        return {"quality": "none", "email": None, "user_id": None}

    tok = (st.get("accessToken") or "").strip('"')
    rtok = (st.get("refreshToken") or "").strip('"')
    email = st.get("email") or ""
    uid = str(st.get("wynd:user_id") or "").strip('"')

    info = _session_token_info()
    if info:
        email = info.get("email") or email
        uid = info.get("user_id") or uid

    if not tok and not rtok:
        return {"quality": "empty", "email": email or None, "user_id": uid or None}

    em = (info or {}).get("email") or email or ""
    if _is_guest_email(em):
        return {"quality": "guest", "email": em, "user_id": uid or None, "exp": (info or {}).get("exp")}

    if info:
        return {"quality": "real", "email": em, "user_id": uid or None, "exp": info.get("exp")}

    return {"quality": "empty", "email": em or None, "user_id": uid or None}

def _account_verdict(q=None):
    q = q or _session_quality()
    email = (q.get("email") or "").strip().lower()
    uid = str(q.get("user_id") or "").strip()
    my_email = (EMAIL or "").strip().lower()
    lines = []
    level = q["quality"]

    if q["quality"] == "real":
        if my_email and email and email != my_email:
            level = "mismatch"
            lines.append(f"⚠️ đang đăng nhập email {q.get('email')} — KHÔNG khớp EMAIL cấu hình {EMAIL}")
        else:
            lines.append(f"✅ tài khoản: {q.get('email') or '?'} | user_id={uid or '?'}")
    elif q["quality"] == "guest":
        lines.append("🚨 phiên GUEST = tài khoản ẢO DANH — KHÔNG kiếm điểm!")
        lines.append("   → auto_login() hoặc google_login() để vào tài khoản thật.")
    elif q["quality"] == "empty":
        lines.append("⚠️ chưa có phiên đăng nhập — chạy auto_login().")
    else:
        lines.append("❌ chưa có store.json.")

    return level, lines

def check_session():
    q = _session_quality()
    print(f"[session] quality={q['quality']} email={q.get('email')} user_id={q.get('user_id')}")
    _, lines = _account_verdict(q)
    for l in lines:
        print(l)
    return q["quality"]

def _download_session_from_url(url):
    """HOTFIX 13: tải session tgz từ URL (Google Drive) về SESSION_DIR."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    dst = os.path.join(SESSION_DIR, "grass_desktop_session_remote.tgz")
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        return dst  # đã tải từ lần trước

    try:
        hdr = {"User-Agent": "Mozilla/5.0"}
        blob = urllib.request.urlopen(
            urllib.request.Request(url, headers=hdr), timeout=120).read()

        # Google Drive: file lớn hoặc cần confirm -> xử lý trang warning
        if b"<html" in blob[:1000].lower():
            html = blob.decode("utf-8", "replace")
            m = re.search(r'name="confirm"\s+value="([^"]+)"', html)
            mu = re.search(r'name="uuid"\s+value="([^"]+)"', html)
            if m:
                extra = "&confirm=" + m.group(1)
                if mu:
                    extra += "&uuid=" + mu.group(1)
                blob = urllib.request.urlopen(
                    urllib.request.Request(url + extra, headers=hdr),
                    timeout=180).read()

        if b"<html" in blob[:1000].lower():
            print("[session] URL trả về HTML — không tải được file (link hết quyền share?)")
            return None

        open(dst, "wb").write(blob)
        print(f"[session] đã tải phiên từ URL: {len(blob)/1024/1024:.2f} MB -> {dst}")
        return dst
    except Exception as e:
        print("[session] tải từ URL lỗi:", str(e)[:150])
        return None

def _find_session_tgz():
    cands = []
    if SESSION_FILE and not SESSION_FILE.startswith("http"):
        cands.append(SESSION_FILE)

    cands += [c for c in sorted(glob.glob(os.path.join(SESSION_DIR, "*.tgz")),
                                key=os.path.getmtime, reverse=True)
              if "_guest" not in os.path.basename(c).lower()]

    for c in cands:
        if c and os.path.exists(c) and os.path.getsize(c) > 1000:
            return c

    # HOTFIX 13: SESSION_FILE là URL (Drive) -> tải về rồi dùng
    if SESSION_FILE and SESSION_FILE.startswith("http"):
        dst = _download_session_from_url(SESSION_FILE)
        if dst:
            return dst
    return None

def _peek_tgz_quality(tar):
    try:
        with tarfile.open(tar, "r:gz") as tf:
            for m in tf.getmembers():
                if m.name.endswith("io.getgrass.desktop/store.json") and m.isfile():
                    st = json.loads(tf.extractfile(m).read().decode("utf-8", "ignore"))
                    tok = str(st.get("accessToken") or "").strip('"') or str(st.get("refreshToken") or "").strip('"')
                    if not tok:
                        return "empty"
                    em = _jwt_payload(tok).get("email") or str(st.get("email") or "").strip('"')
                    return "guest" if _is_guest_email(em) else "real"
    except Exception:
        pass
    return "none"

def restore_session(force=False):
    tar = _find_session_tgz()
    if not tar:
        print("[session] chưa có file phiên -> sẽ cần auto_login()")
        return False

    print(f"[session] dùng file phiên: {tar}")
    if not force:
        fq = _peek_tgz_quality(tar)
        cur = _session_quality().get("quality")
        if fq in ("empty", "guest") and cur == "real":
            print("[session] ⛔ máy đang có phiên THẬT, không nạp file guest/rỗng")
            return False

    try:
        with tarfile.open(tar, "r:gz") as tf:
            members = tf.getmembers()
            keep = [m for m in members if not (SKIP_WEBKIT_CACHE and m.name.startswith(".cache/grass-desktop"))]
            try:
                tf.extractall(HOME, members=keep, filter="data")
            except TypeError:
                tf.extractall(HOME, members=keep)

        if SKIP_WEBKIT_CACHE:
            shutil.rmtree(os.path.join(HOME, ".cache/grass-desktop"), ignore_errors=True)
    except Exception as e:
        print("[session] lỗi giải nén:", e)
        return False

    q = _session_quality()
    print(f"[session] sau restore: {q.get('quality')} | email={q.get('email')} | user_id={q.get('user_id')}")
    return True

def save_session():
    if not AUTO_SAVE_SESSION:
        return
    try:
        os.makedirs(SESSION_DIR, exist_ok=True)
        paths = _grass_config_dirs()
        if not paths:
            print("[session] chưa thấy thư mục config Grass")
            return

        q = _session_quality()
        tar = os.path.join(SESSION_DIR, "grass_desktop_session.tgz")
        if q["quality"] != "real":
            tar = os.path.join(SESSION_DIR, "grass_desktop_session_GUEST.tgz")

        with tarfile.open(tar, "w:gz") as tf:
            for p in paths:
                tf.add(p, arcname=os.path.relpath(p, HOME))

        json.dump({"paths": paths, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "quality": q["quality"]},
                  open(os.path.join(SESSION_DIR, "session_info.json"), "w"), indent=2)

        print(f"[session] đã lưu phiên -> {tar}")
    except Exception as e:
        print("[session] lỗi lưu:", e)

def clear_session():
    for f in glob.glob(os.path.join(SESSION_DIR, "*.tgz")):
        os.remove(f)
    print("[session] đã xoá session đã lưu")

# ---------- APP RUN ----------
APP_PROC = {"p": None}

_SNI_WATCHER_SRC = r'''
import dbus, dbus.service, dbus.mainloop.glib
from gi.repository import GLib
BUS_NAME = "org.kde.StatusNotifierWatcher"
OBJ = "/StatusNotifierWatcher"
class W(dbus.service.Object):
    def __init__(s, bus):
        s.items = []; super().__init__(bus, OBJ)
    @dbus.service.method(BUS_NAME, in_signature="s", out_signature="")
    def RegisterStatusNotifierItem(s, service):
        s.items.append(service); print("REGISTERED_ITEM:", service, flush=True)
        s.StatusNotifierItemRegistered(service)
    @dbus.service.method(BUS_NAME, in_signature="", out_signature="as")
    def RegisteredStatusNotifierItems(s): return s.items
    @dbus.service.method(BUS_NAME, in_signature="s", out_signature="")
    def RegisterStatusNotifierHost(s, service): pass
    @dbus.service.method(BUS_NAME, in_signature="", out_signature="b")
    def IsStatusNotifierHostRegistered(s): return True
    @dbus.service.method(BUS_NAME, in_signature="", out_signature="i")
    def ProtocolVersion(s): return 0
    @dbus.service.signal(BUS_NAME, signature="s")
    def StatusNotifierItemRegistered(s, service): pass
    @dbus.service.signal(BUS_NAME, signature="s")
    def StatusNotifierItemUnregistered(s, service): pass
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
dbus.service.BusName(BUS_NAME, bus)
W(bus)
print("WATCHER_READY", flush=True)
GLib.MainLoop().run()
'''

def _grass_pids():
    out = subprocess.getoutput("pgrep -x grass-desktop 2>/dev/null").split()
    if not out:
        out = subprocess.getoutput(f"pgrep -f '{APP_ROOT}/usr/bin/grass-desktop' 2>/dev/null").split()
    if not out:
        out = subprocess.getoutput("pgrep -f '/tmp/ld-grass' 2>/dev/null").split()
    return [p for p in out if p.strip()]

def app_alive():
    return bool(_grass_pids())

def stop_app():
    subprocess.run("pkill -x grass-desktop", shell=True, capture_output=True, env=_clean_system_env())
    subprocess.run(f"pkill -f '{APP_ROOT}/usr/bin/grass-desktop'", shell=True, capture_output=True, env=_clean_system_env())
    subprocess.run("pkill -f '/tmp/ld-grass'", shell=True, capture_output=True, env=_clean_system_env())
    time.sleep(2)
    APP_PROC["p"] = None
    print("[app] đã dừng")

def find_window():
    out = subprocess.getoutput("xdotool search --class grass-desktop 2>/dev/null | head -1").strip()
    if out:
        return out
    out = subprocess.getoutput("wmctrl -lx 2>/dev/null | grep -i grass | head -1").strip()
    if out:
        return out.split()[0]
    return None

def window_visible():
    out = subprocess.getoutput("xdotool search --onlyvisible --class grass-desktop 2>/dev/null | head -1").strip()
    if out:
        return out
    out = subprocess.getoutput("xdotool search --onlyvisible --name Grass 2>/dev/null | head -1").strip()
    return out or None

def _bus_addr_of(pid):
    try:
        for ln in open(f"/proc/{pid}/environ", "rb").read().split(b"\0"):
            if ln.startswith(b"DBUS_SESSION_BUS_ADDRESS="):
                return ln.split(b"=", 1)[1].decode()
    except Exception:
        pass
    return None

_TRAY_STATE = {"started": False}

def start_tray_host():
    if _TRAY_STATE["started"]:
        return True

    pids = _grass_pids()
    if not pids:
        return False

    bus = _bus_addr_of(pids[0])
    if not bus:
        print("[tray] không tìm thấy dbus session của app")
        return False

    env = dict(_clean_system_env(), DBUS_SESSION_BUS_ADDRESS=bus)

    wsrc = "/tmp/grass_sni_watcher.py"
    open(wsrc, "w").write(_SNI_WATCHER_SRC)

    syspy = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
    r = subprocess.run([syspy, "-c", "import dbus"], env=env, capture_output=True)
    if r.returncode != 0:
        print("[tray] python3-dbus chưa sẵn sàng")
        return False

    if not subprocess.getoutput("pgrep -f grass_sni_watcher").strip():
        subprocess.Popen([syspy, wsrc],
                         stdout=open("/tmp/grass_sni.log", "w"),
                         stderr=subprocess.STDOUT,
                         env=env,
                         start_new_session=True)
        time.sleep(3)

    _TRAY_STATE["started"] = True
    return True

def _grass_exec_parts():
    """
    HOTFIX 12: trả về (argv_list, ld_library_path) — KHÔNG còn dùng shell.

    Vì sao glibc239 PHẢI ở đầu LD_LIBRARY_PATH của app:
    app chạy với libc 2.39 (glibc239) nên các lib bạn của libc
    (libresolv, libm, libpthread, libdl...) cũng phải lấy từ glibc239.
    Nếu rơi ra bản của host -> host libresolv yêu cầu version node
    GLIBC_ABI_DT_X86_64_PLT mà libc 2.39 Ubuntu không export ->
    "version `GLIBC_ABI_DT_X86_64_PLT' not found".

    Vì sao an toàn (chỗ mà hotfix 10 phải bỏ nó ra): hotfix 10 bỏ
    glibc239 khỏi LD_LIBRARY_PATH để cứu `bash -c`. Giờ app được Popen
    thẳng argv, KHÔNG có shell/binary host nào chạy với env này nữa ->
    trả lại glibc239 đầu danh sách.
    """
    ld = ensure_glibc239()
    if not ld:
        return [APP_BIN], os.environ.get("LD_LIBRARY_PATH", "")

    glibc_lib = os.path.dirname(ld)
    lib_list = [
        glibc_lib,
        f"{LIBROOT}/usr/lib/x86_64-linux-gnu",
        f"{LIBROOT}/lib/x86_64-linux-gnu",
        f"{LIBROOT}/usr/lib",
        f"{LIBROOT}/lib",
        "/lib/x86_64-linux-gnu",
        "/usr/lib/x86_64-linux-gnu",
        "/lib64",
        "/usr/lib",
        "/lib",
    ]

    is_patched = False
    try:
        data = open(APP_BIN, "rb").read()
        if b"/tmp/ld-grass" in data or ld.encode() in data:
            is_patched = True
    except Exception:
        pass

    if is_patched:
        return [APP_BIN], ":".join(lib_list)

    return [ld, "--library-path", ":".join(lib_list), APP_BIN], ":".join(lib_list)

def launch_app(force=False):
    if APP_PROC["p"] and APP_PROC["p"].poll() is None and not force:
        return True
    if force:
        stop_app()

    if not os.path.exists(APP_BIN):
        print("[!] chưa có binary — gọi ensure_app()")
        return False

    if not xserver_alive():
        print("[fix] Xvfb không sống -> dựng lại display")
        setup_display()

    app_argv, grass_ld = _grass_exec_parts()

    # HOTFIX 12: glibc239 ở ĐẦU LD_LIBRARY_PATH của app (libresolv/libm...
    # phải là bản 2.39 khớp libc 2.39). An toàn vì app được Popen thẳng
    # argv — không còn shell/binary host nào chạy với env này.

    xdg = "/tmp/xdgr"
    os.makedirs(xdg, exist_ok=True)
    try:
        os.chmod(xdg, 0o700)
    except Exception:
        pass

    sys_env = _clean_system_env()

    grass_env = dict(
        sys_env,
        DISPLAY=f":{DISPLAY_NUM}",
        LD_LIBRARY_PATH=grass_ld,
        NO_AT_BRIDGE="1",
        WEBKIT_DISABLE_COMPOSITING_MODE="1",
        WEBKIT_DISABLE_DMABUF_RENDERER="1",
        WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS="1",
        GDK_BACKEND="x11",
        XDG_RUNTIME_DIR=xdg,
        HOME=HOME,
    )

    # DBus riêng, chạy bằng env sạch
    bus_addr = f"unix:path={xdg}/grass-bus"
    conf = ""
    for c in ("/usr/share/dbus-1/session.conf", f"{LIBROOT}/usr/share/dbus-1/session.conf"):
        if os.path.exists(c):
            conf = c
            break

    ddm = shutil.which("dbus-daemon") or (
        f"{LIBROOT}/usr/bin/dbus-daemon" if os.path.exists(f"{LIBROOT}/usr/bin/dbus-daemon") else ""
    )

    if conf and ddm:
        subprocess.Popen(
            [ddm, "--nofork", "--address", bus_addr, "--config-file", conf],
            stdout=open("/tmp/grass_dbus.log", "w"),
            stderr=subprocess.STDOUT,
            env=sys_env,
            start_new_session=True
        )
        time.sleep(1.2)
        grass_env["DBUS_SESSION_BUS_ADDRESS"] = bus_addr
        sys_env["DBUS_SESSION_BUS_ADDRESS"] = bus_addr
        print(f"[dbus] {bus_addr}")

    # Tray watcher bằng env sạch
    try:
        syspy = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
        wsrc = "/tmp/grass_sni_watcher.py"
        open(wsrc, "w").write(_SNI_WATCHER_SRC)
        if subprocess.run([syspy, "-c", "import dbus"], env=sys_env, capture_output=True).returncode == 0:
            subprocess.Popen(
                [syspy, wsrc],
                stdout=open("/tmp/grass_sni.log", "w"),
                stderr=subprocess.STDOUT,
                env=sys_env,
                start_new_session=True
            )
    except Exception as e:
        print("[tray] watcher bỏ qua:", e)

    open(APP_LOG, "w").close()

    # HOTFIX 12: Popen thẳng argv — KHÔNG dùng bash/sh. Shell (binary host)
    # chạy với env có glibc239 chính là nguyên nhân crash GLIBC_PRIVATE cũ.
    APP_PROC["p"] = subprocess.Popen(
        app_argv,
        env=grass_env,
        stdout=open(APP_LOG, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

    return wait_window(75)

_SDK_LOG_RE = re.compile(r"grass_proxy_sdk|sharing (paused|resumed|started)|signed in|awaiting", re.I)

def wait_window(timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if APP_PROC["p"] and APP_PROC["p"].poll() is not None:
            print("[!] app thoát sớm — tail log:")
            tail_log(12)
            return False

        try:
            log = open(APP_LOG, errors="ignore").read()
        except Exception:
            log = ""

        if _SDK_LOG_RE.search(log):
            wid = find_window()
            if wid:
                name = subprocess.getoutput(f"xdotool getwindowname {wid} 2>/dev/null")
                print(f"🪟 Cửa sổ app đã lên (id {wid}: {name})")
            else:
                print("✅ Engine Grass đã chạy. Cửa sổ có thể ẩn ở tray -> open_window()")
            return True

        time.sleep(3)

    print("[!] chờ app sẵn sàng quá lâu — tail log:")
    tail_log(12)
    return False

def open_window():
    wid = find_window()
    if wid and window_visible():
        subprocess.run(["xdotool", "windowactivate", "--sync", wid], capture_output=True, env=_clean_system_env())
        subprocess.run(["xdotool", "windowmove", wid, "120", "40"], capture_output=True, env=_clean_system_env())
        print(f"🪟 đã activate cửa sổ có sẵn (id {wid})")
        return True

    pids = _grass_pids()
    if not pids:
        print("[!] app chưa chạy")
        return False

    bus = _bus_addr_of(pids[0])
    if not bus:
        print("[!] không tìm thấy dbus session của app")
        return False

    env = dict(_clean_system_env(), DBUS_SESSION_BUS_ADDRESS=bus)
    start_tray_host()

    try:
        own = subprocess.run(["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.DBus",
                              "/", "org.freedesktop.DBus.GetNameOwner",
                              "string:org.io_getgrass_desktop.SingleInstance"],
                             capture_output=True, text=True, env=env).stdout
        m = re.search(r'"(:1\.\d+)"', own)
        dest = m.group(1) if m else None
    except Exception:
        dest = None

    ITEM = "/org/ayatana/NotificationItem/tray_icon_tray_app"

    def window_seen():
        w = subprocess.getoutput("xdotool search --onlyvisible --name '^Grass$' 2>/dev/null | head -1").strip()
        if not w:
            w = subprocess.getoutput("xdotool search --onlyvisible --name Grass 2>/dev/null | head -1").strip()
        return w or None

    if dest:
        for attempt in range(2):
            subprocess.run(["dbus-send", "--session", "--print-reply", f"--dest={dest}",
                            ITEM, "org.kde.StatusNotifierItem.Activate", "int32:0", "int32:0"],
                           capture_output=True, text=True, env=env)
            end = time.time() + 12
            while time.time() < end:
                wid = window_seen()
                if wid:
                    subprocess.run(["xdotool", "windowactivate", "--sync", wid], capture_output=True, env=_clean_system_env())
                    print(f"🪟 Cửa sổ Grass đã mở (id {wid})")
                    return True
                time.sleep(2)

    # single-instance fallback
    app_argv, grass_ld = _grass_exec_parts()
    env2 = dict(_clean_system_env(), LD_LIBRARY_PATH=grass_ld, DISPLAY=f":{DISPLAY_NUM}", HOME=HOME)
    # HOTFIX 12: Popen thẳng argv, KHÔNG shell — env2 có glibc239 nên
    # bash/sh (binary host) nếu chạy sẽ crash GLIBC_PRIVATE.
    subprocess.Popen(app_argv, env=env2,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    end = time.time() + 15
    while time.time() < end:
        wid = window_seen()
        if wid:
            subprocess.run(["xdotool", "windowactivate", "--sync", wid], capture_output=True, env=_clean_system_env())
            print(f"🪟 Cửa sổ Grass đã mở (id {wid})")
            return True
        time.sleep(2)

    print("[!] chưa mở được cửa sổ")
    return False

_MSS_CACHE = {"mod": None, "tried": False}

def _get_mss():
    """HOTFIX 16: import mss an toàn, cache ở module-level. Hết lỗi
    "cannot access local variable 'mss'" (import trong hàm gắn tên local,
    fallback global không thấy được)."""
    if _MSS_CACHE["mod"] is not None:
        return _MSS_CACHE["mod"]
    try:
        import mss
        import mss.tools  # noqa
        _MSS_CACHE["mod"] = mss
        return mss
    except ImportError:
        pass
    if not _MSS_CACHE["tried"]:
        _MSS_CACHE["tried"] = True
        for extra in ([], ["--break-system-packages"]):
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "mss", *extra],
                           env=_clean_system_env(), capture_output=True)
            try:
                import importlib
                _m = importlib.import_module("mss")
                importlib.import_module("mss.tools")
                _MSS_CACHE["mod"] = _m
                return _m
            except ImportError:
                continue
    return None

def take_screenshot(path=None):
    path = path or f"{BASE}/screen_{time.strftime('%H%M%S')}.png"
    mod = _get_mss()
    if not mod:
        print("[shot] không cài được mss")
        return None

    try:
        os.environ["DISPLAY"] = f":{DISPLAY_NUM}"
        with mod.mss() as s:
            shot = s.grab(s.monitors[0])
            mod.tools.to_png(shot.rgb, shot.size, output=path)
        print(f"📸 {path}")
        return path
    except Exception as e:
        print("[shot] mss lỗi:", e)
        return None

def tail_log(n=8):
    try:
        lines = open(APP_LOG, errors="ignore").read().splitlines()[-n:]
        for ln in lines:
            print("   |", ln[:180])
    except Exception:
        pass

def auto_connect():
    try:
        log = open(APP_LOG, errors="ignore").read()[-4000:]
    except Exception:
        log = ""

    if not re.search(r"sharing paused", log):
        print("[connect] engine không ở trạng thái paused -> bỏ qua")
        return False

    if not window_visible():
        if not open_window():
            return False
        time.sleep(2)

    wid = subprocess.getoutput("xdotool search --onlyvisible --name '^Grass$' 2>/dev/null | head -1").strip() \
        or subprocess.getoutput("xdotool search --onlyvisible --name Grass 2>/dev/null | head -1").strip()

    if not wid:
        print("[connect] chưa có cửa sổ")
        return False

    subprocess.run(["xdotool", "windowactivate", "--sync", wid], capture_output=True, env=_clean_system_env())
    time.sleep(1)

    x, y = CONNECT_XY
    subprocess.run(["xdotool", "mousemove", "--window", wid, str(x), str(y),
                    "sleep", "0.3", "click", "1"],
                   capture_output=True, env=_clean_system_env())

    print(f"[connect] đã click CONNECT tại ({x},{y})")

    end = time.time() + 30
    while time.time() < end:
        time.sleep(5)
        try:
            log = open(APP_LOG, errors="ignore").read()[-4000:]
        except Exception:
            log = ""
        if re.search(r"sharing (resumed|started)|Grass is connected", log):
            print("✅ engine đã BẮT ĐẦU share")
            return True
        if "RegistrationFailed" in log:
            print("⚠️ RegistrationFailed")
            tail_log(6)
            return False

    print("[connect] chưa thấy chuyển trạng thái")
    return False

def auto_login():
    if not (EMAIL and PASSWORD):
        print("[login] chưa điền EMAIL/PASSWORD")
        return False

    wid = find_window()
    if not wid:
        if not open_window() or not (wid := find_window()):
            print("[login] không có cửa sổ")
            return False

    if not shutil.which("xdotool"):
        print("[login] thiếu xdotool")
        return False

    def key(k):
        subprocess.run(["xdotool", "key", "--delay", "60", k],
                       capture_output=True, env=_clean_system_env())

    subprocess.run(["xdotool", "windowactivate", "--sync", wid],
                   capture_output=True, env=_clean_system_env())
    time.sleep(2)

    for _ in range(TABS_BEFORE_EMAIL):
        key("Tab")
    subprocess.run(["xdotool", "type", "--delay", "45", EMAIL],
                   capture_output=True, env=_clean_system_env())

    for _ in range(TABS_BEFORE_PASSWORD):
        key("Tab")
    subprocess.run(["xdotool", "type", "--delay", "45", PASSWORD],
                   capture_output=True, env=_clean_system_env())

    key("Return")
    print("[login] đã gửi email/password (best-effort)")
    return True

_STATUS_RE = re.compile(r"awaiting_login|registering|registration_failed|connecting|reconnecting|"
                        r"recovering|sharing|paused|revoked|crashed|device_quota|partner_refused", re.I)

def count_conns():
    pids = _grass_pids()
    if not pids:
        return 0, []

    pid = pids[0]
    out = []
    try:
        ss = subprocess.getoutput("ss -tnp state established 2>/dev/null").splitlines()
        out = [ln for ln in ss if f"pid={pid}," in ln]
    except Exception:
        pass

    peers = sorted({mm[-1] for ln in out
                    for mm in [re.findall(r"\d+\.\d+\.\d+\.\d+:\d+", ln)] if mm})
    return len(out), peers[:5]

def status():
    al = app_alive()
    conns, peers = count_conns()
    print(f"[status] app={'CHẠY' if al else 'CHẾT'} | cửa sổ={'có' if find_window() else 'không'} | "
          f"kết nối server: {conns} | version={installed_version()}")
    if peers:
        print(f"[status] peers: {', '.join(peers)}")
    tail_log(6)
    try:
        earning_status()
    except Exception:
        pass
    return {"app": al, "conns": conns}

def earning_status():
    """HOTFIX 16: chấm 'sức khỏe kiếm điểm' từ log engine.
    Trả về {'verdict': EARNING|NOT_EARNING|UNKNOWN, 'signals': [...]}"""
    try:
        log = open(APP_LOG, errors="ignore").read()[-12000:]
    except Exception:
        print("[earn] không đọc được app log")
        return {"verdict": "UNKNOWN", "signals": []}

    sig = []
    if re.search(r"device registered", log):
        sig.append("✅ thiết bị đã đăng ký với server Grass")
    n_bridge = len(re.findall(r"opening bridge tunnel", log))
    if n_bridge:
        sig.append(f"✅ bridge tunnel đã mở {n_bridge} lần (server ĐANG đẩy job qua node này)")
    if re.search(r"sharing paused", log, re.I):
        last_paused = max((m.start() for m in re.finditer(r"sharing paused", log)), default=-1)
        last_bridge = max((m.start() for m in re.finditer(r"opening bridge tunnel", log)), default=-1)
        if last_paused > last_bridge:
            sig.append("⛔ 'sharing paused' MỚI HƠN lần mở bridge cuối -> có thể ĐANG nghỉ, không tính điểm")
        else:
            sig.append("ℹ️ 'sharing paused' cũ hơn lần mở bridge cuối (chỉ là log trước CONNECT) -> vô hại")
    n_to = len(re.findall(r"origin dial timed out", log))
    if n_to:
        sig.append(f"⚠️ {n_to} job fail (origin dial timeout) — thi thoảng gặp là bình thường, không mất uptime")
    conns, _peers = count_conns()
    if conns > 0:
        sig.append(f"✅ {conns} kết nối TCP đang mở")
    else:
        sig.append("⛔ 0 kết nối TCP")

    if any(s.startswith("⛔") for s in sig):
        verdict = "NOT_EARNING"
    elif any(s.startswith("✅") for s in sig):
        verdict = "EARNING"
    else:
        verdict = "UNKNOWN"

    icon = {"EARNING": "🟢", "NOT_EARNING": "🔴", "UNKNOWN": "🟡"}[verdict]
    print(f"[earn] {icon} ĐÁNH GIÁ KIẾM ĐIỂM: {verdict}")
    for s in sig:
        print("   -", s)
    if verdict == "EARNING":
        print("   → node ĐANG được server dùng. Điểm cộng theo uptime giờ x hệ số chất lượng IP;")
        print("     xem số điểm thật tại app.grass.io sau vài giờ để biết tốc độ thực tế.")
    elif verdict == "NOT_EARNING":
        print("   → thử: auto_connect() hoặc restart_app(); nếu vẫn paused -> show_screen() xem UI")
    return {"verdict": verdict, "signals": sig}

def diagnose():
    print("\n===== CHẨN ĐOÁN =====")
    print("BASE:", BASE)
    print("DISPLAY:", os.environ.get("DISPLAY"))
    print("LD_LIBRARY_PATH global:", os.environ.get("LD_LIBRARY_PATH", "(empty)")[:500])
    print("dpkg:", shutil.which("dpkg"))
    print("apt-get:", shutil.which("apt-get"))
    print("patchelf:", shutil.which("patchelf"))
    print("glibc ld:", _find_glibc_ld())
    print("APP_BIN:", APP_BIN, os.path.exists(APP_BIN))

    try:
        data = open(APP_BIN, "rb").read()
        print("Grass interp patched:", "YES" if (b"/tmp/ld-grass" in data) else "NO")
    except Exception:
        pass

    print("Xvfb alive:", xserver_alive())
    print(subprocess.getoutput("ps aux | grep -E 'Xvfb|grass' | grep -v grep | cut -c1-160") or "(không có tiến trình)")
    print("--- app log ---")
    tail_log(40)
    print("=====================\n")

def restart_app():
    return launch_app(force=True)

def bug_report():
    print("===== BUG REPORT =====")
    status()
    diagnose()
    take_screenshot()
    print("======================")

LOGIN_OK_RE = re.compile(r"signed in|login (successful|success)|sharing (started|resumed)", re.I)
LOGIN_WAIT_RE = re.compile(r"awaiting[_ ]login|please (log|sign)[- ]?in|not authenticated|need.?login", re.I)
RATELIMIT_RE = re.compile(r"registration failed err=rate limited.*?retry_after=Some\((\d+)s\)", re.I)
_RATELIM_NOISE_RE = re.compile(r"asking the host who is signed in")

def _ratelimit_info():
    try:
        log = open(APP_LOG, errors="ignore").read()[-12000:]
    except Exception:
        return None

    for ln in reversed(log.splitlines()):
        m = RATELIMIT_RE.search(ln)
        if not m:
            continue
        total = int(m.group(1))
        left = total
        try:
            import datetime
            mt = re.search(r"\[(\d{4}-\d{2}-\d{2})\]\[(\d{2}:\d{2}:\d{2})\]", ln)
            if mt:
                ts = datetime.datetime.strptime(mt.group(1) + " " + mt.group(2), "%Y-%m-%d %H:%M:%S")
                left = total - int(time.time() - ts.timestamp())
        except Exception:
            pass
        return {"total": total, "left": min(total, max(0, left))}
    return None

def _rl_mins(rl):
    return max(1, rl["left"] // 60) if rl else 0

def login_state():
    try:
        log = open(APP_LOG, errors="ignore").read()[-12000:]
    except Exception:
        return None, []

    ok = [ln.strip() for ln in log.splitlines()
          if LOGIN_OK_RE.search(ln) and not _RATELIM_NOISE_RE.search(ln)][-2:]
    wait = [ln.strip() for ln in log.splitlines() if LOGIN_WAIT_RE.search(ln)][-2:]

    if ok:
        return True, ok
    if wait:
        return False, wait
    return None, []

def _verdict_text():
    ok, ev = login_state()
    tok = _session_token_info()
    q = _session_quality()
    conns, peers = count_conns()
    out = []

    if q["quality"] == "guest":
        out.append("🔑 ĐĂNG NHẬP: ⚠️ phiên GUEST — tài khoản ẩn danh, không kiếm điểm.")
    elif ok is True or (tok and ok is not False):
        out.append("🔑 ĐĂNG NHẬP: ✅ ĐÃ ĐĂNG NHẬP")
        if tok:
            out.append(f"       | token: user={tok['user_id']} | email={tok['email']} | hết hạn {tok['exp']}")
        out += [f"       | log: {e[:150]}" for e in ev]
    elif ok is False:
        out.append("🔑 ĐĂNG NHẬP: ❌ CHƯA ĐĂNG NHẬP — chạy auto_login()")
        out += [f"       | log: {e[:150]}" for e in ev]
    else:
        out.append("🔑 ĐĂNG NHẬP: ⚠️ chưa rõ — xem log / ảnh")

    if conns:
        out.append(f"🌐 KẾT NỐI : ✅ {conns} kết nối TCP đang mở")
    else:
        out.append("🌐 KẾT NỐI : ⚠️ 0 kết nối")

    if peers:
        out.append(f"       | peers: {', '.join(peers)}")

    return "\n".join(out), conns

def _show_png(path, width=960):
    try:
        from IPython.display import Image as _Img, display as _disp
        _disp(_Img(filename=path, width=width))
    except Exception as e:
        print("(không hiển thị được ảnh:", e, f"— mở file: {path})")

def show_screen(compact=False, width=960, auto_open=True):
    if auto_open and not window_visible():
        print("[👀] desktop trống -> thử open_window()")
        try:
            open_window()
            time.sleep(3)
        except Exception as e:
            print("[👀] mở cửa sổ lỗi:", e)

    path = take_screenshot()
    if path and os.path.exists(path) and os.path.getsize(path) > 1000:
        _show_png(path, width)
    else:
        print("(không chụp được ảnh)")

    v, conns = _verdict_text()
    print(v)
    return conns

def _get_secret(name):
    try:
        if ON_COLAB:
            from google.colab import userdata
            return userdata.get(name)
        if ON_KAGGLE:
            from kaggle_secrets import UserSecretsClient
            return UserSecretsClient().get_secret(name)
    except Exception:
        pass
    return os.environ.get(name)

_HF_PUSH_N = 0

def push_status_hf(force=False):
    global _HF_PUSH_N
    _HF_PUSH_N += 1
    if not force and _HF_PUSH_N % HF_PUSH_EVERY != 1:
        return False

    tok = _get_secret(HF_TOKEN_SECRET)
    if not tok:
        if force:
            print("[hf] chưa có secret HF_TOKEN -> bỏ qua dashboard")
        return False

    try:
        try:
            from huggingface_hub import HfApi
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub"],
                           env=_clean_system_env(), capture_output=True)
            from huggingface_hub import HfApi

        info = _session_token_info() or {}
        conns = count_conns()[0] if app_alive() else 0
        data = {
            "ts": int(time.time()),
            "iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            "platform": "kaggle" if ON_KAGGLE else ("colab" if ON_COLAB else "local"),
            "app": app_alive(),
            "conns": conns,
            "version": installed_version() or "?",
            "token_exp": info.get("exp", ""),
            "email": info.get("email", "")
        }

        p = os.path.join(BASE, "hf_status.json")
        json.dump(data, open(p, "w"))
        HfApi(token=tok).upload_file(
            path_or_fileobj=p,
            path_in_repo="status.json",
            repo_id=HF_STATUS_REPO,
            repo_type="space"
        )

        url = "https://" + HF_STATUS_REPO.replace("/", "-").lower() + ".static.hf.space"
        print(f"[hf] ✅ đã đẩy status -> {url}")
        return True
    except Exception as e:
        print("[hf] đẩy status lỗi:", str(e)[:150])
        return False

def do_health_cycle(i):
    print(f"\n===== Vòng #{i} @ {time.strftime('%H:%M:%S')} =====")

    if AUTO_UPDATE:
        maybe_update()

    if not app_alive():
        print("[fix] app không chạy -> khởi động lại")
        if not launch_app(force=True):
            diagnose()

    st = status()

    if SHOW_SHOT_IN_LOOP:
        try:
            show_screen(compact=True)
        except Exception as e:
            print("[👀] lỗi:", e)

    try:
        _rl = _ratelimit_info()
        if _rl:
            print(f"⏳ RATE LIMITED ~{_rl_mins(_rl)} phút nữa — giữ máy chạy, đừng restart liên tục.")

        q = _session_quality()
        _, lines = _account_verdict(q)
        for l in lines:
            print(l)

        if q["quality"] in ("guest", "empty"):
            print("   → auto_login() hoặc google_login() để đăng nhập tài khoản thật.")
            # HOTFIX 13: tự chữa — có file phiên THẬT mà máy đang guest/empty
            # -> restore + restart app (WebKit chỉ đọc session lúc khởi động)
            try:
                _tar = _find_session_tgz()
                if _tar and _peek_tgz_quality(_tar) == "real":
                    print("[fix] có file phiên THẬT -> restore + restart app")
                    if restore_session() and launch_app(force=True):
                        time.sleep(15)
                        open_window()
                        auto_connect()
            except Exception as _e:
                print("[fix] tự chữa lỗi:", str(_e)[:120])
    except Exception:
        pass

    if st["app"] and st["conns"] == 0:
        if not window_visible():
            print("[fix] 0 kết nối + cửa sổ ẩn -> open_window()")
            if open_window():
                time.sleep(3)
                auto_connect()
        else:
            print("[hint] app chạy nhưng 0 kết nối -> show_screen() + auto_login()")

    if AUTO_SAVE_SESSION:
        save_session()

    push_status_hf()

def main():
    install_deps()
    ensure_app()
    setup_display()
    restore_session()

    if not launch_app():
        diagnose()
        raise RuntimeError("App không lên được — xem chẩn đoán.")

    time.sleep(10)
    open_window()
    time.sleep(5)

    # HOTFIX 13: phiên đã nạp từ file session -> KHÔNG gõ tay auto_login
    # (gõ mù vào form dễ dính reCAPTCHA, phá phiên WebKit đang tốt)
    _q0 = _session_quality().get("quality")
    if _q0 == "real":
        print(f"[login] ✅ phiên thật đã nạp sẵn ({_session_quality().get('email')}) — bỏ qua auto_login")
    else:
        auto_login()
    auto_connect()
    time.sleep(20)

    if not find_window():
        print("[info] không có cửa sổ — app tray-only. Engine vẫn chạy nền.")
        take_screenshot()

    status()
    show_screen()
    save_session()
    push_status_hf(force=True)

    print("\n" + "=" * 58)
    print("ĐIỀU KHIỂN NHANH:")
    print("  status()")
    print("  open_window()")
    print("  show_screen()")
    print("  check_session()")
    print("  restart_app()")
    print("  diagnose()")
    print("=" * 58)

    if not RUN_MODE:
        return

    i = 0
    try:
        while MAX_LOOPS is None or i < MAX_LOOPS:
            i += 1
            do_health_cycle(i)
            print(f"[..] ngủ {SLEEP_SECONDS}s")
            time.sleep(SLEEP_SECONDS)
    except KeyboardInterrupt:
        print("\n[Đã dừng vòng lặp]")

main()