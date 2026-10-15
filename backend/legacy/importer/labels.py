"""Read literal PHP language labels as data; never load or execute PHP."""

import re

from .reader import file_hash, safe_file

_STRING = r"""(?:'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")"""
_LABEL = re.compile(
    r"""(?P<key>['"]LBL_[A-Za-z0-9_]+['"])\s*(?:\]\s*=|=>)\s*(?P<value>"""
    + _STRING
    + r""")"""
)


def unquote(token):
    text = token[1:-1]
    if token[0] == "'":
        return re.sub(r"\\([\\'])", r"\1", text)
    escaped = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\", "$": "$"}
    return re.sub(r'\\([nrt"\\$])', lambda m: escaped[m.group(1)], text)


def source_labels(reader):
    result = {}
    files = reader.manifest.get("metadata_files", [])
    for entry in sorted(files, key=lambda x: ("en_us" in x["path"], x["path"])):
        if not entry["path"].endswith(".php"):
            continue
        path = safe_file(reader.root.parent / "metadata", entry["path"])
        if file_hash(path) != entry["sha256"]:
            raise ValueError("Source metadata hash mismatch")
        parts = path.parts
        module = parts[parts.index("modules") + 1] if "modules" in parts else ""
        for match in _LABEL.finditer(path.read_text(encoding="utf-8")):
            result[(module, unquote(match.group("key")))] = unquote(
                match.group("value")
            )
    return result


def source_lists(reader):
    """Extract only flat literal dropdown arrays; expressions are never evaluated."""
    output = {}
    prefix = re.compile(
        r"\$app_list_strings\s*\[\s*(?P<key>" + _STRING + r")\s*\]\s*=\s*array\s*\("
    )
    entries = sorted(
        reader.manifest.get("metadata_files", []),
        key=lambda x: ("en_us" in x["path"].lower(), x["path"]),
    )
    for entry in entries:
        if (
            not entry["path"].endswith(".php")
            or "language" not in entry["path"].lower()
        ):
            continue
        path = safe_file(reader.root.parent / "metadata", entry["path"])
        if file_hash(path) != entry["sha256"]:
            raise ValueError("Source metadata hash mismatch")
        text = path.read_text(encoding="utf-8")
        for match in prefix.finditer(text):
            pos = match.end()
            items = []
            while True:
                pos = re.compile(r"\s*").match(text, pos).end()
                if text[pos : pos + 1] == ")":
                    output[unquote(match.group("key"))] = items
                    break
                key = re.compile(_STRING).match(text, pos)
                if not key:
                    break
                pos = re.compile(r"\s*").match(text, key.end()).end()
                if text[pos : pos + 2] != "=>":
                    break
                pos = re.compile(r"\s*").match(text, pos + 2).end()
                value = re.compile(_STRING).match(text, pos)
                if not value:
                    break
                code = unquote(key.group())
                if code:
                    items.append({"value": code, "label": unquote(value.group())})
                pos = re.compile(r"\s*").match(text, value.end()).end()
                if text[pos : pos + 1] == ",":
                    pos += 1
                elif text[pos : pos + 1] != ")":
                    break
    return output
