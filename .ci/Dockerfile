FROM python:3.8
ARG PYPI_OPTIONS="-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com"
RUN apt update && apt install libldap2-dev libsasl2-dev && apt clean
WORKDIR /app/server
COPY requirements.txt /app/server/requirements.txt
RUN sh -c "pip install -r requirements.txt ${PYPI_OPTIONS}"
