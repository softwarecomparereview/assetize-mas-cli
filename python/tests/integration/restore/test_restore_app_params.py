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

"""Integration tests for `mas restore` application parameters.

Covers the Db2 database name (ibm-mas/cli#2513) and the workspace ID used to name restored
application PVCs (ibm-mas/cli#2547).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.backup_restore_test_helper import BackupRestoreTestConfig, runBackupRestoreTest  # noqa: E402

BASE_ARGV = [
    "--instance-id",
    "inst1",
    "--restore-version",
    "20260101-000000",
    "--backup-storage-class",
    "ibmc-file-gold-gid",
    "--backup-storage-access-mode",
    "ReadWriteMany",
    "--exclude-dro",
    "--no-confirm",
]

MANAGE_ARGV = ["--restore-manage-app", "--restore-manage-include-pvc", "--restore-manage-db"]
FACILITIES_ARGV = ["--restore-facilities-app", "--restore-facilities-include-pvc", "--restore-facilities-db"]


def test_restore_non_interactive_without_optional_app_params():
    """
    Given a non-interactive restore of Manage and Facilities without workspace ID or dbname flags
    When the restore pipeline is launched
    Then no workspace ID or dbname params are sent, so the pipeline derives them from the backup
    """
    result = runBackupRestoreTest(BackupRestoreTestConfig(command="restore", argv=BASE_ARGV + MANAGE_ARGV + FACILITIES_ARGV))

    params = result.launchParams
    assert params is not None, "launchRestorePipeline was not called"
    assert params["mas_instance_id"] == "inst1"
    assert params["restore_version"] == "20260101-000000"
    assert params["restore_manage_app"] == "true"
    assert params["restore_manage_db"] == "true"
    assert params["restore_facilities_app"] == "true"
    for key in ["manage_workspace_id", "manage_db2_dbname", "facilities_workspace_id", "facilities_db2_dbname"]:
        assert key not in params, f"{key} should not be set"


def test_restore_non_interactive_with_workspace_and_dbname():
    """
    Given a non-interactive restore with workspace ID and Db2 database name flags for Manage and Facilities
    When the restore pipeline is launched
    Then the workspace IDs and database names are passed through as pipeline params
    """
    argv = (
        BASE_ARGV
        + MANAGE_ARGV
        + ["--manage-workspace-id", "ws1", "--manage-db2-dbname", "MAXDB"]
        + FACILITIES_ARGV
        + ["--facilities-workspace-id", "ws2", "--facilities-db2-dbname", "TRIDB"]
    )
    result = runBackupRestoreTest(BackupRestoreTestConfig(command="restore", argv=argv))

    params = result.launchParams
    assert params is not None, "launchRestorePipeline was not called"
    assert params["manage_workspace_id"] == "ws1"
    assert params["manage_db2_dbname"] == "MAXDB"
    assert params["facilities_workspace_id"] == "ws2"
    assert params["facilities_db2_dbname"] == "TRIDB"


def _interactivePromptHandlers(workspaceId: str, dbName: str) -> dict:
    return {
        ".*Proceed with this cluster.*": lambda msg: "y",
        ".*Instance ID.*": lambda msg: "inst1",
        ".*Set the backup version to use for this restore.*": lambda msg: "20260101-000000",
        ".*Use the auto-detected storage classes.*": lambda msg: "y",
        ".*Enter PVC storage size.*": lambda msg: "20Gi",
        ".*use the storage classes from backup.*": lambda msg: "y",
        ".*Include MongoDB in restore.*": lambda msg: "n",
        ".*install Grafana instance.*": lambda msg: "n",
        ".*restore SLS instance from backup.*": lambda msg: "y",
        ".*change SLS Domain.*": lambda msg: "n",
        ".*install DRO instance.*": lambda msg: "n",
        ".*change the MAS domain.*": lambda msg: "n",
        ".*restore Suite-level SLSCfg from backup.*": lambda msg: "y",
        ".*change the SLS URL.*": lambda msg: "n",
        ".*restore Suite-level BASCfg from backup.*": lambda msg: "y",
        ".*change the DRO URL.*": lambda msg: "n",
        ".*restore the Manage application.*": lambda msg: "y",
        ".*Manage workspace ID.*": lambda msg: workspaceId,
        ".*include PVC restore for Manage.*": lambda msg: "y",
        ".*restore the Manage database.*": lambda msg: "y",
        ".*Manage Db2 database name.*": lambda msg: dbName,
        ".*restore the Facilities application.*": lambda msg: "n",
        ".*download the backup archive before restore.*": lambda msg: "n",
        ".*Clean the workspace.*": lambda msg: "y",
        ".*Proceed with these settings.*": lambda msg: "y",
    }


def test_restore_interactive_with_workspace_and_dbname():
    """
    Given an interactive restore of Manage including its Db2 database
    When the user enters a workspace ID and a Db2 database name
    Then both are passed to the restore pipeline
    """
    result = runBackupRestoreTest(BackupRestoreTestConfig(command="restore", prompt_handlers=_interactivePromptHandlers("ws1", "MAXDB")))

    params = result.launchParams
    assert params is not None, "launchRestorePipeline was not called"
    assert params["mas_instance_id"] == "inst1"
    assert params["restore_manage_app"] == "true"
    assert params["restore_manage_db"] == "true"
    assert params["manage_workspace_id"] == "ws1"
    assert params["manage_db2_dbname"] == "MAXDB"


def test_restore_interactive_defaults_to_backup_values():
    """
    Given an interactive restore of Manage including its Db2 database
    When the user leaves the workspace ID and Db2 database name empty
    Then neither is passed, so the pipeline derives both from the backup
    """
    result = runBackupRestoreTest(BackupRestoreTestConfig(command="restore", prompt_handlers=_interactivePromptHandlers("", "")))

    params = result.launchParams
    assert params is not None, "launchRestorePipeline was not called"
    assert params["restore_manage_app"] == "true"
    assert "manage_workspace_id" not in params
    assert "manage_db2_dbname" not in params
