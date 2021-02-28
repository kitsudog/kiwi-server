#!/usr/bin/env sh
set -x
SCRIPT_DIR=$(dirname "$0")
SCRIPT_DIR=$(python -c "import os;print(os.path.realpath('${SCRIPT_DIR}'))")
echo "SCRIPT_DIR=${SCRIPT_DIR}"
cd "$SCRIPT_DIR" || exit 1
cd ../..
test "$(pwd | awk -F/ '{print $NF}')" == "project" || echo 不是项目目录
cd ..
test $# -lt 1 && exit 1
MODULE=${1#*module_}
MODULE_DIR=project/module_${MODULE}
if [ ! -x "${MODULE_DIR}" ]; then
  mkdir -p "${MODULE_DIR}"
fi
mkdir -p "${MODULE_DIR}/modules/${MODULE}"
mkdir -p "${MODULE_DIR}/modules/${MODULE}/mgr"
mkdir -p "${MODULE_DIR}/modules/${MODULE}/actions"

if [ ! -e "${MODULE_DIR}/modules/${MODULE}/main.py" ]; then
  cat <<EOF >"${MODULE_DIR}/modules/${MODULE}/main.py"
def init_server():
    pass


def prepare():
    pass
EOF
fi

if [ ! -e "${MODULE_DIR}/modules/${MODULE}/models.py" ]; then
  cat <<EOF >"${MODULE_DIR}/modules/${MODULE}/models.py"
# models
EOF
fi

"${SCRIPT_DIR}/init.sh"
