# -*- coding: utf-8 -*-
"""Loader minimaliste : rend ``import mocaxextendpy.mocax_extend`` fonctionnel.
Linux ET Windows.

    from mocax_extend_loader import load_mocax_extend
    me = load_mocax_extend()  # cherche sous $MOCAX_ROOT, sinon ~/mocax

Natifs attendus (cf. INSTALLATION.pdf de la librairie) :
  Linux   : libtensorvals.so, libhommat.so          (+ libcblas du systeme)
  Windows : tensorvals.dll,   hommat.dll, gslcblas.dll (fournie dans shared_libs)

Sous Windows (Python >= 3.8), le PATH n'est PLUS utilise pour resoudre les
dependances d'une DLL : on enregistre donc les dossiers des DLL avec
os.add_dll_directory, sinon tensorvals.dll echoue avec "WinError 126" car
gslcblas.dll est introuvable.

La livraison contient Linux/ et Windows/ : le dossier de l'autre plateforme est
ignore pendant la recherche.
"""
import ctypes
import os
import re
import sys

from compat import IS_WINDOWS, default_mocax_root, walk_platform

_MODULE = None
LOADED_ROOTS = None          # racines utilisees : relues par les processus fils (spawn)
_DLL_DIR_HANDLES = []        # garder les handles de os.add_dll_directory vivants

if IS_WINDOWS:
    _REQUIRED = ("tensorvals", "hommat")
    _OPTIONAL = ("gslcblas",)          # dependance de tensorvals/hommat
else:
    _REQUIRED = ("libtensorvals.so", "libhommat.so")
    _OPTIONAL = ()


def _stem(name):
    """'libtensorvals.so.1' / 'tensorvals.dll' / 'TensorVals' -> 'tensorvals'."""
    b = os.path.basename(str(name)).lower()
    b = re.sub(r"(\.dll|\.so(\.\d+)*|\.dylib)$", "", b)
    if b.startswith("lib"):
        b = b[3:]
    return b


def _is_native(fname):
    f = fname.lower()
    return f.endswith(".dll") if IS_WINDOWS else (".so" in f)


def load_mocax_extend(search_roots=None, verbose=False):
    global _MODULE, LOADED_ROOTS
    if _MODULE is not None:
        return _MODULE

    roots = [r for r in (search_roots or [default_mocax_root()]) if r]

    # 1) package importable
    parent = _find(roots, lambda d, files: os.path.basename(d) == "mocaxextendpy"
                   and "__init__.py" in files, as_dir=True)
    if parent is None:
        raise RuntimeError("Package 'mocaxextendpy' introuvable sous %s" % roots)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    # 2) natifs (chemins absolus)
    natives = {}                                  # stem -> chemin absolu
    for name in _REQUIRED + _OPTIONAL:
        stem = _stem(name)
        p = _find(roots, lambda d, files, s=stem: any(
            _is_native(f) and _stem(f) == s for f in files), pick=stem)
        if p is None:
            if name in _REQUIRED:
                raise RuntimeError(
                    "Natif '%s' introuvable sous %s.%s" % (
                        name, roots, " Attendu : Windows/Library/shared_libs/"
                        "%s.dll" % stem if IS_WINDOWS else ""))
            if verbose:
                print("Avertissement : %s non trouvee (doit alors etre dans le PATH)." % name)
            continue
        natives[stem] = p
    lib_dirs = sorted({os.path.dirname(p) for p in natives.values()})

    # 3) Windows : declarer les dossiers des DLL (dependances inter-DLL)
    if IS_WINDOWS:
        _register_dll_dirs(lib_dirs)

    # 4) precharger tous les natifs des dossiers trouves, passes multiples
    #    (deps inter-bibliotheques : gslcblas avant tensorvals, OpenBLAS versionne...)
    pending = [os.path.join(d, f) for d in lib_dirs
               for f in sorted(os.listdir(d)) if _is_native(f)]
    # gslcblas en premier sous Windows
    pending.sort(key=lambda p: 0 if _stem(p) in [_stem(o) for o in _OPTIONAL] else 1)
    progress, last_err = True, {}
    while pending and progress:
        progress, still = False, []
        for p in pending:
            try:
                if IS_WINDOWS:
                    ctypes.CDLL(p)
                else:
                    ctypes.CDLL(p, mode=ctypes.RTLD_GLOBAL)
                progress = True
            except OSError as exc:
                last_err[p] = exc
                still.append(p)
        pending = still
    blocking = [p for p in pending if p in natives.values()]
    if blocking:
        raise OSError("Chargement de %s impossible : %s%s"
                      % (blocking[0], last_err[blocking[0]], _hint(last_err[blocking[0]])))

    # 5) import : rediriger les noms nus ('libtensorvals.so', 'tensorvals.dll',
    #    'tensorvals'...) vers les chemins absolus trouves -- fonctionne aussi si
    #    le package Python est la version Linux.
    _orig_load = ctypes.cdll.LoadLibrary

    def _redirect(n):
        return natives.get(_stem(n), n) if n else n

    _OrigCDLL = ctypes.CDLL

    class _RedirectCDLL(_OrigCDLL):               # cas ctypes.CDLL("...") direct
        def __init__(self, name, *a, **kw):
            _OrigCDLL.__init__(self, _redirect(name), *a, **kw)

    ctypes.cdll.LoadLibrary = lambda n: _orig_load(_redirect(n))
    ctypes.CDLL = _RedirectCDLL
    try:
        import mocaxextendpy.mocax_extend as me
    finally:
        ctypes.cdll.LoadLibrary = _orig_load
        ctypes.CDLL = _OrigCDLL

    _MODULE = me
    LOADED_ROOTS = list(roots)
    if verbose:
        print("mocaxextendpy importe depuis", parent)
        for s, p in natives.items():
            print("  natif %-10s : %s" % (s, p))
    return me


def _register_dll_dirs(dirs):
    for d in dirs:
        if hasattr(os, "add_dll_directory"):           # Python >= 3.8
            try:
                _DLL_DIR_HANDLES.append(os.add_dll_directory(d))
            except OSError:
                pass
        # pour Python 3.7 et les DLL chargees par nom nu
        if d.lower() not in os.environ.get("PATH", "").lower():
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _hint(exc):
    s = str(exc)
    if "193" in s:
        return ("\n -> WinError 193 : DLL 32 bits avec un Python 64 bits (ou "
                "l'inverse). Verifier `python -c \"import struct;print(struct."
                "calcsize('P')*8)\"` et recompiler les DLL (gcc 64 bits, MinGW-w64).")
    if "126" in s or "127" in s:
        return ("\n -> WinError 126/127 : une dependance est introuvable "
                "(gslcblas.dll, ou runtime MinGW libgcc_s_seh-1.dll / "
                "libwinpthread-1.dll). La placer dans le meme dossier que "
                "tensorvals.dll.")
    return ""


def _find(roots, match, as_dir=False, pick=None):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in walk_platform(root):
            if match(dirpath, files):
                if as_dir:
                    return os.path.dirname(dirpath)
                f = next(f for f in files if _is_native(f) and _stem(f) == pick)
                return os.path.join(dirpath, f)
    return None
