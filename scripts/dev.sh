#!/usr/bin/env sh
HOST="${HOST:-open.test.bee9527.com}"
if [ "$1" == login ]; then
  curl -k -c cookies.txt "https://${HOST}/dev/login0" -X POST -F "uuid=$2"
elif [ "$1" == dev_login ]; then
  curl -k -c cookies.txt "http://localhost:8000/dev/login0" -X POST -F "uuid=$2"
elif [ "$1" == api ]; then
  if [ -e "cookies.txt" ]; then
    curl -k -c cookies.txt -H "d-token: $(cat cookies.txt | grep -P '(?<=d-token)\s*.*' -o)" -X POST "http://localhost:8000/$2" "${@:3}"
  else
    curl -k -c cookies.txt -X POST "http://localhost:8000/$2" "${@:3}"
  fi
else
  echo "command not found"
fi
