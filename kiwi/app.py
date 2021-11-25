#!/usr/bin/env python3
from skywalking.trace.span import NoopSpan

if __name__ == "__main__":
    from gevent import monkey

    print("monkey::patch_all")
    monkey.patch_all()
import json
import logging
import mimetypes
import os
import random
from datetime import datetime
from time import sleep
from typing import Iterable, Dict, TypedDict, List, Optional

import click
import flask_migrate
import gevent
import requests
# import pretty_errors
from flask import Flask, request, Response, send_from_directory
from flask_cors import CORS
from flask_migrate import Migrate

from base.style import Block, Log, is_debug, active_console, inactive_console, Trace, is_dev, now, Assert, Error, \
    has_sentry, json_str, init_sky_walking, has_sky_walking
from base.utils import read_file, flatten, load_module, write_file
from frameworks.actions import Action
from frameworks.base import Request
from frameworks.context import Server
from frameworks.main_server import wsgi_handler, tick_cycle, service_cycle
from frameworks.sql_model import db

# pretty_errors.configure(
#     line_length=140,
#     separator_character='=',
#     display_timestamp=True,
#     timestamp_function=datetime.now,
#     exception_above=True,
#     exception_below=True,
#     stack_depth=0,
#     top_first=False,
#     always_display_bottom=True,
#     filename_display=pretty_errors.FILENAME_COMPACT,
#     line_number_first=True,
#     display_link=True,
#     lines_before=5,
#     lines_after=5,
#     trace_lines_after=0,
#     trace_lines_before=0,
#     truncate_code=True,
#     display_locals=True,
#     display_trace_locals=False,
#     truncate_locals=True,
#     display_arrow=True,
#     inner_exception_message="[inner_exception_message]",
#     inner_exception_separator=True,
#     prefix="[ERROR-START]",
#     infix="",
#     postfix="[ERROR-END]",
#     reset_stdout=False,
#     line_color=pretty_errors.RED + '>>>>' + pretty_errors.default_config.line_color,
#     code_color='####' + pretty_errors.default_config.line_color,
#     link_color="File ",
# )
# pretty_errors.replace_stderr()
# pretty_errors.blacklist(os.path.join(os.path.dirname(__file__), 'venv'))

if config := load_module("config", fail=False, log_fail=False):
    TAG = config.TAG
    MYSQL_SUPPORT = False
else:
    MYSQL_SUPPORT = True
    TAG = os.environ.get("TAG", "dev")
if has_sentry():
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.redis import RedisIntegration


    class SentryEventDict(TypedDict):
        level: str
        logger: str
        logentry: Dict
        extra: Dict
        event_id: str
        timestamp: str
        breadcrumbs: Dict
        contexts: Dict
        modules: Dict
        threads: Dict
        release: str
        environment: str
        server_name: str
        sdk: Dict
        platform: str
        _meta: Dict


    class SentryEventHintDict(TypedDict):
        log_record: logging.LogRecord
        attachments: List


    class SentryCrumbDict(TypedDict):
        ty: str
        level: str
        category: str
        message: str
        timestamp: datetime
        date: Dict
        type: str


    class SentryCrumbHintDict(TypedDict):
        log_record: logging.LogRecord


    class TransactionContextDict(TypedDict):
        trace_id: str
        span_id: str
        parent_span_id: Optional[str]
        same_process_as_parent: bool
        op: str
        description: str
        start_timestamp: datetime
        timestamp: Optional[str]
        name: str
        sampled: Optional[bool]
        parent_sampled: Optional[bool]


    class SamplingContextDict(TypedDict):
        transaction_context: TransactionContextDict
        parent_sampled: Optional[bool]


    def before_send(event: SentryEventDict, hint: SentryEventHintDict):
        if logentry := event.get("logentry"):
            # todo: 剔除log中的时间戳
            if message := logentry.get("message"):
                if message.startswith("["):
                    logentry["message"] = message[message.find(" ") + 1:]
        return event


    def before_breadcrumb(crumb: SentryCrumbDict, hint: SentryCrumbHintDict):
        return crumb


    # noinspection PyUnusedLocal
    def traces_sampler(sampling_context: SamplingContextDict):
        return 1.0


    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        integrations=[LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        ), RedisIntegration()],
        traces_sample_rate=1.0,
        sample_rate=1.0,
        debug=is_debug(),
        release=TAG,
        max_breadcrumbs=100,
        attach_stacktrace=True,
        send_default_pii=True,
        server_name=os.environ.get("SERVER_NAME") or os.environ.get("HOSTNAME") or os.environ.get(
            "VIRTUAL_HOST") or "no-server-name",
        request_bodies="always",
        with_locals=True,
        shutdown_timeout=10,
        environment=os.environ.get("MODE") or "dev",
        before_send=before_send,
        before_breadcrumb=before_breadcrumb,
        traces_sampler=traces_sampler,
        _experiments={"auto_enabling_integrations": True}
    )
    Error("StartServer")

app = Flask(__name__, root_path=os.path.curdir)
cors = CORS(app, resources={r"/*": {"origins": "*"}})
app.debug = is_dev()
if config:
    app.config.from_object(config)
    db.init_app(app)
    migrate = Migrate(app, db)
else:
    pass
mimetypes.add_type('text/css; charset=utf-8', '.css')


@app.before_request
def get_params():
    if request.method == "OPTIONS":
        return
    if request.content_type and "json" in request.content_type:
        request.params = json.loads(request.get_data(as_text=True))
    elif request.form:
        print(f"params warning[{request.path}]")
        params = {}
        for k, v in request.form.items():  # type: str,str
            if not v and k.startswith("{"):
                params.update(json.loads(k))
        request.params = params
    else:
        request.params = {
        }


@app.teardown_request
def teardown_request(error):
    if not error:
        return
    Trace("请求异常", error)


@app.teardown_appcontext
def teardown_appcontext(error):
    if not error:
        return
    Trace("请求异常", error)


@app.errorhandler
def errorhandler(error):
    Trace("请求异常", error)
    raise error


@app.after_request
def after_request(response: Response):
    if response.is_streamed:
        pass
    else:
        content = response.get_data()
        if content.startswith(b"{"):
            ret = json.loads(content.decode("utf8"))
            if "data" not in ret:
                ret = {
                    "data": ret
                }
            if "code" not in ret:
                ret["code"] = 0
            # noinspection PyArgumentList
            response.set_data(json.dumps(ret))
            if is_dev() and request.method == "POST":
                print(f"[C=>S] {request.path}", getattr(request, "params", {}))
                print(f"[S=>C] {request.path}", response.get_data()[:100])

    return response


@app.route('/')
def index():
    return f'Hello World[{TAG}]!'


@app.route('/<int:product_id>/callback')
def open_callback(product_id):
    return requests.post(
        f"{request.host_url}quick/game_callback?product_id={product_id}&{request.query_string}",
        data=request.args
    ).text


@app.route('/download', methods=['GET'])
def download():
    filename = request.args["filename"]
    # 修正名字
    return send_from_directory("static", "." + request.args["path"], attachment_filename=filename, as_attachment=True)


@app.route('/stream', methods=['GET'])
def stream():
    def generate():
        for _ in range(100):
            sleep(1)
            yield f"line[{_}]"

    from flask import stream_with_context
    return Response(stream_with_context(generate()))


@app.after_request
def after_request(rsp):
    rsp.direct_passthrough = False
    return rsp


@app.cli.command()
def init_database():
    if not os.path.exists("migrations"):
        flask_migrate.init(multidb=True)
        flask_migrate.migrate(message="first")
    flask_migrate.upgrade()
    flask_migrate.show()


@app.cli.command()
@click.argument("message")
def migrate(message):
    flask_migrate.migrate(message=message)
    flask_migrate.show()


@app.before_first_request
def init():
    print("[flask::app::before_first_request] start")
    print("[flask::app::before_first_request] over")


class FlaskWSGIAction:
    def __init__(self, _application):
        self.application = _application

    # noinspection PyListCreation
    def __call__(self, environ, start_response):
        if has_sky_walking():
            from skywalking.trace.context import get_context
            carrier = None
            with get_context().new_entry_span(op=environ["PATH_INFO"], carrier=carrier) as sw_span:
                ret = wsgi_handler(environ, start_response, skip_status={404}, sw_span=sw_span)
        else:
            ret = wsgi_handler(environ, start_response, skip_status={404}, sw_span=NoopSpan())
        if ret == [b'404']:
            # 重新转发到flask
            return self.application(environ, start_response)
        else:
            return ret


application = FlaskWSGIAction(app.wsgi_app)


def startup(forever=True):
    with Block("准备上传目录"):
        Server.upload_dir = "static/uploads"
        Server.upload_prefix = "/uploads"
        os.makedirs("static/uploads", exist_ok=True)

    def ip_injector(_request: Request):
        return _request.session.get_ip()

    Action.reg_param_injector("__ip", ip_injector)

    app.wsgi_app = application

    def gevent_tick_cycle():
        while True:
            expire = now() + 10
            tick_cycle()
            gevent.sleep(max(0.001, (expire - now())) / 1000)

    def gevent_service_cycle():
        while True:
            expire = now() + 100
            service_cycle()
            gevent.sleep(max(0.001, (expire - now())) / 1000)

    gevent.spawn(gevent_tick_cycle)
    gevent.spawn(gevent_service_cycle)
    if forever:
        Log("Server Ready ...")
        if not is_dev() and not is_debug():
            inactive_console()
        if is_dev():
            app.run(host="0.0.0.0", port=8000, debug=True)
        else:
            from gevent import pywsgi
            pywsgi.WSGIServer(('', 8000), application=app, log=None).serve_forever()
    else:
        # for wsgi
        print("wait for wsgi")


# https://click.palletsprojects.com/en/7.x/options/
@click.command()
@click.option('--tag', help="启动标记而已")
@click.option('--mode', default=["full"], multiple=True,
              type=click.Choice(
                  ['full'] + list(filter(lambda x: os.path.isdir(f"modules/{x}"), os.listdir("modules")))
              ), show_default=True, help="启动的模式", )
def main(**kwargs):
    if kwargs.get("tag"):
        global TAG
        TAG = kwargs["tag"]
    _main(kwargs["mode"])
    startup()


def _main(mode: Iterable[str]):
    active_console()
    Log("初始化服务器")
    with Block("启动服务器"):
        if not os.path.exists("conf/module.conf"):
            os.makedirs("conf", exist_ok=True)
            write_file("conf/module.conf", json_str({
                "main": [
                    "core",
                ]
            }, pretty=True).encode("utf8"))
        module_conf: Dict = eval(read_file("conf/module.conf"))
        if full_module := os.environ.get("FULL_MODULE"):
            Log(f"外部指定加载的模块[{full_module}]")
            module_conf["full"] = full_module.split(",")
        else:
            Log("默认加载模块")
            module_conf["full"] = flatten(module_conf.values())
        all_entry = flatten(list(map(lambda x: module_conf[x], mode)))
        all_module = {

        }
        with Block("检查所有模块models"):
            for entry in all_entry:
                load_module("modules.%s.models" % entry)
        init_sky_walking(f"{os.environ.get('VIRTUAL_HOST', ''.join(all_entry))}@{TAG}")
        if is_debug():
            # 调试阶段随机初始化顺序依次破除顺序依赖
            random.shuffle(all_entry)
        with Block("加载模块"):
            for entry in set(all_entry):
                with Block(f"加载模块[{entry}]", log=True):
                    injector_list = []
                    with Block("初始化injector"):
                        # noinspection PyBroadException
                        try:
                            for each in load_module("modules.%s.injector" % entry).__dict__.values():
                                if isinstance(each, Action.Injector):
                                    injector_list.append(each)
                        except ModuleNotFoundError:
                            pass
                    module = all_module[entry] = load_module("modules.%s.main" % entry)
                    Assert("init_server" in module.__dict__, f"模块[{entry}]主需要包含[init_server]方法作为加载后的初始化")
                    Assert("prepare" in module.__dict__, f"模块[{entry}]主需要包含[prepare]方法作为模块启动初始化")
                    module.__dict__["init_server"]()
                    with Block("卸载模块自定义的injector"):
                        for each in injector_list:
                            Action.Injector.remove_default_inspector(each)

        with Block("初始化模块", log_both=True, log_cost=True):
            has_prepared_module = set()
            need_prepare_module = list(set(all_entry))
            for _ in range(10000):
                Assert(_ < 9000, "存在循环依赖的模块请检查配置")
                if len(need_prepare_module) == 0:
                    break
                entry = need_prepare_module.pop(0)
                if set(module_conf.get(entry, [])[1:]) <= has_prepared_module:
                    with Block(f"初始化模块[{entry}]", log=True):
                        all_module[entry].__dict__["prepare"]()
                        has_prepared_module.add(entry)
                else:
                    need_prepare_module.append(entry)


def test():
    with Block("核心框架的测试"):
        from frameworks import action_sample
        from frameworks import db_sample
        from frameworks import node_sample

        action_sample.test()
        if not MYSQL_SUPPORT:
            db_sample.test()
        node_sample.test()


if __name__ == '__main__':
    if is_debug():
        test()
    main()
elif __name__ == 'app':
    _main(mode=["full"])
    startup(forever=False)
