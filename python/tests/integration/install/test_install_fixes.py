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
Focused tests for small install fixes:
  - BaseApp.warningIcon exists (used when enabling the Pipelines console plugin fails)
  - getCompatibleVersions() returns [] for apps not available on a core channel (ibm-mas/cli#2060)
  - sync-install ConfigMap is reset before an install is launched (ibm-mas/cli#1398)
  - Db2 storage class / access mode flags (ibm-mas/cli#1037)
  - --configure-ai-assistant and the legacy --configure-aiassistant spelling (ibm-mas/cli#2503)
  - Existing MongoDBCommunity cluster detection (ibm-mas/cli#1907)
  - Storage classes that the provider reports as missing (None) are prompted for (ibm-mas/cli#1520)
"""

import shlex
from unittest import mock
from unittest.mock import MagicMock

import pytest
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError
from prompt_toolkit.application import create_app_session
from prompt_toolkit.output import DummyOutput

from mas.cli.cli import BaseApp
from mas.cli.install.app import InstallApp
from mas.cli.install.argParser import installArgParser
from mas.cli.install.params import optionalParams

BASE_ARGV = ["--mas-instance-id", "inst1", "--mas-channel", "9.1.x"]


def createMockApp(params=None):
    app = MagicMock(spec=InstallApp)
    app.params = dict(params or {})
    app.setParam = lambda key, value: app.params.__setitem__(key, value)
    app.getParam = lambda key: app.params.get(key, "")
    app.dynamicClient = MagicMock()
    return app


@pytest.fixture
def baseApp():
    with create_app_session(output=DummyOutput()):
        yield BaseApp()


# -----------------------------------------------------------------------------
# Icons
# -----------------------------------------------------------------------------
def test_warning_icon_defined(baseApp):
    """
    GIVEN a BaseApp
    WHEN the icons are inspected
    THEN success, failure and warning icons are all defined and distinct
    """
    assert baseApp.warningIcon
    assert len({baseApp.successIcon, baseApp.failureIcon, baseApp.warningIcon}) == 3


# -----------------------------------------------------------------------------
# getCompatibleVersions / configAppChannel
# -----------------------------------------------------------------------------
def test_get_compatible_versions_missing_app_returns_empty(baseApp):
    """
    GIVEN a core channel that does not list a given application
    WHEN getCompatibleVersions is called
    THEN an empty list is returned instead of raising KeyError
    """
    assert baseApp.getCompatibleVersions("9.2.x", "assist") == []
    assert baseApp.getCompatibleVersions("1.0.x", "manage") == []
    assert baseApp.getCompatibleVersions("9.2.x", "manage")[0] == "9.2.x"


def test_get_compatible_versions_returns_copy(baseApp):
    """
    GIVEN the compatibility matrix
    WHEN the caller mutates the returned list
    THEN the matrix itself is not modified
    """
    versions = baseApp.getCompatibleVersions("9.2.x", "manage")
    versions.clear()
    assert baseApp.getCompatibleVersions("9.2.x", "manage") != []


def test_config_app_channel_unknown_app_explains_and_prompts():
    """
    GIVEN a known core channel with no compatible channel for an application
    WHEN configAppChannel is called
    THEN the user is told why and asked for a custom channel rather than the CLI crashing
    """
    app = createMockApp({"mas_channel": "9.2.x"})
    app.compatibilityMatrix = {"9.2.x": {"manage": ["9.2.x"]}}
    app.getCompatibleVersions = BaseApp.getCompatibleVersions.__get__(app)
    InstallApp.configAppChannel(app, "assist")
    app.printDescription.assert_called_once()
    assert "No compatible assist channel" in app.printDescription.call_args[0][0][0]
    app.promptForString.assert_called_once()
    assert app.promptForString.call_args[0][1] == "mas_app_channel_assist"


# -----------------------------------------------------------------------------
# sync-install ConfigMap
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("deleteSideEffect", [None, NotFoundError(ApiException(status=404))])
def test_setup_approvals_resets_sync_install(deleteSideEffect):
    """
    GIVEN an install pipelines namespace that may or may not contain a sync-install ConfigMap from a previous run
    WHEN setupApprovals runs before the PipelineRun is launched
    THEN the sync-install ConfigMap is deleted, and a missing ConfigMap is ignored
    """
    app = createMockApp()
    app.approvals = {"approval_core": {"id": "suite-verify"}}
    app.resetSyncInstallConfigMap = InstallApp.resetSyncInstallConfigMap.__get__(app)
    cmAPI = MagicMock()
    cmAPI.delete.side_effect = deleteSideEffect
    app.dynamicClient.resources.get.return_value = cmAPI

    InstallApp.setupApprovals(app, "mas-inst1-pipelines")

    app.initializeApprovalConfigMap.assert_called_once_with("mas-inst1-pipelines", "suite-verify", False)
    cmAPI.delete.assert_called_once_with(name="sync-install", namespace="mas-inst1-pipelines")


# -----------------------------------------------------------------------------
# Db2 storage classes and access modes
# -----------------------------------------------------------------------------
def test_db2_storage_class_flags_parse():
    """
    GIVEN the Db2 storage class and access mode flags
    WHEN they are parsed by the install argParser
    THEN each maps onto the matching db2_* param, and every param is passed straight through in non-interactive mode
    """
    argv = list(BASE_ARGV)
    for volume in ["meta", "data", "backup", "logs", "temp"]:
        argv += [f"--db2-{volume}-storage-class", f"sc-{volume}", f"--db2-{volume}-storage-accessmode", "ReadWriteOnce"]
    args = vars(installArgParser.parse_args(argv))
    for volume in ["meta", "data", "backup", "logs", "temp"]:
        assert args[f"db2_{volume}_storage_class"] == f"sc-{volume}"
        assert args[f"db2_{volume}_storage_accessmode"] == "ReadWriteOnce"
        assert f"db2_{volume}_storage_class" in optionalParams
        assert f"db2_{volume}_storage_accessmode" in optionalParams


def test_db2_storage_accessmode_rejects_invalid_value():
    """
    GIVEN an invalid access mode
    WHEN it is parsed
    THEN argparse rejects it
    """
    with pytest.raises(SystemExit):
        installArgParser.parse_args(BASE_ARGV + ["--db2-data-storage-accessmode", "ReadOnlyMany"])


def test_normalize_db2_access_modes_fills_role_defaults():
    """
    GIVEN only the Db2 data access mode was customized
    WHEN the access modes are normalized
    THEN the remaining access modes get the db2 role defaults (the PipelineRun only passes them when meta is set)
    """
    app = createMockApp({"db2_data_storage_accessmode": "ReadWriteMany"})
    InstallApp.normalizeDb2StorageAccessModes(app)
    assert app.params["db2_data_storage_accessmode"] == "ReadWriteMany"
    assert app.params["db2_meta_storage_accessmode"] == "ReadWriteMany"
    assert app.params["db2_backup_storage_accessmode"] == "ReadWriteMany"
    assert app.params["db2_logs_storage_accessmode"] == "ReadWriteOnce"
    assert app.params["db2_temp_storage_accessmode"] == "ReadWriteOnce"


def test_normalize_db2_access_modes_noop_when_unset():
    """
    GIVEN no Db2 access mode was customized
    WHEN the access modes are normalized
    THEN nothing is set, leaving the decision to the db2 role
    """
    app = createMockApp()
    InstallApp.normalizeDb2StorageAccessModes(app)
    assert app.params == {}


# -----------------------------------------------------------------------------
# --configure-ai-assistant
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("flag", ["--configure-ai-assistant", "--configure-aiassistant"])
def test_configure_ai_assistant_flag_and_legacy_alias(flag):
    """
    GIVEN the documented flag or the spelling emitted by older buildCommand() output
    WHEN it is parsed
    THEN both set configure_aiassistant
    """
    args = installArgParser.parse_args(BASE_ARGV + [flag, "pipeline"])
    assert args.configure_aiassistant == "pipeline"


# -----------------------------------------------------------------------------
# Existing MongoDb cluster detection
# -----------------------------------------------------------------------------
def test_existing_mongodb_clusters_found():
    """
    GIVEN a MongoDBCommunity instance in the mongoce namespace
    WHEN existing clusters are looked up
    THEN its name is returned
    """
    app = createMockApp()
    result = MagicMock()
    result.to_dict.return_value = {"items": [{"metadata": {"name": "mas-mongo-ce"}}]}
    app.dynamicClient.resources.get.return_value.get.return_value = result
    assert InstallApp.getExistingMongoDbClusters(app, "mongoce") == ["mas-mongo-ce"]
    app.dynamicClient.resources.get.assert_called_once_with(api_version="mongodbcommunity.mongodb.com/v1", kind="MongoDBCommunity")


@pytest.mark.parametrize(
    "error",
    [ResourceNotFoundError("no crd"), NotFoundError(ApiException(status=404)), ApiException(status=403)],
)
def test_existing_mongodb_clusters_tolerates_errors(error):
    """
    GIVEN the MongoDBCommunity CRD or namespace does not exist (or cannot be read)
    WHEN existing clusters are looked up
    THEN no clusters are reported and no exception escapes
    """
    app = createMockApp()
    app.dynamicClient.resources.get.side_effect = error
    assert InstallApp.getExistingMongoDbClusters(app, "mongoce") == []


def test_config_mongodb_reports_existing_cluster():
    """
    GIVEN an existing MongoDBCommunity cluster in mongoce
    WHEN the user is asked whether to create a MongoDb cluster
    THEN they are first told that the databases will be added to the existing cluster
    """
    app = createMockApp()
    app.devMode = False
    app.architecture = "amd64"
    app.showAdvancedOptions = False
    app.getExistingMongoDbClusters = MagicMock(return_value=["mas-mongo-ce"])
    app.yesOrNo = MagicMock(return_value=True)
    with mock.patch("mas.cli.install.settings.mongodbSettings.print_formatted_text") as printText:
        InstallApp.configMongoDb(app)
    printed = " ".join(str(call.args[0].value) for call in printText.call_args_list if hasattr(call.args[0], "value"))
    assert "added to the existing cluster 'mas-mongo-ce'" in printed
    assert app.params["mongodb_namespace"] == "mongoce"


# -----------------------------------------------------------------------------
# Storage classes reported as missing (None) by getDefaultStorageClasses
# -----------------------------------------------------------------------------
def test_config_storage_classes_prompts_for_missing_rwx():
    """
    GIVEN a detected storage provider whose RWX storage class is not present in the cluster (rwx=None)
    WHEN storage classes are configured interactively
    THEN the user is not offered the auto-detected classes, and is prompted only for the RWX class
    """
    app = createMockApp()
    app.isSNO = MagicMock(return_value=False)
    detected = MagicMock(provider="ibmc", providerName="IBM Cloud", rwo="ibmc-block-gold", rwx=None)
    with (
        mock.patch("mas.cli.install.app.getDefaultStorageClasses", return_value=detected),
        mock.patch("mas.cli.install.app.getStorageClasses", return_value=[]),
        mock.patch("mas.cli.install.app.print_formatted_text"),
        mock.patch("mas.cli.install.app.prompt", return_value="my-rwx") as promptMock,
    ):
        InstallApp.configStorageClasses(app)

    app.yesOrNo.assert_not_called()
    assert promptMock.call_count == 1
    assert "ReadWriteMany" in str(promptMock.call_args[0][0].value)
    assert app.params["storage_class_rwo"] == "ibmc-block-gold"
    assert app.params["storage_class_rwx"] == "my-rwx"
    assert app.pipelineStorageClass == "my-rwx"


def test_config_storage_classes_offers_autodetected_when_both_present():
    """
    GIVEN a detected storage provider with both classes present
    WHEN the user accepts the auto-detected classes
    THEN no storage class prompts are shown
    """
    app = createMockApp()
    app.isSNO = MagicMock(return_value=False)
    app.yesOrNo = MagicMock(return_value=True)
    detected = MagicMock(provider="ocs", providerName="ODF", rwo="ocs-rbd", rwx="ocs-cephfs")
    with (
        mock.patch("mas.cli.install.app.getDefaultStorageClasses", return_value=detected),
        mock.patch("mas.cli.install.app.print_formatted_text"),
        mock.patch("mas.cli.install.app.prompt") as promptMock,
    ):
        InstallApp.configStorageClasses(app)

    promptMock.assert_not_called()
    assert app.params["storage_class_rwo"] == "ocs-rbd"
    assert app.params["storage_class_rwx"] == "ocs-cephfs"


# -----------------------------------------------------------------------------
# buildCommand() de-duplication and Db2 storage flags
# -----------------------------------------------------------------------------
def test_build_command_no_duplicate_flags_and_reparses():
    """
    GIVEN an install of Manage (with persistent volumes) and AI Service, with in-cluster Db2 for both and custom Db2 storage settings
    WHEN the non-interactive command is built
    THEN each flag appears once, --configure-ai-assistant is spelled correctly and the command re-parses
    """
    app = createMockApp(
        {
            "mas_catalog_version": "v9-261007-amd64",
            "mas_channel": "9.1.x",
            "mas_instance_id": "inst1",
            "mas_workspace_id": "ws1",
            "mas_workspace_name": "Workspace 1",
            "storage_class_rwo": "rwo",
            "storage_class_rwx": "rwx",
            "sls_namespace": "ibm-sls",
            "dro_contact_email": "a@b.com",
            "dro_contact_firstname": "A",
            "dro_contact_lastname": "B",
            "mas_app_channel_manage": "9.1.x",
            "mas_appws_bindings_jdbc_manage": "workspace-application",
            "mas_appws_components": "base=latest",
            "mas_app_settings_persistent_volumes_flag": "true",
            "aiservice_channel": "9.1.x",
            "configure_aiassistant": "pipeline",
            "db2_action_manage": "install",
            "db2_action_aiservice": "install",
            "db2_channel": "v110509.0",
            "db2_data_storage_class": "db2-data",
            "db2_meta_storage_accessmode": "ReadWriteMany",
        }
    )
    for attr in [
        "localConfigDir",
        "manualCertsDir",
        "slsLicenseFileLocal",
        "facilitiesPropertiesFileLocal",
        "cliDigest",
        "aiserviceTenantSchedulingConfigFileLocal",
        "aiserviceTenantOperatorConfigFileLocal",
    ]:
        setattr(app, attr, None)
    app.db2LicenseFileLocal = "/tmp/db2.lic"
    app.operationalMode = 1
    app.mas_admin_mode = ""
    app.pipelineStorageClass = "rwx"
    app.pipelineStorageAccessMode = "ReadWriteMany"
    app.devMode = False
    app.useCliDigest = False
    for flag in [
        "installAssist",
        "installIoT",
        "installMonitor",
        "installOptimizer",
        "installPredict",
        "installInspection",
        "installFacilities",
        "installArcgis",
    ]:
        setattr(app, flag, False)
    app.installManage = True
    app.installAIService = True

    command = InstallApp.buildCommand(app)
    lines = [line for line in command.split("\n") if not line.startswith("export ")]
    tokens = shlex.split(" ".join(line.rstrip().rstrip("\\") for line in lines))
    flags = [token for token in tokens if token.startswith("--")]
    assert sorted({f for f in flags if flags.count(f) > 1}) == []
    assert "--configure-aiassistant" not in flags

    args = installArgParser.parse_args(tokens[2:])
    assert args.configure_aiassistant == "pipeline"
    assert args.aiservice_channel == "9.1.x"
    assert args.db2_channel == "v110509.0"
    assert args.db2_license_file == "/tmp/db2.lic"
    assert args.mas_app_settings_persistent_volumes_flag == "true"
    assert args.db2_data_storage_class == "db2-data"
    assert args.db2_meta_storage_accessmode == "ReadWriteMany"
