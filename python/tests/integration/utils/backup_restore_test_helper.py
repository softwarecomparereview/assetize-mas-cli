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

"""Shared helper for `mas backup` and `mas restore` integration tests.

The Kubernetes client and every mas.devops function that talks to the cluster or launches a
PipelineRun are mocked.  The params dict handed to launchBackupPipeline / launchRestorePipeline
is captured so tests can assert on exactly what would be sent to the Tekton pipeline.
"""

import contextlib
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional
from unittest import mock
from unittest.mock import MagicMock

from kubernetes.dynamic import DynamicClient

from utils.prompt_tracker import create_prompt_handler


class BackupRestoreTestConfig:
    """Configuration for a backup or restore test scenario."""

    def __init__(
        self,
        command: str,
        argv: Optional[List[str]] = None,
        prompt_handlers: Optional[Dict[str, Callable[[str], str]]] = None,
        mas_instances: Optional[List[Dict]] = None,
        workspace_id: Optional[str] = "ws1",
        architecture: str = "amd64",
        expect_system_exit: bool = False,
    ):
        """
        Args:
            command: "backup" or "restore"
            argv: Command line arguments passed to the app
            prompt_handlers: PromptTracker handlers (regex -> handler) for interactive mode
            mas_instances: Suite CRs returned by listMasInstances (backup only)
            workspace_id: Value returned by getWorkspaceId (backup only)
            architecture: Architecture reported by the cluster nodes
            expect_system_exit: Whether the app is expected to exit (e.g. fatalError)
        """
        assert command in ["backup", "restore"]
        self.command = command
        self.argv = argv if argv is not None else []
        self.prompt_handlers = prompt_handlers if prompt_handlers is not None else {}
        self.mas_instances = mas_instances if mas_instances is not None else [{"metadata": {"name": "inst1"}, "status": {"versions": {"reconciled": "9.1.7"}}}]
        self.workspace_id = workspace_id
        self.architecture = architecture
        self.expect_system_exit = expect_system_exit


class BackupRestoreTestResult:
    """Outcome of a backup or restore test run."""

    def __init__(self, app, launchParams: Optional[Dict], launchMock: MagicMock, systemExit: Optional[SystemExit]):
        self.app = app
        self.launchParams = launchParams
        self.launchMock = launchMock
        self.systemExit = systemExit


def _setupDynamicClient() -> MagicMock:
    dynamicClient = MagicMock(DynamicClient)
    resources = MagicMock()
    dynamicClient.resources = resources

    routesApi = MagicMock()
    route = MagicMock()
    route.spec.host = "console.test.maximo.ibm.com"
    routesApi.get.return_value = route

    resourceApis = {"Route": routesApi}
    resources.get.side_effect = lambda **kwargs: resourceApis.get(kwargs["kind"], MagicMock())
    return dynamicClient


def runBackupRestoreTest(config: BackupRestoreTestConfig) -> BackupRestoreTestResult:
    """Run `mas backup` or `mas restore` with all cluster interactions mocked.

    Returns:
        BackupRestoreTestResult holding the params passed to the launch function (None if it was not called)
    """
    moduleName = f"mas.cli.{config.command}.app"
    launchFunction = "launchBackupPipeline" if config.command == "backup" else "launchRestorePipeline"
    secretsFunction = "prepareBackupSecrets" if config.command == "backup" else "prepareRestoreSecrets"

    defaultStorageClasses = SimpleNamespace(provider="ibmc", providerName="IBM Cloud", rwo="ibmc-block-gold", rwx="ibmc-file-gold-gid")

    patches = {
        "config": mock.patch("mas.cli.cli.config"),
        "dynamicClientClass": mock.patch("mas.cli.cli.DynamicClient"),
        "getNodes": mock.patch("mas.cli.cli.getNodes"),
        "isAirgapInstall": mock.patch("mas.cli.cli.isAirgapInstall"),
        "isSNO": mock.patch("mas.cli.cli.isSNO"),
        "mixinsPrompt": mock.patch("mas.cli.displayMixins.prompt"),
        "promptSessionClass": mock.patch("mas.cli.displayMixins.PromptSession"),
        "appPrompt": mock.patch(f"{moduleName}.prompt"),
        "createNamespace": mock.patch(f"{moduleName}.createNamespace"),
        "getConsoleURL": mock.patch(f"{moduleName}.getConsoleURL"),
        "getStorageClasses": mock.patch(f"{moduleName}.getStorageClasses"),
        "getDefaultStorageClasses": mock.patch(f"{moduleName}.getDefaultStorageClasses"),
        "preparePipelinesNamespace": mock.patch(f"{moduleName}.preparePipelinesNamespace"),
        "installOpenShiftPipelines": mock.patch(f"{moduleName}.installOpenShiftPipelines"),
        "updateTektonDefinitions": mock.patch(f"{moduleName}.updateTektonDefinitions"),
        "prepareSecrets": mock.patch(f"{moduleName}.{secretsFunction}"),
        "launch": mock.patch(f"{moduleName}.{launchFunction}"),
    }
    if config.command == "backup":
        patches["listMasInstances"] = mock.patch(f"{moduleName}.listMasInstances")
        patches["getWorkspaceId"] = mock.patch(f"{moduleName}.getWorkspaceId")

    tracker, promptHandler = create_prompt_handler(config.prompt_handlers)
    launchParams: Dict = {}
    systemExit = None
    app = None

    with contextlib.ExitStack() as stack:
        mocks = {name: stack.enter_context(patch) for name, patch in patches.items()}

        mocks["dynamicClientClass"].return_value = _setupDynamicClient()
        mocks["getNodes"].return_value = [{"status": {"nodeInfo": {"architecture": config.architecture}}}]
        mocks["isAirgapInstall"].return_value = False
        mocks["isSNO"].return_value = False
        mocks["getConsoleURL"].return_value = "https://console.test.maximo.ibm.com"
        mocks["getStorageClasses"].return_value = []
        mocks["getDefaultStorageClasses"].return_value = defaultStorageClasses
        mocks["installOpenShiftPipelines"].return_value = True

        def captureLaunch(dynClient, params):
            # Copy so later mutations of app.params cannot affect the assertions
            launchParams.update(params)
            return "https://pipeline.test.maximo.ibm.com"

        mocks["launch"].side_effect = captureLaunch

        if config.command == "backup":
            mocks["listMasInstances"].return_value = config.mas_instances
            mocks["getWorkspaceId"].return_value = config.workspace_id

        promptSessionInstance = MagicMock()
        mocks["promptSessionClass"].return_value = promptSessionInstance
        mocks["mixinsPrompt"].side_effect = promptHandler
        mocks["appPrompt"].side_effect = promptHandler
        promptSessionInstance.prompt.side_effect = promptHandler

        try:
            if config.command == "backup":
                from mas.cli.backup.app import BackupApp

                app = BackupApp()
                app.backup(config.argv)
            else:
                from mas.cli.restore.app import RestoreApp

                app = RestoreApp()
                app.restore(config.argv)
        except SystemExit as e:
            systemExit = e
            if not config.expect_system_exit:
                raise

        if config.expect_system_exit and systemExit is None:
            raise AssertionError("Expected SystemExit to be raised but it was not")

        if len(config.prompt_handlers) > 0:
            tracker.verify_all_prompts_matched(allow_unmatched=config.expect_system_exit)

        return BackupRestoreTestResult(app, launchParams if mocks["launch"].called else None, mocks["launch"], systemExit)
