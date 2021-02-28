#!/usr/bin/env python3
import json
import os
import re

import alembic.config

from base.style import Block, active_console
from base.utils import read_file, md5


# 激活migrate之前注册所有相关的model


def get_sign():
    from frameworks.sql_model import sql_alchemy_binds

    alembic.config.main(["upgrade", "head", "--sql"])
    sql = {}
    for key, value in sql_alchemy_binds.items():
        sql[key] = read_file(f"{key}.sql")
        sql[key] = re.sub(r"UPDATE alembic_version .+", "", sql[key])
        sql[key] = re.sub(r"INSERT INTO alembic_version .+", "", sql[key])
        sql[key] = re.sub(r"--.+", "", sql[key])
        sql[key] = re.sub(r"\n+", "\n", sql[key]).strip()
    result = os.popen("alembic show head").read()
    if result:
        rev = re.compile(r"Rev: (\S+) \(head\)").findall(result)[0]
        return rev, md5(json.dumps(sql, sort_keys=True)), sql
    else:
        return "", "", sql


def main():
    active_console()
    orig_rev, orig_sign, orig_sql = get_sign()
    with Block("先更新到最新"):
        alembic.config.main(["upgrade", "head"])
    with Block("更新"):
        alembic.config.main(["revision", "--autogenerate"])
    rev, sign, sql = get_sign()
    if orig_sign == sign:
        for each in os.listdir("migrations/versions"):
            if each.startswith(rev):
                os.remove(os.path.join("migrations/versions", each))
        print("not modified")
        exit(0)


if __name__ == '__main__':
    # pythonpath注入
    import sys

    sys.path.insert(0, os.path.dirname(sys.argv[0]))
    from frameworks import db_sample

    db_sample.prepare()
    main()
