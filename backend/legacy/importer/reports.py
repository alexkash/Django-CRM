"""Atomic private reports; neither temp nor final files are world readable."""

import json
import os
import tempfile
from pathlib import Path

from django.core.serializers.json import DjangoJSONEncoder


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".report-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(
                report,
                out,
                cls=DjangoJSONEncoder,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            out.write("\n")
        os.replace(name, path)
        path.chmod(0o600)
    finally:
        Path(name).unlink(missing_ok=True)
