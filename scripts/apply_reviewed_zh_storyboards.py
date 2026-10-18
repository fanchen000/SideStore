"""Apply reviewed Simplified-Chinese strings to static iOS storyboards.

Why: UIKit's compiled tab titles and some static settings labels did not
honor zh-Hans .strings resources in the embedded SideStore framework.
Compile these localized *presentation text attributes* into nibs instead.
Does not change actions, outlets, identifiers, signing or authentication.

Dry run by default. Pass --write only in an isolated build checkout.
"""
import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    "Main": ROOT / "AltStore/iOS/Main.storyboard",
    "Settings": ROOT / "AltStore/Settings/Settings.storyboard",
    "Sources": ROOT / "AltStore/Sources/Sources.storyboard",
    "Authentication": ROOT / "AltStore/Authentication/Authentication.storyboard",
}
REQUIRED = {
    "Main": {
        "OZm-Le-7oJ.title", "Uwh-Bg-Ymq.title", "4gT-9u-k7y.title",
        "fVN-ed-uO1.title", "Q7y-bi-ncT.title",
    },
    "Settings": {"EbG-HB-IOn.text", "PCh-Up-aJJ.text"},
}


def translate(source: bytes, mapping: dict[str, str]):
    lines = source.decode("utf-8").splitlines(keepends=True)
    found = set()
    applied = []
    for key, value in mapping.items():
        identifier, dot, attr = key.rpartition(".")
        if not dot or attr not in ("title", "text", "placeholder"):
            continue
        if "\n" in value or "\r" in value:
            continue
        target = 'id="' + identifier + '"'
        matches = [i for i, line in enumerate(lines) if target in line]
        if len(matches) != 1:
            continue
        i = matches[0]
        expression = re.compile(r"(?<![\w-])" + re.escape(attr) + r'="[^"]*"')
        replaced, count = expression.subn(
            lambda _: attr + '="' + html.escape(value, quote=True) + '"',
            lines[i], count=1,
        )
        if count != 1:
            continue
        found.add(key)
        if replaced != lines[i]:
            applied.append(key)
            lines[i] = replaced
    return "".join(lines).encode("utf-8"), found, applied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    mapping = json.loads((ROOT / "scripts/zh_storyboard_map.json").read_text(encoding="utf-8"))
    totals = {}
    for name, source_path in SOURCES.items():
        original = source_path.read_bytes()
        edited, found, applied = translate(original, mapping[name])
        missing = sorted(REQUIRED.get(name, set()) - found)
        if missing:
            raise SystemExit(f"ERROR: required storyboard keys missing in {name}: {missing}")
        if args.write:
            source_path.write_bytes(edited)
        totals[name] = {"mapped": len(mapping[name]), "matched": len(found), "changed": len(applied)}
    if totals["Main"]["changed"] < 8 or totals["Settings"]["changed"] < 20:
        raise SystemExit("ERROR: too few translated iOS storyboard labels")
    print(json.dumps({"status": "STORYBOARD_ZH_APPLIED" if args.write else "STORYBOARD_ZH_DRY_RUN",
                      "counts": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
