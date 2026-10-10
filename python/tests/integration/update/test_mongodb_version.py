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
Tests for the MongoDb CE version checks performed by `mas update`.

Covers numeric (rather than string) version comparison and early rejection of
updates that would skip a MongoDb major version (https://github.com/ibm-mas/cli/issues/1282).
"""

import os
import sys

import pytest

from mas.cli.update.app import parseVersionTuple
from utils import UpdateTestConfig, UpdateTestHelper

# Add test directory to path for utils import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MAS_INSTANCES = [{"metadata": {"name": "inst1"}, "status": {"versions": {"reconciled": "9.1.7"}}}]


def runMongoUpdate(tmpdir, currentVersion, targetVersion, extraArgs=None, expectSystemExit=False):
    config = UpdateTestConfig(
        prompt_handlers={},
        mongodb_namespaces=["mongoce"],
        mongodb_current_version=currentVersion,
        mongodb_target_version=targetVersion,
        mas_instances=MAS_INSTANCES,
        argv=["--catalog", "v9-260129-amd64", "--no-confirm"] + (extraArgs or []),
        expect_system_exit=expectSystemExit,
        expected_exit_code=1 if expectSystemExit else None,
    )
    helper = UpdateTestHelper(tmpdir, config)
    helper.run_update_test()
    return helper


@pytest.mark.parametrize(
    "version, expected",
    [
        ("8.0.12", (8, 0, 12)),
        ("8.0.4", (8, 0, 4)),
        ("10.0.1", (10, 0, 1)),
        ("v7.0", (7, 0, 0)),
        ("6.0.5-ent", (6, 0, 5)),
        ("7.0.22+build.1", (7, 0, 22)),
        ("not-a-version", None),
        (None, None),
    ],
)
def test_parse_version_tuple(version, expected):
    """
    Given a MongoDb version string
    When it is parsed for comparison
    Then a zero-padded tuple of integers is returned (or None when it is not a version)
    """
    assert parseVersionTuple(version) == expected


def test_parse_version_tuple_compares_numerically():
    """
    Given versions whose string ordering differs from their numeric ordering
    When the parsed tuples are compared
    Then the numeric ordering is used
    """
    assert parseVersionTuple("8.0.12") > parseVersionTuple("8.0.4")
    assert parseVersionTuple("10.0.0") > parseVersionTuple("9.0.0")
    assert parseVersionTuple("7.0") == parseVersionTuple("7.0.0")


def test_mongo_patch_update_allowed(tmpdir):
    """
    Given MongoDb 8.0.4 is installed and the target catalog provides 8.0.12
    When mas update runs non-interactively
    Then the update is not treated as a downgrade and the pipeline is launched
    """
    helper = runMongoUpdate(tmpdir, "8.0.4", "8.0.12")
    assert helper.mocks["launch_update_pipeline"].called
    assert helper.app.getParam("mongodb_namespace") == "mongoce"
    assert helper.app.getParam("mongodb_version") == "8.0.12"
    assert helper.app.getParam("mongodb_action") == ""


def test_mongo_downgrade_rejected(tmpdir):
    """
    Given MongoDb 8.0.12 is installed and the target catalog provides 8.0.4
    When mas update runs non-interactively
    Then the update fails before the pipeline is launched
    """
    helper = runMongoUpdate(tmpdir, "8.0.12", "8.0.4", expectSystemExit=True)
    assert not helper.mocks["launch_update_pipeline"].called


def test_mongo_single_major_update_with_approval(tmpdir):
    """
    Given MongoDb 7.0.22 is installed and the target catalog provides 8.0.12
    When mas update runs non-interactively with --mongodb-v8-upgrade
    Then the MongoDb install action is set and the pipeline is launched
    """
    helper = runMongoUpdate(tmpdir, "7.0.22", "8.0.12", extraArgs=["--mongodb-v8-upgrade"])
    assert helper.mocks["launch_update_pipeline"].called
    assert helper.app.getParam("mongodb_action") == "install"


def test_mongo_single_major_update_without_approval_rejected(tmpdir):
    """
    Given MongoDb 7.0.22 is installed and the target catalog provides 8.0.12
    When mas update runs with --no-confirm but without --mongodb-v8-upgrade
    Then the update fails before the pipeline is launched
    """
    helper = runMongoUpdate(tmpdir, "7.0.22", "8.0.12", expectSystemExit=True)
    assert not helper.mocks["launch_update_pipeline"].called


@pytest.mark.parametrize(
    "currentVersion, targetVersion, approvalFlag",
    [
        ("4.4.21", "6.0.12", "--mongodb-v6-upgrade"),
        ("5.0.23", "7.0.22", "--mongodb-v7-upgrade"),
        ("6.0.12", "8.0.12", "--mongodb-v8-upgrade"),
    ],
)
def test_mongo_multi_major_jump_rejected(tmpdir, caplog, currentVersion, targetVersion, approvalFlag):
    """
    Given MongoDb is installed at a version more than one major behind the target catalog
    When mas update runs, even with the major version approval flag
    Then the update fails early, naming the intermediate major version that is required
    """
    helper = runMongoUpdate(tmpdir, currentVersion, targetVersion, extraArgs=[approvalFlag], expectSystemExit=True)
    assert not helper.mocks["launch_update_pipeline"].called

    requiredMajor = int(currentVersion.split(".")[0]) + 1
    output = caplog.text
    assert f"cannot be directly updated to version {targetVersion}" in output
    assert f"intermediate catalog that provides MongoDB v{requiredMajor}" in output
