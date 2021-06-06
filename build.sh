#!/usr/bin/env sh
rm -fr dist
docker-compose -f compose-egg.yaml up --build && docker-compose -f compose-egg.yaml down
unzip -l dist/*.egg
