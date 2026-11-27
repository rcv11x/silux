# Security

## Reporting a vulnerability

Please report it privately, not in a public issue: use **Report a
vulnerability** in the repository's
[Security tab](https://github.com/rcv11x/silux/security). Say what it
affects, how to reproduce it and which version (`silux --version` gives the
version and the commit). You will get an answer within a week.

## What runs with privileges

Silux reads most data as the user. What only the administrator can read
(memory modules, disk health, core voltage, some power and usage counters)
goes through a small helper started with `pkexec`:

- It understands eight requests and nothing else: no paths, no commands, no
  arguments on its command line.
- It only reads: devices are opened read-only, the disk commands are the
  fixed diagnostic ones, and the performance counters count without
  sampling. The one exception is asked for with a button: loading one of
  four sensor modules (`drivetemp`, `spd5118`, `ee1004`, `at24`) or `msr`
  (which only lets root open the processor's registers) with `modprobe`,
  until the next boot. It writes no file.
- It talks only to the process that started it, through a pipe.
- It can run once (the password is asked every time) or be installed in
  `/usr/local/libexec/silux/`, owned by root, with its own polkit action.

How it works and why: [docs/privilegios.md](docs/privilegios.md) (in
Spanish).

One more thing leaves the machine: the updater. On opening it asks GitHub
for the latest version, sending nothing but its own version, and Settings
turns that off. It downloads only when the user presses «Update», and
verifies the AppImage before putting it in place.

## Reports and privacy

The bug report (`--report`) and its annex cover the machine's name, the
user's name, addresses, serial numbers and mount points.
`tools/comprobar_privacidad.py` checks what would be published. A report
that still identifies someone is a vulnerability too.

## Supported versions

The latest release and the latest test release (`0.4.0rcN`).
