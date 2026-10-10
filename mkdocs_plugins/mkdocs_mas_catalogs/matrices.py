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
Cross-catalog matrices rendered from the python-devops catalog data.

These functions are pure: they take a list of ``(tag, catalog)`` tuples (as
returned by :func:`loadCatalogs`) and return HTML, so they can be unit tested
without running MkDocs.
"""

import re
from datetime import datetime
from html import escape

# Columns rendered in the version matrix: (catalog data key, column heading)
MAS_COMPONENTS = [
    ("mas_core_version", "Core"),
    ("mas_manage_version", "Manage"),
    ("mas_iot_version", "IoT"),
    ("mas_monitor_version", "Monitor"),
    ("mas_predict_version", "Predict"),
    ("mas_optimizer_version", "Optimizer"),
    ("mas_visualinspection_version", "Visual Inspection"),
    ("mas_assist_version", "Assist"),
    ("mas_facilities_version", "Real Estate and Facilities"),
]

_TAG_PATTERN = re.compile(r"^v(\d+)-(\d{6})-([a-z0-9]+)$")
_CHANNEL_PATTERN = re.compile(r"^(\d+)\.(\d+)\.x(-feature)?$")


def normalizeOcpVersion(version) -> str:
    """
    Return an OCP minor version as a string.

    Unquoted YAML values such as ``4.20`` are loaded as the float ``4.2``; every OCP
    release MAS has supported is 4.10 or later, so a single-digit minor is padded.
    """
    if isinstance(version, float):
        major, minor = repr(version).split(".")
        if len(minor) == 1:
            minor += "0"
        return f"{major}.{minor}"
    return str(version).strip()


def ocpSortKey(version: str) -> tuple:
    return tuple(int(part) for part in version.split("."))


def channelSortKey(channel: str) -> tuple:
    """Sort key for MAS channels: newest release first, GA channel before its -feature channel."""
    match = _CHANNEL_PATTERN.match(channel)
    if not match:
        return (-1, -1, -1)
    return (int(match.group(1)), int(match.group(2)), 0 if match.group(3) else 1)


def releaseDate(tag: str) -> str:
    """Derive the release date (YYYY-MM-DD) from a catalog tag such as v9-261007-amd64."""
    match = _TAG_PATTERN.match(tag)
    if not match:
        return "N/A"
    return datetime.strptime(match.group(2), "%y%m%d").strftime("%Y-%m-%d")


def shortTag(tag: str) -> str:
    """v9-261007-amd64 -> v9-261007"""
    match = _TAG_PATTERN.match(tag)
    return f"v{match.group(1)}-{match.group(2)}" if match else tag


def loadCatalogs(listCatalogTags, getCatalog, arch: str = "amd64", prefix: str = "v9-") -> list:
    """Load every catalog for ``arch`` whose tag starts with ``prefix``, newest first."""
    tags = [tag for tag in listCatalogTags(arch) if tag.startswith(prefix)]
    tags.sort(key=lambda tag: _TAG_PATTERN.match(tag).group(2) if _TAG_PATTERN.match(tag) else tag, reverse=True)
    return [(tag, getCatalog(tag)) for tag in tags]


def coreChannels(catalog: dict) -> list:
    """MAS channels with a core release in this catalog, newest first."""
    core = catalog.get("mas_core_version") or {}
    return sorted([channel for channel, version in core.items() if version], key=channelSortKey, reverse=True)


def _catalogCell(tag: str, linkFor) -> str:
    label = escape(shortTag(tag))
    href = linkFor(tag) if linkFor else None
    if href:
        return f'<a href="{escape(href)}">{label}</a>'
    return label


def renderVersionMatrix(catalogs: list, linkFor=None) -> str:
    """
    Render one table listing, for each catalog (newest first) and each MAS channel it
    provides, the version of MAS core and each application available in that channel.
    """
    if not catalogs:
        return "!!! warning\n    No catalog data available.\n"

    headings = "".join(f"<th>{escape(label)}</th>" for _, label in MAS_COMPONENTS)
    html = [
        "<table>",
        "  <thead>",
        f'    <tr><th style="min-width: 110px;">Catalog</th><th style="min-width: 100px;">Released</th><th>Channel</th>{headings}</tr>',
        "  </thead>",
        "  <tbody>",
    ]
    for tag, catalog in catalogs:
        channels = coreChannels(catalog)
        if not channels:
            continue
        for index, channel in enumerate(channels):
            cells = []
            if index == 0:
                rowspan = len(channels)
                cells.append(f'<td rowspan="{rowspan}"><span style="font-weight: bold">{_catalogCell(tag, linkFor)}</span></td>')
                cells.append(f'<td rowspan="{rowspan}">{releaseDate(tag)}</td>')
            cells.append(f"<td>{escape(channel)}</td>")
            for key, _ in MAS_COMPONENTS:
                version = (catalog.get(key) or {}).get(channel) or "-"
                cells.append(f"<td>{escape(str(version))}</td>")
            html.append(f"    <tr>{''.join(cells)}</tr>")
    html.extend(["  </tbody>", "</table>", ""])
    return "\n".join(html)


def buildOcpIndex(catalogs: list) -> dict:
    """Pivot ``ocp_compatibility``: OCP minor version -> list of (tag, catalog), newest catalog first."""
    index = {}
    for tag, catalog in catalogs:
        for version in catalog.get("ocp_compatibility") or []:
            index.setdefault(normalizeOcpVersion(version), []).append((tag, catalog))
    return index


def renderOcpMatrix(catalogs: list, linkFor=None) -> str:
    """
    Render one table listing, for each OCP minor version (newest first), the catalogs
    certified on it and the MAS channels those catalogs provide.
    """
    index = buildOcpIndex(catalogs)
    if not index:
        return "!!! warning\n    No OCP compatibility data available.\n"

    html = [
        "<table>",
        "  <thead>",
        "    <tr><th>OCP</th><th>MAS Channels</th><th>Newest Catalog</th><th>Oldest Catalog</th><th>All Catalogs</th></tr>",
        "  </thead>",
        "  <tbody>",
    ]
    for version in sorted(index, key=ocpSortKey, reverse=True):
        entries = index[version]
        channels = set()
        for _, catalog in entries:
            channels.update(coreChannels(catalog))
        channelText = ", ".join(sorted(channels, key=channelSortKey, reverse=True)) or "-"
        newestTag, oldestTag = entries[0][0], entries[-1][0]
        allLinks = ", ".join(_catalogCell(tag, linkFor) for tag, _ in entries)
        html.append(
            "    <tr>"
            f'<td><span style="font-weight: bold">{escape(version)}</span></td>'
            f"<td>{escape(channelText)}</td>"
            f"<td>{_catalogCell(newestTag, linkFor)}</td>"
            f"<td>{_catalogCell(oldestTag, linkFor)}</td>"
            f"<td><details><summary>{len(entries)} catalogs</summary>{allLinks}</details></td>"
            "</tr>"
        )
    html.extend(["  </tbody>", "</table>", ""])
    return "\n".join(html)
