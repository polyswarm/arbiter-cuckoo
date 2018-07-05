Cuckoo Arbiter
==============

Cuckoo Sandbox Arbiter Backend for PolySwarm.


Usage
=====

Refer to the installation guide at `install_guide`_.
Then run the Arbiter from the VirtualEnv::

    source venv/bin/activate
    arbiter run


Run Arbiter in debug mode and with a clean database::

    arbiter --clean --debug run

.. _install_guide: docs/installation.rst


PolyMock
========

If you want to run a fake ``polyswarmd`` instance, with integrated Cuckoo API
mock, you can run PolyMock::

    source venv/bin/activate
    python polymock/polymock.py

PolyMock runs on port 8091.
Note that you can tweak some of its constants in order to adjust the
speed of block mining, bounties created per block, and so on.


Unit tests
==========

Install required unit testing libraries:

.. code:: bash

    pip install pytest mock

Run the unit tests:

.. code:: bash

    py.test
