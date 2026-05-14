from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fa.task import storage


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    with patch.object(storage, "find_project_root", return_value=tmp_path):
        yield tmp_path
