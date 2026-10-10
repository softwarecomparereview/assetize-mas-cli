# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""Conftest for restore tests.

Automatically applies the 'restore' marker to all tests in this directory and subdirectories.
"""

import pytest
from pathlib import Path


def pytest_collection_modifyitems(config, items):
    """Auto-apply restore marker to all tests in this directory."""
    restoreDir = Path(__file__).parent
    for item in items:
        itemPath = Path(item.fspath)
        if restoreDir in itemPath.parents or itemPath.parent == restoreDir:
            item.add_marker(pytest.mark.restore)
