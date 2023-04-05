A generic TCP proxy that can inspect, drop, alter and inject arbitrary TCP packages.

The main features include:

- An easily extensible command line interface with history and auto-complete to do anything you want.
- Live update of your package parser and command line commands without the need to restart the application or reconnect the client. Your module is automatically reloaded when it has changed. You can even load entirely new parsers from files on the fly.
- Display and decode packets based on your code to show them in a human readable format.
- Built in hexdump with configurable colors.
- Drop, forward, alter or inject packets based on your code, either with a custom command, or triggered when a packet arrives and matching your filter or even in a custom thread for more complex scenarios.
- Easy to use API to manipulate your network traffic. Any data received is sent to the parse function and any data you want to send you simply send with the `Proxy.SendToClient(bytes)` or `Proxy.SendToServer(bytes)` functions.
- Proxies are spun up as threads. Create and kill them on the fly as they are needed without the need to restart or reconnect anything.
- The binding ports stay open, if you get disconnected, just connect again. No need to restart the proxy. Connecting again with a connection already open closes that connection.
- Spin up multiple proxies at once by providing more port pairs
- Extensive online help with the `help` command
- You can set variables and store them to a file to be reloaded later and then use those variables in your commands.

