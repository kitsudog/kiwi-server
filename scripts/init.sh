#!/usr/bin/env bash
# 初始化整个项目的结构
SCRIPT_DIR=$(dirname "$0")
SCRIPT_DIR=$(python -c "import os;print(os.path.realpath('${SCRIPT_DIR}'))")
echo "SCRIPT_DIR=${SCRIPT_DIR}"
cd "$SCRIPT_DIR" || exit 1
cd ../..
test "$(pwd | awk -F/ '{print $NF}')" == "project" || echo 不是项目目录
cd ..
BASE_DIR=project/kiwi_server
# shellcheck disable=SC2226
ln -sF "${BASE_DIR}/app.py"
# shellcheck disable=SC2226
ln -sF "${BASE_DIR}/.dockerignore"
# shellcheck disable=SC2226
ln -sF "${BASE_DIR}/.gitignore"
# shellcheck disable=SC2226
ln -sF "${BASE_DIR}/Dockerfile"
# shellcheck disable=SC2226
ln -sF "${BASE_DIR}/migrate.py"
# shellcheck disable=SC2226
ln -sF "${BASE_DIR}/base"
# shellcheck disable=SC2226
ln -sF "${BASE_DIR}/frameworks"
if [ ! -e requirements.txt ]; then
  cp "${BASE_DIR}/requirements.txt" .
fi
if [ ! -e alembic.ini ]; then
  cp "${BASE_DIR}/alembic.ini" .
fi
if [ ! -e config.py ]; then
  cp "${BASE_DIR}/config.py" .
fi

if [ ! -d migrations ]; then
  cp -r "${BASE_DIR}/migrations" .
fi

mkdir -p modules
if [ ! -x modules/__init__.py ]; then
  cat <<EOF >modules/__init__.py
EOF
fi

find project -type d -iname modules | while read line; do
  # shellcheck disable=SC2012
  ln -sF "../${line}/$(ls "${line}" | head -n1)" modules/
done

MODULES=$(find -L modules -iname main.py -d 2 | cut -d/ -f2 | sort)

mkdir -p conf
cat <<EOF >conf/module.conf
{
    "main":$(echo "$MODULES" | python -c"import sys,json;print(json.dumps(sys.stdin.read().splitlines()))"),
}
EOF
echo SUCC

if [ ! -d venv ]; then
  python3.8 -m venv venv
fi
