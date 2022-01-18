#!/usr/bin/env sh
export VERSION=v${BUILD_NUMBER:-0.1}
export IMAGE=${IMAGE:-${JOB_BASE_NAME:-local}:${VERSION}}

echo "image: ${IMAGE}"
set -x
if [ "${NO_GFW}" = "TRUE" ]; then
  docker build . -f .ci/Dockerfile -t "${IMAGE}" --build-arg "BUILD_NUMBER=${BUILD_NUMBER}" --build-arg "GIT_TAG=${GIT_TAG:-dev}" --build-arg PYPI_OPTIONS=""
else
  docker build . -f .ci/Dockerfile -t "${IMAGE}" --build-arg "BUILD_NUMBER=${BUILD_NUMBER}" --build-arg "GIT_TAG=${GIT_TAG:-dev}"
fi

