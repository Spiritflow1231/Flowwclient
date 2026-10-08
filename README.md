# Flowclient Launcher

A lightweight Minecraft Java launcher.

- Offline accounts with skins and capes
- Profiles: pick a loader (Vanilla, Fabric, Quilt, Forge, NeoForge) and a version it supports
- Add mods, resource packs and shaders from Modrinth, or add any Modrinth modpack
- Per-profile RAM, extra Java arguments, edit and delete
- One-click FPS boost pack (Sodium, Lithium, FerriteCore, ImmediatelyFast, Entity Culling, ModernFix)

## Run it from source

    pip install -r requirements.txt
    python main.py

## Build the Windows app

Push a tag like `v1.0.0`. GitHub Actions builds `FlowclientLauncher.exe` and attaches it to the Release.
