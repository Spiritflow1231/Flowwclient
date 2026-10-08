"""Flowclient Launcher - GUI."""
import os
import queue
import shutil
import threading
import traceback
from tkinter import filedialog, messagebox

import customtkinter as ctk

import core

ACCENT, ACCENT_H, ACCENT_T = "#b8f24a", "#a2d93c", "#10140d"
BG, PANEL, CARD = "#0e110e", "#141914", "#1b221b"
MUTED = "#8a9a86"
DANGER, DANGER_H = "#8b2e2e", "#a63a3a"

LOADER_KEYS = {v: k for k, v in core.LOADER_NAMES.items()}
NAV = [("home", "Home"), ("profiles", "Profiles"), ("create", "Create profile"),
       ("modpacks", "Modpacks"), ("accounts", "Accounts")]


def detail(p):
    lv = f" {p['loader_version']}" if p.get("loader_version") else ""
    return f"Minecraft {p['mc_version']}   •   {core.LOADER_NAMES[p['loader']]}{lv}   •   {p['ram']} GB RAM"


def button(parent, text, command, kind="accent", width=110, height=32):
    colors = {"accent": (ACCENT, ACCENT_H, ACCENT_T),
              "ghost": ("#2a332a", "#364136", "#e8efe5"),
              "danger": (DANGER, DANGER_H, "#ffffff")}[kind]
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=height,
                         fg_color=colors[0], hover_color=colors[1], text_color=colors[2],
                         corner_radius=8, font=("Segoe UI", 13, "bold"))


def alive(w):
    try:
        return bool(w.winfo_exists())
    except Exception:
        return False


# =====================================================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Flowclient Launcher")
        self.geometry("1040x720")
        self.minsize(920, 620)
        self.configure(fg_color=BG)

        self.store = core.load_store()
        core.save_store(self.store)
        self.q = queue.Queue()
        self.running = False
        self.pmax = 1
        self.page = "home"

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.build_bottom()

        self.after(40, self._poll)
        self.show("home")

    # ------------------------------------------------------------ plumbing
    def ui(self, fn):
        self.q.put(fn)

    def _poll(self):
        while True:
            try:
                fn = self.q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                traceback.print_exc()
        self.after(40, self._poll)

    def bg(self, work, done=None, fail=None):
        def run():
            try:
                res = work()
            except Exception as e:  # noqa
                err = e
                self.ui(lambda: (fail or self.fail)(err))
                return
            if done:
                self.ui(lambda: done(res))
        threading.Thread(target=run, daemon=True).start()

    def fail(self, e):
        self.set_status(f"Error: {e}")

    def set_status(self, text):
        self.ui(lambda: self.status.configure(text=str(text)))

    def save(self):
        core.save_store(self.store)

    def unique_name(self, name, exclude_id=None):
        used = {p["name"].lower() for p in self.store["profiles"] if p["id"] != exclude_id}
        if name.lower() not in used:
            return name
        i = 2
        while f"{name} ({i})".lower() in used:
            i += 1
        return f"{name} ({i})"

    def account(self):
        s = self.store
        return next(a for a in s["accounts"] if a["id"] == s["active_account"])

    def profile_by_id(self, pid):
        return next((p for p in self.store["profiles"] if p["id"] == pid), None)

    # ------------------------------------------------------------ chrome
    def build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, fg_color=PANEL, corner_radius=0)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sb.grid_propagate(False)
        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.pack(anchor="w", padx=20, pady=(22, 2))
        ctk.CTkLabel(logo, text="flow", font=("Segoe UI", 24, "bold")).pack(side="left")
        ctk.CTkLabel(logo, text="client", font=("Segoe UI", 24, "bold"),
                     text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(sb, text="JAVA EDITION", font=("Segoe UI", 10), text_color=MUTED
                     ).pack(anchor="w", padx=22, pady=(0, 22))
        self.nav = {}
        for key, label in NAV:
            b = ctk.CTkButton(sb, text=label, anchor="w", height=40, corner_radius=8,
                              fg_color="transparent", hover_color="#232b23",
                              font=("Segoe UI", 14), text_color="#e8efe5",
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=12, pady=2)
            self.nav[key] = b
        self.acc_label = ctk.CTkLabel(sb, text="", font=("Segoe UI", 12), text_color=MUTED,
                                      justify="left")
        self.acc_label.pack(side="bottom", anchor="w", padx=20, pady=16)
        self.update_sidebar_account()

    def update_sidebar_account(self):
        a = self.account()
        self.acc_label.configure(text=f"Playing as\n{a['name']}")

    def build_bottom(self):
        bar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=46)
        bar.grid(row=1, column=1, sticky="ew")
        self.status = ctk.CTkLabel(bar, text="Ready", anchor="w", font=("Segoe UI", 12),
                                   text_color=MUTED)
        self.status.pack(side="left", padx=18, pady=10)
        self.bar = ctk.CTkProgressBar(bar, width=260, progress_color=ACCENT)
        self.bar.set(0)
        self.bar.pack(side="right", padx=18)

    def heading(self, parent, title, sub=""):
        ctk.CTkLabel(parent, text=title, font=("Segoe UI", 28, "bold"), anchor="w"
                     ).pack(fill="x", padx=28, pady=(26, 0))
        if sub:
            ctk.CTkLabel(parent, text=sub, font=("Segoe UI", 13), text_color=MUTED, anchor="w"
                         ).pack(fill="x", padx=28, pady=(2, 8))

    def show(self, name):
        self.page = name
        for k, b in self.nav.items():
            b.configure(fg_color="#26311f" if k == name else "transparent",
                        text_color=ACCENT if k == name else "#e8efe5")
        for w in self.content.winfo_children():
            w.destroy()
        getattr(self, "page_" + name)()

    # ------------------------------------------------------------ HOME
    def page_home(self):
        c = self.content
        self.heading(c, "Good to have you back.", "Pick a profile and get into your next world.")
        profiles = self.store["profiles"]
        card = ctk.CTkFrame(c, fg_color=CARD, corner_radius=14)
        card.pack(fill="x", padx=28, pady=10)
        if not profiles:
            ctk.CTkLabel(card, text="You have no profiles yet.", font=("Segoe UI", 16, "bold")
                         ).pack(padx=24, pady=(24, 4), anchor="w")
            ctk.CTkLabel(card, text="Create one (pick a version and a loader) or add a modpack.",
                         text_color=MUTED).pack(padx=24, anchor="w")
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(padx=24, pady=20, anchor="w")
            button(row, "Create profile", lambda: self.show("create"), width=150, height=40).pack(side="left")
            button(row, "Browse modpacks", lambda: self.show("modpacks"), "ghost", 150, 40
                   ).pack(side="left", padx=10)
            return

        cur = self.profile_by_id(self.store.get("last_profile")) or profiles[0]
        names = [p["name"] for p in profiles]
        info = ctk.CTkLabel(card, text=detail(cur), text_color=MUTED, anchor="w")

        def current():
            return next(p for p in profiles if p["name"] == box.get())

        def on_pick(_=None):
            info.configure(text=detail(current()))

        ctk.CTkLabel(card, text="PLAY PROFILE", font=("Segoe UI", 11), text_color=MUTED
                     ).pack(anchor="w", padx=24, pady=(20, 2))
        box = ctk.CTkComboBox(card, values=names, width=340, height=36, command=on_pick)
        box.set(cur["name"])
        box.pack(anchor="w", padx=24)
        info.pack(anchor="w", padx=24, pady=(6, 14))

        ctk.CTkLabel(card, text="ACCOUNT", font=("Segoe UI", 11), text_color=MUTED
                     ).pack(anchor="w", padx=24, pady=(0, 2))
        accs = {a["name"]: a for a in self.store["accounts"]}
        abox = ctk.CTkComboBox(card, values=list(accs), width=340, height=36)
        abox.set(self.account()["name"])

        def on_acc(choice):
            self.store["active_account"] = accs[choice]["id"]
            self.save()
            self.update_sidebar_account()
        abox.configure(command=on_acc)
        abox.pack(anchor="w", padx=24)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(anchor="w", padx=24, pady=22)
        button(row, "PLAY", lambda: self.play(current()), width=190, height=48).pack(side="left")
        button(row, "Edit profile", lambda: EditWindow(self, current()), "ghost", 130, 48
               ).pack(side="left", padx=10)

        tip = ctk.CTkFrame(c, fg_color=CARD, corner_radius=14)
        tip.pack(fill="x", padx=28, pady=6)
        ctk.CTkLabel(tip, text="More FPS", font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=20, pady=(14, 0))
        ctk.CTkLabel(tip, justify="left", anchor="w", text_color=MUTED, wraplength=720,
                     text="Profiles made with Fabric, Quilt, Forge or NeoForge can install the FPS boost pack "
                          "(Sodium, Lithium, FerriteCore, ImmediatelyFast, Entity Culling, ModernFix) in one click. "
                          "Open a profile with Edit, then Mods, then 'Install FPS boost pack'."
                     ).pack(anchor="w", padx=20, pady=(2, 14))

    # ------------------------------------------------------------ PLAY
    def play(self, p):
        if self.running:
            self.set_status("A game is already running.")
            return
        acct = self.account()
        self.running = True
        self.store["last_profile"] = p["id"]
        self.save()
        self.pmax = 1
        cb = {"setStatus": self.set_status,
              "setMax": lambda m: setattr(self, "pmax", max(m, 1)),
              "setProgress": lambda v: self.ui(lambda: self.bar.set(min(v / self.pmax, 1)))}

        def work():
            proc = core.launch(p, acct, cb, self.set_status)
            self.save()
            self.set_status(f"Minecraft {p['mc_version']} is running...")
            self.ui(lambda: self.bar.set(0))
            return proc.wait()

        def done(code):
            self.running = False
            if code == 0:
                self.set_status("Game closed.")
            else:
                self.set_status(f"Game stopped with code {code}. See launcher_log.txt in the profile folder.")

        def failed(e):
            self.running = False
            self.bar.set(0)
            self.set_status(f"Error: {e}")

        self.set_status(f"Preparing {p['name']}...")
        self.bg(work, done, failed)

    # ------------------------------------------------------------ PROFILES
    def page_profiles(self):
        c = self.content
        top = ctk.CTkFrame(c, fg_color="transparent")
        top.pack(fill="x")
        self.heading(top, "Profiles", "Every profile has its own mods, packs, worlds and RAM.")
        button(c, "+ New profile", lambda: self.show("create"), width=140, height=36
               ).place(relx=1.0, x=-28, y=34, anchor="ne")
        lst = ctk.CTkScrollableFrame(c, fg_color="transparent")
        lst.pack(fill="both", expand=True, padx=18, pady=6)
        if not self.store["profiles"]:
            ctk.CTkLabel(lst, text="No profiles yet. Press '+ New profile'.", text_color=MUTED
                         ).pack(pady=40)
        for p in self.store["profiles"]:
            card = ctk.CTkFrame(lst, fg_color=CARD, corner_radius=12)
            card.pack(fill="x", padx=10, pady=5)
            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True, padx=16, pady=12)
            title = p["name"] + ("   (modpack)" if p.get("modpack") else "")
            ctk.CTkLabel(left, text=title, font=("Segoe UI", 16, "bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(left, text=detail(p), text_color=MUTED, anchor="w").pack(anchor="w")
            right = ctk.CTkFrame(card, fg_color="transparent")
            right.pack(side="right", padx=12)
            button(right, "▶ Play", lambda q=p: self.play(q), width=84).pack(side="left", padx=3)
            button(right, "✎ Edit", lambda q=p: EditWindow(self, q), "ghost", 84).pack(side="left", padx=3)
            button(right, "🗑", lambda q=p: self.delete_profile(q), "danger", 40).pack(side="left", padx=3)

    def delete_profile(self, p):
        if not messagebox.askyesno("Delete profile",
                                   f"Delete '{p['name']}' completely?\n\nIts mods, worlds and settings "
                                   "will be removed. This cannot be undone."):
            return
        core.delete_profile_files(p)
        self.store["profiles"] = [x for x in self.store["profiles"] if x["id"] != p["id"]]
        self.save()
        self.set_status(f"Deleted {p['name']}.")
        self.show(self.page)

    # ------------------------------------------------------------ CREATE
    def page_create(self):
        c = self.content
        self.heading(c, "Create profile",
                     "Pick a loader first. Only Minecraft versions that loader supports are listed.")
        f = ctk.CTkFrame(c, fg_color=CARD, corner_radius=14)
        f.pack(fill="x", padx=28, pady=10)
        f.grid_columnconfigure(1, weight=1)
        W = {}
        self.cr = W

        def row(i, label):
            ctk.CTkLabel(f, text=label, text_color=MUTED, anchor="w", width=130
                         ).grid(row=i, column=0, padx=(22, 8), pady=9, sticky="w")

        row(0, "Profile name")
        W["name"] = ctk.CTkEntry(f, height=36, placeholder_text="My Profile")
        W["name"].grid(row=0, column=1, padx=(0, 22), pady=9, sticky="ew")

        row(1, "Loader")
        W["loader"] = ctk.CTkComboBox(f, values=list(core.LOADER_NAMES.values()), height=36,
                                      command=self.on_loader)
        W["loader"].set("Fabric")
        W["loader"].grid(row=1, column=1, padx=(0, 22), pady=9, sticky="ew")

        row(2, "Minecraft version")
        W["mc"] = ctk.CTkComboBox(f, values=["loading..."], height=36, command=self.on_mc)
        W["mc"].grid(row=2, column=1, padx=(0, 22), pady=9, sticky="ew")

        row(3, "Loader version")
        W["lv"] = ctk.CTkComboBox(f, values=["-"], height=36)
        W["lv"].grid(row=3, column=1, padx=(0, 22), pady=9, sticky="ew")

        row(4, "RAM")
        rf = ctk.CTkFrame(f, fg_color="transparent")
        rf.grid(row=4, column=1, padx=(0, 22), pady=9, sticky="ew")
        mx = core.max_ram_gb()
        W["ram_lbl"] = ctk.CTkLabel(rf, text="", width=60)
        W["ram"] = ctk.CTkSlider(rf, from_=1, to=mx, number_of_steps=max(mx - 1, 1),
                                 progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_H,
                                 command=lambda v: W["ram_lbl"].configure(text=f"{int(v)} GB"))
        W["ram"].set(min(4, mx))
        W["ram_lbl"].configure(text=f"{int(W['ram'].get())} GB")
        W["ram"].pack(side="left", fill="x", expand=True)
        W["ram_lbl"].pack(side="left", padx=(10, 0))

        W["boost"] = ctk.CTkSwitch(f, text="Install the FPS boost pack (Sodium, Lithium, ...)",
                                   progress_color=ACCENT)
        W["boost"].select()
        W["boost"].grid(row=5, column=0, columnspan=2, padx=22, pady=(6, 4), sticky="w")

        button(f, "Create profile", self.do_create, width=170, height=42
               ).grid(row=6, column=0, columnspan=2, padx=22, pady=(10, 20), sticky="w")
        self.on_loader()

    def on_loader(self, _=None):
        W = self.cr
        key = LOADER_KEYS[W["loader"].get()]
        W["mc"].configure(values=["loading..."])
        W["mc"].set("loading...")
        W["lv"].set("-")
        if key == "vanilla":
            W["boost"].deselect()

        def done(vs):
            if not alive(W["mc"]) or LOADER_KEYS[W["loader"].get()] != key:
                return
            W["mc"].configure(values=vs or ["none"])
            W["mc"].set(vs[0] if vs else "none")
            self.on_mc()
        self.bg(lambda: core.mc_versions(key), done)

    def on_mc(self, _=None):
        W = self.cr
        key = LOADER_KEYS[W["loader"].get()]
        mc = W["mc"].get()
        if key == "vanilla" or mc in ("loading...", "none"):
            W["lv"].configure(values=["-"])
            W["lv"].set("-")
            return
        W["lv"].set("loading...")

        def done(vs):
            if not alive(W["lv"]) or W["mc"].get() != mc or LOADER_KEYS[W["loader"].get()] != key:
                return
            W["lv"].configure(values=vs or ["-"])
            W["lv"].set(vs[0] if vs else "-")
        self.bg(lambda: core.loader_versions(key, mc), done)

    def do_create(self):
        W = self.cr
        key = LOADER_KEYS[W["loader"].get()]
        mc, lv = W["mc"].get(), W["lv"].get()
        if mc in ("loading...", "none", ""):
            self.set_status("Wait for the version list to load first.")
            return
        if key != "vanilla" and lv in ("loading...", "-", ""):
            self.set_status("Wait for the loader version to load first.")
            return
        name = self.unique_name(W["name"].get().strip() or "My Profile")
        p = core.new_profile(name, mc, key, None if key == "vanilla" else lv, int(W["ram"].get()))
        boost = bool(W["boost"].get()) and key != "vanilla"
        self.store["profiles"].append(p)
        self.save()
        self.set_status(f"Creating {name}...")

        def work():
            os.makedirs(core.profile_dir(p), exist_ok=True)
            if boost:
                return core.install_boost(p, self.set_status)
            return []

        def done(got):
            extra = f" FPS mods installed: {len(got)}." if boost else ""
            self.set_status(f"Profile '{name}' is ready.{extra} Press PLAY to start it.")
            self.show("profiles")
        self.bg(work, done)

    # ------------------------------------------------------------ MODPACKS
    def page_modpacks(self):
        c = self.content
        self.heading(c, "Modpacks", "Every modpack on Modrinth. Search, press Add, then PLAY.")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=28, pady=6)
        self.mp_entry = ctk.CTkEntry(row, width=380, height=36, placeholder_text="Search modpacks...")
        self.mp_entry.pack(side="left")
        self.mp_entry.bind("<Return>", lambda e: self.modpack_search())
        button(row, "Search", self.modpack_search, width=90, height=36).pack(side="left", padx=8)
        button(row, "Import .mrpack file", self.import_mrpack, "ghost", 150, 36).pack(side="left")
        self.mp_list = ctk.CTkScrollableFrame(c, fg_color="transparent")
        self.mp_list.pack(fill="both", expand=True, padx=18, pady=6)
        self.modpack_search()

    def modpack_search(self):
        q = self.mp_entry.get().strip()
        self.set_status("Searching Modrinth...")

        def done(hits):
            if not alive(self.mp_list):
                return
            for w in self.mp_list.winfo_children():
                w.destroy()
            self.set_status(f"{len(hits)} modpacks found.")
            for h in hits:
                card = ctk.CTkFrame(self.mp_list, fg_color=CARD, corner_radius=12)
                card.pack(fill="x", padx=10, pady=5)
                left = ctk.CTkFrame(card, fg_color="transparent")
                left.pack(side="left", fill="x", expand=True, padx=16, pady=10)
                ctk.CTkLabel(left, text=h["title"], font=("Segoe UI", 15, "bold"), anchor="w").pack(anchor="w")
                ctk.CTkLabel(left, text=f"by {h.get('author', '?')}   •   {h.get('downloads', 0):,} downloads",
                             text_color=MUTED, anchor="w", font=("Segoe UI", 11)).pack(anchor="w")
                ctk.CTkLabel(left, text=h["description"], wraplength=620, justify="left", anchor="w"
                             ).pack(anchor="w", pady=(3, 0))
                button(card, "Add", lambda x=h: self.pick_pack_version(x), width=80
                       ).pack(side="right", padx=14)
        self.bg(lambda: core.mr_search(q, "modpack", None, None, 24), done)

    def pick_pack_version(self, hit):
        self.set_status(f"Loading versions of {hit['title']}...")

        def done(vs):
            if not vs:
                self.set_status("This modpack has no downloadable versions.")
                return
            win = ctk.CTkToplevel(self)
            win.title(f"Add {hit['title']}")
            win.geometry("560x210")
            win.configure(fg_color=BG)
            win.after(200, lambda: (win.lift(), win.focus_force()))
            labels, seen = {}, set()
            for v in vs:
                gv = v["game_versions"][-1] if v["game_versions"] else "?"
                lab = f"{v['version_number']}  •  Minecraft {gv}  •  {'/'.join(v['loaders'])}"
                while lab in seen:
                    lab += " "
                seen.add(lab)
                labels[lab] = v
            ctk.CTkLabel(win, text=f"Choose a version of {hit['title']}", font=("Segoe UI", 15, "bold")
                         ).pack(padx=22, pady=(22, 8), anchor="w")
            box = ctk.CTkComboBox(win, values=list(labels), width=500, height=36)
            box.set(next(iter(labels)))
            box.pack(padx=22)

            def go():
                v = labels[box.get()]
                win.destroy()
                self.add_modpack(hit, v)
            button(win, "Add as profile", go, width=170, height=40).pack(padx=22, pady=22, anchor="w")
        self.bg(lambda: core.mr_modpack_versions(hit["project_id"]), done)

    def add_modpack(self, hit, v):
        self.set_status(f"Downloading {hit['title']}...")

        def work():
            path = core.download_modpack_version(v)
            return core.read_pack(path), path

        def done(res):
            (pname, mc, loader, lv), path = res
            p = core.new_profile(self.unique_name(hit["title"]), mc, loader, lv,
                                 ram=min(6, core.max_ram_gb()))
            p["mrpack"], p["modpack"] = path, hit["title"]
            self.store["profiles"].append(p)
            self.save()
            self.set_status(f"{hit['title']} added. Press PLAY - the first start downloads all its mods.")
            self.show("profiles")
        self.bg(work, done)

    def import_mrpack(self):
        path = filedialog.askopenfilename(title="Choose a modpack", filetypes=[("Modrinth modpack", "*.mrpack")])
        if not path:
            return

        def work():
            os.makedirs(core.MODPACKS_DIR, exist_ok=True)
            dst = os.path.join(core.MODPACKS_DIR, os.path.basename(path))
            if os.path.abspath(dst) != os.path.abspath(path):
                shutil.copyfile(path, dst)
            return core.read_pack(dst), dst

        def done(res):
            (pname, mc, loader, lv), dst = res
            p = core.new_profile(self.unique_name(pname), mc, loader, lv, ram=min(6, core.max_ram_gb()))
            p["mrpack"], p["modpack"] = dst, pname
            self.store["profiles"].append(p)
            self.save()
            self.set_status(f"{pname} imported.")
            self.show("profiles")
        self.bg(work, done)

    # ------------------------------------------------------------ ACCOUNTS
    def page_accounts(self):
        c = self.content
        self.heading(c, "Accounts", "Offline accounts. Pick a name, then optionally add a skin and a cape (PNG).")
        add = ctk.CTkFrame(c, fg_color=CARD, corner_radius=14)
        add.pack(fill="x", padx=28, pady=6)
        self.acc_entry = ctk.CTkEntry(add, width=330, height=36,
                                      placeholder_text="Username (3-16 letters, numbers, _)")
        self.acc_entry.pack(side="left", padx=16, pady=14)
        self.acc_entry.bind("<Return>", lambda e: self.add_account())
        button(add, "Add account", self.add_account, width=130, height=36).pack(side="left")
        self.acc_list = ctk.CTkScrollableFrame(c, fg_color="transparent")
        self.acc_list.pack(fill="both", expand=True, padx=18, pady=6)
        self.draw_accounts()
        ctk.CTkLabel(c, wraplength=760, justify="left", anchor="w", text_color=MUTED, font=("Segoe UI", 11),
                     text="Skins and capes on offline accounts are shown on your own screen. They need the "
                          "CustomSkinLoader mod, which Flowclient installs automatically on Fabric/Quilt/Forge/"
                          "NeoForge profiles. Other players on a server only see them if that server supports it."
                     ).pack(fill="x", padx=28, pady=(0, 14))

    def draw_accounts(self):
        for w in self.acc_list.winfo_children():
            w.destroy()
        for a in self.store["accounts"]:
            active = a["id"] == self.store["active_account"]
            card = ctk.CTkFrame(self.acc_list, fg_color=CARD, corner_radius=12,
                                border_width=1 if active else 0, border_color=ACCENT)
            card.pack(fill="x", padx=10, pady=5)
            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", padx=16, pady=12)
            ctk.CTkLabel(left, text=a["name"] + ("   • ACTIVE" if active else ""),
                         font=("Segoe UI", 16, "bold"), anchor="w",
                         text_color=ACCENT if active else "#e8efe5").pack(anchor="w")
            ctk.CTkLabel(left, text=f"Skin: {'set' if a['skin'] else 'default'}   •   "
                                    f"Cape: {'set' if a['cape'] else 'none'}",
                         text_color=MUTED, anchor="w").pack(anchor="w")
            right = ctk.CTkFrame(card, fg_color="transparent")
            right.pack(side="right", padx=10)
            if not active:
                button(right, "Use", lambda x=a: self.use_account(x), width=60).pack(side="left", padx=3)
            button(right, "Skin...", lambda x=a: self.pick_image(x, "skin"), "ghost", 76).pack(side="left", padx=3)
            button(right, "Cape...", lambda x=a: self.pick_image(x, "cape"), "ghost", 76).pack(side="left", padx=3)
            if a["skin"] or a["cape"]:
                button(right, "Reset", lambda x=a: self.clear_images(x), "ghost", 64).pack(side="left", padx=3)
            button(right, "🗑", lambda x=a: self.delete_account(x), "danger", 40).pack(side="left", padx=3)

    def add_account(self):
        name = self.acc_entry.get().strip()
        if not core.NAME_RE.match(name):
            messagebox.showwarning("Username", "Use 3 to 16 letters, numbers or underscores.")
            return
        if any(a["name"].lower() == name.lower() for a in self.store["accounts"]):
            messagebox.showwarning("Username", "You already have an account with that name.")
            return
        a = core.new_account(name)
        self.store["accounts"].append(a)
        self.store["active_account"] = a["id"]
        self.save()
        self.acc_entry.delete(0, "end")
        self.update_sidebar_account()
        self.draw_accounts()

    def use_account(self, a):
        self.store["active_account"] = a["id"]
        self.save()
        self.update_sidebar_account()
        self.draw_accounts()

    def pick_image(self, a, kind):
        path = filedialog.askopenfilename(title=f"Choose a {kind} image", filetypes=[("PNG image", "*.png")])
        if not path:
            return
        try:
            w, h = core.png_size(path)
            if kind == "skin":
                ok = w % 64 == 0 and h in (w, w // 2)
                hint = "A skin is 64x64 (or 64x32) pixels."
            else:
                ok = (w, h) == (22, 17) or (w % 64 == 0 and h == w // 2)
                hint = "A cape is 64x32 pixels."
            if not ok:
                messagebox.showerror("Wrong size", f"This image is {w}x{h}. {hint}")
                return
            core.set_account_image(a, kind, path)
        except Exception as e:  # noqa
            messagebox.showerror("Image", str(e))
            return
        self.save()
        self.draw_accounts()

    def clear_images(self, a):
        core.remove_account_files(a)
        self.save()
        self.draw_accounts()

    def delete_account(self, a):
        if len(self.store["accounts"]) == 1:
            messagebox.showinfo("Accounts", "You need at least one account.")
            return
        if not messagebox.askyesno("Delete account", f"Delete the account '{a['name']}'?"):
            return
        core.remove_account_files(a)
        self.store["accounts"] = [x for x in self.store["accounts"] if x["id"] != a["id"]]
        if self.store["active_account"] == a["id"]:
            self.store["active_account"] = self.store["accounts"][0]["id"]
        self.save()
        self.update_sidebar_account()
        self.draw_accounts()


# =====================================================================================
class EditWindow(ctk.CTkToplevel):
    """Edit one profile: general settings, mods, resource packs, shaders."""

    LABELS = {"mod": "mods", "resourcepack": "resource packs", "shader": "shader packs"}

    def __init__(self, app, p):
        super().__init__(app)
        self.app, self.p = app, p
        self.title(f"Edit profile - {p['name']}")
        self.geometry("800x700")
        self.configure(fg_color=BG)
        self.after(200, lambda: (self.lift(), self.focus_force()))
        self.parts = {t: {} for t in self.LABELS}

        tabs = ctk.CTkTabview(self, fg_color=PANEL, segmented_button_selected_color=ACCENT,
                              segmented_button_selected_hover_color=ACCENT_H)
        tabs.pack(fill="both", expand=True, padx=14, pady=14)
        try:
            tabs._segmented_button.configure(selected_text_color=ACCENT_T)
        except Exception:
            pass
        self.build_general(tabs.add("General"))
        self.build_content(tabs.add("Mods"), "mod")
        self.build_content(tabs.add("Resource packs"), "resourcepack")
        self.build_content(tabs.add("Shaders"), "shader")

    def say(self, text):
        self.app.set_status(text)

    # ---------------------------------------------------------------- general
    def build_general(self, tab):
        p = self.p
        ctk.CTkLabel(tab, text=detail(p), text_color=MUTED).pack(anchor="w", padx=16, pady=(12, 2))
        if p.get("modpack"):
            ctk.CTkLabel(tab, text=f"Modpack: {p['modpack']}", text_color=ACCENT).pack(anchor="w", padx=16)

        ctk.CTkLabel(tab, text="Profile name", text_color=MUTED).pack(anchor="w", padx=16, pady=(14, 2))
        self.name_entry = ctk.CTkEntry(tab, width=400, height=36)
        self.name_entry.insert(0, p["name"])
        self.name_entry.pack(anchor="w", padx=16)

        mx = core.max_ram_gb()
        self.ram_lbl = ctk.CTkLabel(tab, text=f"Allocated RAM: {p['ram']} GB", text_color=MUTED)
        self.ram_lbl.pack(anchor="w", padx=16, pady=(16, 2))
        self.ram = ctk.CTkSlider(tab, from_=1, to=mx, number_of_steps=max(mx - 1, 1), width=400,
                                 progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_H,
                                 command=lambda v: self.ram_lbl.configure(text=f"Allocated RAM: {int(v)} GB"))
        self.ram.set(min(p["ram"], mx))
        self.ram.pack(anchor="w", padx=16)
        ctk.CTkLabel(tab, text="4 GB is plenty for vanilla and light mods. Big modpacks like 6-8 GB. "
                               "More is not always faster.", text_color=MUTED, font=("Segoe UI", 11)
                     ).pack(anchor="w", padx=16, pady=(2, 0))

        ctk.CTkLabel(tab, text="Extra Java arguments (optional)", text_color=MUTED
                     ).pack(anchor="w", padx=16, pady=(16, 2))
        self.jvm = ctk.CTkEntry(tab, width=560, height=36)
        self.jvm.insert(0, p.get("jvm_args", ""))
        self.jvm.pack(anchor="w", padx=16)

        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(anchor="w", padx=16, pady=24)
        button(row, "Save changes", self.save_general, width=150, height=40).pack(side="left")
        button(row, "Open folder", lambda: core.open_folder(core.profile_dir(p)), "ghost", 130, 40
               ).pack(side="left", padx=10)
        button(row, "🗑 Delete profile", self.delete, "danger", 150, 40).pack(side="left")

    def save_general(self):
        p = self.p
        p["name"] = self.app.unique_name(self.name_entry.get().strip() or p["name"], exclude_id=p["id"])
        p["ram"] = int(self.ram.get())
        p["jvm_args"] = self.jvm.get().strip()
        self.app.save()
        self.title(f"Edit profile - {p['name']}")
        self.say(f"Saved {p['name']}.")
        self.app.show(self.app.page)

    def delete(self):
        p = self.p
        if not messagebox.askyesno("Delete profile",
                                   f"Delete '{p['name']}' completely?\n\nIts mods, worlds and settings "
                                   "will be removed. This cannot be undone.", parent=self):
            return
        core.delete_profile_files(p)
        self.app.store["profiles"] = [x for x in self.app.store["profiles"] if x["id"] != p["id"]]
        self.app.save()
        self.say(f"Deleted {p['name']}.")
        self.destroy()
        self.app.show("profiles")

    # ---------------------------------------------------------------- mods / packs / shaders
    def build_content(self, tab, ptype):
        p, w = self.p, self.parts[ptype]
        if p["loader"] == "vanilla" and ptype in ("mod", "shader"):
            what = "Mods" if ptype == "mod" else "Shaders"
            ctk.CTkLabel(tab, wraplength=640, justify="left", text_color=MUTED,
                         text=f"{what} need a mod loader, and this profile is Vanilla.\n\n"
                              "Create a new profile with Fabric (best for FPS), Quilt, Forge or NeoForge "
                              "from 'Create profile'."
                         ).pack(padx=20, pady=30, anchor="w")
            return
        label = self.LABELS[ptype]
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(10, 4))
        w["entry"] = ctk.CTkEntry(row, width=380, height=34, placeholder_text=f"Search {label}...")
        w["entry"].pack(side="left")
        w["entry"].bind("<Return>", lambda e: self.search(ptype))
        button(row, "Search", lambda: self.search(ptype), width=80, height=34).pack(side="left", padx=6)
        button(row, "Add file...", lambda: self.add_local(ptype), "ghost", 90, 34).pack(side="left")
        button(row, "Folder", lambda: core.open_folder(
            os.path.join(core.profile_dir(p), core.TYPE_DIRS[ptype])), "ghost", 70, 34
               ).pack(side="left", padx=6)

        if ptype == "mod":
            button(tab, "⚡ Install FPS boost pack", self.boost, width=220, height=34
                   ).pack(anchor="w", padx=10, pady=(2, 4))
        if ptype == "shader":
            button(tab, "Install shader support (Iris + Sodium)", self.shader_support, width=300, height=34
                   ).pack(anchor="w", padx=10, pady=(2, 4))

        w["results"] = ctk.CTkScrollableFrame(tab, height=190, label_text=f"Compatible {label} (Minecraft {p['mc_version']})")
        w["results"].pack(fill="x", padx=8, pady=4)
        w["installed"] = ctk.CTkScrollableFrame(tab, height=140, label_text="Installed in this profile")
        w["installed"].pack(fill="x", padx=8, pady=4)
        self.refresh(ptype)
        self.search(ptype)

    def search(self, ptype):
        w, p = self.parts[ptype], self.p
        q = w["entry"].get().strip()
        self.say("Searching Modrinth...")

        def done(hits):
            if not alive(w["results"]):
                return
            for c in w["results"].winfo_children():
                c.destroy()
            self.say(f"{len(hits)} results.")
            for h in hits:
                card = ctk.CTkFrame(w["results"], fg_color=CARD)
                card.pack(fill="x", padx=2, pady=3)
                ctk.CTkLabel(card, text=h["title"], font=("Segoe UI", 13, "bold"), anchor="w"
                             ).pack(fill="x", padx=10, pady=(6, 0))
                d = h["description"]
                ctk.CTkLabel(card, text=d if len(d) < 90 else d[:87] + "...", text_color=MUTED,
                             anchor="w", wraplength=520, justify="left").pack(fill="x", padx=10)
                button(card, "Install", lambda x=h: self.install(ptype, x), width=76, height=26
                       ).pack(anchor="e", padx=10, pady=5)
        self.app.bg(lambda: core.mr_search(q, ptype, p["mc_version"], p["loader"], 20), done)

    def install(self, ptype, hit):
        p = self.p
        self.say(f"Installing {hit['title']}...")

        def work():
            return core.mr_install(hit["project_id"], ptype, p, self.say)

        def done(_):
            self.say(f"{hit['title']} installed.")
            if alive(self):
                self.refresh(ptype)
        self.app.bg(work, done)

    def boost(self):
        p = self.p
        self.say("Installing the FPS boost pack...")

        def done(got):
            self.say(f"FPS boost pack installed ({len(got)} mods).")
            if alive(self):
                self.refresh("mod")
        self.app.bg(lambda: core.install_boost(p, self.say), done)

    def shader_support(self):
        p = self.p
        self.say("Installing shader support...")

        def done(got):
            self.say("Shader support installed. Put shader packs in the Shaders list, then pick one in-game.")
            if alive(self):
                self.refresh("mod")
        self.app.bg(lambda: core.install_shader_support(p, self.say), done)

    def add_local(self, ptype):
        kinds = {"mod": ("Mod file", "*.jar"), "resourcepack": ("Resource pack", "*.zip"),
                 "shader": ("Shader pack", "*.zip")}
        paths = filedialog.askopenfilenames(parent=self, filetypes=[kinds[ptype]])
        if not paths:
            return
        d = os.path.join(core.profile_dir(self.p), core.TYPE_DIRS[ptype])
        os.makedirs(d, exist_ok=True)
        for src in paths:
            shutil.copyfile(src, os.path.join(d, os.path.basename(src)))
        self.say(f"Added {len(paths)} file(s).")
        self.refresh(ptype)

    def refresh(self, ptype):
        w = self.parts[ptype]
        if "installed" not in w or not alive(w["installed"]):
            return
        for c in w["installed"].winfo_children():
            c.destroy()
        files = core.list_installed(self.p, ptype)
        if not files:
            ctk.CTkLabel(w["installed"], text="Nothing installed yet", text_color=MUTED).pack(pady=8)
        for f in files:
            r = ctk.CTkFrame(w["installed"], fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=f if len(f) < 70 else f[:67] + "...", anchor="w").pack(side="left", padx=4)
            button(r, "Remove", lambda n=f: self.remove(ptype, n), "danger", 64, 24).pack(side="right", padx=4)

    def remove(self, ptype, name):
        core.remove_installed(self.p, ptype, name)
        self.refresh(ptype)


if __name__ == "__main__":
    App().mainloop()
