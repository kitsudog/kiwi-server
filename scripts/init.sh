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
if [ ! -e .gitignore ]; then
  cp "${BASE_DIR}/.gitignore" .
fi
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
  cp "${BASE_DIR}/config.py.sample" config.py
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
  if [ -d "${line}/../static" ]; then
    find "${line}/../static" -type f | while read static_file; do
      source=$(python -c "import os;print(os.path.realpath('${static_file}'))")
      target=$(python -c "import os;print(os.path.realpath('static${static_file#*static}'))")
      mkdir -p "$(dirname "${target}")"
      if [ -s "${target}" ]; then
        if [ "$(md5sum "${source}" | cut -d" " -f1)" = "$(md5sum "${target}" | cut -d" " -f1)" ]; then
          echo "pass[${source}]"
        else
          echo "重复的static文件[${source}]"
        fi
      else
        python -c "import os;os.symlink(os.path.relpath('${source}', start=os.path.dirname('${target}')), '${target}')"
      fi
    done
  fi
done

MODULES=$(find -L modules -iname main.py -d 2 | cut -d/ -f2 | sort)

mkdir -p conf
python3.8 -c "
import json
import os
if os.path.exists('conf/module.conf'):
  with open('conf/module.conf') as fin:
    obj = eval(fin.read())
else:
  obj = {}
obj.update({
  'main': '''$MODULES'''.splitlines(),
})
with open('conf/module.conf', mode='w') as fout:
  fout.write(json.dumps(obj, indent=4))
"
echo SUCC

if [ ! -d venv ]; then
  python3.8 -m venv venv
fi
