# debugging
from __future__ import annotations
import typing
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

if typing.TYPE_CHECKING:
    PHType = typing.Callable[[bytes, typing.Any, ESocketRole], typing.NoReturn]
    OHType = typing.Callable[[list[str], typing.NoReturn]]

# This is where users may do live edits and alter the behavior of the proxy.

class Proxy(Thread):
    def __init__(self, bindAddr: str, remoteAddr: str, localPort: int, remotePort: int, name: str, packetHandler: PHType, outputHandler: OHType):
        super().__init__()
        
        self.BIND_SOCKET_TIMEOUT = 3.0 # in seconds

        self.name = name
        self._packetHandler = packetHandler
        self._outputHandler = outputHandler

        self._connected = False
        self._isShutdown = False

        self._bindAddr = bindAddr
        self.remoteAddr = remoteAddr
        self._localPort = localPort
        self.remotePort = remotePort
        
        # Sockets
        self._bindSocket = None
        self._server = None
        self._client = None

        self._bind(self._bindAddr, self._localPort)
        
        return

    def __str__(self) -> str:
        ret = f'{self.name} ['
        if self._isShutdown:
            ret += 'DEAD]'
            return ret

        if not self._connected:
            if self._client is not None:
                ch, cp = self.getClient()
                ret += f'C] {ch}:{cp} <---> :{self._localPort} >--->'
            else:
                ret += f'L] {self._bindAddr} >---> :{self._localPort} X---X'
        else:
            ch, cp = self.getClient()
            ret += f'E] {ch}:{cp} <---> :{self._localPort} <--->'
        rh, rp = (self.remoteAddr, self.remotePort)
        ret += f' {rh}:{rp}'
        return ret

    def run(self) -> typing.NoReturn:
        # after client disconnected await a new client connection
        while not self._isShutdown:
            output = []
            try:
                # Wait for a client.
                newClientHasConnected = self._waitForClient()
                if not newClientHasConnected:
                    continue
                
                # Client has connected.
                ch, cp = self.getClient()
                output.append(f'[{self}]: Client connected: {ch}:{cp}')
                
                # Connect to the remote host after a client has connected.
                output.append(f'[{self}]: Connecting to {self.remoteAddr}:{self.remotePort}')
                if not self._connect():
                    output.append(f'[{self}]: Could not connect to remote host.')
                    self._client.start()
                    self._client.stop()
                    self._client.join()
                    self._client = None
                    continue
                
                output.append(f'[{self}]: Connection established.')

                # Start client and server socket handler threads.
                self._client.start()
                self._server.start()
                
                self._connected = True
            finally:
                self._outputHandler(output)
        # Shutdown
        if not self._bindSocket is None:
            self._bindSocket.close()

        if not self._client is None:
            self._client.stop()
            self._client.join()
            self._client = None

        if not self._server is None:
            self._server.stop()
            self._server.join()
            self._server = None
        return

    def shutdown(self) -> typing.NoReturn:
        self._isShutdown = True
        return

    def sendData(self, destination: ESocketRole, data: bytes) -> typing.NoReturn:
        sh = self._client if destination == ESocketRole.client else self._server
        if sh is None:
            return
        sh.send(data)
        return
    
    def sendToServer(self, data: bytes) -> typing.NoReturn:
        self.sendData(ESocketRole.server, data)
        return
    
    def sendToClient(self, data: bytes) -> typing.NoReturn:
        self.sendData(ESocketRole.client, data)
        return

    def getClient(self) -> typing.Tuple[str, int]:
        if self._client is None:
            return (None, None)
        return (self._client.getHost(), self._client.getPort())

    def getServer(self) -> typing.Tuple[str, int]:
        if self._server is None:
            return (None, None)
        return (self._server.getHost(), self._server.getPort())

    def getBind(self) -> typing.Tuple[str, int]:
        return (self._bindAddr, self._localPort)

    def _bind(self, host: str, port: int) -> typing.NoReturn:
        self._outputHandler(f'[{self}]: Starting listening socket on {host}:{port}')
        self._bindSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._bindSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._bindSocket.bind((host, port))
        self._bindSocket.listen(1)
        self._bindSocket.settimeout(self.BIND_SOCKET_TIMEOUT)

    def _waitForClient(self) -> bool:
        try:
            sock, _ = self._bindSocket.accept()
        except TimeoutError:
            return False
        
        # Disconnect the old client if there was one.
        if self._client is not None:
            self._client.stop()
            self._client.join()
            self._client = None
        
        if self._server is not None:
            self._server.stop()
            self._server.join()
            self._server = None

        # Set new client
        try:
            self._client = SocketHandler(sock, ESocketRole.client, self)
        except (OSError, TimeoutError) as e:
            self._outputHandler(f'[{self}]: New client tried to connect but exception occurred: {e}')
            return False
        return True
    
    def _connect(self) -> bool:
        if self._server is not None:
            raise RuntimeError(f'[{self}]: Already connected to {self._server}.')

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.remoteAddr, self.remotePort))
            self._server = SocketHandler(sock, ESocketRole.server, self)
            return True
        # pylint: disable=broad-except
        except Exception as e:
            self._outputHandler(f'[{self}]: Unable to connect to server {self.remoteAddr}:{self.remotePort}: {e}')
        return False
    
    def getIsConnected(self) -> bool:
        return self._connected

    def disconnect(self) -> typing.NoReturn:
        if self._client is not None:
            self._client.stop()
            self._client = None
        
        if self._server is not None:
            self._server.stop()
            self._server = None

        self._connected = False
        return

    def getOutputHandler(self) -> OHType:
        return self._outputHandler

    def getPacketHandler(self) -> PHType:
        return self._packetHandler

###############################################################################

# This class owns a socket, receives all it's data and accepts data into a queue to be sent to that socket.
class SocketHandler(Thread):
    def __init__(self, sock: socket.socket, role: ESocketRole, proxy: Proxy, readBufferSize: int = 0xFFFF):
        super().__init__()
        
        self._sock = sock                # The socket
        self._ROLE = role                # Either client or server
        self._proxy = proxy              # To disconnect on error
        self._READ_BUFFER_SIZE = readBufferSize

        # Get this once, so there is no need to check for validity of the socket later.
        self._host, self._port = sock.getpeername()
        
        # Simple, thread-safe data structure for our messages to the socket to be queued into.
        self._dataQueue = SimpleQueue()
        
        self._running = False

        # Set socket non-blocking. recv() will return if there is no data available.
        self._sock.setblocking(True)

        self._lock = Lock()

    def send(self, data: bytes) -> typing.NoReturn:
        self._dataQueue.put(data)
        return

    def getHost(self) -> str:
        return self._host

    def getPort(self) -> int:
        return self._port

    def stop(self) -> typing.NoReturn:
        # Cleanup of the socket is in the thread itself, in the run() function, to avoid the need for locks.
        with self._lock:
            self._running = False
        return

    def _getSocketStatus(self) -> typing.Tuple[bool, bool, bool]:
        try:
            readyToRead, readyToWrite, inError = select.select([self._sock,], [self._sock,], [], 3)
        except select.error:
            self.stop()
        return (len(readyToRead) > 0, len(readyToWrite) > 0, inError)

    def _sendQueue(self) -> bool:
        abort = False
        try:
            # Send any data which may be in the queue
            while not self._dataQueue.empty():
                message = self._dataQueue.get()
                self._sock.sendall(message)
        # pylint: disable=broad-except
        except Exception as e:
            self._proxy.getOutputHandler()(f'[EXCEPT] - xmit data to {self}: {e}')
            abort = True
        return abort

    def __str__(self) -> str:
        return f'{self._ROLE.name} [{self._host}:{self._port}]'

    def run(self) -> typing.NoReturn:
        if self._sock is None:
            raise RuntimeError('Socket has expired. Can not start again after shutdown.')
        with self._lock:
            self._running = True
        localRunning = True
        while localRunning:
            # Receive data from the host.
            data = False
            abort = False

            readyToRead, readyToWrite, _ = self._getSocketStatus()

            if readyToRead:
                # pylint: disable=broad-except
                try:
                    data = self._sock.recv(self._READ_BUFFER_SIZE)
                    if len(data) == 0:
                        raise IOError('Socket Disconnected')
                except BlockingIOError:
                    # No data was available at the time.
                    pass
                except Exception as e:
                    self._proxy.getOutputHandler()(f'[EXCEPT] - recv data from {self}: {e}')
                    abort = True
            
            # If we got data, parse it.
            if data:
                try:
                    self._proxy.getPacketHandler()(data, self._proxy, self._ROLE)
                # pylint: disable=broad-except
                except Exception as e:
                    output = [f'[EXCEPT] - parse data from {self}: {e}', traceback.format_exc()]
                    self._proxy.getOutputHandler()(output)
                    self._proxy.disconnect()
            
            # Send the queue
            queueEmpty = self._dataQueue.empty()
            readyToRead, readyToWrite, _ = self._getSocketStatus()
            abort2 = False
            if not queueEmpty and readyToWrite:
                abort2 = self._sendQueue()
            
            if abort or abort2:
                self._proxy.disconnect()

            # Prevent the CPU from Melting
            # Sleep if we didn't get any data or if we didn't send
            if not data and (queueEmpty or not readyToWrite):
                sleep(0.001)
            
            with self._lock:
                localRunning = self._running
        
        # Stopped, clean up socket.
        # Send all remaining messages.
        sleep(0.1)
        self._sendQueue()
        sleep(0.1)

        self._sock.close()
        self._sock = None
        return

