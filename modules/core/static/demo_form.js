function assert(expr, msg) {
    if (!expr) {
        console.error(expr, msg);
        if (msg) {
            throw new Error(msg);
        } else {
            throw new Error(`断言出现错误了而已[${msg}]`);
        }
    }
}

data = function () {
    return {
        config: {outputString: true},
    }
}


dynamicData = function () {
    return {
    }
}

methods = {
    async recover_force() {
        if (!confirm("强制恢复会无条件用冷存数据覆盖, 确认用户满意老数据")) {
            return
        }
        let data = await window.app.$refs.KFB.getData();
        Vue.http.post("recover", {
            platform: data.platform, //
            role_id: data.role_id, //
            cate: data.cate, force: true,
        }).then(response => {
            assert(response.body.ret === 0, `服务器异常[ret=${response.body.error}]`)
            alert("强制恢复成功");
            this.detail();
        }).catch(e => {
            alert(`异常[${e}]`);
        });
    }, async recover() {
        let data = await window.app.$refs.KFB.getData();
        Vue.http.post("recover", {
            platform: data.platform, //
            role_id: data.role_id, //
            cate: data.cate,
        }).then(response => {
            assert(response.body.ret === 0, `服务器异常[ret=${response.body.error}]`)
            alert("恢复成功");
            this.detail();
        }).catch(e => {
            alert(`异常[${e}]`);
        });
    }, async detail() {
        let data = await window.app.$refs.KFB.getData();
        let role_id = parseInt(data.role_id);
        await Vue.http.post("detail", {
            platform: data.platform, //
            role_id: role_id, //
        }).then(response => {
            assert(response.body.ret === 0, `服务器异常[ret=${response.body.error}]`)
            let result = response.body.result;
            let output = [result.info.detail];
            window.app.$refs.KFB.setData({
                output: output.join("\n"), //
            });
        }).catch(e => {
            if (e.status === 500) {
                alert(`服务器异常[${e.statusText}]`)
            } else {
                alert(`出现异常[${e}]`)
            }
        })
    }, handleSubmit(p) {
        // 通过表单提交按钮触发，获取promise对象
        p().then(res => {
            // 获取数据成功

        }).catch(err => {
            console.log(err, '校验失败')
        })
    },
};