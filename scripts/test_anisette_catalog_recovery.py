#!/usr/bin/env python3
"""Run the production AnisetteProvider with synthetic SideSign/SideStore mocks.

Compiles Swift offline. Never loads device identifiers, credentials, ADI files,
pairing files, Apple account information, or any network service.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "scripts/AnisetteRecoveryFixtures"
PROVIDER = ROOT / "SideStore/Core/Anisette/AnisetteProvider.swift"
FORBIDDEN = ("@example.com", "Apple ID", "ALTCertificate.p12")
assert PROVIDER.is_file() and all(
    (FIXTURES / name).is_file()
    for name in ("MockSideSign.swift", "MockSideStore.swift", "MockMain.swift")
)
for name in ("MockSideSign.swift", "MockSideStore.swift", "MockMain.swift"):
    fixture = (FIXTURES / name).read_text(encoding="utf8")
    assert not any(marker in fixture for marker in FORBIDDEN), "Fixture contains prohibited data"

with tempfile.TemporaryDirectory(prefix="prephone-anisette-") as tmp:
    dst = Path(tmp)
    for name in ("MockSideSign.swift", "MockSideStore.swift", "MockMain.swift"):
        shutil.copyfile(FIXTURES / name, dst / name)
    shutil.copyfile(PROVIDER, dst / "AnisetteProvider.swift")
    lib = dst / ("libSideSign.dylib" if sys.platform == "darwin" else "libSideSign.so")
    subprocess.run(
        ["swiftc", "-emit-module", "-emit-library", "-module-name", "SideSign",
         str(dst / "MockSideSign.swift"), "-o", str(lib)],
        cwd=dst, check=True, timeout=120,
    )
    exe = dst / "test-anisette"
    subprocess.run(
        ["swiftc", "-parse-as-library", "-I", str(dst), "-L", str(dst),
         "-lSideSign", str(dst / "MockSideStore.swift"),
         str(dst / "AnisetteProvider.swift"), str(dst / "MockMain.swift"),
         "-o", str(exe)],
        cwd=dst, check=True, timeout=120,
    )
    env = os.environ.copy()
    key = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    env[key] = str(dst)
    completed = subprocess.run(
        [str(exe)], cwd=dst, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30,
    )
    print(completed.stdout, end="")
    assert completed.stdout.count("PASS:") == 7
    assert "ANISI_CATALOG_RECOVERY_7_OF_7_PASS" in completed.stdout
