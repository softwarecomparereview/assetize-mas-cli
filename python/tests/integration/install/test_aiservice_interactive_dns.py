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
Interactive install tests for AI Service DNS configuration scenarios.

Three scenarios are covered:
  1. MAS is configured with a non-Cloudflare DNS provider (CIS) — AI Service inherits the
     same domain and derives its certificate issuer automatically.
  2. MAS is configured with Cloudflare — AI Service DNS config is skipped (description
     printed, no DNS prompts presented).
  3. MAS has no custom domain — AI Service is configured independently with CIS DNS.
"""

import shlex
from mas.cli.install.argParser import installArgParser
from mas.cli.install.catalogs import supportedCatalogs
from utils import InstallTestConfig, run_install_test

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _base_prompts(tmpdir):
    """Return the prompt handlers common to all three interactive DNS tests.

    These cover every step that runs before and after the DNS/AI Service DNS
    sections, so each test only needs to add the DNS-specific overrides.
    """
    return {
        ".*Proceed with this cluster.*": lambda msg: "y",
        ".*Show advanced installation options.*": lambda msg: "y",
        ".*Select catalog source.*": lambda msg: "v9-master-amd64",
        ".*Select channel.*": lambda msg: "9.2.x",
        ".*Use the auto-detected storage classes.*": lambda msg: "y",
        ".*SLS Mode.*": lambda msg: "1",
        ".*SLS channel.*": lambda msg: "3.x",
        ".*>License file<.*": lambda msg: f"{tmpdir}/authorized_entitlement.lic",
        ".*Contact e-mail address.*": lambda msg: "maximo@ibm.com",
        ".*Contact first name.*": lambda msg: "Test",
        ".*Contact last name.*": lambda msg: "Test",
        r".*IBM Data Reporter Operator \(DRO\) Namespace.*": lambda msg: "redhat-marketplace",
        ".*IBM entitlement key.*": lambda msg: "testEntitlementKey",
        ".*Artifactory username.*": lambda msg: "artiuser",
        ".*Artifactory token.*": lambda msg: "artipass",
        ".*Mas Admin Mode.*": lambda msg: "1",
        ".*Certificate issuer kind.*": lambda msg: "2",
        # Fires twice: once for MAS instance ID, once for AI Service instance ID
        ".*Instance ID.*": (lambda msg: "inst1", 2),
        ".*Workspace ID.*": lambda msg: "testws",
        ".*Workspace.*name.*": lambda msg: "Test Workspace",
        ".*Operational Mode.*": lambda msg: "1",
        ".*Trust default CAs.*": lambda msg: "y",
        ".*Cluster ingress certificate secret name.*": lambda msg: "",
        ".*Configure manual certificates.*": lambda msg: "n",
        ".*Routing Mode.*": lambda msg: "1",
        ".*Do you want to use Let's Encrypt for certificate management.*": lambda msg: "n",
        ".*Configure ingress namespace ownership policy to enable path-based routing for MAS.*": lambda msg: "y",
        ".*Enable OpenShift Service Mesh support for MAS.*": lambda msg: "n",
        ".*Configure SSO properties.*": lambda msg: "n",
        ".*Allow special characters for user IDs.*": lambda msg: "n",
        ".*Enable feature adoption metrics.*": lambda msg: "n",
        ".*Enable deployment progression metrics.*": lambda msg: "n",
        ".*Enable usability metrics.*": lambda msg: "n",
        ".*Enable Guided Tour.*": lambda msg: "n",
        ".*Install IoT.*": lambda msg: "n",
        ".*Install Monitor.*": lambda msg: "n",
        ".*Install Manage.*": lambda msg: "n",
        ".*Install Optimizer.*": lambda msg: "n",
        ".*Install Visual Inspection.*": lambda msg: "n",
        ".*Install.*Real Estate and Facilities.*": lambda msg: "n",
        ".*Install AI Service.*": lambda msg: "y",
        ".*Custom channel for AI Service.*": lambda msg: "9.2.x",
        ".*Customize database settings.*": lambda msg: "n",
        ".*Enter AI Service Tenant ID to bind with Manage:.*": lambda msg: "user",
        ".*Manage foundation server timezone.*": lambda msg: "GMT",
        ".*Base language.*": lambda msg: "EN",
        ".*Secondary language.*": lambda msg: "ES",
        ".*Install Minio.*": lambda msg: "y",
        ".*minio root username.*": lambda msg: "minioadmin",
        ".*minio root password.*": lambda msg: "minioadmin",
        ".*Entitlement end date.*": lambda msg: "2027-08-28",
        ".*Configure Scheduling policies for AI Service tenant.*": lambda msg: "n",
        ".*Customize the AI Service tenant operator deployment.*": lambda msg: "n",
        ".*Watsonxai api key.*": lambda msg: "testWxApiKey",
        ".*Watsonxai machine learning url.*": lambda msg: "https://us-south.ml.cloud.ibm.com",
        ".*Watsonxai project id.*": lambda msg: "testProjectId",
        ".*Does the Watsonxai AI use a self-signed certificate.*": lambda msg: "n",
        ".*Watsonxai Deployment ID.*": lambda msg: "",
        ".*Watsonxai Space ID.*": lambda msg: "",
        ".*Does the RSL API use a self-signed certificate.*": lambda msg: "n",
        ".*Create MongoDb cluster.*": lambda msg: "y",
        ".*MongoDb namespace.*": lambda msg: "mongoce",
        ".*Create Manage foundation dedicated Db2 instance using the IBM Db2 Universal Operator.*": lambda msg: "y",
        ".*Select the Manage foundation dedicated DB2 instance type.*": lambda msg: "1",
        # Fires twice: once for Manage Db2, once for AI Service Db2
        ".*Db2 License file.*": (lambda msg: "", 2),
        ".*Install namespace.*": lambda msg: "db2u",
        ".*Configure node affinity.*": lambda msg: "n",
        ".*Configure node tolerations.*": lambda msg: "n",
        ".*Customize CPU and memory request/limit.*": lambda msg: "n",
        ".*Customize storage capacity.*": lambda msg: "n",
        r".*Select Db2 Custom Resource\(CR\).*": lambda msg: "n",
        ".*Do you want to use an external database.*": lambda msg: "n",
        ".*Do you want to configure AiCfg.*": lambda msg: "n",
        ".*Install Grafana.*": lambda msg: "n",
        ".*Use additional configurations.*": lambda msg: "n",
        ".*Use pod templates.*": lambda msg: "n",
        ".*Proceed with these settings.*": lambda msg: "y",
    }


def _config(prompt_handlers, tmpdir):
    """Return an InstallTestConfig for an advanced interactive install."""
    return InstallTestConfig(
        prompt_handlers=prompt_handlers,
        current_catalog={"catalogId": supportedCatalogs["amd64"][1]},
        architecture="amd64",
        is_sno=False,
        is_airgap=False,
        storage_class_name="nfs-client",
        storage_provider="nfs",
        storage_provider_name="NFS Client",
        ocp_version="4.18.0",
        timeout_seconds=30,
        argv=["--dev-mode"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_install_interactive_aiservice_inherits_cis_dns(tmpdir):
    """Test that AI Service inherits MAS CIS DNS config in interactive mode.

    GIVEN MAS is configured with a custom domain and CIS as the DNS provider,
        and the user confirms AI Service DNS configuration
    WHEN the install command runs interactively in advanced mode
    THEN AI Service domain is set to the MAS domain and the AI Service certificate
        issuer is derived from the MAS cluster issuer by replacing the MAS instance
        ID with the AI Service instance ID.
    """
    prompts = _base_prompts(tmpdir)

    # 13. MAS DNS section: custom domain + CIS
    prompts.update(
        {
            # Matches only the MAS DNS prompt — ends with "management?" not "management for AI Service?"
            r".*Configure domain.*certificate management\?.*": lambda msg: "y",
            ".*Configure custom domain.*": lambda msg: "y",
            ".*MAS top-level domain.*": lambda msg: "mas.example.com",
            ".*DNS Provider.*": lambda msg: "2",  # IBM Cloud Internet Services
            ".*CIS e-mail.*": lambda msg: "cis@example.com",
            ".*CIS API token.*": lambda msg: "testCisApiKey",
            ".*CIS CRN.*": lambda msg: "crn:v1:test",
            ".*CIS subdomain.*": lambda msg: "mas",
            ".*Certificate issuer.*": lambda msg: "1",  # LetsEncrypt Production
            ".*Configure enhanced security for CIS.*": lambda msg: "n",
            ".*Cluster Ingress Domain Override.*": lambda msg: "",
            # 18. AI Service DNS: user opts in; MAS domain/CIS already set → inherited automatically
            ".*Configure.*domain.*certificate management for AI Service.*": lambda msg: "y",
        }
    )

    app = run_install_test(tmpdir, _config(prompts, tmpdir))

    assert app.getParam("dns_provider") == "cis"
    assert app.getParam("mas_domain") == "mas.example.com"
    assert app.getParam("aiservice_domain") == "mas.example.com"
    # cert issuer: inst1-cis-le-prod → inst2 not set so replace inst1 with aiservice_instance_id
    assert app.getParam("mas_cluster_issuer") == "inst1-cis-le-prod"
    assert app.getParam("aiservice_certificate_issuer") == "inst1-cis-le-prod"


def test_install_interactive_aiservice_cloudflare_dns_skipped(tmpdir):
    """Test that AI Service DNS configuration is skipped when MAS uses Cloudflare.

    GIVEN MAS is configured with Cloudflare as the DNS provider,
        and the user confirms AI Service DNS configuration
    WHEN the install command runs interactively in advanced mode
    THEN the CLI prints a description explaining Cloudflare is unsupported for AI Service
        and leaves aiservice_domain and aiservice_certificate_issuer empty.
    """
    prompts = _base_prompts(tmpdir)

    # 13. MAS DNS section: custom domain + Cloudflare
    prompts.update(
        {
            # Matches only the MAS DNS prompt — ends with "management?" not "management for AI Service?"
            r".*Configure domain.*certificate management\?.*": lambda msg: "y",
            ".*Configure custom domain.*": lambda msg: "y",
            ".*MAS top-level domain.*": lambda msg: "mas.example.com",
            ".*DNS Provider.*": lambda msg: "1",  # Cloudflare
            ".*Cloudflare e-mail.*": lambda msg: "cf@example.com",
            ".*Cloudflare API token.*": lambda msg: "testCfToken",
            ".*Cloudflare zone.*": lambda msg: "example.com",
            ".*Cloudflare subdomain.*": lambda msg: "mas",
            ".*Certificate issuer.*": lambda msg: "1",  # LetsEncrypt Production
            ".*Cluster Ingress Domain Override.*": lambda msg: "",
            # 18. AI Service DNS: user opts in; MAS provider is cloudflare → description printed, no DNS sub-prompts
            ".*Configure.*domain.*certificate management for AI Service.*": lambda msg: "y",
        }
    )

    app = run_install_test(tmpdir, _config(prompts, tmpdir))

    assert app.getParam("dns_provider") == "cloudflare"
    assert app.getParam("mas_domain") == "mas.example.com"
    assert app.getParam("aiservice_domain") == ""
    assert app.getParam("aiservice_certificate_issuer") == ""


def test_install_interactive_aiservice_cis_dns_no_mas_domain(tmpdir):
    """Test that AI Service can configure CIS DNS independently when MAS has no custom domain.

    GIVEN MAS is NOT configured with a custom domain (user answers n to Configure custom domain),
        and the user opts in to AI Service DNS configuration
    WHEN the install command runs interactively in advanced mode
    THEN the CLI prompts for the AI Service domain and DNS provider independently,
        and the AI Service certificate issuer is set from the CIS LetsEncrypt issuer.
    """
    prompts = _base_prompts(tmpdir)

    # 13. MAS DNS section: no custom domain
    prompts.update(
        {
            # Matches only the MAS DNS prompt — ends with "management?" not "management for AI Service?"
            r".*Configure domain.*certificate management\?.*": lambda msg: "y",
            ".*Configure custom domain.*": lambda msg: "n",
            # No custom domain -> optional custom certificate issuer (blank = MAS default self-signed issuer)
            ".*Custom certificate issuer name.*": lambda msg: "",
            # 18. AI Service DNS: MAS has no domain → full independent DNS flow
            ".*Configure.*domain.*certificate management for AI Service.*": lambda msg: "y",
            ".*AI Service domain.*": lambda msg: "aiservice.example.com",
            ".*DNS Provider.*": lambda msg: "1",  # IBM Cloud Internet Services (first in the AI Service list)
            ".*CIS e-mail.*": lambda msg: "cis@example.com",
            ".*CIS API token.*": lambda msg: "testCisApiKey",
            ".*CIS CRN.*": lambda msg: "crn:v1:test",
            ".*CIS subdomain.*": lambda msg: "aiservice",
            ".*Certificate issuer.*": lambda msg: "1",  # LetsEncrypt Production
            ".*Configure enhanced security for CIS.*": lambda msg: "n",
            ".*Cluster Ingress Domain Override.*": lambda msg: "",
        }
    )

    app = run_install_test(tmpdir, _config(prompts, tmpdir))

    assert app.getParam("dns_provider") == "cis"
    assert app.getParam("mas_domain") == ""
    assert app.getParam("aiservice_domain") == "aiservice.example.com"
    assert app.getParam("aiservice_certificate_issuer") == f"{app.getParam('aiservice_instance_id')}-cis-le-prod"


# ---------------------------------------------------------------------------
# buildCommand() round-trip, custom certificate issuer and Db2 storage classes
# ---------------------------------------------------------------------------


def _parseBuiltCommand(command):
    """Turn the output of buildCommand() back into argv and parse it with the install argParser."""
    lines = [line for line in command.split("\n") if not line.startswith("export ")]
    text = " ".join(line.rstrip().rstrip("\\") for line in lines)
    tokens = shlex.split(text)
    assert tokens[:2] == ["mas", "install"], f"Unexpected command prefix: {tokens[:2]}"
    flags = [token for token in tokens[2:] if token.startswith("--")]
    duplicates = sorted({flag for flag in flags if flags.count(flag) > 1})
    assert duplicates == [], f"buildCommand() emitted duplicate flags: {duplicates}"
    return installArgParser.parse_args(tokens[2:])


def test_install_interactive_custom_cluster_issuer_round_trip(tmpdir):
    """Test that a custom certificate issuer can be chosen interactively and survives buildCommand().

    GIVEN an advanced interactive install with a custom domain and no DNS integration
    WHEN the user enters a custom certificate issuer name
    THEN mas_cluster_issuer is set and the generated non-interactive command re-parses with
        the same values and no duplicated flags.
    """
    prompts = _base_prompts(tmpdir)
    prompts.update(
        {
            r".*Configure domain.*certificate management\?.*": lambda msg: "y",
            ".*Configure custom domain.*": lambda msg: "y",
            ".*MAS top-level domain.*": lambda msg: "mas.example.com",
            ".*DNS Provider.*": lambda msg: "4",  # None (I will set up DNS myself)
            ".*Custom certificate issuer name.*": lambda msg: "corporate-ca-issuer",
            ".*Configure.*domain.*certificate management for AI Service.*": lambda msg: "n",
        }
    )

    app = run_install_test(tmpdir, _config(prompts, tmpdir))

    assert app.getParam("mas_cluster_issuer") == "corporate-ca-issuer"
    assert app.getParam("dns_provider") == ""

    args = _parseBuiltCommand(app.buildCommand())
    assert args.mas_cluster_issuer == "corporate-ca-issuer"
    assert args.mas_domain == "mas.example.com"
    assert args.mas_instance_id == "inst1"
    assert args.mas_channel == app.getParam("mas_channel")
    assert args.aiservice_channel == app.getParam("aiservice_channel")
    if app.getParam("configure_aiassistant") != "":
        assert args.configure_aiassistant == app.getParam("configure_aiassistant")


def test_install_interactive_db2_storage_classes(tmpdir):
    """Test that Db2 storage classes can be customized in advanced interactive mode.

    GIVEN an advanced interactive install that installs a dedicated Db2 instance
    WHEN the user customizes storage capacity and opts in to customizing the Db2 storage classes
    THEN the db2_*_storage_class params are set and are emitted by buildCommand() in a re-parseable form.
    """
    prompts = _base_prompts(tmpdir)
    storageClasses = {
        "Data": "db2-data-sc",
        "Temporary": "db2-temp-sc",
        "Metadata": "db2-meta-sc",
        "Transaction Logs": "db2-logs-sc",
        "Backup": "db2-backup-sc",
    }
    prompts.update(
        {
            r".*Configure domain.*certificate management\?.*": lambda msg: "n",
            ".*Configure.*domain.*certificate management for AI Service.*": lambda msg: "n",
            ".*Customize storage capacity.*": lambda msg: "y",
            r".*\+ Data Volume.*": lambda msg: "100Gi",
            r".*\+ Temporary Volume.*": lambda msg: "10Gi",
            r".*\+ Metadata Volume.*": lambda msg: "10Gi",
            r".*\+ Transaction Logs Volume.*": lambda msg: "10Gi",
            r".*\+ Backup Volume.*": lambda msg: "50Gi",
            ".*Customize Db2 storage classes.*": lambda msg: "y",
        }
    )
    # Domain & certificate management is skipped entirely, so the manual certificates prompt is never shown
    prompts.pop(".*Configure manual certificates.*")
    for label, storageClass in storageClasses.items():
        prompts[rf".*\+ {label} Storage Class.*"] = lambda msg, sc=storageClass: sc

    app = run_install_test(tmpdir, _config(prompts, tmpdir))

    assert app.getParam("db2_data_storage_class") == "db2-data-sc"
    assert app.getParam("db2_temp_storage_class") == "db2-temp-sc"
    assert app.getParam("db2_meta_storage_class") == "db2-meta-sc"
    assert app.getParam("db2_logs_storage_class") == "db2-logs-sc"
    assert app.getParam("db2_backup_storage_class") == "db2-backup-sc"

    args = _parseBuiltCommand(app.buildCommand())
    assert args.db2_data_storage_class == "db2-data-sc"
    assert args.db2_meta_storage_class == "db2-meta-sc"
    assert args.db2_backup_storage_class == "db2-backup-sc"
    assert args.db2_data_storage_size == "100Gi"
