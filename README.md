# Wine for Marvelous Designer

Fixes for running **Marvelous Designer** on Linux in **Bottles**. Install Marvelous Designer in a bottle, run one script, and you're done.

> **I made this for my own setup and I'm sharing it as is. There's no support, so please don't contact me about it.** If it doesn't work on your system, `sh install.sh --uninstall` puts everything back. Use it at your own risk.
>
> Vibe-coded with [Claude](https://claude.com/claude-code) (Claude Code).

| # | Problem | Fix |
|---|---------|-----|
| 1 | Marvelous Designer 2026 crashes right at start (*stack overflow*) | It needs Wine 11.20 or newer. The script can download Wine 11.20 (SHA-256 checked) as a Bottles runner and switch the bottle to it |
| 2 | The simulation only uses one CPU core | Wine's own `vcomp140` instead of Microsoft's, so the simulation runs on all cores |
| 3 | Closing a window (e.g. Library) leaves a black box on the screen (Wine 11.20 on GNOME) | Turns off Wine's own window decorations; Marvelous Designer draws its own title bars anyway |
| 4 | No menu entry, or a generic icon | Menu entry for every Marvelous Designer version in the bottle, with its own icon. If you already have one, it's kept and only routed through the launcher |
| 5 | Starting Marvelous Designer a second time freezes Bottles | Only one Marvelous Designer per bottle at a time: a second start only shows a notification |
| 6 | *"failed to set protection"* when a program starts (SELinux, e.g. Fedora, Rocky, RHEL) | Checks the SELinux setting and tells you the command |

## Requirements

- [Bottles](https://usebottles.com) (Flatpak or native)
- Marvelous Designer installed in a bottle (tested: Personal 2024.0 and 2026.1), added as a program in Bottles
- An X11 desktop or XWayland. Tested on Rocky Linux 9 with GNOME on X11.

### Installing Marvelous Designer

- Bottles (Flatpak) can't see your Downloads folder. Put the installer on a drive or in a folder Bottles can see, or copy it into the bottle's `drive_c`.
- **Use a separate bottle for every version.** The 2026 installer installs into the same folder as 2024 and overwrites it. Also, 2026 needs Wine 11.20, while 2024 is tested on Wine 11.0 (soda-11.0-10).

## Install

1. Close Marvelous Designer.
2. Run:
   ```sh
   sh install.sh
   ```
   The script finds the bottle that has Marvelous Designer in it. If you have more than one (e.g. 2024 and 2026), run it once for each: `sh install.sh --bottle NAME`.
3. Start Marvelous Designer from the menu or the dock.

If you run the script with `--yes`, it answers every question with yes, including the Wine 11.20 download.

### Start Marvelous Designer only once

If you start a second Marvelous Designer in the same bottle while one is already running, Bottles freezes. Bottles (Flatpak) runs every launch in its own sandbox, and the two break each other. The launcher (`~/.local/bin/wine-for-marvelous-designer-BOTTLE`) prevents this: if Marvelous Designer is already running in that bottle, or still starting, you only get a notification. Versions in **different** bottles can run at the same time.

The script looks for menu entries (`.desktop` files in `~/.local/share/applications`) that start Marvelous Designer from this bottle and routes them through the launcher, so your dock icon keeps working. If there's none, it creates one for each version.

Before it starts the program, the launcher also closes a dead Bottles sandbox of the same bottle, if one was left behind: Wine's services (services.exe, winedevice.exe, ...) still running without a wineserver. Otherwise the next start can hang without a window. It never closes a sandbox that still has a wineserver, a program or the Bottles window in it.

Starting Marvelous Designer with the ▶ button in the Bottles window isn't protected.

The notification is urgent, so GNOME shows it on top of a fullscreen window too. It stays until you close it.

## Uninstall

```sh
sh install.sh --uninstall --bottle NAME
```

This restores the bottle's old runner, the old `vcomp140` and window decoration settings and your menu entries, and removes the launcher. The Wine 11.20 runner can then be deleted in Bottles (*Preferences → Runners*) if no other bottle uses it.

## What it changes

- **Runner** (only for Marvelous Designer 2026 or newer on a Wine older than 11.20, and only if you say yes): downloads `wine-11.20-staging-amd64.tar.xz` from [Kron4ek/Wine-Builds](https://github.com/Kron4ek/Wine-Builds/releases/tag/11.20), checks its SHA-256, unpacks it as the Bottles runner `kron4ek-11.20-staging`, and sets it in `bottle.yml` (a backup is saved as `bottle.yml.bak-wine-for-marvelous-designer`). If the bottle also has an older version, the runner isn't changed.
- `user.reg` (a backup is saved as `user.reg.bak-wine-for-marvelous-designer`): DLL override `vcomp140` = `builtin`. Microsoft's `vcomp140.dll` (which Bottles installs with *vcredist*) runs the simulation on a single thread under Wine; Wine's own one uses all cores.
- `user.reg`, only on Wine 11.20 or newer: `[Software\Wine\X11 Driver]` `"Decorated"="N"`. Without it, a window that Marvelous Designer closes stays mapped on X11 and shows as a black box until you open it again.
- `~/.local/bin/wine-for-marvelous-designer-BOTTLE`: starts Marvelous Designer with `bottles-cli`, unless one is already running in this bottle.
- Menu entries that start Marvelous Designer from this bottle get `Exec=` pointing to the launcher (a backup is saved next to them as `*.bak-wine-for-marvelous-designer`). If there's none: `~/.local/share/applications/wine-for-marvelous-designer-BOTTLE-PROGRAM.desktop`.
- Icons taken from the `.exe`: `~/.local/share/icons/hicolor/256x256/apps/wine-for-marvelous-designer-YEAR.png`.
- The old values are kept in `.wine-for-marvelous-designer.json` in the bottle folder, for the uninstall.
- SELinux is only checked, never changed.

## Tested on

**Software**

| | Version |
|---|---|
| Marvelous Designer | Personal 2024.0.125 and Personal 2026.1.237, in separate bottles |
| Bottles | 67.5 (Flatpak, GNOME Platform 50 runtime) |
| Wine runner | 2024: soda-11.0-10 (Wine 11.0) · 2026: Kron4ek wine-11.20-staging |
| Bottle | Application environment, Windows 10, DXVK 3.1.1, VKD3D-Proton 3.0.1 |
| OS | Rocky Linux 9.8, kernel 5.14.0-687, SELinux enforcing |
| Desktop | GNOME 40.10 on **X11** (Xorg 1.20.11) |
| GPU driver | NVIDIA 580.178.04 (open kernel module) |

**Hardware**

| | |
|---|---|
| CPU | AMD Ryzen 9 5900X (12 cores / 24 threads) |
| RAM | 128 GB |
| GPU | NVIDIA GeForce RTX 3090 |
| Display | 2 × 4K (3840 × 2160) 60 Hz |

AMD/Intel GPUs, Wayland (XWayland), KDE and other distros haven't been tested.

## Known limitations

- **Simulation speed on Wine 11.20:** newer Wine versions no longer have *fsync/esync*; they use *ntsync*, which needs Linux kernel 6.14 or newer. On older kernels (e.g. Rocky 9) the simulation spreads over all cores, but each core is less busy than on Windows, so it's slower than native.
- GPU (CUDA) simulation isn't available under Wine; the simulation runs on the CPU.
- Only one Marvelous Designer per bottle at a time, and only if you start it through the launcher (see *Start Marvelous Designer only once*).
- Marvelous Designer only sees folders that Bottles has access to (use Flatseal to add more).
