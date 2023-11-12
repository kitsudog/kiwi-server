import json
from typing import Dict, List

from frameworks.base import HTMLPacket


# noinspection PyDefaultArgument
def markdown_table_html(
        markdown: str, css: str, table: List[Dict] = [], header: List[str] = [],
        alignment_center=[], alignment_right=[], tag_header=[],
        number_header=[], date_header=[], title: str = "table",
) -> HTMLPacket:
    return HTMLPacket(f"""\
<!doctype html>
<html>
<head>
    <link rel="icon" href="data:image/ico;base64,aWNv">
    <meta charset="utf-8"/>
    <title>{title}</title>
</head>
<body>
    <div id="content">
    <pre>
{markdown}
    </pre>
    </div>
    <!--<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>-->
    <script src="js/showdown.min.js"></script>
    <script src="js/jquery-3.3.1.min.js"></script>
    <script src="js/jquery.tablesort.min.js"></script>
    <script src="js/jquery.json-viewer.js"></script>
    <script src="js/luxon.min.js"></script>
    <script type="text/javascript" src="js/tabulator.min.js"></script>
    <script type="text/javascript" src="js/jquery.dataTables.min.js"></script>
    <link href="css/jquery.dataTables.min.css" type="text/css" rel="stylesheet">
    <link href="css/tabulator.min.css" type="text/css" rel="stylesheet">
    <link href="css/jquery.json-viewer.css" type="text/css" rel="stylesheet">
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
            $("em").each((i,x)=>{{$(x).replaceWith("_" + $(x).text() + "_")}});
            var raw_table={json.dumps(table)};
            var header={json.dumps(header)};
            function dict(keys,values){{
                return Array.from(keys).reduce((accumulator, key, index) => {{
                  accumulator[key] = values[index];
                  return accumulator;
                }}, {{}})
            }}
            var table=Array.from($("tr").slice(1).map((_,x)=>dict($("th").map((_,x)=>$(x).text()),$(x).find("td").map((_,y)=>$(y).html()))));
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
            $("table").append("<tfoot><tr></tr></tfoot>")
            header.forEach((x)=>{{
                $("tfoot tr").append(`<th>${{x}}</th>`)
            }});
            let adv = location.search.slice(1).split("&").filter(x=>x.indexOf("adv=")>=0);
            if(adv.length==0){{
                adv = "datatables";
            }}else{{
                adv = adv[0].split("=")[1];    
            }}
            if(adv=="datatables"){{
                var dataTable = $('table').DataTable({{
                    stateSave: true,
                    initComplete: function () {{
                        this.api()
                            .columns()
                            .every(function () {{
                                let column = this;
                                let title = column.footer().textContent;
                 
                                // Create input element
                                let input = document.createElement('input');
                                input.placeholder = title;
                                column.footer().replaceChildren(input);
                 
                                // Event listener for user input
                                input.addEventListener('keyup', () => {{
                                    if (column.search() !== this.value) {{
                                        column.search(input.value).draw();
                                    }}
                                }});
                            }});
                    }},
                }});
            }}
            if(adv=="tabulator"){{
                var alignment_center = {json.dumps(alignment_center)};
                var alignment_right = {json.dumps(alignment_right)};
                var tag_header = {json.dumps(tag_header)};
                var number_header = {json.dumps(number_header)};
                var date_header = {json.dumps(date_header)};
                var align = (x) => alignment_center.indexOf(x) >= 0 ? 'center' : (alignment_right.indexOf(x) >= 0 ? 'right' : 'left');
                var tabulator = new Tabulator("#content", {{
                    data: table,
                    layout: "fitDataTable",
                    autoColumns: true, 
                    
                    persistence: {{
                      sort:true,
                      filter:true,
                      columns:true,
                    }},
                    movableColumns: true,
                    autoColumnsDefinitions: header.map(x=>Object({{
                        field: x, title: x, 
                        headerFilterParams: {{valuesLookup: tag_header.indexOf(x) >= 0, clearable: true}},
                        variableHeight: true,
                        vertAlign: 'middle',
                        headerHozAlign: align(x),
                        hozAlign: align(x),
                        formatter: number_header.indexOf(x) >= 0 ? 'plaintext' : (date_header.indexOf(x) >= 0 ? 'datetime' : 'html'),
                        formatterParams: {{
                            outputFormat: "yyyy/MM/dd HH:mm:ss",
                            timezone: "Asia/Shanghai",
                        }},
                        sorter: number_header.indexOf(x) >= 0 ? 'number' : (date_header.indexOf(x) >= 0 ? 'datetime' : 'string'),
                        sorterParams: {{
                            format: "yyyy-MM-dd HH:mm:ss",
                        }},
                        headerFilter: true,
                    }})),
                }});
                tabulator.on("tableBuilt", ()=>{{
                    $("[name=json1]").css("text-align", "left").each((i, each)=>{{
                        $(each).jsonViewer(JSON.parse(each.innerText), {{
                          collapsed: true,
                          rootCollapsable: true,
                          withQuotes: true,
                          withLinks: false,
                        }});
                        $(each).parent().css("height", "");
                    }});
                }});
            }}
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
.tag {{
    padding: 4px 4px 4px 4px;
    border: 1px solid #EEEEEE;
    border-radius: 5px;
    margin-right: 5px;
    display: inline;
    line-height: 40px;
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
