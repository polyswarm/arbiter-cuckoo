# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import setuptools

setuptools.setup(
    name="arbiter",
    version="0.1",
    author="Jurriaan Bremer",
    author_email="jbr@cuckoo.sh",
    packages=[
        "arbiter",
    ],
    url="https://cuckoo.sh/",
    license="MIT License",
    description="PolySwarm Arbiter backend",
    long_description="PolySwarm Arbiter backend framework",
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "arbiter = arbiter.main:main",
        ],
    },
    install_requires=[
        "click==6.6",
        "future==0.16.0",
        "pyyaml==3.12",
        "requests>=2.13.0",
        "six==1.11.0",
        "websocket-client==0.47.0",
    ],
)
