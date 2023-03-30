#!/bin/python3

import os
import sys
import argparse

# For networking
import socket

# Thread safe data structure to hold messages we want to send
from queue import SimpleQueue

# For creating multiple threads
from threading import Thread
#from threading import Lock
from time import sleep

# This allows us to reload a python file
from importlib import reload

# This is where users may do live edits and alter the behavior of the proxy.
import parser as parser

class Proxy(Thread):
    def __init__(self, bindAddr: str, remoteAddr: str, localPort: int, remotePort: int):
        super(Proxy, self).__init__()
        
        self.running = False
        self.identifier = "{}:{} -> {}:{}".format(bindAddr, localPort, remoteAddr, remotePort)

        self.bindAddr = bindAddr
        self.remoteAddr = remoteAddr
        self.localPort = localPort
        self.remotePort = remotePort
        
        # Sending threads
        self.dataSenderClient = None
        self.dataSenderServer = None

        # Receiving threads
        self.dataReceiverClient = None
        self.dataReceiverServer = None
        
        # Sockets
        self.bindSocket = None
        self.clientSocket = None
        self.remoteSocket = None

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
            self.identifier = "{}:{} -> {}:{}".format(ch, cp, self.remoteAddr, self.remotePort)
            print(f"[proxy({self.identifier})] client connected. Connecting to remote host.")
            
            # Connect to the remote host after a client has connected.
            self.connect()
            print(f"[proxy({self.identifier})] connection established.")

            # Set up and start the data receiver threads.
            self.dataReceiverClient = DataReceiver(self.clientSocket, self.remoteSocket, 'c', self)
            self.dataReceiverServer = DataReceiver(self.remoteSocket, self.clientSocket, 's', self)
            self.dataReceiverClient.start()
            self.dataReceiverServer.start()
            
            # Set up and start the data sender threads.
            self.dataSenderClient = DataSender(self.clientSocket, self)
            self.dataSenderServer = DataSender(self.remoteSocket, self)
            self.dataSenderClient.start()
            self.dataSenderServer.start()
            
            self.running = True
        return

    def sendData(self, destination: str, data: bytes) -> None:
        ds = self.dataSenderClient if destination == 'c' else self.dataSenderServer
        ds.send(data)
        return
    
    def sendToServer(self, data: bytes) -> None:
        self.sendData('s', data)
        return
    
    def sendToClient(self, data: bytes) -> None:
        self.sendData('c', data)
        return

    def getClient(self) -> (str, int):
        return self.clientSocket.getpeername()

    def getServer(self) -> (str, int):
        return self.remoteSocket.getpeername()
    
    def bind(self, host: str, port: int) -> None:
        print(f"[proxy({self.identifier})] Starting listening socket on {host}:{port}")
        self.bindSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bindSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bindSocket.bind((host, port))
        self.bindSocket.listen(1)

    def waitForClient(self) -> None:
        oldClientSocket = self.clientSocket
        # Lock until new connection is established
        self.clientSocket, addr = self.bindSocket.accept()

        # Set socket non-blocking. recv() will return if there is no data available.
        #self.clientSocket.setblocking(0)

        if oldClientSocket != None:
            # There is a client already, disconnect them.
            oldClientSocket.close()
            # Also disconnect from the server
            self.disconnectServer()

        return
    
    def connect(self) -> None:
        print(f"[proxy({self.identifier})] Connecting to {self.remoteAddr}:{self.remotePort}")
        if self.remoteSocket != None:
            print(f"[proxy({self.identifier})] Already connected to remote host.")
            return

        self.resetDataSenderServerAndDataReceiverServer()
        
        try:
            self.remoteSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.remoteSocket.connect((self.remoteAddr, self.remotePort))
            # Set socket non-blocking. recv() will return if there is no data available.
            #self.remoteSocket.setblocking(0)
        except Exception as e:
            print('[proxy({})] Unable to connect to server {}:{}.'.format(self.identifier, self.remoteAddr, self.remotePort))
            self.disconnectClient()

        return

    def disconnectServer(self) -> None:
        self.resetDataSenderServerAndDataReceiverServer()
        if self.remoteSocket == None:
            return

        self.remoteSocket.close()
        self.remoteSocket = None
        return

    def disconnectClient(self) -> None:
        self.resetDataSenderClientAndDataReceiverClient()
        if self.clientSocket == None:
            return
        
        self.clientSocket.close()
        self.clientSocket = None
        return

    def resetDataSenderServerAndDataReceiverServer(self) -> None:
        # Reset data senders and receivers.
        if self.dataSenderServer != None:
            self.dataSenderServer.stop()
            self.dataSenderServer.join()
            self.dataSenderServer = None
        
        if self.dataReceiverServer != None:
            self.dataReceiverServer.stop()
            self.dataReceiverServer.join()
            self.dataReceiverServer = None
        
        return

    def resetDataSenderClientAndDataReceiverClient(self) -> None:
        # Reset data senders and receivers.
        if self.dataSenderClient != None:
            self.dataSenderClient.stop()
            self.dataSenderClient.join()
            self.dataSenderClient = None
        
        if self.dataReceiverClient != None:
            self.dataReceiverClient.stop()
            self.dataReceiverClient.join()
            self.dataReceiverClient = None

        return

##############################################################################################

# Any traffic sent to this thread will be parsed by the parser.
class DataReceiver(Thread):
    def __init__(self, srcSock: socket.socket, destSock: socket.socket, origin: str, proxy: Proxy):
        super(DataReceiver, self).__init__()
        self.srcSock = srcSock
        self.destSock = destSock
        self.proxy = proxy
        self.origin = origin
        self.running = False

    def run(self) -> None:
        self.running = True
        while self.running:
            # Fetch data from the client.
            data = False
            host = None
            port = None
            try:
                host, port = self.srcSock.getpeername()
                data = self.srcSock.recv(4096)
            except BlockingIOError as e:
                # No data was available at the time.
                pass
            except Exception as e:
                print('[EXCEPT] - recv {} data [{}:{}]: {}'.format(self.origin, host, port, e))
                self.proxy.disconnectClient()
                self.stop()

            # If we got data, parse it.
            if data:
                try:
                    # Parse the data. The parser may enqueue any data it wants to send on to the server.
                    # The parser adds any packages it actually wants to forward for the server to the queue.
                    parser.parse(data, self.srcSock, self.destSock, self.origin, self.proxy)
                except Exception as e:
                    print('[EXCEPT] - recv {} data [{}:{}]: {}'.format(self.origin, host, port, e))
                    self.stop()
        return

    def stop(self) -> None:
        self.running = False
        return

##############################################################################################

# This thread will send data to the client and server from thread safe queues.
# Anything may attach messages to either queue.
class DataSender(Thread):
    def __init__(self, socket: socket.socket, proxy: Proxy):
        super(DataSender, self).__init__()
        self.dataQueue = SimpleQueue()
        self.socket = socket
        self.running = False
        self.proxy = proxy

    def send(self, data: bytes) -> None:
        self.dataQueue.put(data)

    def run(self) -> None:
        self.running = True
        while self.running:
            host = None
            port = None
            try:
                host, port = self.socket.getpeername()
                # Send any data which may be in the queue
                while not self.dataQueue.empty():
                    data = self.dataQueue.get()
                    # print(f"Sending {data} to the client")
                    self.socket.sendall(data)
                # Stop the CPU from melting.
                sleep(0.001)
            except Exception as e:
                print('[EXCEPT] - xmit data [{}:{}]: {}'.format(host, port, e))
                self.proxy.disconnectClient()
                self.stop()
        return

    def stop(self) -> None:
        self.running = False

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
