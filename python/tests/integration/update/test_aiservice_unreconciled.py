#!/usr/bin/env python
# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""
Tests for `mas update` with AI Service instances that have never reconciled (https://github.com/ibm-mas/cli/issues/1944).
"""

import os
import sys

import pytest

from utils import UpdateTestConfig, UpdateTestHelper

# Add test directory to path for utils import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MAS_INSTANCES = [{"metadata": {"name": "inst1"}, "status": {"versions": {"reconciled": "9.1.7"}}}]
RECONCILED_AISERVICE = {"metadata": {"name": "aisvc1"}, "status": {"versions": {"reconciled": "9.1.2"}}}


@pytest.mark.parametrize(
    "unreconciled",
    [
        {"metadata": {"name": "aisvc2"}},
        {"metadata": {"name": "aisvc2"}, "status": None},
        {"metadata": {"name": "aisvc2"}, "status": {}},
        {"metadata": {"name": "aisvc2"}, "status": {"versions": {}}},
    ],
)
def test_unreconciled_aiservice_skipped(tmpdir, caplog, unreconciled):
    """
    Given one reconciled and one never-reconciled AI Service instance
    When mas update runs non-interactively
    Then the unreconciled instance is skipped with a warning and the update proceeds for the reconciled one
    """
    config = UpdateTestConfig(
        prompt_handlers={},
        mas_instances=MAS_INSTANCES,
        aiservice_instances=[RECONCILED_AISERVICE, unreconciled],
        argv=["--catalog", "v9-260129-amd64", "--no-confirm"],
    )
    helper = UpdateTestHelper(tmpdir, config)
    helper.run_update_test()

    assert helper.mocks["launch_update_pipeline"].called
    assert helper.app.getParam("aiservice_instance_ids") == "aisvc1"
    assert "AI Service instance 'aisvc2' has not reconciled" in caplog.text


def test_only_unreconciled_aiservice_with_mas(tmpdir, caplog):
    """
    Given a MAS instance and only a never-reconciled AI Service instance
    When mas update runs non-interactively
    Then the AI Service instance is skipped and the catalog update still proceeds
    """
    config = UpdateTestConfig(
        prompt_handlers={},
        mas_instances=MAS_INSTANCES,
        aiservice_instances=[{"metadata": {"name": "aisvc2"}, "status": {"conditions": []}}],
        argv=["--catalog", "v9-260129-amd64", "--no-confirm"],
    )
    helper = UpdateTestHelper(tmpdir, config)
    helper.run_update_test()

    assert helper.mocks["launch_update_pipeline"].called
    assert helper.app.getParam("aiservice_instance_ids") == ""
    assert "has not reconciled" in caplog.text


def test_only_unreconciled_aiservice_without_mas(tmpdir):
    """
    Given no MAS instances and only a never-reconciled AI Service instance
    When mas update runs non-interactively
    Then there is nothing to update and the command fails cleanly rather than crashing
    """
    config = UpdateTestConfig(
        prompt_handlers={},
        mas_instances=[],
        aiservice_instances=[{"metadata": {"name": "aisvc2"}}],
        argv=["--catalog", "v9-260129-amd64", "--no-confirm"],
        expect_system_exit=True,
        expected_exit_code=1,
    )
    helper = UpdateTestHelper(tmpdir, config)
    helper.run_update_test()

    assert not helper.mocks["launch_update_pipeline"].called
