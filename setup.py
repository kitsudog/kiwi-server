import os
import re

from setuptools import find_packages, setup

READMEFILE = "README.md"
VERSIONFILE = "_version.py"
VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"


def get_version():
    mo = re.search(VSRE, open(VERSIONFILE, "rt").read(), re.M)
    if mo:
        return mo.group(1)
    else:
        raise RuntimeError("Unable to find version string in %s." % VERSIONFILE)


def get_package():
    with open("requirements.txt") as fin:
        return fin.readlines()


setup(
    name='kiwi',
    version=get_version(),
    description='',
    long_description=open(READMEFILE).read(),
    url='',
    author='dave luo',
    license='BSD',
    packages=find_packages(),
    install_requires=get_package(),
    include_package_data=True,
    classifiers=[
    ],
)
