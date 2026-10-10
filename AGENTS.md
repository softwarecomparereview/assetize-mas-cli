# AGENTS.md — Repository Guide for LLMs and New Contributors

> Purpose: give an AI agent (or a new human) everything needed to work in this repo
> **without re-reading the whole codebase**. Read this first; open source files only
> for the specific area you are changing.
>
> **Rule:** this file, `CLAUDE.md` and any other AI-agent file are fork-only —
> never add them to an upstream (`ibm-mas/*`) contribution. See §12.
>
> Snapshot: written against upstream commit `af88cb2` (2026-10-09, latest catalog
> `v9-261007`). Verify anything version-specific before relying on it.

---

## 1. What this repository is

- **A fork of [`ibm-mas/cli`](https://github.com/ibm-mas/cli)** — IBM's official
  admin CLI for **IBM Maximo Application Suite (MAS)** on OpenShift. Fork remote:
  `softwarecomparereview/assetize-mas-cli`. At the time of writing the fork contains
  **no Assetize-specific changes**; `master` is identical to upstream (clone is shallow,
  ~50 commits).
- Licence: **EPL-1.0** (IBM copyright headers on every file).
- Published artefacts (upstream): PyPI `mas-cli`, container image `quay.io/ibmmas/cli`,
  docs at <https://ibm-mas.github.io/cli/>.
- It is one of **three cooperating repos**:

| Repo | What it provides | How this repo consumes it |
|---|---|---|
| `ibm-mas/ansible-devops` | Ansible collection `ibm.mas_devops` — the roles that actually install/configure everything | Installed into the container image; every Tekton task runs a role from it |
| `ibm-mas/python-devops` | PyPI `mas-devops` (`mas.devops.*`) — k8s helpers, catalog data, Tekton launch logic, PipelineRun templates | Python dependency (`mas-devops >= 9.0.0`) |
| `ibm-mas/cli` (this) | The user-facing CLI (Python `mas-cli` + bash `mas`), Tekton task/pipeline definitions, container image, docs, catalog manifests | — |

Assetize forks (all use the same working branch name for cross-repo changes):
`softwarecomparereview/assetize-mas-cli` (this), `softwarecomparereview/assetize-python-devops`,
`paananiruddh/assetize-ansible-devops`. Each carries its own `AGENTS.md` and the pre-push guard.

Other upstream repos referenced: `ibm-mas/cli-base` (base image), `ibm-mas/pre-install`
(pre-install RBAC), `ibm-mas/image-set-configs` (oc-mirror configs), `ibm-mas/gitops`
(ArgoCD ApplicationSets consumed by `mas gitops-*`).

When changing behaviour across repos, upstream convention is to use **the same branch
name in all three repos** so CI picks up matching builds.

---

## 2. Mental model (the one diagram to remember)

```
user ──► mas (bash, /mascli/mas in the container image)
          ├─ provision-*, mirror-images, configure-airgap, gitops-*, debug ... → bash functions → ansible-playbook ibm.mas_devops.*
          └─ install|update|upgrade|uninstall|backup|restore|mirror|must-gather|setup-rbac|pre-install|aiservice-*
                 └─► mas-cli (Python, python/src/mas/cli)
                       1. prompt (interactive) or parse flags (non-interactive)
                       2. build flat dict self.params
                       3. mas.devops.tekton: install OpenShift Pipelines, create namespace,
                          apply ibm-mas-tekton.yaml, create secrets, launch PipelineRun
                              └─► Tekton Pipeline (tekton/src/pipelines/*.yml.j2)
                                    └─► Task (tekton/src/tasks/**) in image quay.io/ibmmas/cli:<ver>
                                          └─► /opt/app-root/src/run-role.sh <role>
                                                └─► ansible-playbook ibm.mas_devops.run_role  (ROLE_NAME=<role>)
```

Key invariant: **Tekton param → UPPERCASE env var → ibm.mas_devops role variable.**
Adding a new install option normally touches: Python argParser/params/prompt →
pipeline params (`tekton/src/params`) → task params+env (`tekton/src/tasks`) → the
role in ansible-devops.

Exceptions that do **not** use Tekton: `mas-cli mirror` (runs `oc-mirror`/`helm`
locally), `mas-cli must-gather` (pure kubernetes client), the bash provisioning,
mirroring, gitops and debug commands.

---

## 3. Directory map

| Path | Contents |
|---|---|
| `python/src/mas/cli/` | Python CLI package (`mas-cli`) — see §4 |
| `python/tests/` | pytest suites: `unit/` (mostly must-gather) and `integration/` (scripted end-to-end app runs) |
| `image/cli/` | Container image: `Dockerfile`, `install/` (build-time install scripts), `app-root/src/` (Tekton step wrappers, FVT result scripts), `mascli/` (bash `mas` + functions + templates), `masfvt/` (FVT launcher playbooks), `usr/bin/gather` (`oc adm must-gather` entrypoint) |
| `tekton/` | Jinja2 sources for Tekton Tasks/Pipelines, generator playbooks, JSON schemas + `test_schema.py` |
| `catalogs/` | One OLM `CatalogSource` YAML per IBM Maximo operator catalog release (`v9-YYMMDD-<arch>.yaml`, legacy `v8-*`) |
| `docs/` + `mkdocs.yml` + `mkdocs_plugins/` | mkdocs (carbon theme) site; custom plugins render catalog pages and CLI usage |
| `rbac/install/` | Kustomize bundle of minimal RBAC for a non-cluster-admin install |
| `build/` | Build scripts (versioning, image build, tekton build, docs, artifactory upload) |
| `.github/` | Workflows, CODEOWNERS (`@ibm-mas/pr-review-team`), issue templates, `fetch-artifactory-token` action |
| `.assetize/` | Fork-only Assetize tooling (git hooks). Never pushed upstream |
| `.bob/` | Config for IBM's internal "Bob" AI assistant: rules, skills, dated plan files (useful coding conventions — see §10) |
| `Makefile`, `pyproject.toml`, `pytest.ini`, `.flake8`, `.pre-commit-config.yaml`, `.secrets.baseline` | Tooling |

---

## 4. Python CLI (`python/src/mas/cli`)

### 4.1 Entry point and commands
- `pyproject.toml`: `mas-cli = "mas.cli.__main__:main"`; Python ≥ 3.12; deps
  `mas-devops>=9.0.0`, `kubernetes==33.1.0`, prompt_toolkit, halo, alive-progress,
  tabulate, prettytable, jsonpath-ng.
- `__main__.py` `main()` dispatches on `argv[1]` with **lazy imports** and catches
  `ApiException`, `MaxRetryError`, `TemplateNotFound`.

| Command | Module / class | Tekton namespace |
|---|---|---|
| `install` | `install/app.py` `InstallApp` (3.2k lines) | `mas-<id>-pipelines` |
| `update` | `update/app.py` `UpdateApp` | `mas-pipelines` (cluster-wide) |
| `upgrade` | `upgrade/app.py` `UpgradeApp` | `mas-<id>-pipelines` |
| `uninstall` | `uninstall/app.py` `UninstallApp` | `mas-<id>-pipelines` |
| `backup` / `restore` | `backup/app.py`, `restore/app.py` | `mas-<id>-pipelines` |
| `mirror` | `mirror/app.py` `MirrorApp` (oc-mirror v2, m2m/m2d/d2m) | none |
| `must-gather` | `must_gather/app.py` `MustGatherApp` | none |
| `setup-rbac` | `setup_rbac/app.py` (applies `rbac/install`) | `mas-<id>-pipelines` |
| `pre-install` | `pre_install/app.py` (per-app pre-install RBAC) | — |
| `aiservice-install` / `aiservice-upgrade` | `aiservice/install|upgrade/app.py` | `aiservice-<id>-pipelines` |

Each command has `<cmd>/argParser.py` (argparse). `usage()` in `__main__.py` does not
list `restore`, `aiservice-install`, `aiservice-upgrade`.

### 4.2 `BaseApp` (`cli.py`)
- Mixes in `PrintMixin` / `PromptMixin` (`displayMixins.py`): `printH1/H2`,
  `printSummary`, `yesOrNo`, `promptForString/Int/ListSelect/File/Dir`.
- Logging → rotating `./mas.log` (5 MB × 2).
- Static data that encodes MAS release knowledge:
  - `compatibilityMatrix` — core channel → allowed app channels (e.g. core `9.2.x`
    allows manage `9.2.x`, `9.2.x-feature`, `9.1.x`).
  - `licenses` — per-channel licence URLs.
  - `upgrade_path` — channel → next channel.
  - `version` placeholder `100.0.0-pre.local`, stamped at build.
- k8s: `dynamicClient` (in-cluster or kubeconfig); `connect()` prompts for
  server/token if needed; requires `kubectl` on PATH; architecture must be amd64,
  s390x or ppc64le.
- `isAirgap()` hard-fails on legacy `ImageContentSourcePolicy` (must use IDMS).
- `createTektonFileWithDigest()` pins the CLI image by digest (airgap or
  `--use-cli-digest`) using `skopeo inspect`.
- `self.params` / `setParam` / `getParam` = the PipelineRun params (unset → `""`).
- Approval gates: `approval-<id>` ConfigMaps (`MAX_RETRIES`, `DELAY`,
  `IGNORE_FAILURE`, `STATUS`).
- Entitlement key validated via `mas.devops.utils.validateIBMEntitlementKey`.
- `validators.py` — prompt_toolkit validators (instance ID, workspace ID, storage
  class, JSON, language, bucket prefix, AI service instance/tenant).

### 4.3 Install flow (`install/app.py`)
`InstallApp(BaseApp, InstallSettingsMixin, InstallSummarizerMixin, ConfigGeneratorMixin, installArgBuilderMixin)`;
settings mixins live in `install/settings/` (Db2, MongoDb, Kafka, Manage,
AdditionalConfigs, AI).

1. Parse args. **No `--mas-instance-id` ⇒ interactive** (`interactiveMode()`);
   otherwise `nonInteractiveMode()` validates `requiredParams` / copies
   `optionalParams` from `install/params.py`.
2. Catalog choice limited to `install/catalogs.py` `supportedCatalogs` (latest 4 per
   arch); catalog metadata comes from `mas.devops.data.getCatalog`.
3. Interactive order: catalog → licence → SNO/storage → SLS/DRO/ICR → admin mode &
   pre-install RBAC → cert-manager → core → apps → per-app settings → ArcGIS, MongoDB,
   Db2, Kafka, AI, Grafana.
4. Extras: `--additional-configs` dir (special filenames switch Mongo/Kafka to BYO),
   `--pod-templates best-effort|guaranteed|<dir>` (`templates/pod-templates/`),
   Jinja templates in `templates/*.j2` rendered by `gencfg.py` (JDBC, AI, Mongo,
   Facilities configs).
5. `buildCommand()` (`install/argBuilder.py`) prints the equivalent non-interactive
   command — useful for reproducible installs.
6. `displayInstallSummary()` → confirm → launch: install OpenShift Pipelines → create
   namespace → `preparePipelinesNamespace` → `prepareInstallSecrets` → approvals →
   `updateTektonDefinitions` → `launchInstallPipeline(params)` (returns PipelineRun URL).
   **The PipelineRun template itself lives in `mas-devops`, not here.**

### 4.4 must-gather (`must_gather/`, design in `must_gather/README.md`)
- Subcommands `collect` (default), `serve` (local web viewer), `summarize`.
- Collectors: `ocp, db2, kafka, mongodb, cp4d, cert-manager, grafana, sls, mas,
  rhoai, aiservice, lic, pipelines, amlen` (`--collectors`).
- Phases: CRD processing → `planCollection` (CollectionPlan of task tuples) →
  `parallel_executor` (ThreadPool 50, thread-local DynamicClient) → summaries
  (`summarizer/{subscriptions,nodes,suite,licensing}`) + `web_viewer` → tar.gz,
  optional Artifactory upload. Secrets' `data` is always stripped.
- Does **not** depend on `mas.devops`.

### 4.5 `mas.devops` functions used (python-devops)
`ocp` (connect, namespaces, storage classes, cluster version, path-based routing),
`mas` (instances, channels, catalog, installed apps, airgap), `data` (catalog data),
`sls`, `aiservice`, `utils` (`isVersionEqualOrAfter`, entitlement check),
`tekton` (pipelines install, secrets prep, all `launch*Pipeline` functions),
`pre_install` (`applyPreInstallMASRBAC`). If a behaviour is not in this repo, it is
probably in `mas.devops`.

---

## 5. Container image and bash `mas` (`image/cli`)

- `Dockerfile` FROM `quay.io/ibmmas/cli-base:latest` (oc, ansible, python 3.12, aws,
  ibmcloud, jq/yq, jinjanate come from the base image). Copies `app-root/src`,
  `rbac/` (copied in by CI), `mascli/`, `masfvt/`, `usr/bin`. `PATH=/mascli:$PATH`.
- Build-time `install/` scripts:
  - `install-python-packages.sh` — installs `mas_cli.tar.gz`; `mas-devops` from a local
    tarball → matching python-devops git branch (`master`→`stable`) → PyPI.
  - `install-ansible-collections.sh` — `ibm.mas_devops` from local tarball → Artifactory
    branch build (IBM-internal) → Ansible Galaxy (always for tag builds).
  - `pre-install-rbac.sh` — clones `ibm-mas/pre-install`.
- **bash `mas`** (`mascli/mas`): big `case`. Delegates to Python `mas-cli` for
  install/update/upgrade/uninstall/mirror/must-gather/backup/restore/setup-rbac/
  pre-install/aiservice-*. Bash-only commands (implementations in `mascli/functions/`):
  - Provisioning: `provision-fyre`, `provision-roks`, `provision-roks-vpc`, `provision-aws`
  - Registry/airgap: `setup-registry`, `teardown-registry`, `mirror-images`,
    `aiservice-mirror-images`, `mirror-redhat-images`, `configure-airgap`,
    `aiservice-configure-airgap`
  - `configtool-oidc`, `debug` (Liberty core/thread dumps, HAProxy logging)
  - `gitops-*` (~60 commands): non-interactive generators that render Jinja templates
    (`mascli/templates/gitops/`) into a GitHub "config repo" laid out
    `<account>/<cluster>/<instance>/…` for ArgoCD ApplicationSets (`ibm-mas/gitops`);
    secrets live in **AWS Secrets Manager** and are resolved by ArgoCD Vault Plugin;
    `gitops-iac-*` generate Terraform (EFS, S3, MSK, RDS Db2); Redis locking, git
    push retries, PR automation in `functions/gitops_utils`.
- `mascli/backup-restore/` (legacy scripts), `mascli/db-scripts/facilities/` (external
  Db2/MSSQL/Oracle prep for Real Estate & Facilities), `mascli/image-validation/`
  (IBM signing keys + `policy.json`), `mascli/templates/deployment.yaml` (run CLI as an
  in-cluster Deployment).
- `masfvt/` — Ansible playbooks that create FVT PipelineRuns (IBM internal test
  infra: MongoDB result store, Jira, Artifactory-hosted test images).
- `app-root/src/run-role.sh` / `run-playbook.sh` — the generic Tekton step wrappers.

---

## 6. Tekton (`tekton/`)

- All sources are Jinja2 (`*.yml.j2`) rendered by Ansible.
- Tasks: `tekton/src/tasks/{dependencies,aiservice,fvt,fvt-launcher,gitops,framework,ocp,ivt,common}` plus `suite-*`.
  - Every task includes `common/cli-params.yml.j2` and `common/cli-env.yml.j2`
    via `{{ lookup('template', …) | indent(N) }}`.
  - Single step: `command: [/opt/app-root/src/run-role.sh, <role>]`,
    `image: quay.io/ibmmas/cli:latest` (rewritten to the release tag at build).
- Pipelines: `tekton/src/pipelines/*.yml.j2` (+ `gitops/`), params composed from
  `tekton/src/params/*.yml.j2`, task snippets from `pipelines/taskdefs/**`.
  Main: `mas-install`, `mas-update`, `mas-upgrade`, `mas-uninstall`, `mas-backup`,
  `mas-restore`, `aiservice-upgrade`, many `mas-fvt-*`, `gitops-*`.
- Generators: `generate-tekton-tasks.yml` (**new tasks must be added to its
  `with_items` lists**), `generate-tekton-pipelines.yml` (`all_pipelines`; supports
  `-e pipeline_name=X`; gitops pipelines rendered 3 ways).
- `build/bin/build-tekton.sh` (`make tekton`) renders, concatenates into
  `tekton/target/ibm-mas-tekton.yaml` (+ `ibm-mas-tekton-fvt.yaml`) and copies into
  `python/src/mas/cli/templates/` and `image/cli/mascli/templates/` (both
  git-ignored/generated).
- Validate: `pytest tekton/test_schema.py -v` (JSON-schema check of generated YAML).
- Detailed rules: `.bob/rules/tekton-development.md`.

---

## 7. Catalogs (`catalogs/`, `docs/catalogs/`)

- Each file is an OLM `CatalogSource` named `ibm-operator-catalog` in
  `openshift-marketplace` pointing at
  `icr.io/cpopen/ibm-maximo-operator-catalog@sha256:…` (`v8-amd64.yaml` is the
  dynamic tag-based one). Monthly-ish cadence plus interim updates.
- The Python CLI does **not** read these files: catalog metadata (operator channels,
  OCP compatibility, what's new, known issues) comes from `mas.devops.data`.
  The CLI only allows the 4 newest catalogs (`install/catalogs.py`).
- Adding a catalog (upstream pattern, see commit `0c6684b`): add the 3 arch YAMLs,
  `docs/catalogs/<tag>.md`, update `install/catalogs.py`, `mkdocs.yml` nav, and the
  corresponding data in python-devops.
- Docs pages use `:::mas-catalog-*` directives expanded by
  `mkdocs_plugins/mkdocs_mas_catalogs` from `mas.devops.data`.

---

## 8. Build, versioning, CI

- Versioning: commit/PR title prefix **`[major]` / `[minor]` / `[patch]`** (and
  `[skip ci]`, `[doc]` to deploy docs). `build/bin/initbuild.sh` computes semver;
  branch builds are `x.y.z-pre.<branch>`. (`build/README.md` still mentions Travis;
  CI is GitHub Actions.)
- Workflows: `build-cli.yml` (tekton → python lint/test/build → per-arch image build
  with OpenSCAP scan → quay.io push → multi-arch manifest → PyPI on release),
  `docs.yml`, `pre-commit.yml`, `tekton-validation.yml`, `tekton-cleanup.yml`,
  `verify-cli-pr.yml`.
- **On this fork most of `build-cli.yml` will fail**: it needs IBM secrets
  (`IBM_CLOUD_APIKEY`, IBM Secrets Manager → Artifactory token, quay.io credentials,
  PyPI token, IBM OCP cluster for tekton-cleanup). `pre-commit`, `tekton-validation`
  and `verify-cli-pr` work without secrets. Docs build pulls data from upstream
  `ibm-mas`.

---

## 9. Local development cheatsheet

```bash
# Python
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # pulls mas-devops from PyPI
.venv/bin/pytest python/tests              # all
.venv/bin/pytest -m unit                   # or: integration, install, update, upgrade, mirror, must-gather
# Tekton
make tekton                                # renders + schema-tests (needs ansible)
# Lint (also enforced by pre-commit)
pre-commit run -a                          # black (160 cols), flake8, basedpyright (must_gather), detect-secrets
# Docs
make mkdocs-serve                          # expects ../python-devops checked out alongside
# Run the released CLI
podman run -ti --rm -e IBM_ENTITLEMENT_KEY quay.io/ibmmas/cli:latest bash
```

- Integration tests drive the real apps with prompts scripted by
  `tests/integration/utils/prompt_tracker.py` (`PromptTracker` regex → answer, asserts
  every handler fired) and mock k8s + `mas.devops` launch functions
  (`install_test_helper.py`). No tests exist for backup, restore, uninstall,
  setup-rbac, pre-install.
- detect-secrets uses IBM's fork with `--fail-on-unaudited`; any new secret-looking
  string must be added/audited in `.secrets.baseline`.

---

## 10. Conventions (from CONTRIBUTING.md and `.bob/rules`)

- Python 3.12, Black line length 160, flake8 (`E501, E203, D` ignored).
- Naming: snake_case modules, **camelCase functions/variables**, PascalCase classes.
- Keep files under ~600 lines (new code), TDD with pytest, Given-When-Then test
  docstrings.
- Tekton params default to `""`, always have a `description`; reuse
  `storage_class_rwo/rwx`.
- Every source file carries the IBM EPL copyright header
  (`build/update-copyright-headers.py`).
- Plans for non-trivial work go in `.bob/plans/YYYY-MM-DD-<topic>.md`.

---

## 11. Known issues found during review (candidates for upstream PRs)

| Where | Issue |
|---|---|
| `python/src/mas/cli/install/app.py:3124` | `self.warningIcon` is never defined → `AttributeError` if enabling the Pipelines console plugin fails |
| `python/src/mas/cli/install/app.py:3101-3103` | "installation failed" spinner uses `successIcon` |
| `build/bin/build-cli.sh:16` | `chmod ug+x …/mascli/must-gather/*` — directory no longer exists; fails under `set -e` |
| `python/src/mas/cli/__main__.py` `usage()` | omits `restore`, `aiservice-install`, `aiservice-upgrade` |
| `build/README.md` | describes Travis; CI is GitHub Actions |
| `python/tests` | no coverage for backup, restore, uninstall, setup-rbac, pre-install |

---

## 12. Working on this fork (Assetize notes)

> **HARD RULE — never contribute AI-agent files upstream.**
> Never include our own AI-agent / assistant files in any commit, branch or PR
> targeting `ibm-mas/*` (or any other upstream). This covers, at minimum:
> `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.cursor*`, `.github/copilot-instructions.md`,
> `.windsurf*`, `.aider*`, `GEMINI.md`, `.assetize/`, and any other agent prompt,
> rule, skill, memory or plan file we add. They are fork-only. Before opening an
> upstream PR, check `git diff --name-only upstream/master...HEAD` and drop any such file.
>
> **Enforced by a pre-push hook** — run once per clone:
> `.assetize/install-hooks.sh`. It blocks any push to a remote whose URL is not
> `github.com/softwarecomparereview/*` or `github.com/paananiruddh/assetize-*` (override with `ASSETIZE_FORK_PATTERN`) if the
> pushed tree, or any commit being pushed, contains one of these paths. Never bypass
> it with `--no-verify`. When adding a new agent-file type, add it to the pattern in
> `.assetize/hooks/pre-push` as well as to the list above.
> (Upstream's own `.bob/` directory is theirs — leave it untouched unless the
> upstream change genuinely requires it.)

- Keep `master` a clean mirror of upstream; put Assetize-specific work on branches or
  in separate directories so upstream merges stay conflict-free.
- Upstream contributions: branch from upstream `master`, use `[patch]/[minor]` titles,
  no Assetize branding in upstream PRs, include tests, follow §10.
- Before changing CI on the fork, decide whether to disable the IBM-secret jobs or
  gate them with `if: github.repository == 'ibm-mas/cli'`.
