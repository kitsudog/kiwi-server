from frameworks.actions import GetAction
from frameworks.base import HTMLPacket


@GetAction
def smart(__params):
    path = __params["#raw#"]["PATH_INFO"].replace(".html", "")
    return HTMLPacket("""\
<!DOCTYPE html>
<!--suppress JSUnresolvedFunction -->
<html>

<head>
    <title>表单</title>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="k-form-design/lib/k-form-design.css">
</head>

<body>
<div style="text-align: right;">
    <a onclick="gotoDesign()">编辑器</a>
</div>
<div class="app" style="margin: 10px;">
    <k-form-build ref="KFB" :config="config" @submit="handleSubmit" :value="jsonData" @change="handleChange"></k-form-build>
</div>
<script src="js/vue.min.js"></script>
<script src="js/vue-resource.min.js"></script>
<script src="k-form-design/lib/k-form-design.umd.min.js"></script>
<script>
var original=Object.keys(window);
</script>
<script src="%(path)s.js"></script>
<script>
    var jsonData = {};
    function gotoDesign(){
        localStorage.setItem("form::design", JSON.stringify(jsonData));
        window.location.href="/k-form-design/index.html";
    }
    (async () => {
        jsonData = (await Vue.http.get(`%(path)s.json`)).data;
        const __config = {
            el: '.app',
            methods: {
                handleChange: console.log,
            },
        }
        Object.keys(window).filter(x => original.indexOf(x) < 0).forEach(x => {
            if(typeof window[x] == "object" && __config[x]){
                Object.keys(window[x]).forEach(key => {
                    __config[x][key] = window[x][key];
                })
            } else {
                __config[x] = window[x];
            }
            console.info("inject", x, __config[x]);
        });
        let tmp = (typeof window.data=="function"?window.data():window.data) || {};
        __config.data = function() {
            tmp.jsonData = jsonData;
            tmp.config = (typeof window.config=="function"?window.config():window.config) || tmp.config || {};
            return tmp;
        }
        Vue.config.productionTip = true;
        Vue.config.devtools=true;
        if(!__config.methods.handleSubmit){
            alert("请补齐methods::handleSubmit方法");
        } else {
            console.log("config", __config, __config.data());
            new Vue(__config);
        }
    })();
</script>
</body>

</html>
""" % {
        "path": path,
    })
