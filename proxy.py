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

# This thread class connects to a remote host.
# Any data received from that host is put through the parser.
class Remote2Proxy(Thread):

    def __init__(self, host, port):
        super(Remote2Proxy, self).__init__()
        self.client = None # game client socket not known yet
        self.port = port
        self.host = host
        print(f"Connecting to {host}:{port}")
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.connect((host, port))
        self.server.setblocking(False)

    # run in thread
    def run(self):
        while True:
            # receive data from the server
            data = False
            try:
                data = self.server.recv(4096)
            except BlockingIOError as e:
                # no data was available at the time
                pass
            if data:
                try:
                    # parse the data from the parser
                    # if the parser wants to send the data, it will append it to the queue, potentially modified
                    parser.parse(data, self.port, 'server')
                except Exception as e:
                    print('[EXCEPT] - server[{}]: {}'.format(self.port, e))

            # send any data which may be in the queue to the client
            # this only works because this thread is the only consumer for the queue
            while not parser.CLIENT_QUEUE.empty():
                pkt = parser.CLIENT_QUEUE.get()
                # print(f"Sending {pkt} to the client")
                self.client.sendall(pkt)

# this thread binds a listening port and awaits a connection.
# any traffic sent to it will be parsed by the parser and then sent onto the server.
class Client2Proxy(Thread):

    def __init__(self, host, port):
        super(Client2Proxy, self).__init__()
        self.server = None # real server socket not known yet
        self.port = port
        self.host = host
        print(f"Starting listening socket on {host}:{port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(1)
        # waiting for a connection
        self.client, addr = sock.accept()
        self.client.setblocking(False)

    def run(self):
        while True:
            # fetch data from the client
            data = False
            try:
                data = self.client.recv(4096)
            except BlockingIOError as e:
                # no data was available at the time
                pass

            # if we got data, parse it.
            if data:
                try:
                    # parse the data. the parser may enqueue any data it wants to send on to the server.
                    # the parser adds any packages it actually wants to forward for the server to the queue.
                    parser.parse(data, self.port, 'client')
                except Exception as e:
                    print('[EXCEPT] - client[{}]: {}'.format(self.port, e))

            # send any data which may be in the queue to the server
            # this only works because this thread is the only consumer for the queue
            while not parser.SERVER_QUEUE.empty():
                pkt = parser.SERVER_QUEUE.get()
                # print(f"Sending {pkt} to the server")
                self.server.sendall(pkt)

class Proxy(Thread):

    def __init__(self, bind, remote, localport, remoteport):
        super(Proxy, self).__init__()
        self.bind = bind
        self.remote = remote
        self.localport = localport
        self.remoteport = remoteport
        self.running = False
        self.identifier = "{}:{} -> {}:{}".format(self.bind, self.localport, self.remote, self.remoteport)

    def run(self):
        # after client disconnected await a new client connection
        while True:
            print(f"[proxy({self.identifier})] setting up")
            self.c2p = Client2Proxy(self.bind, self.localport) # waiting for a client
            self.s2p = Remote2Proxy(self.remote, self.remoteport)
            print(f"[proxy({self.identifier})] connection established")
            # set up reference to each other
            self.c2p.server = self.s2p.server
            self.s2p.client = self.c2p.client
            self.running = True

            self.c2p.start()
            self.s2p.start()


def main():
    # parse command line arguments
    arg_parser = argparse.ArgumentParser(description='Create a proxy connection')
    arg_parser.add_argument('-b', '--bind', required=False, help='Bind address for the listening socket. Default \'0.0.0.0\'', default='0.0.0.0')
    arg_parser.add_argument('-r', '--remote', required=True, help='Remote host connect to')
    arg_parser.add_argument('-l', '--localport', type=int, required=True, help='Local port to bind to')
    arg_parser.add_argument('-p', '--remoteport', type=int, required=True, help='Remote port to connect to')

    args = arg_parser.parse_args()

    # create a proxy with, binding on all interfaces
    proxy = Proxy(args.bind, args.remote, args.localport, args.remoteport)
    proxy.start()

    # accept user input and parse it
    while True:
        try:
            cmd = input('$ ')
            if cmd == 'quit' or cmd == 'exit':
                os._exit(0)
            elif cmd[0:2] == 'S ':
                # send to server
                pkt = bytes.fromhex(cmd[2:])
                if proxy.running:
                    parser.SERVER_QUEUE.put(pkt)
            elif cmd[0:2] == 'C ':
                # send to client
                pkt = bytes.fromhex(cmd[2:])
                if proxy.running:
                    parser.CLIENT_QUEUE.put(pkt)
            # more commands here
            elif len(cmd.strip()) == 0:
                pass
            else:
                print(f"Undefined command: \"{cmd}\"")
            
            reload(parser)
        except Exception as e:
            print(e)

if __name__ == '__main__':
    main()
