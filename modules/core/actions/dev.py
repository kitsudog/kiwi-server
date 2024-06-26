import re
import time
from collections import ChainMap
from typing import List, Dict, Set, Iterable

import requests

from base.style import str_json, json_str, str_json_i, Block, is_debug, Fail, Log, get_sw8_header, now
from frameworks.actions import GetAction, local_request, FastAction, Action, Code, NONE, ChunkAction
from frameworks.base import ChunkPacket, ChunkStream, RedirectResponse
from frameworks.context import DefaultRouter
from frameworks.main_server import forward_response, forward
from frameworks.redis_mongo import db_other, db_config
from frameworks.server_context import SessionContext
from frameworks.session import SessionMgr
from modules.core.injector import JWTPayload
from modules.core.utils import markdown_table_html


# noinspection PyStringFormat
def td_format(header, value, *, is_tag: bool):
    if is_tag:
        if not isinstance(value, Iterable):
            value = str(value)
        if isinstance(value, str):
            if value:
                value = value.split(",")
            else:
                value = []
        return "".join(map(lambda x: f"<div class=tag>{x}</div>", value))
    elif isinstance(value, dict):
        return f"<div name=json1>{json_str(value)}</div>"
    else:
        return f"%-{len(header)}s" % value


# noinspection PyDefaultArgument
@GetAction
def table_show(
        header: List[str] = None,
        table: List[Dict] = None,
        row: List[Dict] = None,
        add_no: bool = True,
        alignment_center: Set[str] = None,
        alignment_right: Set[str] = None,
        tag_header: Set[str] = None,
        number_header: Set[str] = None,
        date_header: Set[str] = None,
        default: Dict = None,
        title: str = None,
        css="",
):
    if not header and table:
        header = set()
        for each in table:
            header = header ^ set(each.keys())
        header = sorted(list(header))
    if is_debug():
        header = ["header-1", "header-2", "header-3", "header-4", "date"] if header is None else header
        table = [
            {"header-1": 1, "header-2": 2, "header-3": 3, "header-4": 4},
            {"header-1": 5, "header-3": 12, "header-4": 8},
        ] if table is None else table
        row = [
            ["c11", "c12", "c13", "c14", now() - 24 * 3600 * 1000],
            ["c21", "c22", "c23", "c24", now() + 24 * 3600 * 1000],
            ["c31", "c32", {"a": 1, "b": 2, "c": 3, "d": 4}],
            [{"a": 1, "b": 2, "c": 3, "d": 4}, 2],
        ] if row is None else row
        alignment_center = {"header-2"} if alignment_center is None else alignment_center
        alignment_right = {"header-3"} if alignment_right is None else alignment_right
        default = {
            "header-1": "DEFAULT[a]", "header-2": "DEFAULT[b]",
            "header-3": "DEFAULT[c]", "header-4": "DEFAULT[d]",
        } if default is None else default
        tag_header = {"header-3"} if tag_header is None else tag_header
        date_header = {"date"} if date_header is None else date_header
        title = title or "table"
    header = header or []
    table: List[Dict] = table or []
    row = row or []
    alignment_center = alignment_center or set()
    alignment_right = alignment_right or set()
    default = default or {}
    tag_header = tag_header or set()
    number_header = number_header or set()
    date_header = date_header or set()

    if row:
        for each in row:
            table.append(dict(ChainMap(dict(zip(header, each)), default)))
    for each in table:
        for h in header:
            if h not in each:
                each[h] = default.get(h)
    if add_no:
        header = ["no"] + header
        for i, each in enumerate(table, start=1):
            each["no"] = i
        alignment_right.add("no")
    for h in header:
        if len(list(filter(lambda x: type(x) not in {int, float}, map(lambda x: x[h], table)))) == 0:
            number_header.add(h)
        if h in date_header:
            for each in table:
                if not each.get(h):
                    each[h] = "1970-1-1 00:00:00"
                if isinstance(each[h], int):
                    each[h] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(each[h] / 1000))
                elif isinstance(each[h], float):
                    each[h] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(each[h]))
    number_header -= date_header
    markdown = [f"|{'|'.join(header)}|"]
    tmp = []
    for h in header:
        if h in alignment_center:
            tmp.append(":-" + "-" * max(0, (len(h) - 4)) + "-:")
        elif h in alignment_right:
            tmp.append("-" * max(0, (len(h) - 4)) + "---:")
        else:
            tmp.append(":---" + "-" * max(0, (len(h) - 4)))
    markdown.append("|%s|" % "|".join(tmp))

    for each in table:
        tmp = []
        for h in header:
            tmp.append(td_format(h, each.get(h, default.get(h)), is_tag=h in tag_header))
        markdown.append("|%s|" % "|".join(tmp))
    return markdown_table_html(
        "\n".join(markdown), css, table=table, header=header,
        alignment_center=list(alignment_center), alignment_right=list(alignment_right),
        tag_header=list(tag_header), number_header=list(number_header), date_header=list(date_header), title=title,
    )


@GetAction
def api_log(__params, api: str):
    """
    api历史记录方便调试
    """
    api_log_list = list(map(str_json, db_other.lrange(f"{api}", 0, 20)))
    result_map = {}
    if api_log_list:
        key_set = set()
        result = api_log_list[0]["rsp"].get("result")
        if isinstance(result, set):
            pass
        else:
            if result is None:
                pass
            elif isinstance(result, dict):
                for k, v in result.items():
                    result_map[k] = type(v).__name__
                    key_set.add(k)
                for each in api_log_list:
                    if each["rsp"]["ret"] != 0:
                        continue
                    if set(result.keys()) != key_set:
                        result_map.clear()
                        break
            elif isinstance(result, str):
                pass
        __raw = __params["#raw#"]
        example = f"""\
curl {__raw['wsgi.url_scheme']}://{__raw['HTTP_HOST']}/{api.replace('.', '/')} -X POST -v \\
    --data-raw '{api_log_list[0]["req"]}'
"""
    else:
        api_log_list = [{
            "req": "",
            "rsp": {"ret": 0, "result": {}},
        }]
        example = f"""\
暂时没人调用过
"""

    markdown = f"""\
## 请求示例
<div class=example>
```sh
{example}
```
</div>
## __result__ 描述
<div name=json2>
{json_str(result_map) if result_map else "暂不统一请自行查看记录"}
</div>
## 历史记录
|状态 |请求 |返回 |
|:---|:---|:---|
"""
    for each in api_log_list:
        # if each["rsp"]["ret"] != 0:
        #     continue
        req, response = each["req"], each["rsp"]
        req = str_json_i(req, default={
            "query": req,
        }, fail=False)
        if each["rsp"]["ret"] == 0:
            rsp = response["result"]
        else:
            rsp = response
        markdown += f"|{response['ret']}" \
                    f"|<div name=json1>{json_str(req)}</div>" \
                    f"|<div name=json2>{json_str(rsp)}</div>" \
                    f"|\n"

    return markdown_table_html(markdown, """
#请求 {
    min-width: 300px;
}
#返回 {
    min-width: 200px;
}
#状态 {
    min-width: 50px;
}
""", title="api_log")


@GetAction
def api_list(module="*"):
    """
    开发阶段用的
    todo: Swagger
    :param module: 指定模块
    """
    req = local_request()

    # noinspection PyShadowingNames
    def merge(lines):
        return "<br/>".join([each.strip() for each in filter(lambda x: len(x.strip()), lines)])

    # noinspection PyShadowingNames
    def desc(_action: FastAction):
        ret = []
        if isinstance(_action, Action):
            for each in sorted(_action.injector_list_iter(), key=lambda x: x.alias):
                if each.param.startswith("_"):
                    continue
                if found := re.findall(fr"\s*:param {each.param}: ([^:]+)", _action.__doc__ or "", re.S):
                    param_comment = merge(found[0].splitlines())
                else:
                    param_comment = ""
                if each.default_value is not NONE:
                    ret.append(f"{each.alias}:{each.human()} = {repr(each.default_value)}|{param_comment}")
                else:
                    ret.append(f"{each.alias}:{each.human()}|{param_comment}")
        return ret

    def comment(_action: FastAction):
        content = _action.__doc__ or "-"
        ret = {
            "default": merge(content.split(":param")[0].splitlines())
        }
        return ret

    with Block("BCode部分"):
        markdown = f"""\
# {"测试机" if is_debug() else "正式机"}
# BCode列表
|code|消息|内部消息|
|:---|:---|:---|
"""
        tmp = []
        for code in Code.all_code():
            if module != "*" and module not in code.__module__:
                continue
            tmp.append({
                "code": code.code,
                "msg": code.msg,
                "internal_msg": code.internal_msg if code.msg != code.internal_msg else ""
            })

        def to_table(data):
            table_format = f"|%s|%s|%s|"
            return table_format % (data["code"], data["msg"], data["internal_msg"])

        with Block("markdown Table部分"):
            for each in tmp:
                markdown += to_table(each) + "\n"
    with Block("api部分"):
        markdown += f"""\
# api列表
|模块 |api |参数 |备注|
|:---|:---|:---|:---|
"""
        tmp = []
        for api, action in sorted(DefaultRouter.router_map.items(), key=lambda x: x[0]):  # type: str, FastAction
            if module != "*" and module != action.module:
                continue
            tmp.append({
                "module": action.module,
                "api": api,
                "action": action,
                "describe": desc(action),
                "comment": comment(action),
            })
        if not len(tmp):
            for api, action in sorted(DefaultRouter.router_map.items(), key=lambda x: x[0]):  # type: str, FastAction
                if api.startswith(module + "."):
                    tmp.append({
                        "module": action.module,
                        "api": api,
                        "action": action,
                        "describe": desc(action),
                        "comment": comment(action),
                    })

        if len(tmp):
            module_set = set(map(lambda x: x["module"], tmp))
            module_max_len = max([len(each) + 4 for each in module_set])
            api_max_len = max([len(each['api']) for each in tmp])
            action_max_len = max([max(map(lambda x: len(x), each['describe'] or [""])) for each in tmp])
        else:
            module_set = set()
            module_max_len = 0
            api_max_len = 0
            action_max_len = 0

        # noinspection PyShadowingNames
        def to_table(data):
            # noinspection PyStringFormat
            table_format = f"|%{-module_max_len}s|%{-api_max_len}s|%{-action_max_len}s|%-50s|"
            ret = [table_format % (
                f"[{data['module']}][]",
                f"[{data['api']}][]",
                "",
                f"**{data['comment']['default'] or '-'}**",
            )]
            for each in data['describe']:
                # ret.append(table_format % ("", "", each.split("|")[0], each.split("|")[1]))
                param_str, comment_str = each.split("|")
                markdown_param_str = re.sub(r"^([^:]+):", r"**\1** :", param_str)
                ret.append(
                    table_format % (
                        "",
                        "",
                        "<div class=tooltip>%s<span class=tooltip-text>%s</span></div>" %
                        (markdown_param_str, comment_str) if comment_str else markdown_param_str,
                        f"",
                    )
                )
            return "\n".join(ret)

        with Block("markdown Table部分"):
            for each in tmp:
                if each["api"].count(".") != 1:
                    continue
                markdown += to_table(each) + "\n"
        with Block("markdown 模块链接"):
            for module in module_set:
                markdown += f"[{module}]: {req.params['#raw#']['PATH_INFO']}?module={module}" + "\n"
        with Block("markdown Action链接"):
            markdown += "\n"
            for each in tmp:
                markdown += f"[{each['api']}]: api_log?api={each['api']}" + "\n"
    return markdown_table_html(markdown, """
#模块 {
    width: 50px;
}
#api {
    width: 200px;
}
#参数 {
    width: 300px;
}
""", title="api_list")


@GetAction
def auth(__basic_auth):
    return ""


@GetAction
def jwt_auth(__jwt: JWTPayload):
    return ""


@GetAction
def ldap_auth(__ldap_auth):
    return __ldap_auth


@Action
def login0(__session: SessionContext, uuid: str):
    SessionMgr.login(__session, uuid)
    return {
        "token": __session.get_token(),
    }


@Action
def login1(__auth, __session: SessionContext):
    return {
        "token": __session.get_token(),
    }


@GetAction
def redis_info():
    Log("redis_info")
    return db_config.info()


@GetAction
def requests_test():
    return requests.get("https://cip.cc", headers=ChainMap(get_sw8_header(), {
        "User-Agent": "curl/7.77.0",
    })).text


@GetAction
def chunk():
    def generator():
        for _ in range(10):
            time.sleep(1)
            yield f"line[{_}]".encode("utf8")

    return ChunkPacket(generator())


@ChunkAction
def chunk2(num: int, sleep=1):
    for _ in range(num):
        time.sleep(sleep)
        yield f"line[{_}]".encode("utf8")
    raise Fail("test")


@GetAction
def chunk3(__stream: ChunkStream, num: int, sleep=1, error=True, is_html=True):
    Log("chunk3")
    if is_html:
        __stream.Log("<pre>")
    for _ in range(num):
        time.sleep(sleep)
        __stream.Log(f"line[{_}]")
    if error:
        raise Fail("test")
    return "over"


@GetAction
def chunk4(__stream: ChunkStream):
    # FIXME: 不支持
    forward_response(None, "dev.chunk3", {"num": 10}, stream=__stream, wait_chunk=True)


@GetAction
def chunk5(__stream: ChunkStream, num=10, has_over=True):
    __stream.Log(f"start waiting {num} sec")
    time.sleep(num)
    if has_over:
        __stream.Log(f"end waiting {num} sec")


@GetAction
def forward_test():
    return forward(None, "manager.user_by_user_id", param={})


# noinspection PyUnusedLocal,PyDefaultArgument
@GetAction
def param_test(a: List = [], b: Set = set()):
    pass


@GetAction
def redirect_baidu():
    return RedirectResponse("https://www.baidu.com")
