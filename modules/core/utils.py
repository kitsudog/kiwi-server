from frameworks.base import HTMLPacket


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
    <script src="/js/jquery.tablesort.min.js"></script>
    <script src="/js/jquery.json-viewer.js"></script>
    <link href="/css/jquery.json-viewer.css" type="text/css" rel="stylesheet">
    <script>
        var content = document.getElementById('content');
        var markdown = content.getElementsByTagName("pre")[0].innerHTML;
        // content.innerHTML = marked(markdown);
        $(function(){{
            $.tablesort.defaults = {{
                compare: function(a, b) {{		// Function used to compare values when sorting.
                    try{{
                        a = parseInt(a)||a;
                        b = parseInt(b)||b;
                    }}catch(e){{
                    }}
                    if (a > b) return 1;
                    else if (a < b) return -1;
                    else return 0;
                }}
            }};
            $('table').tablesort();
        }});
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
            $("[name=json1]").css("text-align","left").each((i, each)=>{{
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
