A generic TCP proxy that can inspect, drop, alter and inject arbitrary TCP packages.

Originally adopted from lifeoverflow, created for the pwn adventure CTF

Original code at
https://github.com/LiveOverflow/PwnAdventure3/tree/master/tools/proxy

I have adopted the following changes:

- Python 3, because who uses Python 2 anymore for new projects?!
- Stripped any specific code for the CTF
- Argparse for more flexibility
- Using non blocking sockets to allow for injections via command
- Every packet now goes through the query arrays, this allows the parser to drop packets it doesn't want or inject multiple at once
