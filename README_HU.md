# Wine for Marvelous Designer

Javítások ahhoz, hogy a **Marvelous Designer** Linuxon, **Bottles**-ben rendesen működjön. Telepítsd a Marvelous Designert egy bottle-be, futtass le egy szkriptet, és kész.

> **Ezt a saját gépemre készítettem, és úgy osztom meg, ahogy van. Támogatást nem adok hozzá, kérlek, ne keress meg vele.** Ha nálad nem működik, a `sh install.sh --uninstall` mindent visszaállít. Csak saját felelősségre használd.
>
> Vibe coding, [Claude](https://claude.com/claude-code)-dal (Claude Code) készült.

| # | Probléma | Megoldás |
|---|----------|----------|
| 1 | A Marvelous Designer 2026 rögtön induláskor összeomlik (*stack overflow*) | Wine 11.20 vagy újabb kell neki. A szkript le tudja tölteni a Wine 11.20-at (SHA-256-tal ellenőrizve) Bottles-runnerként, és átállítja rá a bottle-t |
| 2 | A szimuláció csak egy processzormagot használ | A Microsoft-féle helyett a Wine saját `vcomp140`-e, így a szimuláció minden magon fut |
| 3 | Ha bezársz egy ablakot (pl. Library), fekete kocka marad a helyén (Wine 11.20, GNOME) | Kikapcsolja a Wine saját ablakkeretezését; a Marvelous Designer úgyis saját fejlécet rajzol |
| 4 | Nincs menüpont, vagy általános ikonja van | Menüpont a bottle-ben lévő minden Marvelous Designer verzióhoz, a saját ikonjával. Ha már van menüpontod, az marad, csak az indítón keresztül indul |
| 5 | Ha másodszor is elindítod a Marvelous Designert, a Bottles lefagy | Bottle-önként egyszerre csak egy Marvelous Designer: a második indítás csak értesítést ad |
| 6 | Program indításakor *„failed to set protection”* hiba (SELinux, pl. Fedora, Rocky, RHEL) | Ellenőrzi a SELinux beállítást, és megadja a parancsot |

## Ami kell hozzá

- [Bottles](https://usebottles.com) (Flatpak vagy natív)
- Egy bottle-be telepített Marvelous Designer (kipróbálva: Personal 2024.0 és 2026.1), programként felvéve a Bottlesben
- X11 asztal vagy XWayland. Kipróbálva: Rocky Linux 9, GNOME, X11.

### A Marvelous Designer telepítése

- A Bottles (Flatpak) nem látja a Letöltések mappát. A telepítőt tedd olyan meghajtóra vagy mappába, amit a Bottles lát, vagy másold a bottle `drive_c` mappájába.
- **Minden verziót külön bottle-be telepíts.** A 2026-os telepítő ugyanabba a mappába telepít, mint a 2024-es, és felülírja. Ráadásul a 2026-nak Wine 11.20 kell, a 2024 pedig Wine 11.0-val (soda-11.0-10) van kipróbálva.

## Telepítés

1. Zárd be a Marvelous Designert.
2. Futtasd:
   ```sh
   sh install.sh
   ```
   Magától megkeresi azt a bottle-t, amelyikben a Marvelous Designer van. Ha több ilyen van (pl. 2024 és 2026), mindegyikre futtasd le egyszer: `sh install.sh --bottle NÉV`.
3. Indítsd a Marvelous Designert a menüből vagy a dokkról.

Ha a szkriptet `--yes` kapcsolóval futtatod, minden kérdésre igent mond, a Wine 11.20 letöltésére is.

### Egyszerre csak egy Marvelous Designer

Ha ugyanabban a bottle-ben elindítasz egy második Marvelous Designert, miközben egy már fut, a Bottles lefagy. A Bottles (Flatpak) minden indítást külön dobozban futtat, és a kettő összeakad. Az indító (`~/.local/bin/wine-for-marvelous-designer-BOTTLE`) ezt megakadályozza: ha abban a bottle-ben már fut vagy éppen indul a Marvelous Designer, csak egy értesítést kapsz. A **különböző** bottle-ökben lévő verziók egyszerre is futhatnak.

A szkript megkeresi azokat a menübejegyzéseket (`.desktop` fájlok a `~/.local/share/applications` mappában), amelyek ebből a bottle-ből indítják a Marvelous Designert, és átirányítja őket az indítóra, így a dokkon lévő ikonod is így működik. Ha nincs ilyen, minden verzióhoz létrehoz egyet.

Indítás előtt az indító bezárja ugyanennek a bottle-nek az esetleg bent maradt, halott Bottles dobozát is: amikor a Wine szolgáltatásai (services.exe, winedevice.exe …) még futnak, de a wineserver már nem. Enélkül a következő indítás ablak nélkül beragadhat. Olyan dobozt soha nem zár be, amiben még fut a wineserver, egy program vagy a Bottles ablaka.

Ha a Bottles ablakában a ▶ gombbal indítod a Marvelous Designert, az nincs védve.

Az értesítés sürgős, így a GNOME a teljes képernyős ablakok fölött is megmutatja. Addig marad kint, amíg be nem zárod.

## Eltávolítás

```sh
sh install.sh --uninstall --bottle NÉV
```

Visszaállítja a bottle régi runnerét, a régi `vcomp140`- és ablakkeret-beállítást és a menübejegyzéseidet, és törli az indítót. A Wine 11.20 runnert utána a Bottlesben törölheted (*Beállítások → Runners*), ha másik bottle nem használja.

## Mit változtat

- **Runner** (csak Marvelous Designer 2026 vagy újabb esetén, ha a Wine régebbi 11.20-nál, és csak ha igent mondasz): letölti a `wine-11.20-staging-amd64.tar.xz`-t a [Kron4ek/Wine-Builds](https://github.com/Kron4ek/Wine-Builds/releases/tag/11.20) oldalról, ellenőrzi a SHA-256-ját, kicsomagolja `kron4ek-11.20-staging` néven Bottles-runnerként, és beállítja a `bottle.yml`-ben (mentés: `bottle.yml.bak-wine-for-marvelous-designer`). Ha a bottle-ben régebbi verzió is van, a runnert nem állítja át.
- `user.reg` (mentés: `user.reg.bak-wine-for-marvelous-designer`): a `vcomp140` DLL-beállítás `builtin` lesz. A Microsoft-féle `vcomp140.dll` (amit a Bottles a *vcredist*-tel telepít) Wine alatt egy szálon futtatja a szimulációt, a Wine sajátja minden magot használ.
- `user.reg`, csak Wine 11.20-on vagy újabbon: `[Software\Wine\X11 Driver]` `"Decorated"="N"`. Enélkül az az ablak, amit a Marvelous Designer bezár, X11 alatt a képernyőn marad, és fekete kockaként látszik, amíg újra meg nem nyitod.
- `~/.local/bin/wine-for-marvelous-designer-BOTTLE`: a `bottles-cli`-vel indítja a Marvelous Designert, kivéve, ha ebben a bottle-ben már fut egy.
- Azok a menübejegyzések, amelyek ebből a bottle-ből indítják a Marvelous Designert, az indítóra mutató `Exec=` sort kapnak (mentés mellettük: `*.bak-wine-for-marvelous-designer`). Ha nincs ilyen: `~/.local/share/applications/wine-for-marvelous-designer-BOTTLE-PROGRAM.desktop`.
- Ikonok az `.exe`-ből: `~/.local/share/icons/hicolor/256x256/apps/wine-for-marvelous-designer-ÉVSZÁM.png`.
- A régi értékek az eltávolításhoz a bottle mappájában, a `.wine-for-marvelous-designer.json` fájlban maradnak meg.
- A SELinuxot csak ellenőrzi, soha nem módosítja.

## Tesztgép

**Szoftver**

| | Verzió |
|---|---|
| Marvelous Designer | Personal 2024.0.125 és Personal 2026.1.237, külön bottle-ökben |
| Bottles | 67.5 (Flatpak, GNOME Platform 50 runtime) |
| Wine runner | 2024: soda-11.0-10 (Wine 11.0) · 2026: Kron4ek wine-11.20-staging |
| Bottle | Application környezet, Windows 10, DXVK 3.1.1, VKD3D-Proton 3.0.1 |
| Rendszer | Rocky Linux 9.8, kernel 5.14.0-687, SELinux enforcing |
| Asztal | GNOME 40.10, **X11** (Xorg 1.20.11) |
| Videókártya-meghajtó | NVIDIA 580.178.04 (open kernel module) |

**Hardver**

| | |
|---|---|
| Processzor | AMD Ryzen 9 5900X (12 mag / 24 szál) |
| Memória | 128 GB |
| Videókártya | NVIDIA GeForce RTX 3090 |
| Kijelző | 2 × 4K (3840 × 2160), 60 Hz |

AMD/Intel videókártyával, Waylanddel (XWayland), KDE-vel és más disztribúciókkal nincs kipróbálva.

## Ismert korlátok

- **Szimulációs sebesség Wine 11.20-on:** az újabb Wine-okban már nincs *fsync/esync*, helyette *ntsync* van, amihez 6.14-es vagy újabb Linux kernel kell. Régebbi kernelen (pl. Rocky 9) a szimuláció minden magra szétoszlik, de a magok kevésbé vannak kihasználva, mint Windowson, ezért lassabb a natívnál.
- A GPU-s (CUDA) szimuláció Wine alatt nem érhető el, a szimuláció a processzoron fut.
- Bottle-önként egyszerre csak egy Marvelous Designer futhat, és ez csak akkor van védve, ha az indítón keresztül indítod (lásd *Egyszerre csak egy Marvelous Designer*).
- A Marvelous Designer csak azokat a mappákat látja, amelyekhez a Bottlesnek van hozzáférése (továbbiakat a Flatseallel adhatsz hozzá).
