# -*- coding: utf-8 -*-
"""Compatibilite Linux / Windows : tout ce qui depend de l'OS est ICI.

  IS_WINDOWS            : True sous Windows
  default_mocax_root()  : variable d'env MOCAX_ROOT, sinon ~/mocax
  mp_context()          : "fork" si disponible (Linux), sinon "spawn" (Windows)
  clamp_workers(n)      : Windows plafonne ProcessPoolExecutor a 61 processus
  limit_blas_threads()  : 1 thread BLAS par processus quand on parallelise
"""
import multiprocessing as mp
import os
import sys

IS_WINDOWS = sys.platform.startswith("win") or os.name == "nt"

# Dossier de la distribution MoCaX a IGNORER sur cette plateforme (la livraison
# contient Linux/ et Windows/ cote a cote : ne jamais charger le mauvais).
OTHER_PLATFORM_DIR = "linux" if IS_WINDOWS else "windows"

_WIN_MAX_WORKERS = 61


def default_mocax_root():
    env = os.environ.get("MOCAX_ROOT")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), "mocax")


def mp_context():
    """fork (Linux, comportement historique) sinon spawn (Windows, macOS)."""
    methods = mp.get_all_start_methods()
    return mp.get_context("fork" if "fork" in methods else "spawn")


def clamp_workers(n):
    n = max(1, int(n or 1))
    if IS_WINDOWS and n > _WIN_MAX_WORKERS:
        print("Windows : n_workers ramene de %d a %d (limite de l'OS)." % (n, _WIN_MAX_WORKERS))
        n = _WIN_MAX_WORKERS
    return n


def limit_blas_threads():
    """A appeler AVANT l'import de numpy : herite par les processus fils."""
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(v, "1")


def walk_platform(root):
    """os.walk qui saute le dossier de l'AUTRE plateforme (Linux/ sous Windows...)."""
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() != OTHER_PLATFORM_DIR]
        yield dirpath, dirs, files
