#!/bin/bash
# Assetize fork-only: build the MAS CLI container image from the three Assetize forks.
#
#   assetize-mas-cli        (this repo)  -> mas-cli python package, bash "mas", Tekton definitions
#   assetize-python-devops               -> mas-devops python package
#   assetize-ansible-devops              -> ibm.mas_devops Ansible collection
#
# The image is IBM's image/cli/Dockerfile unchanged; the forks' builds are dropped into
# image/cli/install/ as local archives, which the image's install scripts prefer over
# PyPI / Galaxy / IBM Artifactory. Every reference to quay.io/ibmmas/cli in what the image
# ships (Tekton task images, airgap digest lookup, in-cluster deployment template) is
# rewritten to $IMAGE so OpenShift Pipelines run this image, not IBM's.
#
# Usage:
#   assetize/image/build.sh
#
# Environment:
#   PYTHON_DEVOPS_DIR   path to assetize-python-devops   (default: ../assetize-python-devops)
#   ANSIBLE_DEVOPS_DIR  path to assetize-ansible-devops  (default: ../assetize-ansible-devops)
#   IMAGE               image repository                 (default: ghcr.io/softwarecomparereview/mas-cli)
#   IMAGE_TAG           image tag                        (default: assetize-<yyyymmdd>-<cli short sha>)
#   EXTRA_TAGS          space separated additional tags  (default: none)
#   PLATFORM            docker platform                  (default: linux/amd64)
#   PUSH                "true" to push instead of loading into the local docker (default: false)
#   STAGE_DIR           working directory                (default: a new temp directory)
set -euo pipefail

CLI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_DEVOPS_DIR="$(cd "${PYTHON_DEVOPS_DIR:-$CLI_DIR/../assetize-python-devops}" && pwd)"
ANSIBLE_DEVOPS_DIR="$(cd "${ANSIBLE_DEVOPS_DIR:-$CLI_DIR/../assetize-ansible-devops}" && pwd)"
IMAGE="${IMAGE:-ghcr.io/softwarecomparereview/mas-cli}"
CLI_SHA="$(git -C "$CLI_DIR" rev-parse --short=8 HEAD)"
IMAGE_TAG="${IMAGE_TAG:-assetize-$(date -u +%Y%m%d)-$CLI_SHA}"
EXTRA_TAGS="${EXTRA_TAGS:-}"
PLATFORM="${PLATFORM:-linux/amd64}"
PUSH="${PUSH:-false}"
STAGE_DIR="${STAGE_DIR:-$(mktemp -d)}"
PYTHON="${PYTHON:-python3}"

# PEP 440 / semver friendly package versions that still identify the exact commits
PY_DEVOPS_SHA="$(git -C "$PYTHON_DEVOPS_DIR" rev-parse --short=8 HEAD)"
ANSIBLE_SHA="$(git -C "$ANSIBLE_DEVOPS_DIR" rev-parse --short=8 HEAD)"
CLI_PKG_VERSION="100.0.0+assetize.$CLI_SHA"
PY_DEVOPS_PKG_VERSION="100.0.0+assetize.$PY_DEVOPS_SHA"
ANSIBLE_PKG_VERSION="100.0.0-assetize.$ANSIBLE_SHA"

echo "== Assetize MAS CLI image build"
echo "   image ............. $IMAGE:$IMAGE_TAG ${EXTRA_TAGS:+(+ $EXTRA_TAGS)}"
echo "   cli ............... $CLI_DIR @ $CLI_SHA"
echo "   python-devops ..... $PYTHON_DEVOPS_DIR @ $PY_DEVOPS_SHA"
echo "   ansible-devops .... $ANSIBLE_DEVOPS_DIR @ $ANSIBLE_SHA"
echo "   stage ............. $STAGE_DIR"

# 1. Stage clean copies of the committed sources (uncommitted changes are not built)
# -----------------------------------------------------------------------------
for repo in cli python-devops ansible-devops; do
  case $repo in
    cli) src=$CLI_DIR ;;
    python-devops) src=$PYTHON_DEVOPS_DIR ;;
    ansible-devops) src=$ANSIBLE_DEVOPS_DIR ;;
  esac
  rm -rf "${STAGE_DIR:?}/$repo" && mkdir -p "$STAGE_DIR/$repo"
  git -C "$src" archive HEAD | tar -x -C "$STAGE_DIR/$repo"
done
rm -rf "${STAGE_DIR:?}"/dist-* "$STAGE_DIR"/mas_cli.contents
S="$STAGE_DIR/cli"
INSTALL_DIR="$S/image/cli/install"

# 2. Stamp versions and point every CLI image reference at $IMAGE
# -----------------------------------------------------------------------------
sed -i "s#__version__ = \"100.0.0\"#__version__ = \"$CLI_PKG_VERSION\"#" "$S/python/src/mas/cli/__init__.py"
sed -i "s#self.version: str = \"100.0.0-pre.local\"#self.version: str = \"$IMAGE_TAG\"#" "$S/python/src/mas/cli/cli.py"
grep -q "self.version: str = \"$IMAGE_TAG\"" "$S/python/src/mas/cli/cli.py" || { echo "Failed to stamp the CLI version in cli.py"; exit 1; }
sed -i "s#VERSION=\"\${VERSION:-latest}\"#VERSION=$IMAGE_TAG#" "$S/image/cli/mascli/mas"
sed -i "s#quay.io/ibmmas/cli:#$IMAGE:#g; s#quay.io/ibmmas/cli@#$IMAGE@#g" "$S/python/src/mas/cli/cli.py"
sed -i "s#quay.io/ibmmas/cli:latest#$IMAGE:$IMAGE_TAG#g" "$S/image/cli/mascli/templates/deployment.yaml"
sed -i "s#^__version__ = \"100.0.0\"#__version__ = \"$PY_DEVOPS_PKG_VERSION\"#" "$STAGE_DIR/python-devops/src/mas/devops/__init__.py"
sed -i "s#^version: 100.0.0#version: $ANSIBLE_PKG_VERSION#" "$STAGE_DIR/ansible-devops/ibm/mas_devops/galaxy.yml"

# 3. Tekton definitions (tasks run $IMAGE:$IMAGE_TAG)
# -----------------------------------------------------------------------------
(cd "$S" && DEV_MODE=true VERSION="$IMAGE_TAG" bash build/bin/build-tekton.sh > "$STAGE_DIR/build-tekton.log" 2>&1) \
  || { tail -50 "$STAGE_DIR/build-tekton.log"; exit 1; }
for f in "$S/tekton/target/ibm-mas-tekton.yaml" "$S/tekton/target/ibm-mas-tekton-fvt.yaml" \
         "$S/image/cli/mascli/templates/ibm-mas-tekton.yaml" "$S/python/src/mas/cli/templates/ibm-mas-tekton.yaml"; do
  sed -i "s#quay.io/ibmmas/cli:$IMAGE_TAG#$IMAGE:$IMAGE_TAG#g" "$f"
done
if grep -q "quay.io/ibmmas/cli" "$S/python/src/mas/cli/templates/ibm-mas-tekton.yaml"; then
  echo "Tekton definitions still reference quay.io/ibmmas/cli"; exit 1
fi
echo "   tekton ............ $(grep -c "image: \"$IMAGE:$IMAGE_TAG\"" "$S/python/src/mas/cli/templates/ibm-mas-tekton.yaml") task steps use $IMAGE:$IMAGE_TAG"

# 4. Build the three packages into image/cli/install/
# -----------------------------------------------------------------------------
"$PYTHON" -m build --sdist --outdir "$STAGE_DIR/dist-cli" "$S" > "$STAGE_DIR/build-cli.log" 2>&1 || { tail -30 "$STAGE_DIR/build-cli.log"; exit 1; }
cp "$STAGE_DIR"/dist-cli/mas_cli-*.tar.gz "$INSTALL_DIR/mas_cli.tar.gz"
# (list to a file first: "tar | grep -q" fails under pipefail when grep exits early)
tar -tzf "$INSTALL_DIR/mas_cli.tar.gz" > "$STAGE_DIR/mas_cli.contents"
grep -q "templates/ibm-mas-tekton.yaml" "$STAGE_DIR/mas_cli.contents" || { echo "mas_cli sdist is missing the Tekton definitions"; exit 1; }

"$PYTHON" -m build --sdist --outdir "$STAGE_DIR/dist-devops" "$STAGE_DIR/python-devops" > "$STAGE_DIR/build-devops.log" 2>&1 || { tail -30 "$STAGE_DIR/build-devops.log"; exit 1; }
cp "$STAGE_DIR"/dist-devops/mas_devops-*.tar.gz "$INSTALL_DIR/mas_devops.tar.gz"

ansible-galaxy collection build "$STAGE_DIR/ansible-devops/ibm/mas_devops" --output-path "$STAGE_DIR/dist-ansible" --force > "$STAGE_DIR/build-ansible.log" 2>&1 \
  || { tail -30 "$STAGE_DIR/build-ansible.log"; exit 1; }
cp "$STAGE_DIR"/dist-ansible/ibm-mas_devops-*.tar.gz "$INSTALL_DIR/ibm-mas_devops.tar.gz"

# The image build copies rbac/ from the build context (IBM CI copies it in the same way)
rm -rf "$S/image/cli/rbac" && cp -r "$S/rbac" "$S/image/cli/rbac"

ls -l "$INSTALL_DIR"/*.tar.gz

# 5. Build the image
# -----------------------------------------------------------------------------
TAG_ARGS=(-t "$IMAGE:$IMAGE_TAG")
for t in $EXTRA_TAGS; do TAG_ARGS+=(-t "$IMAGE:$t"); done
OUTPUT_ARG="--load"
[[ "$PUSH" == "true" ]] && OUTPUT_ARG="--push"

docker buildx build "$S/image/cli" \
  --platform "$PLATFORM" \
  --build-arg "VERSION_LABEL=$IMAGE_TAG" \
  --label "org.opencontainers.image.source=https://github.com/softwarecomparereview/assetize-mas-cli" \
  --label "org.opencontainers.image.revision=$(git -C "$CLI_DIR" rev-parse HEAD)" \
  --label "au.com.assetize.python-devops.revision=$(git -C "$PYTHON_DEVOPS_DIR" rev-parse HEAD)" \
  --label "au.com.assetize.ansible-devops.revision=$(git -C "$ANSIBLE_DEVOPS_DIR" rev-parse HEAD)" \
  --label "quay.expires-after=" \
  "${TAG_ARGS[@]}" \
  "$OUTPUT_ARG"

echo "== Built $IMAGE:$IMAGE_TAG"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "image=$IMAGE:$IMAGE_TAG" >> "$GITHUB_OUTPUT"
  echo "tag=$IMAGE_TAG" >> "$GITHUB_OUTPUT"
fi
