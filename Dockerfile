FROM python:3.8
ARG GIT_TAG=no-tag
WORKDIR /app/server
COPY requirements.txt /app/server/requirements.txt
# export ARCHFLAGS="-arch x86_64"
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
WORKDIR /app/server
VOLUME /app/server/static/uploads
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/server \
    PYTHON_PRETTY_ERRORS_ISATTY_ONLY=1 \
    LANG=C.UTF-8 \
    MONGO_HOST=mongo \
    REDIS_HOST=redis \
    DB_HOST=mysql \
    GIT_TAG=$GIT_TAG \
    IMAGE_DEBUG=FALSE \
    DEBUG=FALSE \
    TZ=Asia/Shanghai
EXPOSE 8000
COPY . /app/server
ENTRYPOINT sh -c "test "\$IMAGE_DEBUG" = TRUE && tail -f /dev/stdout || ( python migrate.py && python app.py --tag=$GIT_TAG )"
