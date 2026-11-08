# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""Conftest for backup tests.

Automatically applies the 'backup' marker to all tests in this directory and subdirectories.
"""

import pytest
from pathlib import Path


def pytest_collection_modifyitems(config, items):
    """Auto-apply backup marker to all tests in this directory."""
    backupDir = Path(__file__).parent
    for item in items:
        itemPath = Path(item.fspath)
        if backupDir in itemPath.parents or itemPath.parent == backupDir:
            item.add_marker(pytest.mark.backup)
