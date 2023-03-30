#!/bin/python3

import socket
import os
import sys
from threading import Thread
import parser as parser
import random
import struct
from importlib import reload
import argparse
from queue import SimpleQueue

class Proxy:
    pass

# This thread class connects to a remote host.
# Any data received from that host is put through the parser.
class Remote2Proxy(Thread):
    def __init__(self, host: str, port: int, proxy: Proxy):
        super(Remote2Proxy, self).__init__()
        self.port = port
        self.host = host
        self.proxy = proxy
        print(f"Connecting to {host}:{port}")
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.connect((host, port))
        # self.server.setblocking(False)

    # This function ins ran in a thread
    def run(self):
        while True:
            # Receive data from the server
            data = False
            try:
                data = self.server.recv(4096)
            except BlockingIOError as e:
                # no data was available at the time
                pass
            if data:
                try:
                    # Parse the data from the parser
                    # If the parser wants to send the data, it will append it to the queue, potentially modified
                    parser.parse(data, self.port, 'server', self.proxy)
                except Exception as e:
                    print('[EXCEPT] - recv server data [{}]: {}'.format(self.port, e))

# This thread class binds a listening port and awaits a connection.
# Any traffic sent to it will be parsed by the parser and then sent onto the server.
class Client2Proxy(Thread):
    def __init__(self, host: str, port: int, proxy: Proxy):
        super(Client2Proxy, self).__init__()
        self.port = port
        self.host = host
        self.proxy = proxy
        print(f"Starting listening socket on {host}:{port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(1)
        # Wait for a connection.
        self.client, addr = sock.accept()
        # self.client.setblocking(False)

    def run(self):
        while True:
            # Fetch data from the client.
            data = False
            try:
                data = self.client.recv(4096)
            except BlockingIOError as e:
                # No data was available at the time.
                pass

            # If we got data, parse it.
            if data:
                try:
                    # Parse the data. The parser may enqueue any data it wants to send on to the server.
                    # The parser adds any packages it actually wants to forward for the server to the queue.
                    parser.parse(data, self.port, 'client', self.proxy)
                except Exception as e:
                    print('[EXCEPT] - recv client data [{}]: {}'.format(self.port, e))

class Proxy(Thread):
    def __init__(self, bind: str, remote: str, localport: int, remoteport: int):
        super(Proxy, self).__init__()
        self.bind = bind
        self.remote = remote
        self.localport = localport
        self.remoteport = remoteport
        self.running = False
        self.identifier = "{}:{} -> {}:{}".format(self.bind, self.localport, self.remote, self.remoteport)
        self.dataSenderServer = None
        self.dataSenderClient = None

    def run(self):
        # after client disconnected await a new client connection
        while True:
            print(f"[proxy({self.identifier})] setting up")
            # Wait for a client.
            self.c2p = Client2Proxy(self.bind, self.localport, self)
            # Connect to the remote host after a client has connected.
            self.s2p = Remote2Proxy(self.remote, self.remoteport, self)
            print(f"[proxy({self.identifier})] connection established")
            
            # set up reference to each other
            self.c2p.server = self.s2p.server
            self.s2p.client = self.c2p.client

            self.c2p.start()
            self.s2p.start()
            
            # Set up the data sender.
            self.dataSenderClient = DataSender(self.c2p.client)
            self.dataSenderClient.start()
            self.dataSenderServer = DataSender(self.s2p.server)
            self.dataSenderServer.start()
            
            self.running = True

    def sendToClient(self, data: bytes) -> None:
        self.dataSenderClient.dataQueue.put(data)
        return

    def sendToServer(self, data: bytes) -> None:
        self.dataSenderServer.dataQueue.put(data)
        return

# This thread will send data to the client and server from thread safe queues.
# Anything may attach messages to either queue.
class DataSender(Thread):
    def __init__(self, socket):
        super(DataSender, self).__init__()
        self.dataQueue = SimpleQueue()
        self.socket = socket

    def run(self):
        while True:
            try:
                # Send any data which may be in the queue
                while not self.dataQueue.empty():
                    data = self.dataQueue.get()
                    # print(f"Sending {data} to the client")
                    self.socket.sendall(data)
            except Exception as e:
                print('[EXCEPT] - xmit data [{}:{}]: {}'.format(self.socket.addr, self.socket.port, e))

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
