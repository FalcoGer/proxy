#!/bin/python3

import os
import sys
import argparse

# For networking
import socket
import select

# Thread safe data structure to hold messages we want to send
from queue import SimpleQueue

# For creating multiple threads
from threading import Thread
from time import sleep

# This allows us to reload a python file
from importlib import reload

# This is where users may do live edits and alter the behavior of the proxy.
import proxyparser as parser

class Proxy(Thread):
    def __init__(self, bindAddr: str, remoteAddr: str, localPort: int, remotePort: int):
        super().__init__()
 
        self.running = False
        self.identifier = f"{bindAddr}:{localPort} -> {remoteAddr}:{remotePort}"

        self.bindAddr = bindAddr
        self.remoteAddr = remoteAddr
        self.localPort = localPort
        self.remotePort = remotePort
        
        # Sockets
        self.bindSocket = None
        self.server = None
        self.client = None

        self.bind(self.bindAddr, self.localPort)
        return

    def run(self) -> None:
        # after client disconnected await a new client connection
        while True:

            print(f"[proxy({self.identifier})] setting up.")
            # Wait for a client.
            self.waitForClient()
            
            # Client has connected.
            ch, cp = self.getClient()
            self.identifier = f"{ch}:{cp} -> {self.remoteAddr}:{self.remotePort}"
            print(f"[proxy({self.identifier})] client connected. Connecting to remote host.")
            
            # Connect to the remote host after a client has connected.
            self.connect()
            print(f"[proxy({self.identifier})] connection established.")

            # Start client and server socket handler threads.
            if self.client is not None:
                self.client.start()
            if self.server is not None:
                self.server.start()
            
            self.running = True
        return

    def sendData(self, destination: str, data: bytes) -> None:
        sh = self.client if destination == 'c' else self.server
        if sh is None:
            return
        sh.send(data)
        return
    
    def sendToServer(self, data: bytes) -> None:
        self.sendData('s', data)
        return
    
    def sendToClient(self, data: bytes) -> None:
        self.sendData('c', data)
        return

    def getClient(self) -> (str, int):
        ret = (None, None)
        if self.client is not None:
            ret = (self.client.host, self.client.port)
        return ret

    def getServer(self) -> (str, int):
        ret = (None, None)
        if self.server is not None:
            ret = (self.server.host, self.server.port)
        return ret
    
    def bind(self, host: str, port: int) -> None:
        print(f"[proxy({self.identifier})] Starting listening socket on {host}:{port}")
        self.bindSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bindSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bindSocket.bind((host, port))
        self.bindSocket.listen(1)

    def waitForClient(self) -> None:
        oldClient = self.client
        sock, addr = self.bindSocket.accept()
        self.client = SocketHandler(sock, (self.remoteAddr, self.remotePort), 'c', self)
        
        # Disconnect the old client if there was one.
        if oldClient is not None:
            oldClient.stop()
            oldClient.join()
            oldClient = None
            # Also disconnect from the server for a brand new connection.
            if self.server is not None:
                self.server.stop()
                self.server.join()
                self.server = None

        return
    
    def connect(self) -> None:
        print(f"[proxy({self.identifier})] Connecting to {self.remoteAddr}:{self.remotePort}")
        if self.server is not None:
            print(f"[proxy({self.identifier})] Already connected to remote host.")
            return

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.remoteAddr, self.remotePort))
            self.server = SocketHandler(sock, self.getClient(), 's', self)
        except Exception as e:
            print('[proxy({})] Unable to connect to server {}:{}. {}'.format(self.identifier, self.remoteAddr, self.remotePort, e))
            if self.client is not None:
                self.client.stop()
                self.client = None

        return

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.stop()
            self.client = None
        
        if self.server is not None:
            self.server.stop()
            self.server = None
        
        return

###############################################################################

# This class owns a socket, receives all it's data and accepts data into a queue to be sent to that socket.
class SocketHandler(Thread):
    def __init__(self, sock: socket.socket, other: (str, int), role: str, proxy: Proxy):
        super().__init__()
        
        self.sock = sock   # The socket
        self.other = other # The other socket host and port for output in the parser
        self.role = role   # Either 'c' or 's'
        self.proxy = proxy # To pass to the parser
        
        # Get this once, so there is no need to check for validity of the socket later.
        self.host, self.port = sock.getpeername()
        
        # Simple, thread-safe data structure for our messages to the socket to be queued into.
        self.dataQueue = SimpleQueue()
        
        self.running = False

        # Set socket non-blocking. recv() will return if there is no data available.
        sock.setblocking(True)
    
    def send(self, data: bytes) -> None:
        self.dataQueue.put(data)
        return

    def getHost(self) -> str:
        return self.host

    def getPort(self) -> int:
        return self.port

    def stop(self) -> None:
        # Cleanup of the socket is in the thread itself, in the run() function, to avoid the need for locks.
        self.running = False
        return

    def checkAlive(self) -> (bool, bool, bool):
        try:
            readyToRead, readyToWrite, inError = select.select([self.sock,], [self.sock,], [], 3)
        except select.error as e:
            self.stop()
        return (len(readyToRead) > 0, len(readyToWrite) > 0, inError)

    def run(self) -> None:
        self.running = True
        while self.running:
            # Receive data from the host.
            data = False
            abort = False

            readyToRead, readyToWrite, inError = self.checkAlive()
            
            # Check if stop has been called by checkAlive (or anyone else)
            if not self.running:
                continue

            if readyToRead:
                try:
                    data = self.sock.recv(4096)
                    if len(data) == 0:
                        raise IOError("Socket disconnected")
                except BlockingIOError as e:
                    # No data was available at the time.
                    pass
                except Exception as e:
                    print('[EXCEPT] - recv data from {} [{}:{}]: {}'.format(self.role, self.host, self.port, e))
                    self.proxy.disconnect()
                    continue
            
            # If we got data, parse it.
            if data:
                try:
                    # Parse the data. The parser may enqueue any data it wants to send on to the server.
                    # The parser adds any packages it actually wants to forward for the server to the queue.
                    parser.parse(data, (self.host, self.port), self.other, self.role, self.proxy)
                except Exception as e:
                    print('[EXCEPT] - parse data from {} [{}:{}]: {}'.format(self.role, self.host, self.port, e))
                    self.stop()
            
            # Send the queue
            readyToRead, readyToWrite, inError = self.checkAlive()
            if not self.running:
                continue
            
            queueEmpty = self.dataQueue.empty()
            if readyToWrite:
                try:
                    # Send any data which may be in the queue
                    while not self.dataQueue.empty():
                        message = self.dataQueue.get()
                        # print(f"Sending {message} to {self.role}")
                        self.sock.sendall(message)
                except Exception as e:
                    print('[EXCEPT] - xmit data to {} [{}:{}]: {}'.format(self.role, self.host, self.port, e))
                    abort = True
            
            if abort:
                self.proxy.disconnect()
                continue

            # Prevent the CPU from Melting
            # Sleep if we didn't get any data or if we didn't send
            if not data and (queueEmpty or not readyToWrite):
                sleep(0.001)
        
        # Stopped, clean up socket.
        if self.sock is None:
            return
        try:
            self.sock.shutdown(2) # 0: done recv, 1: done xmit, 2: both
        except Exception as e:
            pass
        try:
            self.sock.close()
        except Exception as e:
            pass
        self.sock = None
        return

###############################################################################

def main():
    # parse command line arguments.
    arg_parser = argparse.ArgumentParser(description='Create a proxy connection.')
    arg_parser.add_argument('-b', '--bind', required=False, help='Bind IP-address for the listening socket. Default \'0.0.0.0\'', default='0.0.0.0')
    arg_parser.add_argument('-r', '--remote', required=True, help='Remote host IP-address to connect to.')
    arg_parser.add_argument('-l', '--localport', type=int, required=True, help='Local port number to bind to.')
    arg_parser.add_argument('-p', '--remoteport', type=int, required=True, help='Remote port number to connect to.')

    args = arg_parser.parse_args()

    # Create a proxy with, binding on all interfaces.
    proxy = Proxy(args.bind, args.remote, args.localport, args.remoteport)
    proxy.start()

    # Accept user input and parse it.
    running = True
    while running:
        try:
            cmd = input('$ ')
            running = parser.handleUserInput(cmd, proxy)
            reload(parser)
        except Exception as e:
            print('[EXCEPT] - User Input: {}'.format(e))
    
    # Kill all threads and let the OS free all resources
    os._exit(0)


if __name__ == '__main__':
    main()
