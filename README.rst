Cuckoo Arbiter
==============

Cuckoo Sandbox Arbiter Backend for PolySwarm.

Usage
=====

Create default configuration and initialize database:

.. code:: bash

    virtualenv venv
    source venv/bin/activate
    pip install -e .

    arbiter run


Run Arbiter in debug mode and with a clean database:

.. code:: bash

    arbiter --clean --debug run
