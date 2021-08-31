discord.py (local fork)
==========

This is a local maintenance fork of the discord.py library.

This is primarily intended for my own private projects, and thus, goals of this repository may not be useful to you.

You're still welcome to use this code as-is if you wish, but I can not provide any support at this time, and no warranties are implied.
In particular, backwards-incompatible changes may happen at any time with no warning, for now.
If a well-maintained public fork emerges somewhere, I may try to reconcile this branch with it, or I may not.

The goals of this fork are

* Maintain compatibility with discord API upgrades where feasible

* Include support for threads, application commands (slash commands), and message components (View widgets)

* Power the kind of bots I'm writing, which are typically single-server interactive game projects.

Limitations that will likely show up to simplify the implementation:

* No support for installing different slash commands on a per-guild basis (but a shorthand for installing all currently-wired commands to a server)

The Future of discord.py
--------------------------

Please read the `gist <https://gist.github.com/Rapptz/4a2f62751b9600a31a0d3c78100287f1>`_ for the status of the original project.

Links
------

- `Documentation <https://discordpy.readthedocs.io/en/latest/index.html>`_
- `Official Discord Server <https://discord.gg/r3sSKJJ>`_
- `Discord API <https://discord.gg/discord-api>`_
