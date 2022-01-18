#!/usr/bin/env sh
export IMAGE=kitsudo/kiwi-server:python-3.8

echo "image: ${IMAGE}"
set -x
if [ "${NO_GFW}" = "TRUE" ]; then
  docker build . -f .ci/Dockerfile -t "${IMAGE}" --build-arg "BUILD_NUMBER=${BUILD_NUMBER}" --build-arg "GIT_TAG=${GIT_TAG:-dev}" --build-arg PYPI_OPTIONS=""
else
  docker build . -f .ci/Dockerfile -t "${IMAGE}" --build-arg "BUILD_NUMBER=${BUILD_NUMBER}" --build-arg "GIT_TAG=${GIT_TAG:-dev}"
fi