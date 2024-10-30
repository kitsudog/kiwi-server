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
    <k-form-build ref="KFB" :outputString="true" :dynamicData="dynamicData" :config="config" @submit="handleSubmit" :value="jsonData" @change="handleChange"></k-form-build>
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
        window.$handleChange = console.log;
        const __config = {
            el: '.app',
            methods: {
                handleChange: (newValue, prop)=>{
                  if(window.handleChange){
                    window.handleChange.call(null, prop, newValue);
                  }else{
                    console.log("handleChange", prop, "=>", newValue);
                  }
                },
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
        __config.data = await (async function() {
            let tmp = (typeof window.data==="function"?window.data.call(this):window.data) || {};
            tmp.jsonData = jsonData;
            tmp.dynamicData = (typeof window.dynamicData==="function"?window.dynamicData.call(this):window.dynamicData) || tmp.dynamicData || {};
            if(tmp.dynamicData instanceof Promise){
              tmp.dynamicData = await tmp.dynamicData;
            }
            window.$kfb_dynamicData = tmp.dynamicData;
            Object.keys(__config.methods).filter(x=>typeof __config.methods[x]==="function").forEach(x=>{
                window.$kfb_dynamicData[x] = __config.methods[x];
            });
            tmp.config = (typeof window.config==="function"?window.config():window.config) || tmp.config || {};
            return tmp;
        })();
        Vue.config.productionTip = true;
        Vue.config.devtools=true;
        if(!__config.methods.handleSubmit){
            alert("请补齐methods::handleSubmit方法");
        } else {
            window.app = new Vue(__config);
            console.info("config", __config);
            console.info("data", window.app.$data);
        }
    })();
</script>
</body>

</html>
""" % {
        "path": path,
    })
