=================
Arbiter hardening
=================

The arbiter requires the following privileges:

* Incoming port for Dashboard/API (but you can bind to localhost and defer
  hardening to Nginx)
* Read config file
* Read/write IPFS data from a temporary directory
* Read/write from a temporary directory

It creates the following outgoing connections:

* DNS, if used in URLs.
* PostgreSQL (can be Unix domain socket, localhost, or over network)
* Polyswarmd API + WebSockets
* Submission to analysis backends


Recommended environment
=======================

The arbiter is an autonomous component that runs separately from polyswarmd
or any of the analysis backends; it does not share any resources such as
databases or local storage.
Its runtime environment should adhere to the following properties:

* Run the arbiter in a container or virtual machine so that it has its own
  network namespace.

  Filter ingress and egress traffic from outside this namespace, preventing
  the arbiter from being able to influence filtering.

* Run the arbiter in a read-only filesystem or as a user without access to any
  writable directories.

* Run the arbiter as a unique user.

* Ensure the IPFS cache directory and temporary file directory are writable to
  only the arbiter, and disable ``suid`` and ``exec``.




Syscall filtering
=================

The following syscalls have been observed during a normal run of the arbiter:

    accept4
    access
    arch_prctl
    bind
    brk
    clock_gettime
    clone
    close
    connect
    dup
    epoll_create
    epoll_ctl
    epoll_wait
    exit_group
    fcntl
    fstat
    futex
    getcwd
    getdents
    geteuid
    getpid
    getrandom
    getsockname
    getsockopt
    getuid
    ioctl
    listen
    lseek
    lstat
    mmap
    mprotect
    munmap
    openat
    pipe
    pipe2
    poll
    prlimit64
    read
    readlink
    recvfrom
    recvmsg
    rename
    rt_sigaction
    rt_sigprocmask
    rt_sigreturn
    sendto
    set_robust_list
    setsockopt
    set_tid_address
    sigaltstack
    socket
    stat
    statfs
    sysinfo
    uname
    unlink
    wait4
    write

It is strongly recommended to use e.g. seccomp to whitelist only these
syscalls and deny all others.
Certain syscalls (e.g. ``ioctl``) should further be filtered on their
arguments.
Definitely deny syscalls such as ``ptrace``.

Because the arbiter is written in Python, it is difficult to minimize this
list further. The exact list may also vary between Python versions, you can
use strace and Polymock to create a setup-specific list.
