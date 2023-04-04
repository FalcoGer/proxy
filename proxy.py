# debugging
import traceback

# For networking
import socket
import select

# Thread safe data structure to hold messages we want to send
from queue import SimpleQueue

# For creating multiple threads
from threading import Thread, Lock
from time import sleep

from eSocketRole import ESocketRole

# This is where users may do live edits and alter the behavior of the proxy.

class Proxy(Thread):
    def __init__(self, application, bindAddr: str, remoteAddr: str, localPort: int, remotePort: int, name: str):
        super().__init__()
        
        self.BIND_SOCKET_TIMEOUT = 3.0 # in seconds

        self.application = application
        self.name = name

        self.connected = False
        self.isShutdown = False

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

    def __str__(self):
        ret = f"{self.name} ["
        if self.isShutdown:
            ret += 'DEAD]'
            return ret

        if not self.connected:
            if self.client is not None:
                ch, cp = self.getClient()
                ret += f'C] {ch}:{cp}'
            else:
                ret += f'L] {self.bindAddr}:{self.localPort}'
        else:
            ch, cp = self.getClient()
            ret += f'E] {ch}:{cp} (BP: {self.localPort})'
        rh, rp = (self.remoteAddr, self.remotePort)
        ret += f' - {rh}:{rp}'
        return ret

    def run(self) -> None:
        # after client disconnected await a new client connection
        while not self.isShutdown:
            # Wait for a client.
            newClientHasConnected = self.waitForClient()
            if not newClientHasConnected:
                continue
            
            # Client has connected.
            ch, cp = self.getClient()
            print(f"[{self}] Client connected: {ch}:{cp}")
            
            # Connect to the remote host after a client has connected.
            if not self.connect():
                print(f'[{self}] Could not connect to remote host.')
                self.client.start()
                self.client.stop()
                self.client.join()
                self.client = None
                continue
            
            print(f'[{self}]: Connection established.')

            # Start client and server socket handler threads.
            self.client.start()
            self.server.start()
            
            self.connected = True
        # Shutdown
        if not self.client is None:
            self.client.stop()
            self.client.join()
            self.client = None
        if not self.server is None:
            self.server.stop()
            self.server.join()
            self.server = None
        return

    def shutdown(self) -> None:
        self.isShutdown = True
        return

    def sendData(self, destination: ESocketRole, data: bytes) -> None:
        sh = self.client if destination == ESocketRole.client else self.server
        if sh is None:
            return
        sh.send(data)
        return
    
    def sendToServer(self, data: bytes) -> None:
        self.sendData(ESocketRole.server, data)
        return
    
    def sendToClient(self, data: bytes) -> None:
        self.sendData(ESocketRole.client, data)
        return

    def getClient(self) -> (str, int):
        if self.client is None:
            return (None, None)
        return (self.client.host, self.client.port)

    def getServer(self) -> (str, int):
        if self.server is None:
            return (None, None)
        return (self.server.host, self.server.port)

    def bind(self, host: str, port: int) -> None:
        print(f"[{self}] Starting listening socket on {host}:{port}")
        self.bindSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.bindSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bindSocket.bind((host, port))
        self.bindSocket.listen(1)
        self.bindSocket.settimeout(self.BIND_SOCKET_TIMEOUT)

    def waitForClient(self) -> bool:
        try:
            sock, _ = self.bindSocket.accept()
        except TimeoutError:
            return False
        
        # Disconnect the old client if there was one.
        if self.client is not None:
            self.client.stop()
            self.client.join()
            self.client = None
        
        if self.server is not None:
            self.server.stop()
            self.server.join()
            self.server = None

        # Set new client
        self.client = SocketHandler(sock, ESocketRole.client, self)
        return True
    
    def connect(self) -> bool:
        print(f"[{self}] Connecting to {self.remoteAddr}:{self.remotePort}")
        if self.server is not None:
            raise RuntimeError(f"[{self}] Already connected to {self.server}.")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.remoteAddr, self.remotePort))
            self.server = SocketHandler(sock, ESocketRole.server, self)
            return True
        # pylint: disable=broad-except
        except Exception as e:
            print(f'[{self}] Unable to connect to server {self.remoteAddr}:{self.remotePort}: {e}')
        return False

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.stop()
            self.client = None
        
        if self.server is not None:
            self.server.stop()
            self.server = None

        self.connected = False
        
        return

###############################################################################

# This class owns a socket, receives all it's data and accepts data into a queue to be sent to that socket.
class SocketHandler(Thread):
    def __init__(self, sock: socket.socket, role: ESocketRole, proxy: Proxy):
        super().__init__()
        
        self.sock = sock                # The socket
        self.role = role                # Either client or server
        self.proxy = proxy              # To disconnect on error

        # Get this once, so there is no need to check for validity of the socket later.
        self.host, self.port = sock.getpeername()
        
        # Simple, thread-safe data structure for our messages to the socket to be queued into.
        self.dataQueue = SimpleQueue()
        
        self.running = False

        # Set socket non-blocking. recv() will return if there is no data available.
        sock.setblocking(True)

        self.lock = Lock()

    def send(self, data: bytes) -> None:
        self.dataQueue.put(data)
        return

    def getHost(self) -> str:
        return self.host

    def getPort(self) -> int:
        return self.port

    def stop(self) -> None:
        # Cleanup of the socket is in the thread itself, in the run() function, to avoid the need for locks.
        self.lock.acquire()
        self.running = False
        self.lock.release()
        return

    def checkAlive(self) -> (bool, bool, bool):
        try:
            readyToRead, readyToWrite, inError = select.select([self.sock,], [self.sock,], [], 3)
        except select.error:
            self.stop()
        return (len(readyToRead) > 0, len(readyToWrite) > 0, inError)

    def sendQueue(self) -> bool:
        abort = False
        try:
            # Send any data which may be in the queue
            while not self.dataQueue.empty():
                message = self.dataQueue.get()
                #print(f">>> Sending {len(message)} Bytes to {self.role.name}")
                self.sock.sendall(message)
        # pylint: disable=broad-except
        except Exception as e:
            print(f'[EXCEPT] - xmit data to {self}: {e}')
            abort = True
        return abort

    def __str__(self) -> str:
        return f'{self.role.name} [{self.host}:{self.port}]'

    def run(self) -> None:
        if self.sock is None:
            raise RuntimeError('Socket has expired. Can not start again after shutdown.')
        self.lock.acquire()
        self.running = True
        self.lock.release()
        localRunning = True
        while localRunning:
            self.lock.acquire()
            localRunning = self.running
            self.lock.release()
            # Receive data from the host.
            data = False
            abort = False

            readyToRead, readyToWrite, _ = self.checkAlive()

            if readyToRead:
                # pylint: disable=broad-except
                try:
                    data = self.sock.recv(4096)
                    if len(data) == 0:
                        raise IOError("Socket Disconnected")
                except BlockingIOError:
                    # No data was available at the time.
                    pass
                except Exception as e:
                    print(f'[EXCEPT] - recv data from {self}: {e}')
                    abort = True
            
            # If we got data, parse it.
            if data:
                try:
                    # Parse the data. The parser may enqueue any data it wants to send on to the server.
                    # The parser adds any packages it actually wants to forward for the server to the queue.
                    parser = self.proxy.application.getParserByProxy(self.proxy)
                    parser.parse(data, self.proxy, self.role)
                # pylint: disable=broad-except
                except Exception as e:
                    print(f'[EXCEPT] - parse data from {self}: {e}')
                    print(traceback.format_exc())
                    self.stop()
            
            # Send the queue
            queueEmpty = self.dataQueue.empty()
            readyToRead, readyToWrite, _ = self.checkAlive()
            abort2 = False
            if not queueEmpty and readyToWrite:
                abort2 = self.sendQueue()
            
            if abort or abort2:
                self.proxy.disconnect()

            # Prevent the CPU from Melting
            # Sleep if we didn't get any data or if we didn't send
            if not data and (queueEmpty or not readyToWrite):
                sleep(0.001)
        
        # Stopped, clean up socket.
        # Send all remaining messages.
        sleep(0.1)
        self.sendQueue()
        sleep(0.1)

        self.sock.close()
        self.sock = None
        return

