import io
import tarfile

import pytest
from fastapi import HTTPException

from app.task_bundles import _safe_extract


def test_safe_extract_rejects_parent_traversal(tmp_path):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        payload = b"unsafe"
        member = tarfile.TarInfo("../outside.txt")
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))
    archive.seek(0)

    with tarfile.open(fileobj=archive, mode="r:gz") as tar, pytest.raises(HTTPException) as exc:
        _safe_extract(tar, tmp_path)

    assert "unsafe paths" in exc.value.detail


def test_safe_extract_rejects_links(tmp_path):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc/passwd"
        tar.addfile(member)
    archive.seek(0)

    with tarfile.open(fileobj=archive, mode="r:gz") as tar, pytest.raises(HTTPException) as exc:
        _safe_extract(tar, tmp_path)

    assert "cannot contain links" in exc.value.detail
