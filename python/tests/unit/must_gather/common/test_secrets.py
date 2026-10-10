# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""Tests that must-gather never writes secret values."""

import yaml

from mas.cli.must_gather.common.secrets import LAST_APPLIED_ANNOTATION, _writeYaml


def test_write_yaml_strips_data_and_last_applied_annotation(tmp_path):
    """
    GIVEN a Secret with data, stringData and a kubectl last-applied-configuration annotation holding the encoded data
    WHEN it is written by must-gather
    THEN none of the secret values are written, other metadata is kept and the input is not modified
    """
    secret = {
        "kind": "Secret",
        "metadata": {
            "name": "db-creds",
            "namespace": "mas-inst1-core",
            "labels": {"app": "db"},
            "annotations": {
                LAST_APPLIED_ANNOTATION: '{"data":{"password":"c2VjcmV0"}}',
                "owner": "team-a",
            },
        },
        "type": "Opaque",
        "data": {"password": "c2VjcmV0"},
        "stringData": {"password": "secret"},
    }
    outputFile = tmp_path / "db-creds.yaml"

    _writeYaml(secret, str(outputFile))

    text = outputFile.read_text()
    assert "c2VjcmV0" not in text
    assert "secret\n" not in text
    written = yaml.safe_load(text)
    assert "data" not in written
    assert "stringData" not in written
    assert written["metadata"]["annotations"] == {"owner": "team-a"}
    assert written["metadata"]["labels"] == {"app": "db"}
    # The caller's object is untouched
    assert LAST_APPLIED_ANNOTATION in secret["metadata"]["annotations"]
    assert "data" in secret


def test_write_yaml_without_annotations(tmp_path):
    """
    GIVEN a Secret with no annotations
    WHEN it is written by must-gather
    THEN the data is removed and the metadata is written unchanged
    """
    secret = {"kind": "Secret", "metadata": {"name": "plain"}, "data": {"key": "dmFsdWU="}}
    outputFile = tmp_path / "plain.yaml"

    _writeYaml(secret, str(outputFile))

    written = yaml.safe_load(outputFile.read_text())
    assert "data" not in written
    assert written["metadata"] == {"name": "plain"}
