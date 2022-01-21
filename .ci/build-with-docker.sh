#!/usr/bin/env sh
export IMAGE=kitsudo/kiwi-server:python-3.8

echo "image: ${IMAGE}"
set -x
if [ "${NO_GFW}" = "TRUE" ]; then
  docker build --platform linux/amd64 --progress plain . -f .ci/Dockerfile -t "${IMAGE}" --build-arg PYPI_OPTIONS=""
else
  docker build --platform linux/amd64 --progress plain . -f .ci/Dockerfile -t "${IMAGE}" --build-arg PYPI_OPTIONS="-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com"
fi