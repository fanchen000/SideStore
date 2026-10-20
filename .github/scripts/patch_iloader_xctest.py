"""Isolated iLoader 2.3.10 build patch: preserve an equal XCTest bundle ID.

Only touches the staging checkout of iLoader and a hash-pinned public Rust
crate. No device, account, certificates, profiles or installation operations.
"""
from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path, PurePosixPath
import tarfile
from urllib.request import urlopen

CRATE_URL = "https://static.crates.io/crates/isideload/isideload-0.4.6.crate"
CRATE_SHA256 = "473bde4da71c72bcf5f1cf77acfffdf4b879b65ef989c19f8cb4c3e9ea758a76"
ORIGINAL = '''                if !(id.starts_with(main_app_bundle_id) && id.len() > main_app_bundle_id.len()) {
                    bail!(SideloadError::InvalidBundle(format!(
                        "Extension {} is not part of the main app bundle identifier: {}",
                        ext.bundle_name().unwrap_or("Unknown"),
                        id
                    )));
                } else {
                    ext.set_bundle_identifier(&format!(
                        "{}{}",
                        main_app_id_str,
                        &id[main_app_bundle_id.len()..]
                    ));
                }'''
REPLACEMENT = '''                if id == main_app_bundle_id
                    && ext.bundle_dir.extension().and_then(|x| x.to_str()) == Some("xctest")
                {
                    // XCTest's bundle identifier must equal its host Runner ID.
                    // Never append a second team suffix or create an extra ID.
                    ext.set_bundle_identifier(main_app_id_str);
                } else if id.starts_with(main_app_bundle_id)
                    && id.len() > main_app_bundle_id.len()
                {
                    ext.set_bundle_identifier(&format!(
                        "{}{}",
                        main_app_id_str,
                        &id[main_app_bundle_id.len()..]
                    ));
                } else {
                    bail!(SideloadError::InvalidBundle(format!(
                        "Extension {} is not part of the main app bundle identifier: {}",
                        ext.bundle_name().unwrap_or("Unknown"),
                        id
                    )));
                }'''


def transform(bundle_id: str, nested_id: str, ext_type: str, team: str) -> tuple[str, str]:
    """Test-vector model of the Rust patch, not a signer."""
    final_id = bundle_id + "." + team
    if nested_id == bundle_id and ext_type == "xctest":
        return final_id, final_id
    if nested_id.startswith(bundle_id) and len(nested_id) > len(bundle_id):
        return final_id, final_id + nested_id[len(bundle_id):]
    raise ValueError("invalid child bundle")


def apply(root: Path, archive_bytes: bytes) -> None:
    if hashlib.sha256(archive_bytes).hexdigest() != CRATE_SHA256:
        raise ValueError("Pinned isideload crate SHA256 mismatch")
    cargo = root / "src-tauri" / "Cargo.toml"
    if not cargo.is_file():
        raise ValueError("iLoader Cargo.toml missing")
    contents = cargo.read_text(encoding="utf8")
    old_dep = 'isideload = { version = "0.4.6", features = ["fs-storage"] }'
    new_dep = 'isideload = { path = "vendor/isideload", features = ["fs-storage"] }'
    if contents.count(old_dep) != 1:
        raise ValueError("Unexpected iLoader dependency")
    dest = root / "src-tauri" / "vendor" / "isideload"
    if dest.exists():
        raise ValueError("Refusing to overwrite existing vendor")
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 250:
            raise ValueError("Unexpectedly large Rust crate")
        files = []
        for item in members:
            p = PurePosixPath(item.name)
            if (not item.isfile() and not item.isdir()) or p.is_absolute() or ".." in p.parts:
                raise ValueError("Unsafe crate member")
            if len(p.parts) < 2 or p.parts[0] != "isideload-0.4.6":
                raise ValueError("Unexpected crate layout")
            if item.isfile():
                data = archive.extractfile(item).read()
                files.append((Path(*p.parts[1:]), data))
    src_name = Path("src") / "sideload" / "application.rs"
    original_source = dict(files).get(src_name, b"").decode("utf8")
    if original_source.count(ORIGINAL) != 1:
        raise ValueError("Rust rewrite logic does not match pinned crate")
    for path, data in files:
        final = dest / path
        final.parent.mkdir(parents=True, exist_ok=True)
        if path == src_name:
            data = original_source.replace(ORIGINAL, REPLACEMENT).encode("utf8")
        final.write_bytes(data)
    cargo.write_text(contents.replace(old_dep, new_dep), encoding="utf8")
    print("XCTEST_EQUAL_ID_REWRITE_PATCHED_NO_APPLE_ACCOUNT_ACTION")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--iloader-root", type=Path, required=True)
    p.add_argument("--crate-file", type=Path)
    args = p.parse_args()
    if args.crate_file:
        binary = args.crate_file.read_bytes()
    else:
        with urlopen(CRATE_URL, timeout=30) as response:
            binary = response.read(7_000_000)
    apply(args.iloader_root.resolve(), binary)


if __name__ == "__main__":
    main()
