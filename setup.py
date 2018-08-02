# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import setuptools

setuptools.setup(
    name="arbiter",
    version="0.3.1",
    author="Jurriaan Bremer",
    author_email="jbr@cuckoo.sh",
    packages=setuptools.find_packages(),
    zip_safe=False,
    url="https://cuckoo.sh/",
    license="MIT License",
    description="PolySwarm Arbiter backend",
    long_description=open("README.rst", "rb").read().decode(),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "arbiter = arbiter.main:cli",
        ],
    },
    install_requires=[
        "click==6.6",
        "flask==1.0.2",
        "future==0.16.0",
        "psycopg2-binary",
        "pyyaml==3.12",
        "requests>=2.13.0",
        "gevent>=1.3",
        "gevent-websocket>=0.10",
        "six==1.11.0",
        "sqlalchemy",
        "ws4py>=0.5",
        "web3==4.4.1",
    ],
)
