FROM python:3.8
ARG PYPI_OPTIONS=""
RUN apt update && apt -y install libldap2-dev libsasl2-dev && apt clean
WORKDIR /app/server
COPY requirements.txt /app/kiwi/requirements.txt
RUN sh -c "cd /app/kiwi;pip install -r requirements.txt ${PYPI_OPTIONS}"
COPY . /app/kiwi
RUN cd /app/kiwi && python setup.py install && rm -fr /app/kiwi
RUN pip uninstall -y kiwi-server
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
ARG GIT_TAG=no-tag
ARG LOG_NAME=server
ARG DB_NAME=kiwi
ENV LOG_NAME=$LOG_NAME \
    DB_NAME=$DB_NAME \
    GIT_TAG=$GIT_TAG
ENTRYPOINT sh -c "test '$IMAGE_DEBUG' = TRUE && (echo image debug...;tail -f /dev/stdout) || (python -m kiwi --tag=$GIT_TAG )"

