import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory and change to it for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_cwd = os.getcwd()
        os.chdir(tmpdir)
        yield Path(tmpdir)
        os.chdir(old_cwd)
