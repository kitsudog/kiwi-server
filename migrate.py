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
    # python_path注入
    import sys

    sys.path.insert(0, os.path.dirname(sys.argv[0]))
    from frameworks import db_sample

    db_sample.prepare()
    if len(sys.argv) > 1 and sys.argv[1]:
        if sys.argv[1] == "reset":
            # 重新获取第一个版本
            from frameworks.sql_model import sql_alchemy_binds
            import pymysql

            params = re.search(
                r"://((?P<username>[^:]*)(:(?P<password>[^@]*))?@)?(?P<host>[^:]*)(:(?P<port>\d*))?/(?P<database>[^?]*)",
                sql_alchemy_binds["main"]).groupdict()
            with pymysql.connect(
                    host=params["host"],
                    user=params["username"] or "root",
                    password=params["password"] or "",
                    database=params["database"],
                    port=int(params["port"] or 3306),
            ) as conn:
                with conn.cursor() as cursor:
                    try:
                        cursor.execute("select version_num from alembic_version")
                        if line := cursor.fetchone():
                            cur_version = line[0]
                        else:
                            cursor = None
                    except pymysql.ProgrammingError:
                        cur_version = None

            with pymysql.connect(
                    host="localhost",
                    user="root",
                    password="",
                    # database="mysql",
                    port=3306
            ) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("show databases")
                    if ("__migrate",) in cursor.fetchall():
                        cursor.execute("use __migrate")
                        cursor.execute("show tables")
                        if tables := cursor.fetchall():
                            rebuild = True
                            if (("alembic_version",),) == tables:
                                cursor.execute("select count(1) from alembic_version")
                                if cursor.fetchone() == 0:
                                    rebuild = False
                            if rebuild:
                                cursor.execute("drop database __migrate")
                                cursor.execute("create database __migrate")
                    else:
                        cursor.execute("create database __migrate")
                conn.commit()
            sql_alchemy_binds.update({
                'main': f'mysql+pymysql://root:@127.0.0.1:3306/__migrate?charset=utf8mb4',
            })
            if os.path.exists("migrations/versions"):
                for each in os.listdir("migrations/versions"):
                    if each.endswith(".py"):
                        os.remove(os.path.join("migrations/versions", each))
            main()
            if cur_version:
                for each in os.listdir("migrations/versions"):
                    if each.endswith(".py"):
                        version = each[:-4]
                        os.rename(os.path.join("migrations/versions", each), f"migrations/versions/{cur_version}_.py")
                        with open(f"migrations/versions/{cur_version}_.py", mode="r") as fin:
                            content = fin.readlines()
                        with open(f"migrations/versions/{cur_version}_.py", mode="w") as fout:
                            for line in content:
                                line = line.replace(f"""revision = '{version}'""", f"""revision = '{cur_version}'""")
                                fout.write(line)
                        break
    else:
        main()
