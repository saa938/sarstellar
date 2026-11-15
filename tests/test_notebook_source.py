"""A downloaded notebook must load the exported engine without an unpublished Git branch."""

import ast
import base64
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import nbformat
import pytest

from sarstellar import notebook


def _export():
    return nbformat.reads(notebook.build([-119.2, 48.15, -119.1, 48.22],
                                       ["https://example.test/granule.h5"],
                                       ("2026-07-13", "2026-09-11")).decode(), as_version=4)


def _tagged(nb, tag):
    return next(cell.source for cell in nb.cells if tag in cell.metadata.get("tags", []))


def _constants(source):
    return {node.targets[0].id: ast.literal_eval(node.value)
            for node in ast.parse(source).body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)}


def test_embedded_source_matches_installed_python_files_and_has_provenance():
    nb = _export()
    nbformat.validate(nb)
    values = _constants(_tagged(nb, "embedded-source"))
    archive = base64.b64decode(values["SOURCE_ARCHIVE_B64"])
    assert hashlib.sha256(archive).hexdigest() == values["SOURCE_SHA256"]
    assert nb.metadata.sarstellar.source_sha256 == values["SOURCE_SHA256"]
    root = Path(notebook.__file__).resolve().parent
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        expected = {"sarstellar/" + p.relative_to(root).as_posix(): p.read_bytes()
                    for p in root.rglob("*.py") if not p.is_symlink()}
        assert set(package.namelist()) == set(expected)
        assert all(package.read(name) == content for name, content in expected.items())
    assert len(archive) < 150_000
    assert archive == notebook._source_archive()  # stable checksum for the same source


def test_setup_imports_embedded_engine_offline_with_existing_dependencies(tmp_path):
    nb = _export()
    setup = _tagged(nb, "embedded-source")
    script = setup + (
        '\nprint("SOURCE_CHECK", Path(sys.modules["sarstellar"].__file__)'
        '.is_relative_to(SOURCE_ROOT))\n'
    )
    run = subprocess.run([sys.executable, "-"], input=script, cwd=tmp_path, text=True,
                         capture_output=True, timeout=30, check=True)
    assert "SOURCE_CHECK True" in run.stdout
    assert "Loaded embedded SARstellar engine" in run.stdout


def test_requirements_and_parameters_are_preserved_without_credentials():
    nb = _export()
    requirements = nb.metadata.sarstellar.runtime_requirements
    assert "numpy" in requirements and "nbformat" in requirements
    assert not any("extra" in requirement or "git+" in requirement for requirement in requirements)
    assert "git+https://github.com" not in _tagged(nb, "install-dependencies")
    source = "\n".join(c.source for c in nb.cells)
    assert "2026-07-13" in source and "2026-09-11" in source
    assert "https://example.test/granule.h5" in source
    assert str(Path(notebook.__file__).resolve().parent) not in json.dumps(nb)


@pytest.mark.parametrize("name", ["../bad.py", "/bad.py", "sarstellar/../../bad.py",
                                 "sarstellar\\bad.py", "sarstellar/D:/bad.py",
                                 "sarstellar/secret.env"])
def test_setup_rejects_unsafe_archive_paths(name):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        member = zipfile.ZipInfo()
        member.filename = name  # preserve a raw backslash even on Windows
        archive.writestr(member, "pass")
    blob = stream.getvalue()
    namespace = {"SOURCE_SHA256": hashlib.sha256(blob).hexdigest(),
                 "SOURCE_ARCHIVE_B64": base64.b64encode(blob).decode()}
    with pytest.raises(ValueError, match="Unsafe path"):
        exec(notebook._BOOTSTRAP, namespace)  # noqa: S102 - exercise exported notebook setup
    namespace["SOURCE_DIR_HANDLE"].cleanup()
