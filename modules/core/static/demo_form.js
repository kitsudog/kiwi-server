data = function () {
    return {
        config: {outputString: true},
    }
}

dynamicData = function () {
    return {
        testSend: this.debug,
    }
}

methods = {
    debug() {
        alert("dev");
    },
    handleSubmit(p) {
        // 通过表单提交按钮触发，获取promise对象
        p().then(res => {
            // 获取数据成功
            Vue.http.post("fill_data_to_csv", {
                orig: res.orig, fields: res.fields,
            }).then((response) => {
                if (response.status === 200) {
                    document.getElementById("output").innerHTML = response.bodyText;
                    setTimeout(function () {
                        alert("ok了");
                    }, 300);
                } else {
                    alert("fail");
                }
            });
        }).catch(err => {
            console.log(err, '校验失败')
        })
    },
};