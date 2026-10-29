#!/usr/bin/python3
# Wine for Marvelous Designer - fixes for Marvelous Designer in Bottles.
#
#   1. Marvelous Designer 2026 crashes at start on Wine 11.0 (stack overflow): it needs Wine 11.20.
#      The script can download the Kron4ek Wine 11.20 staging build (SHA-256 checked) as a Bottles
#      runner and switch the bottle to it.
#   2. CPU simulation only uses one core: Microsoft's vcomp140.dll (from vcredist) is slow under
#      Wine. Wine's own vcomp140 spreads the simulation over all cores.
#   3. Wine 11.20 on GNOME: a closed window (e.g. Library) stays on screen as a black box.
#      Turning off Wine's window decorations (X11 Driver "Decorated"="N") fixes it.
#   4. Menu entry for every Marvelous Designer version in the bottle, with its own icon.
#   5. Only one Marvelous Designer per bottle at a time (a second launch would freeze Bottles).
#   6. SELinux: checks the setting Wine needs ("failed to set protection" otherwise).
#
# Undo: sh install.sh --uninstall

import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, tarfile, tempfile, time, \
    urllib.request, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = '.wine-for-marvelous-designer.json'
TAG = 'wine-for-marvelous-designer'
APP_NAME = 'Marvelous Designer'
EXE_RE = re.compile(r'^MarvelousDesigner.*\.exe$', re.I)
DATA = os.path.expanduser(os.environ.get('XDG_DATA_HOME', '~/.local/share'))
ASSUME_YES = False

# Wine >= this is needed by Marvelous Designer >= NEW_MD
NEW_MD = 2026
MIN_WINE = (11, 20)
RUNNER_NAME = 'kron4ek-11.20-staging'
RUNNER_URL = 'https://github.com/Kron4ek/Wine-Builds/releases/download/11.20/wine-11.20-staging-amd64.tar.xz'
RUNNER_SHA256 = '1dc66e214019b747e98955e5dba3ff650fdb5f11354557ac75ac14034a53f688'


def say(msg=''):
    print(msg, flush=True)


def ok(msg):
    say('  [ok] ' + msg)


def warn(msg):
    say('  [!]  ' + msg)


def die(msg):
    say('\nERROR: ' + msg)
    sys.exit(1)


def ask(question, default=False):
    if ASSUME_YES:
        return True
    hint = '[Y/n]' if default else '[y/N]'
    ans = input(f'{question} {hint} ').strip().lower()
    return default if not ans else ans in ('y', 'yes', 'i', 'igen')


# ---- Bottles ----------------------------------------------------------------

def find_bottles_root():
    for p in ('~/.var/app/com.usebottles.bottles/data/bottles', '~/.local/share/bottles'):
        p = os.path.expanduser(p)
        if os.path.isdir(os.path.join(p, 'bottles')):
            return p
    die('Bottles was not found (neither Flatpak nor native).')


def find_exes(bdir):
    """Unix paths of the Marvelous Designer .exe files in the bottle."""
    found = []
    for pf in ('Program Files', 'Program Files (x86)'):
        base = os.path.join(bdir, 'drive_c', pf)
        if not os.path.isdir(base):
            continue
        for d in sorted(os.listdir(base)):
            if 'marvelous' not in d.lower() or not os.path.isdir(os.path.join(base, d)):
                continue
            for f in sorted(os.listdir(os.path.join(base, d))):
                if EXE_RE.match(f):
                    found.append(os.path.join(base, d, f))
    return found


def md_year(exe):
    m = re.search(r'(20\d\d)', os.path.basename(os.path.dirname(exe)))
    return int(m.group(1)) if m else None


def find_app_bottles(root):
    bdir = os.path.join(root, 'bottles')
    return [n for n in sorted(os.listdir(bdir)) if find_exes(os.path.join(bdir, n))]


def find_programs(yml):
    """{program name: executable path as written in bottle.yml} for Marvelous Designer entries."""
    text = open(yml, encoding='utf-8').read()
    out = {}
    for block in re.split(r'\n    [0-9a-f-]{36}:\n', text):
        e = re.search(r'^        executable: (.+)$', block, re.M)
        n = re.search(r'^        name: (.+)$', block, re.M)
        p = re.search(r'^        path: (.+)$', block, re.M)
        if e and n and EXE_RE.match(e.group(1).strip().strip("'\"")):
            out[n.group(1).strip().strip("'\"")] = p.group(1).strip().strip("'\"") if p else ''
    return out


def program_exe(path, bdir):
    """bottle.yml program path (Windows C:\\... or Unix) -> Unix path."""
    if re.match(r'^[A-Za-z]:\\', path):
        return os.path.join(bdir, 'drive_c', *path[3:].split('\\'))
    return path


def read_yaml_value(path, key):
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.startswith(key + ':'):
                return line.split(':', 1)[1].strip().strip("'\"")
    return None


def set_yaml_value(path, key, value):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    text, n = re.subn(r'^%s:.*$' % re.escape(key), '%s: %s' % (key, value), text, count=1, flags=re.M)
    if not n:
        die(f'"{key}" not found in {path}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def bottle_running(bdir):
    """True if any Wine process of this bottle is alive (it would overwrite the registry on exit)."""
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            env = open(f'/proc/{pid}/environ', 'rb').read().split(b'\0')
        except OSError:
            continue
        if ('WINEPREFIX=' + bdir).encode() in env:
            comm = open(f'/proc/{pid}/comm').read().strip()
            if comm == 'wineserver' or comm.lower().endswith('.exe'):
                return True
    return False


# ---- runner ---------------------------------------------------------------------

def wine_version(runner_dir):
    """(major, minor) of a Bottles runner, read from its ntdll (without running it)."""
    for rel in ('lib/wine/x86_64-unix/ntdll.so', 'lib64/wine/x86_64-unix/ntdll.so'):
        p = os.path.join(runner_dir, rel)
        if os.path.exists(p):
            m = re.search(rb'wine-(\d+)\.(\d+)', open(p, 'rb').read())
            if m:
                return int(m.group(1)), int(m.group(2))
    return None


def get_runner(root):
    dst = os.path.join(root, 'runners', RUNNER_NAME)
    if os.path.isdir(dst) and (wine_version(dst) or (0, 0)) >= MIN_WINE:
        ok(f'runner {RUNNER_NAME} is already installed')
        return True
    say(f'  Downloading Wine 11.20 staging (Kron4ek build, ~100 MB):\n  {RUNNER_URL}')
    tmp = tempfile.NamedTemporaryFile(suffix='.tar.xz', delete=False)
    try:
        h = hashlib.sha256()
        with urllib.request.urlopen(RUNNER_URL) as r:
            total = int(r.headers.get('Content-Length') or 0)
            done = 0
            for chunk in iter(lambda: r.read(1 << 20), b''):
                tmp.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    print(f'\r  {done * 100 // total:3d}%', end='', flush=True)
        tmp.close()
        print()
        if h.hexdigest() != RUNNER_SHA256:
            warn('the download does not match the expected SHA-256. Nothing was installed.')
            return False
        ok('download checked (SHA-256)')
        work = tempfile.mkdtemp(dir=os.path.join(root, 'runners'))
        with tarfile.open(tmp.name) as t:
            if hasattr(tarfile, 'data_filter'):
                t.extractall(work, filter='data')
            else:
                for m in t.getmembers():
                    if m.name.startswith('/') or '..' in m.name.split('/'):
                        raise ValueError('unsafe path in archive: ' + m.name)
                t.extractall(work)
        top = [d for d in os.listdir(work) if os.path.isdir(os.path.join(work, d))]
        if len(top) != 1:
            shutil.rmtree(work)
            warn('unexpected archive layout. Nothing was installed.')
            return False
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        os.rename(os.path.join(work, top[0]), dst)
        os.rmdir(work)
        ok(f'runner {RUNNER_NAME} installed (Bottles -> Preferences -> Runners shows it)')
        return True
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


# ---- registry (Wine .reg text) -------------------------------------------------

def _section(text, key):
    m = re.search(r'^\[' + re.escape(key) + r'\][^\n]*\n', text, re.M | re.I)
    if not m:
        return None
    end = text.find('\n\n', m.end())
    return m.end(), (len(text) if end < 0 else end + 1)


def reg_get(text, key, name=None):
    s = _section(text, key)
    if not s:
        return None
    lhs = '@' if name is None else '"%s"' % name
    m = re.search('^' + re.escape(lhs) + '=(.*)$', text[s[0]:s[1]], re.M | re.I)
    return m.group(1) if m else None


def reg_set(text, key, value, name=None):
    """value: raw as written in the file; None deletes the value."""
    lhs = '@' if name is None else '"%s"' % name
    s = _section(text, key)
    if not s:
        if value is None:
            return text
        return text.rstrip('\n') + f'\n\n[{key}] {int(time.time())}\n{lhs}={value}\n'
    a, b = s
    body = text[a:b]
    pat = re.compile('^' + re.escape(lhs) + '=.*\n', re.M | re.I)
    if value is None:
        body = pat.sub('', body, 1)
    elif pat.search(body):
        body = pat.sub(lambda _: f'{lhs}={value}\n', body, 1)
    else:
        body += f'{lhs}={value}\n'
    return text[:a] + body + text[b:]


OVERRIDES = 'Software\\\\Wine\\\\DllOverrides'
X11 = 'Software\\\\Wine\\\\X11 Driver'


# ---- icon from the .exe ----------------------------------------------------------

def exe_icon_png(path):
    """Largest icon of a Windows .exe as PNG bytes (or None)."""
    d = open(path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    rsrc_rva = struct.unpack_from('<I', d, opt + (112 if magic == 0x20b else 96) + 2 * 8)[0]
    sec = opt + struct.unpack_from('<H', d, pe + 20)[0]
    for i in range(nsec):
        va, size, raw = struct.unpack_from('<III', d, sec + i * 40 + 12)
        if va <= rsrc_rva < va + max(size, 1):
            base, delta = raw + rsrc_rva - va, va - raw
            break
    else:
        return None

    def entries(off):
        named, ids = struct.unpack_from('<HH', d, base + off + 12)
        for j in range(named + ids):
            name, child = struct.unpack_from('<II', d, base + off + 16 + j * 8)
            yield name, child

    def leaf(child):
        while child & 0x80000000:          # descend to the first language
            child = next(entries(child & 0x7fffffff))[1]
        rva, size = struct.unpack_from('<II', d, base + child)
        return d[rva - delta:rva - delta + size]

    types = dict(entries(0))
    if 14 not in types or 3 not in types:
        return None
    icons = {n: c for n, c in entries(types[3] & 0x7fffffff)}
    group = leaf(next(entries(types[14] & 0x7fffffff))[1])
    best = None
    for j in range(struct.unpack_from('<H', group, 4)[0]):
        w, h, _, _, _, bpp, size, nid = struct.unpack_from('<BBBBHHIH', group, 6 + j * 14)
        key = ((w or 256), bpp)
        if nid in icons and (best is None or key > best[0]):
            best = (key, nid)
    if not best:
        return None
    img = leaf(icons[best[1]])
    if img[:4] == b'\x89PNG':
        return img
    w = best[0][0]
    if struct.unpack_from('<H', img, 14)[0] != 32:
        return None
    px = img[struct.unpack_from('<I', img, 0)[0]:]
    rows = []
    for y in range(w):
        src = px[(w - 1 - y) * w * 4:(w - y) * w * 4]
        row = bytearray(src)
        row[0::4], row[2::4] = src[2::4], src[0::4]
        rows.append(b'\0' + bytes(row))
    chunk = lambda t, b: struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, w, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))


def png_size(png):
    return struct.unpack_from('>I', png, 16)[0]


# ---- menu entries + launcher -------------------------------------------------------

def menu_entries(bottle, program):
    """Existing .desktop files (yours or Bottles') that start this program from this bottle."""
    apps = os.path.join(DATA, 'applications')
    found = []
    if not os.path.isdir(apps):
        return found
    for f in sorted(os.listdir(apps)):
        p = os.path.join(apps, f)
        if not f.endswith('.desktop') or f.startswith(TAG + '-') or not os.path.isfile(p):
            continue
        m = re.search(r'^Exec=(.*)$', open(p, encoding='utf-8', errors='replace').read(), re.M)
        if not m:
            continue
        ex = m.group(1)
        if (re.search(r'(-b|--bottle)\s+["\']?%s["\']?(\s|$)' % re.escape(bottle), ex) and
                re.search(r'(-p|--program)\s+["\']?%s["\']?(\s|$)' % re.escape(program), ex)) or \
                ex.strip() == '%s "%s"' % (os.path.expanduser(f'~/.local/bin/{TAG}-{slug(bottle)}'), program):
            found.append(p)
    return found


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def install_launcher(root, bottle, bdir, programs, state):
    flatpak = '/.var/app/com.usebottles.bottles/' in root
    cli = 'flatpak run --command=bottles-cli com.usebottles.bottles' if flatpak else 'bottles-cli'
    launcher = os.path.expanduser(f'~/.local/bin/{TAG}-{slug(bottle)}')
    os.makedirs(os.path.dirname(launcher), exist_ok=True)
    script = open(os.path.join(HERE, 'files', 'launch.sh')).read()
    for key, value in (('CLI', cli), ('BOTTLE', bottle), ('PREFIX', bdir), ('EXE', 'MarvelousDesigner'),
                       ('NAME', APP_NAME), ('ICON', TAG)):
        script = script.replace('@%s@' % key, value.replace("'", "'\\''"))
    with open(launcher, 'w') as f:
        f.write(script)
    os.chmod(launcher, 0o755)
    state['launcher'] = launcher

    apps = os.path.join(DATA, 'applications')
    os.makedirs(apps, exist_ok=True)
    for program, path in programs.items():
        exe = program_exe(path, bdir)
        png = exe_icon_png(exe) if os.path.isfile(exe) else None
        icon = TAG
        if png:
            icon = f'{TAG}-{md_year(exe) or "app"}'
            size = png_size(png)
            d = os.path.join(DATA, 'icons', 'hicolor', f'{size}x{size}', 'apps')
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, icon + '.png'), 'wb').write(png)
            if not os.path.exists(os.path.join(d, TAG + '.png')):
                open(os.path.join(d, TAG + '.png'), 'wb').write(png)   # for the notification
        exec_line = f'Exec={launcher} "{program}"'
        existing = menu_entries(bottle, program)
        own = os.path.join(apps, f'{TAG}-{slug(bottle)}-{slug(program)}.desktop')
        if existing:
            # keep the user's entry (and its place in the dock), only route it through the launcher
            for p in existing:
                if not os.path.exists(p + '.bak-' + TAG):
                    shutil.copy2(p, p + '.bak-' + TAG)
                state.setdefault('menu', [])
                if p not in state['menu']:
                    state['menu'].append(p)
                text = open(p, encoding='utf-8').read()
                text = re.sub(r'^Exec=.*$', lambda _: exec_line, text, count=1, flags=re.M)
                open(p, 'w', encoding='utf-8').write(text)
                ok(f'menu entry {os.path.basename(p)} ({program}) now starts through the launcher')
            if os.path.exists(own):
                os.unlink(own)
        else:
            with open(own, 'w') as f:
                f.write(f'[Desktop Entry]\nType=Application\nName={program}\n'
                        f'Comment={program} ({bottle} bottle)\n{exec_line}\n'
                        f'Icon={icon}\nCategories=Graphics;3DGraphics;\nStartupNotify=true\n'
                        'StartupWMClass=steam_proton\n')
            ok(f'menu entry "{program}" created (with its own icon)')
    subprocess.run(['gtk-update-icon-cache', '-f', '-t', os.path.join(DATA, 'icons', 'hicolor')],
                   capture_output=True)
    subprocess.run(['update-desktop-database', apps], capture_output=True)
    ok('a second Marvelous Designer can\'t be started in this bottle by accident (notification instead)')


def uninstall_launcher(bottle, state):
    for p in state.get('menu', []):
        if os.path.exists(p + '.bak-' + TAG):
            shutil.move(p + '.bak-' + TAG, p)
            ok('menu entry %s restored' % os.path.basename(p))
    apps = os.path.join(DATA, 'applications')
    for f in os.listdir(apps) if os.path.isdir(apps) else ():
        if f.startswith(f'{TAG}-{slug(bottle)}-') and f.endswith('.desktop'):
            os.unlink(os.path.join(apps, f))
    if state.get('launcher') and os.path.exists(state['launcher']):
        os.unlink(state['launcher'])
    subprocess.run(['update-desktop-database', apps], capture_output=True)
    ok('launcher and menu entries removed (icons are kept for other bottles)')


# ---- install / uninstall -------------------------------------------------------------

def selinux_check():
    if not shutil.which('getenforce'):
        return ok('no SELinux, nothing to check')
    if subprocess.run(['getenforce'], capture_output=True, text=True).stdout.strip() != 'Enforcing':
        return ok('SELinux is not enforcing, nothing to check')
    out = subprocess.run(['getsebool', 'selinuxuser_execmod'], capture_output=True, text=True).stdout
    if out.strip().endswith('on'):
        return ok('SELinux allows what Wine needs (selinuxuser_execmod is on)')
    warn('SELinux blocks Wine ("failed to set protection" when a program starts). Run this once:')
    warn('    sudo setsebool -P selinuxuser_execmod 1')


def install(root, bottle):
    bdir = os.path.join(root, 'bottles', bottle)
    yml = os.path.join(bdir, 'bottle.yml')
    state_path = os.path.join(bdir, STATE)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    exes = find_exes(bdir)
    years = sorted({md_year(e) for e in exes if md_year(e)})
    say('Marvelous Designer in this bottle: ' + ', '.join(
        os.path.basename(os.path.dirname(e)) for e in exes))

    say('\n1. Wine version')
    runner = read_yaml_value(yml, 'Runner')
    ver = wine_version(os.path.join(root, 'runners', runner or ''))
    say(f'  bottle runner: {runner} (Wine {".".join(map(str, ver)) if ver else "?"})')
    if not years or years[-1] < NEW_MD:
        ok(f'Marvelous Designer {years[-1] if years else ""} runs on this Wine, nothing to change')
    elif ver and ver >= MIN_WINE:
        ok(f'Wine {ver[0]}.{ver[1]} is new enough for Marvelous Designer {years[-1]}')
    elif years[0] < NEW_MD:
        warn(f'Marvelous Designer {years[-1]} needs Wine 11.20 or newer, but this bottle also has')
        warn(f'Marvelous Designer {years[0]}, which is only tested on Wine 11.0. Keep them in separate bottles:')
        warn('in Bottles duplicate this bottle, uninstall the old version from the copy, and run this')
        warn('script on the copy (sh install.sh --bottle NEW_NAME). The runner was not changed.')
    else:
        say(f'  Marvelous Designer {years[-1]} crashes at start on Wine older than 11.20 ("stack overflow").')
        if ask(f'  Download Wine 11.20 ({RUNNER_NAME}) and switch this bottle to it?', True):
            if get_runner(root):
                state.setdefault('runner', runner)
                shutil.copy2(yml, yml + '.bak-' + TAG)
                set_yaml_value(yml, 'Runner', RUNNER_NAME)
                ok(f'bottle "{bottle}" now uses {RUNNER_NAME} (was {runner})')
        else:
            ok('runner left unchanged')

    say('\n2. Simulation on all CPU cores (vcomp140)')
    user_reg = os.path.join(bdir, 'user.reg')
    text = open(user_reg, encoding='utf-8', errors='surrogateescape').read()
    cur = reg_get(text, OVERRIDES, 'vcomp140')
    if cur == '"builtin"':
        ok('vcomp140 is already Wine\'s own (builtin)')
    else:
        if not os.path.exists(user_reg + '.bak-' + TAG):
            shutil.copy2(user_reg, user_reg + '.bak-' + TAG)
        state.setdefault('vcomp140', cur)
        text = reg_set(text, OVERRIDES, '"builtin"', 'vcomp140')
        open(user_reg, 'w', encoding='utf-8', errors='surrogateescape').write(text)
        ok(f'vcomp140 set to builtin (was {cur or "not set"})')

    say('\n3. Closed windows leave a black box (Wine 11.20)')
    ver = wine_version(os.path.join(root, 'runners', read_yaml_value(yml, 'Runner') or ''))
    if not ver or ver < MIN_WINE:
        ok('not needed on this Wine')
    else:
        cur = reg_get(text, X11, 'Decorated')
        if cur == '"N"':
            ok('Wine window decorations are already off')
        else:
            if not os.path.exists(user_reg + '.bak-' + TAG):
                shutil.copy2(user_reg, user_reg + '.bak-' + TAG)
            state.setdefault('decorated', cur)
            text = reg_set(text, X11, '"N"', 'Decorated')
            open(user_reg, 'w', encoding='utf-8', errors='surrogateescape').write(text)
            ok('Wine window decorations turned off (Marvelous Designer draws its own title bars)')

    say('\n4-5. Menu entries, icons, only one Marvelous Designer at a time')
    programs = find_programs(yml)
    for e in exes:
        if not any(os.path.normcase(program_exe(p, bdir)) == os.path.normcase(e) for p in programs.values()):
            warn(f'{os.path.basename(os.path.dirname(e))} is not added as a program in Bottles, skipped.')
            warn('  In Bottles: open the bottle -> Programs -> "..." -> Add program -> ' + os.path.basename(e))
    if programs:
        install_launcher(root, bottle, bdir, programs, state)

    say('\n6. SELinux')
    selinux_check()

    json.dump(state, open(state_path, 'w'), indent=1)
    say('\nDone. Start Marvelous Designer from the menu or the dock.')


def uninstall(root, bottle):
    bdir = os.path.join(root, 'bottles', bottle)
    yml = os.path.join(bdir, 'bottle.yml')
    state_path = os.path.join(bdir, STATE)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    if state.get('runner') and read_yaml_value(yml, 'Runner') == RUNNER_NAME:
        set_yaml_value(yml, 'Runner', state['runner'])
        ok('runner restored to ' + state['runner'])
    if 'vcomp140' in state:
        user_reg = os.path.join(bdir, 'user.reg')
        text = open(user_reg, encoding='utf-8', errors='surrogateescape').read()
        text = reg_set(text, OVERRIDES, state['vcomp140'], 'vcomp140')
        open(user_reg, 'w', encoding='utf-8', errors='surrogateescape').write(text)
        ok('vcomp140 restored to ' + (state['vcomp140'] or 'not set'))
    if 'decorated' in state:
        user_reg = os.path.join(bdir, 'user.reg')
        text = open(user_reg, encoding='utf-8', errors='surrogateescape').read()
        text = reg_set(text, X11, state['decorated'], 'Decorated')
        open(user_reg, 'w', encoding='utf-8', errors='surrogateescape').write(text)
        ok('Wine window decorations restored')
    uninstall_launcher(bottle, state)
    if os.path.exists(state_path):
        os.unlink(state_path)
    say(f'\nDone. The runner {RUNNER_NAME} can be deleted in Bottles if no other bottle uses it.')


def main():
    global ASSUME_YES
    ap = argparse.ArgumentParser(description='Wine for Marvelous Designer fixes for Bottles')
    ap.add_argument('--bottle', help='bottle name (default: the one with Marvelous Designer)')
    ap.add_argument('--uninstall', action='store_true')
    ap.add_argument('--yes', action='store_true', help='answer yes to questions')
    a = ap.parse_args()
    ASSUME_YES = a.yes

    say('Wine for Marvelous Designer')
    root = find_bottles_root()
    bottle = a.bottle
    if not bottle:
        found = find_app_bottles(root)
        if not found:
            die('no bottle with Marvelous Designer found. Install it in a Bottles bottle first, or use --bottle NAME.')
        if len(found) > 1:
            die('several Marvelous Designer bottles found: %s.\n'
                'Run it once for each: sh install.sh --bottle NAME' % ', '.join(found))
        bottle = found[0]
    bdir = os.path.join(root, 'bottles', bottle)
    if not os.path.isfile(os.path.join(bdir, 'bottle.yml')):
        die(f'bottle "{bottle}" not found in {root}/bottles')
    if not a.uninstall and not find_exes(bdir):
        die(f'Marvelous Designer was not found in bottle "{bottle}".')
    say(f'Bottle: {bottle}  ({root})')
    if bottle_running(bdir):
        die('Marvelous Designer (or something else in this bottle) is running. Close it and run this again.')
    if not a.uninstall and not ask('Apply the fixes to this bottle?', True):
        say('Nothing was changed.')
        return
    (uninstall if a.uninstall else install)(root, bottle)


if __name__ == '__main__':
    main()
