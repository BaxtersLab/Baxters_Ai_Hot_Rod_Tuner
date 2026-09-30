"""HRT is MIT: the LICENSE file, the packaged copyright and the README agree.

The public repository had no LICENSE file, its README said MIT, and the
installed package's copyright file said Apache-2.0. The operator ruled MIT
(2026-09-30). These pin all three to one licence, one text and one holder.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENSE = ROOT / "LICENSE"
COPYRIGHT = ROOT / "packaging" / "usr" / "share" / "doc" / "baxters-hot-rod-tuner" / "copyright"
MIT_CLAUSES = (
    "Permission is hereby granted, free of charge",
    "The above copyright notice and this permission notice shall be included",
    'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND',
)


def _words(text: str) -> str:
    return " ".join(text.split())


def _stanzas() -> list[dict[str, str]]:
    """The DEP-5 paragraphs of the packaged copyright, as field -> value."""
    out = []
    for block in re.split(r"\n\s*\n", COPYRIGHT.read_text(encoding="utf-8")):
        fields: dict[str, str] = {}
        key = None
        for line in block.splitlines():
            if line.startswith((" ", "\t")) and key:
                cont = line[1:]
                fields[key] += "\n" + ("" if cont == "." else cont)   # " ." is a blank line
            elif ":" in line:
                key, _, value = line.partition(":")
                fields[key] = value.strip()
        if fields:
            out.append(fields)
    return out


def test_the_licence_file_is_mit():
    text = LICENSE.read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    for clause in MIT_CLAUSES:
        assert clause in _words(text), clause


def test_the_packaged_copyright_is_the_same_mit_text_and_holder():
    stanzas = _stanzas()
    files = next(s for s in stanzas if s.get("Files") == "*")
    assert files["License"] == "MIT"
    body = next(s for s in stanzas if "Files" not in s and s.get("License", "").split("\n")[0] == "MIT")
    licence = LICENSE.read_text(encoding="utf-8")
    grant = licence[licence.index("Permission is hereby granted"):]
    assert _words(body["License"].split("\n", 1)[1]) == _words(grant)
    year, holder = re.search(r"^Copyright \(c\) (\d{4}) (.+)$", licence, re.M).groups()
    assert files["Copyright"] == f"{year} {holder.strip()}"


def test_no_other_licence_is_claimed_for_this_work():
    text = COPYRIGHT.read_text(encoding="utf-8")
    assert "Apache" not in text
    # The python3-gi note names LGPL on purpose: it is about a dependency.
    assert not re.search(r"^License: (?!MIT\b)", text, re.M)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = re.search(r"^## License\s*\n+(.+)$", readme, re.M)
    assert section and section.group(1).startswith("MIT")
