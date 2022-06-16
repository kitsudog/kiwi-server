FROM python:3.8
RUN apt update && apt -y install libldap2-dev libsasl2-dev && apt clean
WORKDIR /app/server
COPY requirements.txt /app/kiwi/requirements.txt
ARG PYPI_OPTIONS
RUN sh -c "cd /app/kiwi;pip install --no-cache-dir --disable-pip-version-check -r requirements.txt ${PYPI_OPTIONS}"
COPY . /app/kiwi
RUN cd /app/kiwi && echo "__version__ = '0.0.0'" > _version.py && python setup.py install && rm -fr /app/kiwi
EXPOSE 8000
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/server \
    PYTHON_PRETTY_ERRORS_ISATTY_ONLY=1 \
    LANG=C.UTF-8 \
    MONGO_HOST=mongo \
    REDIS_HOST=redis \
    DB_HOST=mysql \
    IMAGE_DEBUG=FALSE \
    DEBUG=FALSE \
    VIRTUAL_PORT=8000 \
    TZ=Asia/Shanghai

ONBUILD ARG PYPI_OPTIONS
ONBUILD ARG GIT_TAG=no-tag
ONBUILD ARG LOG_NAME=server
ONBUILD ARG DB_NAME=kiwi
ONBUILD ARG SPRING_CLOUD_CONFIG_SERVER_URL
ONBUILD ENV LOG_NAME=$LOG_NAME \
    SPRING_CLOUD_CONFIG_SERVER_URL=$SPRING_CLOUD_CONFIG_SERVER_URL \
    DB_NAME=$DB_NAME \
    GIT_TAG=$GIT_TAG
CMD sh -c "test '$IMAGE_DEBUG' = TRUE && (echo image debug...;tail -f /dev/stdout) || (python -m kiwi --tag=$GIT_TAG )"

