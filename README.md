A generic TCP proxy that can inspect, drop, alter and inject arbitrary TCP packages.

The main features include:

- An easily extensible command line interface with history and auto-complete to do anything you want.
- Live update of your package parser and command line commands without the need to restart the application or reconnect the client. Simply send a command or an empty line to reload your python script.
- Display and decode packets based on your code to show them in a human readable format.
- Drop, forward, alter or inject packets based on your code, either with a custom command, or triggered when a packet arrives and matching your filter or even in a custom thread for more complex scenarios.
- Easy to use API to manipulate your network traffic. Any data received is sent to the parse function and any data you want to send you simply send with the `Proxy.SendToClient(bytes)` or `Proxy.SendToServer(bytes)` functions.
- Proxies are spun up as threads. If you need more than one at a time you can happily just make more.
- The binding ports stay open, if you get disconnected, just connect again. No need to restart the proxy. Connecting again with a connection already open closes that connection.
- Spin up multiple proxies at once by providing more port pairs

Note: As the parser gets reloaded on every command, you can not store settings in memory if that memory gets initialized in that file as it would simply be overwritten with default values every time you send a new command. A special settings container API is provided.

