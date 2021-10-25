import re
import time

from base.style import str_json, json_str, str_json_i, Block, is_debug, Fail
from frameworks.actions import GetAction, local_request, FastAction, Action, Code, NONE, ChunkAction
from frameworks.base import HTMLPacket, ChunkPacket, ChunkStream
from frameworks.context import DefaultRouter
from frameworks.redis_mongo import db_other
from frameworks.server_context import SessionContext
from frameworks.session import SessionMgr


def markdown_html(markdown: str, css: str) -> HTMLPacket:
    return HTMLPacket(f"""\
<!doctype html>
<html>
<head>
    <link rel="icon" href="data:image/ico;base64,aWNv">
    <meta charset="utf-8"/>
    <title>api_list</title>
</head>
<body>
    <div id="content">
    <pre>
{markdown}
    </pre>
    </div>
    <!--<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>-->
    <script src="/js/showdown.min.js"></script>
    <script src="/js/jquery-3.3.1.min.js"></script>
    <script src="/js/jquery.json-viewer.js"></script>
    <link href="/css/jquery.json-viewer.css" type="text/css" rel="stylesheet">
    <script>
        var content = document.getElementById('content');
        var markdown = content.getElementsByTagName("pre")[0].innerHTML;
        // content.innerHTML = marked(markdown);
    </script>
    <script>
        if(window.location.href.indexOf("debug")<0){{
            var converter = new showdown.Converter({{
                tables: true,
                omitExtraWLInCodeBlocks: true,
                noHeaderId: false,
                parseImgDimensions: true,
                simplifiedAutoLink: true,
                literalMidWordUnderscores: true,
                strikethrough: true,
                tablesHeaderId: true,
                ghCodeBlocks: true,
                tasklists: true,
                smoothLivePreview: true,
                prefixHeaderId: false,
                disableForced4SpacesIndentedSublists: false,
                ghCompatibleHeaderId: true,
                smartIndentationFix: false,
                emoji: true,
            }});
            content.innerHTML = converter.makeHtml(markdown);
            $("[name=json1]").each((i, each)=>{{
                $(each).jsonViewer(JSON.parse(each.innerText), {{
                  collapsed: true,
                  rootCollapsable: true,
                  withQuotes: true,
                  withLinks: false,
                }});
            }});
            $("[name=json2]").each((i, each)=>{{
                try{{
                    $(each).jsonViewer(JSON.parse(each.innerText), {{
                      collapsed: true,
                      rootCollapsable: false,
                      withQuotes: true,
                      withLinks: false,
                    }});
                }}catch(e){{
                    console.log(e);
                }}
            }});
            $("em").each((i,x)=>{{$(x).replaceWith("_" + $(x).text() + "_")}});
        }}
    </script>

</body>
    <style>
table
{{
    border-collapse: collapse;
    margin: 0 auto;
    text-align: center;
    width: 100%;
}}
table td, table th
{{
    border: 2px solid #cad9ea;
    color: #666;
    vertical-align: top;
}}
table thead th
{{
    background-color: #CCE8EB;
}}
table tr:nth-child(odd)
{{
    background: #fff;
}}
table tr:nth-child(even)
{{
    background: #F5FAFA;
}}
.comment
{{
    font-size: small;
}}
.tooltip {{
    position: relative;
    display: inline-block;
    border-bottom: 1px dotted black;
}}

.tooltip .tooltip-text {{
    visibility: hidden;
    width: 200px;
    background-color: black;
    color: #fff;
    text-align: center;
    border-radius: 6px;
    padding: 5px 0;

    /* 定位 */
    position: absolute;
    z-index: 1;
    top: -5px;
    right: 105%;
}}

.tooltip:hover .tooltip-text {{
    visibility: visible;
}}

.tooltip .tooltip-text::after {{
    content: " ";
    position: absolute;
    top: 50%;
    left: 100%; /* 提示工具右侧 */
    margin-top: -5px;
    border-width: 5px;
    border-style: solid;
    border-color: transparent transparent transparent black;
}}
.tooltip .tooltip-text {{
    opacity: 0;
    transition: opacity 0.3s;
}}

.tooltip:hover .tooltip-text {{
    opacity: 1;
}}
{css}
    </style>
</html>
""")


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

    return markdown_html(markdown, """
#请求 {
    min-width: 300px;
}
#返回 {
    min-width: 200px;
}
#状态 {
    min-width: 50px;
}
""")


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
        module_set = set(map(lambda x: x["module"], tmp))
        module_max_len = max([len(each) + 4 for each in module_set])
        api_max_len = max([len(each['api']) for each in tmp])
        action_max_len = max([max(map(lambda x: len(x), each['describe'] or [""])) for each in tmp])

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
                markdown += f"[{each['api']}]: /admin/api_log?api={each['api']}" + "\n"
    return markdown_html(markdown, """
#模块 {
    width: 50px;
}
#api {
    width: 200px;
}
#参数 {
    width: 300px;
}
""")


@Action
def login0(__session: SessionContext, uuid: str):
    SessionMgr.login(__session, uuid)
    return {
        "token": __session.get_token(),
    }


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
    if is_html:
        __stream.Log("<pre>")
    for _ in range(num):
        time.sleep(sleep)
        __stream.Log(f"line[{_}]")
    if error:
        raise Fail("test")
