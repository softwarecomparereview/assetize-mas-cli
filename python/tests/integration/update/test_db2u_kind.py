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
Tests for db2u_kind handling in `mas update` (https://github.com/ibm-mas/cli/issues/2579).

The ibm.mas_devops db2 role defaults DB2U_KIND to db2ucluster and fails with "DB2U_KIND MISMATCH"
when the existing deployment is a Db2uInstance, so the update must pass the detected kind through.
"""

import os
import sys

import pytest

from mas.cli.update.app import UpdateApp
from mas.cli.update.argParser import updateArgParser
from utils import UpdateTestConfig, UpdateTestHelper

# Add test directory to path for utils import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MAS_INSTANCES = [{"metadata": {"name": "inst1"}, "status": {"versions": {"reconciled": "9.1.7"}}}]


def runDb2Update(tmpdir, resourceKind, extraArgs=None, namespaces=None):
    config = UpdateTestConfig(
        prompt_handlers={},
        db2u_namespaces=namespaces if namespaces is not None else ["db2u"],
        db2u_resource_kind=resourceKind,
        mas_instances=MAS_INSTANCES,
        argv=["--catalog", "v9-260129-amd64", "--no-confirm"] + (extraArgs or []),
    )
    helper = UpdateTestHelper(tmpdir, config)
    helper.run_update_test()
    return helper


@pytest.mark.parametrize("resourceKind, expectedKind", [("Db2uInstance", "db2uinstance"), ("Db2uCluster", "db2ucluster")])
def test_db2u_kind_detected_and_passed_to_pipeline(tmpdir, resourceKind, expectedKind):
    """
    Given the cluster has Db2u resources of a single kind
    When mas update runs non-interactively without --db2u-kind
    Then db2u_kind is set to the detected kind and passed to the update PipelineRun
    """
    helper = runDb2Update(tmpdir, resourceKind)
    assert helper.app.getParam("db2u_kind") == expectedKind
    launchParams = helper.mocks["launch_update_pipeline"].call_args.kwargs["params"]
    assert launchParams["db2u_kind"] == expectedKind


def test_db2u_kind_not_set_without_db2(tmpdir):
    """
    Given the cluster has no Db2u resources
    When mas update runs non-interactively
    Then db2u_kind is left unset
    """
    helper = runDb2Update(tmpdir, "Db2uCluster", namespaces=[])
    assert helper.app.getParam("db2u_kind") == ""


def test_db2u_kind_flag_overrides_detection(tmpdir):
    """
    Given the cluster has Db2uCluster resources
    When mas update runs with --db2u-kind db2uinstance
    Then the explicit value is preserved and passed to the update PipelineRun
    """
    helper = runDb2Update(tmpdir, "Db2uCluster", extraArgs=["--db2u-kind", "db2uinstance"])
    assert helper.app.getParam("db2u_kind") == "db2uinstance"
    launchParams = helper.mocks["launch_update_pipeline"].call_args.kwargs["params"]
    assert launchParams["db2u_kind"] == "db2uinstance"


def test_db2u_kind_flag_parsed():
    """
    Given the update argument parser
    When --db2u-kind is provided with a valid value
    Then it is parsed into db2u_kind, and invalid values are rejected
    """
    args = updateArgParser.parse_args(["--catalog", "v9-260129-amd64", "--db2u-kind", "db2uinstance"])
    assert args.db2u_kind == "db2uinstance"

    args = updateArgParser.parse_args(["--catalog", "v9-260129-amd64"])
    assert args.db2u_kind is None

    with pytest.raises(SystemExit):
        updateArgParser.parse_args(["--catalog", "v9-260129-amd64", "--db2u-kind", "db2"])


def test_set_db2u_kind_uses_target_namespace():
    """
    Given Db2uCluster resources in one namespace and Db2uInstance resources in another
    When the Db2u kind is determined for the namespace selected for update
    Then only the resources in that namespace are considered
    """
    app = UpdateApp()
    instances = [
        {"metadata": {"name": "c1", "namespace": "db2-legacy"}},
        {"metadata": {"name": "i1", "namespace": "db2u"}},
    ]
    kinds = ["Db2uCluster", "Db2uInstance"]

    app.setParam("db2_namespace", "db2u")
    app.setDb2uKind(instances, kinds)
    assert app.getParam("db2u_kind") == "db2uinstance"

    app.setParam("db2u_kind", "")
    app.setParam("db2_namespace", "db2-legacy")
    app.setDb2uKind(instances, kinds)
    assert app.getParam("db2u_kind") == "db2ucluster"


def test_set_db2u_kind_prefers_cluster_when_both_in_namespace():
    """
    Given both a Db2uCluster and a Db2uInstance exist in the target namespace
    When the Db2u kind is determined
    Then db2ucluster is used, matching the detection logic of the ibm.mas_devops db2 role
    """
    app = UpdateApp()
    instances = [
        {"metadata": {"name": "c1", "namespace": "db2u"}},
        {"metadata": {"name": "i1", "namespace": "db2u"}},
    ]
    app.setParam("db2_namespace", "db2u")
    app.setDb2uKind(instances, ["Db2uCluster", "Db2uInstance"])
    assert app.getParam("db2u_kind") == "db2ucluster"
