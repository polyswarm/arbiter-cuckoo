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

    # Tip: use quoted strings to ensure the values are valid YAML-syntax.

    # Dashboard and API:
    bind: 'localhost:49080'
    url: 'https://arbiter.cuckoo.sh'

    # Password necessary to log in to the dashboard
    # Example value: 't0ps3cret5'
    dashboard_password: *CHANGE-ME

    # Secret used for analysis backend authentication
    # Example value: 'v3rystr0ngs3cr3t'
    api_secret: *CHANGE-ME

    # PolySwarmd URL and API key
    # Example API URL: 'polyswarmd.polyswarm.io'
    # Example API key: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    polyswarmd: *CHANGE-ME
    apikey: *CHANGE-ME

    # Arbiter account (used to fetch wallet info)
    # Address format: '0x123'
    addr: *CHANGEME
    # Private key format: '0x123'
    addr_privkey: *CHANGEME

    # Artifact cache (needs to be writable)
    artifacts: /srv/arbiter/samples

    # Database
    # Example value: 'postgresql://polyswarm:myL1ttl3p0ly!@localhost/arbiter'
    dburi: *CHANG-EME

    # Optional list of experts that we trust. That is, if they disagree with
    # our verdict the bounty is set to manual mode, requiring a user to
    # double-check the verdict.
    # Example address format: '0xe23bc28b143259aa0ce9c9c949f882c6acb9822b'
    #
    #trusted_experts:
    #- "0x..."

    # You must configure at least one analysis backend. The arbiter needs to
    # be able to access the URL.
    analysis_backends:
      # The name of the backend identifies which backend plugin will be used
      cuckoo:
        # The URL to the Cuckoo API
        url: https://upstream.cuckoo.sh:8090/

        # OPTIONAL: The URL to the Cuckoo Web interface for viewing of reports
        view: https://upstream.cuckoo.sh:8100/

        # We fully trust the verdict if this backend identifies a sample as
        # malicious (doesn't require majority vote)
        trusted: true

      zer0m0n:
        # Explicitly specify which plugin to use, in case you have multiple of
        # the same type (but maybe a different version or options)
        plugin: cuckoo
        url: https://upstream.cuckoo.sh:8090/
        # Cuckoo specific: analysis options
        options: 'analysis=kernel,human=0'

      # Cuckoo Modified
      modified:
        url: https://modified.cuckoo.sh:8090/

      # Example of a process-based scanner (running under abrunner)
      demoscan:
        plugin: process
        url: https://demoscan.cuckoo.sh:8090/

You **must** change all the values to match your setup.
Generate strong random secrets for the dashboard password and API secret.
Make sure only the arbiter can read this file.

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
enable the callback module in ``.cuckoo/conf/reporting.conf`` and configure
the secret used for identification::

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
