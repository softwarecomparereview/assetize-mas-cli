# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************
"""Tests for the cross-catalog matrices rendered by the mkdocs_mas_catalogs plugin."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "mkdocs_plugins"))

from mas.devops.data import getCatalog, listCatalogTags  # noqa: E402
from mkdocs_mas_catalogs.matrices import (  # noqa: E402
    buildOcpIndex,
    channelSortKey,
    loadCatalogs,
    normalizeOcpVersion,
    releaseDate,
    renderOcpMatrix,
    renderVersionMatrix,
)


@pytest.fixture(scope="module")
def catalogs():
    return loadCatalogs(listCatalogTags, getCatalog, arch="amd64", prefix="v9-")


def _rows(html):
    return re.findall(r"<tr>(.*?)</tr>", html.split("<tbody>")[1])


def test_load_catalogs_newest_first(catalogs):
    """
    Given the catalog data shipped with mas-devops
    When v9 amd64 catalogs are loaded
    Then they are all v9 amd64 catalogs sorted newest first
    """
    tags = [tag for tag, _ in catalogs]
    assert len(tags) > 0
    assert all(tag.startswith("v9-") and tag.endswith("-amd64") for tag in tags)
    assert tags == sorted(tags, reverse=True)


def test_normalize_ocp_version():
    """
    Given OCP versions loaded from YAML as strings or floats
    When they are normalized
    Then unquoted values such as 4.20 (float 4.2) keep their trailing zero
    """
    assert normalizeOcpVersion("4.21") == "4.21"
    assert normalizeOcpVersion(4.16) == "4.16"
    assert normalizeOcpVersion(4.2) == "4.20"


def test_channel_sort_order():
    """
    Given a set of MAS channels
    When sorted newest first
    Then GA channels precede their -feature channel and newer releases precede older ones
    """
    channels = ["8.10.x", "9.2.x-feature", "9.0.x", "9.2.x", "9.1.x"]
    assert sorted(channels, key=channelSortKey, reverse=True) == ["9.2.x", "9.2.x-feature", "9.1.x", "9.0.x", "8.10.x"]


def test_release_date():
    """
    Given a catalog tag
    When the release date is derived
    Then it is the ISO date encoded in the tag
    """
    assert releaseDate("v9-260430-amd64") == "2026-04-30"


def test_version_matrix(catalogs):
    """
    Given the real catalog data
    When the version matrix is rendered
    Then it has a row per catalog channel, newest catalog first, with known versions present
    """
    html = renderVersionMatrix(catalogs, linkFor=lambda tag: f"{tag}/")
    rows = _rows(html)
    assert len(rows) >= len(catalogs)
    assert catalogs[0][0] in rows[0]
    v260430 = dict(catalogs)["v9-260430-amd64"]
    assert f"<td>{v260430['mas_core_version']['9.1.x']}</td>" in html
    assert f"<td>{v260430['mas_manage_version']['9.1.x']}</td>" in html
    assert '<a href="v9-260430-amd64/">v9-260430</a>' in html


def test_ocp_matrix(catalogs):
    """
    Given the real catalog data
    When the OCP matrix is rendered
    Then each OCP release is listed newest first and v9-260430 is listed under OCP 4.21
    """
    index = buildOcpIndex(catalogs)
    assert "v9-260430-amd64" in [tag for tag, _ in index["4.21"]]

    html = renderOcpMatrix(catalogs)
    rows = _rows(html)
    assert len(rows) == len(index)
    versions = [re.search(r'bold">([\d.]+)<', row).group(1) for row in rows]
    assert versions == sorted(versions, key=lambda v: tuple(int(p) for p in v.split(".")), reverse=True)
    row421 = next(row for row in rows if 'bold">4.21<' in row)
    assert "v9-260430" in row421


def test_empty_input():
    """
    Given no catalogs
    When either matrix is rendered
    Then a warning admonition is returned instead of an empty table
    """
    assert renderVersionMatrix([]).startswith("!!! warning")
    assert renderOcpMatrix([]).startswith("!!! warning")
