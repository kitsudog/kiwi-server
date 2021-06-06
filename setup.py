import os
import re

from setuptools import find_packages, setup


def get_package():
    with open("requirements.txt") as fin:
        return fin.readlines()


setup(
    version=f"0.1.{time.strftime('%Y%m%d%H%M', time.localtime())}",
    packages=["base", "frameworks", "kiwi", "modules/core", "static", "migrations"],
    install_requires=get_package(),
)
