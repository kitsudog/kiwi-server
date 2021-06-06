import os
import re
import time

from setuptools import find_packages, setup


def get_package():
    with open("requirements.txt") as fin:
        return fin.readlines()


def get_version():
    if os.environ.get("VIRTUAL_ENV"):
        print("update force")
        return f"0.1.{time.strftime('%Y%m%d%H%M', time.localtime())}",
    else:
        return _version.__version__


setup(
    version=get_version(),
    packages=["base", "frameworks", "kiwi", "modules", "static", "migrations"],
    install_requires=get_package(),
)
