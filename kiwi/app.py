#!/usr/bin/env python3
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
import requests
from flask import Flask, request, Response
from skywalking.trace.span import NoopSpan

from base.style import Block, Log, is_debug, active_console, Trace, is_dev, Assert, Error, \
    has_sentry, json_str, init_sky_walking, has_sky_walking, str_json_ex, hour_zero, today_zero, now, HOUR_TS, DAY_TS
from base.utils import read_file, flatten, load_module, write_file

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
else:
    TAG = os.environ.get("TAG", os.environ.get("GIT_TAG", "dev"))
__now = now()
__sentry_traces_sample_rate = os.environ.get("SENTRY_TRACES_SAMPLE_RATE", 0.01)
__sentry_traces_sampler_dau_count = os.environ.get("SENTRY_TRACES_SAMPLE_DAU_COUNT")
__sentry_traces_sampler_dau_expire = today_zero() + DAY_TS
__sentry_traces_sampler_hau_count = os.environ.get("SENTRY_TRACES_SAMPLE_HAU_COUNT")
__sentry_traces_sampler_hau_expire = hour_zero(__now) + HOUR_TS
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


    def traces_sampler(sampling_context: SamplingContextDict):
        global __sentry_traces_sampler_dau_count, __sentry_traces_sampler_hau_count
        __sentry_traces_sampler_dau_count -= 1
        __sentry_traces_sampler_hau_count -= 1
        if __sentry_traces_sampler_dau_count < 0:
            return 0
        if __sentry_traces_sampler_hau_count < 0:
            return 0
        return __sentry_traces_sample_rate


    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        integrations=[LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        ), RedisIntegration()],
        traces_sample_rate=__sentry_traces_sample_rate,
        sample_rate=os.environ.get("SENTRY_SAMPLE_RATE", 1.0),
        debug=is_debug(),
        release=TAG,
        max_breadcrumbs=100,
        attach_stacktrace=True,
        send_default_pii=True,
        server_name=os.environ.get("SERVER_NAME") or os.environ.get("HOSTNAME") or os.environ.get(
            "VIRTUAL_HOST") or "no-server-name",
        shutdown_timeout=10,
        environment=os.environ.get("SPRING_PROFILES_ACTIVE") or "dev",
        before_send=before_send,
        before_breadcrumb=before_breadcrumb,
        traces_sampler=traces_sampler if __sentry_traces_sampler_dau_count or __sentry_traces_sampler_hau_count else None,
        _experiments={
            "continuous_profiling_auto_start": True,
        }
    )
    Error("StartServer")

app = Flask(__name__, root_path=os.path.curdir)
# Todo: 完善的cors前先暂停
# cors = CORS(app, resources={r"/*": {"origins": "*"}})
app.debug = is_dev()
app.url_map.strict_slashes = False
if config:
    app.config.from_object(config)
    # db.init_app(app)
    # migrate = Migrate(app, db)
else:
    pass
mimetypes.add_type('text/css; charset=utf-8', '.css')


@app.before_request
def get_params():
    if request.method == "OPTIONS":
        return
    if request.content_type and "json" in request.content_type:
        request.params = str_json_ex(request.get_data(as_text=True), default_json={}, fail=False)
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


@app.route('/<module>/')
def index2(module):
    return f'Hello World[{module}][{TAG}]!'


@app.route('/<module>/api_list')
def api_list(module):
    return requests.get(f"http://127.0.0.1:{8000}/admin/api_list?module={module}").content


# noinspection PyUnusedLocal
@app.route('/<module>/<module2>/api_list')
def api2_list(module, module2):
    return requests.get(f"http://127.0.0.1:{8000}/admin/api_list?module={module2}").content


# noinspection PyUnusedLocal
@app.route('/<module>/<path>/<file>')
def module_static(module, path, file):
    """
    主要是是弥补没有context_path的
    """
    from flask import make_response
    rsp = make_response(
        requests.get(f"http://127.0.0.1:{int(os.environ.get('KIWI_PORT', 8000))}/{path}/{file}").content
    )
    # 继承 mime
    if mime := mimetypes.guess_type(request.path):
        rsp.headers['Content-Type'] = mime[0]
    else:
        rsp.headers['Content-Type'] = "text/"
    return rsp


# noinspection PyUnusedLocal
@app.route('/<module>/<module2>/<path>/<file>')
def module2_static(module, module2, path, file):
    """
    主要是是弥补没有context_path的
    """
    from flask import make_response
    rsp = make_response(
        requests.get(f"http://127.0.0.1:{int(os.environ.get('KIWI_PORT', 8000))}/{path}/{file}").content
    )
    # 继承 mime
    if mime := mimetypes.guess_type(request.path):
        rsp.headers['Content-Type'] = mime[0]
    else:
        rsp.headers['Content-Type'] = "text/"
    return rsp


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


class FlaskWSGIAction:
    def __init__(self, _application):
        self.application = _application

    # noinspection PyListCreation
    def __call__(self, environ, start_response):
        from frameworks.main_server import wsgi_handler
        if has_sky_walking():
            from skywalking.trace.context import get_context
            from skywalking.trace.carrier import Carrier
            carrier = Carrier()
            for item in carrier:
                if value := environ.get(f"HTTP_{item.key.capitalize().upper().replace('-', '_')}"):
                    item.val = value
            op = environ["PATH_INFO"]
            if carrier.trace_id:
                # 加个前缀
                op = f"+{op}"
            with get_context().new_entry_span(op=op, carrier=carrier) as sw_span:
                ret = wsgi_handler(environ, start_response, skip_status={404}, sw_span=sw_span)
        else:
            ret = wsgi_handler(environ, start_response, skip_status={404}, sw_span=NoopSpan())
        if ret == [b'404']:
            # 重新转发到flask
            return self.application(environ, start_response)
        else:
            return ret


application = FlaskWSGIAction(app.wsgi_app)


# noinspection HttpUrlsUsage


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
    from kiwi.main import startup
    startup(app, application)


def _main(mode: Iterable[str]):
    active_console()
    Log("初始化服务器")
    if spring_cloud_config_server_url := os.environ.get("SPRING_CLOUD_CONFIG_SERVER_URL"):
        # builder = ClientConfigurationBuilder()
        # c = SpringConfigClient(builder.build())
        # c.get_config()
        Log(f"激活配置[{spring_cloud_config_server_url}]")

        class ConfigItem(TypedDict):
            name: str
            source: Dict[str, str]

        class SpringCloudConfig(TypedDict):
            name: str
            profile: List[str]
            label: Optional[str]
            version: str
            state: Optional[str]
            propertySources: List[ConfigItem]

        profile = os.environ.get("SPRING_PROFILES_ACTIVE", "test")
        rsp = requests.get(
            f"{spring_cloud_config_server_url}/{profile}",
            headers=dict(map(
                lambda x: x.partition("="),
                filter(lambda x: x, os.environ.get(
                    "SPRING_CLOUD_CONFIG_SERVER_HEADER", "").split(";")),
            )))
        if rsp.status_code == 200:
            spring_cloud_config: SpringCloudConfig = rsp.json()
            if sources := spring_cloud_config["propertySources"]:
                for each in sources:
                    for k, v in each["source"].items():
                        os.environ[k.upper().replace(".", "_")] = v
    with Block("启动服务器"):
        from frameworks.main_server import reg_static_file, reg_static_file2
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
        with Block("检查所有模块injector"):
            for entry in all_entry:
                load_module("modules.%s.injector" % entry, fail=False)
        import socket
        init_sky_walking(f"{os.environ.get('VIRTUAL_HOST', '-'.join(all_entry))}@{TAG}@{socket.gethostname()}")
        if is_debug():
            # 调试阶段随机初始化顺序依次破除顺序依赖
            random.shuffle(all_entry)
        with Block("加载模块"):
            for entry in set(all_entry):
                with Block(f"加载模块[{entry}]", log=True):
                    with Block("初始化静态资源"):
                        # noinspection PyProtectedMember
                        module_path = load_module("modules.%s" % entry).__path__._path[0]
                        static_path = os.path.realpath(os.path.join(module_path, "static"))
                        if os.path.exists(static_path):
                            for root, _, files in os.walk(static_path):
                                for file in files:
                                    reg_static_file(
                                        static_path,
                                        os.path.join(root[len(static_path):], file),
                                    )
                            for root, _, files in os.walk(static_path):
                                for file in files:
                                    reg_static_file2(
                                        os.path.join(root, file),
                                        os.path.join(entry, root[len(static_path):][1:], file),
                                    )

                    module = all_module[entry] = load_module("modules.%s.main" % entry)
                    Assert("init_server" in module.__dict__,
                           f"模块[{entry}]主需要包含[init_server]方法作为加载后的初始化")
                    Assert("prepare" in module.__dict__, f"模块[{entry}]主需要包含[prepare]方法作为模块启动初始化")
                    module.__dict__["init_server"]()

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
        from frameworks import node_sample
        from frameworks.redis_mongo import is_no_redis

        action_sample.test()
        if not is_no_redis():
            node_sample.test()


if __name__ == '__main__':
    if is_debug():
        test()
    main()
elif __name__ == 'app':
    _main(mode=["full"])
    from kiwi.main import startup

    startup(app, application, forever=False)
