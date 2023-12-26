import os
import time

from setuptools import setup


def get_package():
    with open("requirements.txt") as fin:
        return fin.readlines()


def get_version():
    # 兼容新的setuptools要求
    if os.environ.get("VIRTUAL_ENV"):
        print("update force")
        _now = time.localtime()
        return time.strftime('%Y.%m%d.%H%M', _now).replace(".0", "")
    else:
        import _version
        return _version.__version__


setup(
    version=get_version(),
    packages=["base", "frameworks", "kiwi", "modules", "static", "migrations"],
    install_requires=get_package(),
)
