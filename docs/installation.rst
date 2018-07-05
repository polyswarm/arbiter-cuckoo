====================
Arbiter installation
====================

Create an arbiter user and the necessary directories (adjust the paths to your
liking)::

    useradd -s /usr/sbin/nologin -r arbiter -d /srv/arbiter
    mkdir -p /srv/arbiter/samples /srv/arbiter/tmp
    chown arbiter:arbiter /srv/arbiter/samples /srv/arbiter/tmp
    cd /srv/arbiter

Create a VirtualEnv and install the Arbiter and its dependencies::

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install /path/to/code

To automatically create the initial configuration, run::

    arbiter --config /srv/arbiter/arbiter.yaml conf

Change the configuration of the Arbiter as necessary for your setup.
Annotated example arbiter configuration::

    # Dashboard and API:
    bind: 'localhost:49080'
    url: 'https://arbiter.cuckoo.sh'

    # Password necessary to log in to the dashboard
    dashboard_password: 'N-lYIFcHtB52C1mZ9e3tQA'

    # Secret used for analysis backend authentication
    api_secret: '0FR5bj19nh-BByb6CbArowDuvVL14BrxsdcKMl_Be7A'

    # PolySwarm address
    host: 'localhost:8091'

    # Arbiter account (used to fetch wallet info)
    addr: '0x1f50Cf288b5d19a55ac4c6514e5bA6a704BD03EC'

    # Artifact cache (needs to be writable)
    artifacts: /srv/arbiter/samples

    # Database
    dburi: 'postgresql://polyswarm:myL1ttl3p0ly!@localhost/arbiter'

    # Optional list of experts that we trust. That is, if they disagree with
    # our verdict the bounty is set to manual mode, requiring a user to
    # double-check the verdict.
    trusted_experts:
    - "0xe23bc28b143259aa0ce9c9c949f882c6acb9822b"

    # You must configure at least one analysis backend. The arbiter needs to
    # be able to access the URL.
    analysis_backends:
      # The name of the backend identifies which backend plugin will be used
      cuckoo:
        # The URL to the Cuckoo API
        url: http://upstream.cuckoo.sh:8090/

        # OPTIONAL: The URL to the Cuckoo Web interface for viewing of reports
        view: http://upstream.cuckoo.sh:8100/

        # We fully trust the verdict if this backend identifies a sample as
        # malicious (doesn't require majority vote)
        trusted: true

      zer0m0n:
        # Explicitly specify which plugin to use, in case you have multiple of
        # the same type (but maybe a different version or options)
        plugin: cuckoo
        url: http://upstream.cuckoo.sh:8090/
        # Cuckoo specific: analysis options
        options: 'analysis=kernel,human=0'

      # Cuckoo Modified
      modified:
        url: http://modified.cuckoo.sh:8090/

      # Example of a process-based scanner (running under abrunner)
      demoscan:
        plugin: process
        url: http://demoscan.cuckoo.sh:8090/

Run the arbiter using your favorite deployment method, e.g. using the included
systemd unit::

    cp arbiter.service /etc/systemd/system/arbiter.service
    systemctl daemon-reload
    systemctl start arbiter


Deploying upstream Cuckoo
=========================

Install Cuckoo according to its installation instructions.
The Cuckoo instance should run on a completely separate system.
Run the API server so that the arbiter can submit tasks.
You can optionally run the web interface if you want a nicer interface for
task reports.
If it is used solely by the arbiter, ensure that only the arbiter can access
it over the network.

To allow Cuckoo to report back artifact verdicts, you must
enable the callback module in ``.cuckoo/conf/reporting.conf``::

    [arbiter]
    enabled = yes
    token = cuckoo.1529584770.846d479d12f5422fa4230691f5623b4274a3961d5eb427272bf7cbea03bb8543

The arbiter submits a callback URL to Cuckoo via the ``options`` field during
task creation.
The arbiter reporting module then simply uses this URL to submit a verdict,
based on task score.
The token is generated using the ``scripts/token-gen`` script, which requires
that you first configure ``arbiter.yaml`` with the properties of the Cuckoo
install.
