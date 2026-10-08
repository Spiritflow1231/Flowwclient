"""Flowclient Launcher - core logic (no GUI in this file)."""
import os
import re
import sys
import json
import uuid
import shlex
import shutil
import struct
import hashlib
import zipfile
import threading
import subprocess

import requests
import minecraft_launcher_lib as mll

# ---------------------------------------------------------------- paths
ROOT = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "FlowclientLauncher")
DATA_DIR = os.path.join(ROOT, "mc_data")          # shared game files (versions, libraries, assets, java)
PROFILES_DIR = os.path.join(ROOT, "profiles")     # one folder per profile (mods, saves, packs ...)
SKINS_DIR = os.path.join(ROOT, "skins")
MODPACKS_DIR = os.path.join(ROOT, "modpacks")
STORE_FILE = os.path.join(ROOT, "flowclient.json")

API = "https://api.modrinth.com/v2"
HEADERS = {"User-Agent": "FlowclientLauncher/1.0"}

LOADER_NAMES = {"vanilla": "Vanilla", "fabric": "Fabric", "quilt": "Quilt",
                "forge": "Forge", "neoforge": "NeoForge"}
TYPE_DIRS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}

# FPS boost mods (Modrinth slugs). Anything without a build for the chosen version is skipped.
BOOST_MODS = {
    "fabric":   ["sodium", "lithium", "ferrite-core", "immediatelyfast", "entityculling", "modernfix"],
    "quilt":    ["sodium", "lithium", "ferrite-core", "immediatelyfast", "entityculling", "modernfix"],
    "neoforge": ["sodium", "lithium", "ferrite-core", "immediatelyfast", "entityculling", "modernfix"],
    "forge":    ["embeddium", "ferrite-core", "immediatelyfast", "entityculling", "modernfix"],
}

_lock = threading.RLock()
_cache = {}


# ---------------------------------------------------------------- store
def load_store():
    with _lock:
        try:
            with open(STORE_FILE, encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            s = {}
    s.setdefault("accounts", [])
    s.setdefault("profiles", [])
    s.setdefault("active_account", None)
    if not s["accounts"]:
        a = new_account("Player")
        s["accounts"].append(a)
        s["active_account"] = a["id"]
    if not any(a["id"] == s["active_account"] for a in s["accounts"]):
        s["active_account"] = s["accounts"][0]["id"]
    return s


def save_store(s):
    with _lock:
        os.makedirs(ROOT, exist_ok=True)
        tmp = STORE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
        os.replace(tmp, STORE_FILE)


# ---------------------------------------------------------------- accounts
NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def offline_uuid(name):
    """Same UUID a vanilla server derives for an offline-mode player."""
    b = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode()).digest())
    b[6] = (b[6] & 0x0F) | 0x30
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def new_account(name):
    return {"id": uuid.uuid4().hex[:8], "name": name, "uuid": offline_uuid(name),
            "skin": "", "cape": ""}


def png_size(path):
    with open(path, "rb") as f:
        h = f.read(24)
    if h[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("That file is not a PNG image")
    return struct.unpack(">II", h[16:24])


def set_account_image(acct, kind, src):
    """kind = 'skin' or 'cape'. src='' clears it."""
    os.makedirs(SKINS_DIR, exist_ok=True)
    dst = os.path.join(SKINS_DIR, f"{acct['id']}_{kind}.png")
    if src:
        png_size(src)  # validates it is a PNG
        shutil.copyfile(src, dst)
        acct[kind] = dst
    else:
        if os.path.exists(dst):
            os.remove(dst)
        acct[kind] = ""


def remove_account_files(acct):
    for kind in ("skin", "cape"):
        try:
            set_account_image(acct, kind, "")
        except Exception:
            pass


# ---------------------------------------------------------------- profiles
def profile_dir(p):
    return os.path.join(PROFILES_DIR, p["id"])


def new_profile(name, mc_version, loader, loader_version=None, ram=4):
    return {"id": uuid.uuid4().hex[:8], "name": name, "mc_version": mc_version,
            "loader": loader, "loader_version": loader_version, "ram": int(ram),
            "jvm_args": "", "launch_id": None, "mrpack": None, "pack_done": False,
            "modpack": None}


def delete_profile_files(p):
    shutil.rmtree(profile_dir(p), ignore_errors=True)


def list_installed(p, ptype):
    d = os.path.join(profile_dir(p), TYPE_DIRS[ptype])
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if not f.startswith("."))


def remove_installed(p, ptype, name):
    path = os.path.join(profile_dir(p), TYPE_DIRS[ptype], name)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------- system
def total_ram_gb():
    try:
        if os.name == "nt":
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return max(1, int(m.ullTotalPhys / 1024 ** 3))
        with open("/proc/meminfo") as f:
            return max(1, int(f.readline().split()[1]) // 1024 // 1024)
    except Exception:
        return 16


def max_ram_gb():
    return max(2, min(32, total_ram_gb() - 2))


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------- versions
def ver_key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)


def mc_versions(loader):
    """Minecraft versions that the chosen loader supports (newest first)."""
    key = ("mc", loader)
    if key not in _cache:
        if loader == "vanilla":
            vs = [v["id"] for v in mll.utils.get_version_list() if v["type"] == "release"]
        else:
            vs = mll.mod_loader.get_mod_loader(loader).get_minecraft_versions(True)
            vs = sorted(set(vs), key=ver_key, reverse=True)
        _cache[key] = vs
    return _cache[key]


def loader_versions(loader, mc):
    key = ("lv", loader, mc)
    if key not in _cache:
        ml = mll.mod_loader.get_mod_loader(loader)
        vs = ml.get_loader_versions(mc, True) or ml.get_loader_versions(mc, False)
        _cache[key] = sorted(set(vs), key=ver_key, reverse=True)
    return _cache[key]


# ---------------------------------------------------------------- modrinth
def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
    os.replace(tmp, dest)


def mr_search(query, ptype, mc_version=None, loader=None, limit=20):
    facets = [[f"project_type:{ptype}"]]
    if mc_version:
        facets.append([f"versions:{mc_version}"])
    if loader and loader != "vanilla" and ptype in ("mod", "modpack"):
        cats = [f"categories:{loader}"]
        if loader == "quilt":
            cats.append("categories:fabric")
        facets.append(cats)
    r = requests.get(f"{API}/search", headers=HEADERS, timeout=25, params={
        "query": query, "facets": json.dumps(facets), "limit": limit,
        "index": "relevance" if query else "downloads"})
    r.raise_for_status()
    return r.json()["hits"]


def mr_versions(project, mc_version=None, loaders=None):
    params = {}
    if mc_version:
        params["game_versions"] = json.dumps([mc_version])
    if loaders:
        params["loaders"] = json.dumps(loaders)
    r = requests.get(f"{API}/project/{project}/version", headers=HEADERS, timeout=25, params=params)
    r.raise_for_status()
    return r.json()


def _primary_file(v):
    return next((x for x in v["files"] if x.get("primary")), v["files"][0])


def mr_install(project, ptype, p, log=None, seen=None):
    """Install a mod / resource pack / shader into profile p (mods also pull required dependencies)."""
    log = log or (lambda t: None)
    seen = set() if seen is None else seen
    if project in seen:
        return None
    seen.add(project)
    if ptype == "mod" and p["loader"] == "vanilla":
        raise RuntimeError("This profile is Vanilla. Create a profile with Fabric, Forge, etc. to use mods.")
    loaders = None
    if ptype == "mod":
        loaders = [p["loader"], "fabric"] if p["loader"] == "quilt" else [p["loader"]]
    versions = mr_versions(project, p["mc_version"], loaders)
    if not versions:
        raise RuntimeError(f"No build for Minecraft {p['mc_version']}"
                           + (f" on {LOADER_NAMES[p['loader']]}" if ptype == "mod" else ""))
    v = next((x for x in versions if x.get("version_type") == "release"), versions[0])
    if ptype == "mod":
        for d in v.get("dependencies", []):
            if d.get("dependency_type") == "required" and d.get("project_id"):
                try:
                    mr_install(d["project_id"], "mod", p, log, seen)
                except Exception as e:
                    log(f"Dependency skipped: {e}")
    f = _primary_file(v)
    dest = os.path.join(profile_dir(p), TYPE_DIRS[ptype], f["filename"])
    if not os.path.exists(dest):
        log(f"Downloading {f['filename']}...")
        download(f["url"], dest)
    return f["filename"]


def install_boost(p, log=None):
    log = log or (lambda t: None)
    got = []
    for slug in BOOST_MODS.get(p["loader"], []):
        try:
            mr_install(slug, "mod", p, log)
            got.append(slug)
        except Exception as e:
            log(f"Skipped {slug}: {e}")
    return got


def install_shader_support(p, log=None):
    if p["loader"] not in ("fabric", "quilt", "neoforge"):
        raise RuntimeError("Shaders on this loader need Oculus + Embeddium (Forge). "
                           "Search 'oculus' in the Mods tab.")
    got = []
    for slug in ("iris", "sodium"):
        mr_install(slug, "mod", p, log)
        got.append(slug)
    return got


def mr_modpack_versions(project):
    return mr_versions(project)


def download_modpack_version(v):
    f = _primary_file(v)
    path = os.path.join(MODPACKS_DIR, f["filename"])
    if not os.path.exists(path):
        download(f["url"], path)
    return path


def read_pack(path):
    """Returns (pack name, minecraft version, loader, loader version) from a .mrpack."""
    with zipfile.ZipFile(path) as zf:
        idx = json.loads(zf.read("modrinth.index.json"))
    deps = idx["dependencies"]
    mc = deps["minecraft"]
    for key, loader in (("neoforge", "neoforge"), ("forge", "forge"),
                        ("fabric-loader", "fabric"), ("quilt-loader", "quilt")):
        if key in deps:
            return idx.get("name", "Modpack"), mc, loader, deps[key]
    return idx.get("name", "Modpack"), mc, "vanilla", None


# ---------------------------------------------------------------- install + launch
def runtime_java(mc_version):
    """Path to the Java that Mojang ships for this Minecraft version (installed automatically)."""
    try:
        info = mll.runtime.get_version_runtime_information(mc_version, DATA_DIR)
        if info:
            return mll.runtime.get_executable_path(info["name"], DATA_DIR)
    except Exception:
        pass
    return None


def needs_install(p):
    lid = p.get("launch_id")
    if not lid:
        return True
    if not os.path.isfile(os.path.join(DATA_DIR, "versions", lid, f"{lid}.json")):
        return True
    if p.get("mrpack") and not p.get("pack_done"):
        return True
    return False


def install_profile(p, cb=None):
    cb = cb or {}
    os.makedirs(profile_dir(p), exist_ok=True)
    if p.get("mrpack") and not p.get("pack_done"):
        mll.mrpack.install_mrpack(p["mrpack"], DATA_DIR, modpack_directory=profile_dir(p),
                                  callback=cb, mrpack_install_options={"skipDependenciesInstall": True})
        p["pack_done"] = True
    mll.install.install_minecraft_version(p["mc_version"], DATA_DIR, callback=cb)
    if p["loader"] == "vanilla":
        p["launch_id"] = p["mc_version"]
    else:
        ml = mll.mod_loader.get_mod_loader(p["loader"])
        p["launch_id"] = ml.install(p["mc_version"], DATA_DIR,
                                    loader_version=p.get("loader_version") or None,
                                    callback=cb, java=runtime_java(p["mc_version"]))


def apply_skin(p, acct, log=None):
    """Offline skins/capes: CustomSkinLoader reads PNGs from the profile's LocalSkin folder."""
    log = log or (lambda t: None)
    if p["loader"] == "vanilla" or not (acct.get("skin") or acct.get("cape")):
        return
    mods = os.path.join(profile_dir(p), "mods")
    os.makedirs(mods, exist_ok=True)
    if not any("customskinloader" in f.lower() for f in os.listdir(mods)):
        try:
            log("Installing skin support (CustomSkinLoader)...")
            mr_install("customskinloader", "mod", p, log)
        except Exception as e:
            log(f"Skin support not available for this version: {e}")
            return
    base = os.path.join(profile_dir(p), "CustomSkinLoader", "LocalSkin")
    for folder, key in (("skins", "skin"), ("capes", "cape")):
        os.makedirs(os.path.join(base, folder), exist_ok=True)
        dst = os.path.join(base, folder, acct["name"] + ".png")
        src = acct.get(key)
        if src and os.path.isfile(src):
            shutil.copyfile(src, dst)
        elif os.path.exists(dst):
            os.remove(dst)


def jvm_args(p):
    ram = int(p.get("ram", 4))
    args = [f"-Xmx{ram}G", f"-Xms{ram}G", "-XX:+UseG1GC", "-XX:MaxGCPauseMillis=50",
            "-XX:+DisableExplicitGC", "-XX:+ParallelRefProcEnabled"]
    extra = (p.get("jvm_args") or "").strip()
    if extra:
        args += shlex.split(extra)
    return args


def launch(p, acct, cb=None, log=None):
    """Installs anything missing, then starts Minecraft. Returns the running process."""
    if needs_install(p):
        install_profile(p, cb)
    apply_skin(p, acct, log)
    gdir = profile_dir(p)
    os.makedirs(gdir, exist_ok=True)
    options = {"username": acct["name"], "uuid": acct["uuid"], "token": "",
               "gameDirectory": gdir, "jvmArguments": jvm_args(p),
               "launcherName": "Flowclient", "launcherVersion": "1.0"}
    java = runtime_java(p["mc_version"])
    if java:
        options["executablePath"] = java
    cmd = mll.command.get_minecraft_command(p["launch_id"], DATA_DIR, options)
    flags = 0x08000000 if os.name == "nt" else 0  # no console window
    log_file = open(os.path.join(gdir, "launcher_log.txt"), "w", encoding="utf-8", errors="replace")
    return subprocess.Popen(cmd, cwd=gdir, creationflags=flags,
                            stdout=log_file, stderr=subprocess.STDOUT)
