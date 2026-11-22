"""Reading data the kernel keeps for root.

Some things need privileges with no way around them:

* The full SMBIOS table (`/sys/firmware/dmi/tables/DMI`, mode 0400), where
  the memory modules are: maker, part number, ranks, speed and voltage.
* The processor's MSR registers (`/dev/cpu/*/msr`), where the real core
  voltage comes from.
* The disks' SMART logs, the energy counters and the graphics and memory
  controller's PMU counters.

The main program never runs as root. When one of those data is needed it
launches a minimal helper through polkit, talks to it over a pipe and keeps
it alive for the session. The helper only knows how to do those reads: it
runs no commands, writes nothing and takes no arbitrary paths.
"""
