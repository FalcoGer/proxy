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

from enum_socket_role import ESocketRole

try:
    import setproctitle
    _SETPROCTITLE_AVAILABLE = True
    _PROCTITLE_MAX_CHARS = 15  # Maximum length of a process title is 15 Bytes.
except ImportError:
    _SETPROCTITLE_AVAILABLE = False

if typing.TYPE_CHECKING:
    PHType = typing.Callable[[bytes, 'Proxy', ESocketRole], typing.NoReturn]
    OHType = typing.Callable[[list[str], typing.NoReturn]]


class Proxy(Thread):
    def __init__(self, bindAddr: str, remoteAddr: str, localPort: int, remotePort: int,
                 name: str, packetHandler: PHType, outputHandler: OHType):
        super().__init__(name=name)

        self.BIND_SOCKET_TIMEOUT = 3.0  # in seconds

        self._packetHandler = packetHandler
        self._outputHandler = outputHandler

        self._connected = False
        self._isShutdown = False

        self._bindAddr = bindAddr
        self._remoteAddr = remoteAddr
        self._localPort = localPort
        self._remotePort = remotePort

        # Sockets
        self._bindSocket = None
        self._server = None
        self._client = None

        self._bind(self._bindAddr, self._localPort)

        # Lock for other thread calling this thread's functions
        self._lock = Lock()

        return

    def __str__(self) -> str:
        ret = f'{self.name} ['
        if self._isShutdown:
            ret += 'DEAD]'
            return ret

        if not self._connected:
            if self._client is not None:
                ch, cp = self.getClient()
                ret += f'C] {ch}:{cp} <---> :{self._localPort} >---X'
            else:
                ret += f'L] {self._bindAddr} X---> :{self._localPort} X---X'
        else:
            ch, cp = self.getClient()
            ret += f'E] {ch}:{cp} <---> :{self._localPort} <--->'
        rh, rp = (self._remoteAddr, self._remotePort)
        ret += f' {rh}:{rp}'
        return ret

    def run(self) -> typing.NoReturn:
        # after client disconnected await a new client connection until shutdown.
        while not self._isShutdown:
            output = []
            # update thread title
            if _SETPROCTITLE_AVAILABLE and setproctitle.getthreadtitle() != self.name[:_PROCTITLE_MAX_CHARS]:
                setproctitle.setthreadtitle(self.name[:_PROCTITLE_MAX_CHARS])
            try:
                # Wait for a client.
                newClientHasConnected = self._waitForClient()
                if not newClientHasConnected:
                    continue
                with self._lock:
                    # Client has connected.
                    ch, cp = self.getClient()
                    output.append(f'[{self}]: Client connected: {ch}:{cp}')

                    # Connect to the remote host after a client has connected.
                    output.append(f'[{self}]: Connecting to {self._remoteAddr}:{self._remotePort}')
                    if not self._connect():
                        output.append(f'[{self}]: Could not connect to remote host.')
                        self._client.start()
                        self._client.stop()
                        self._client.join()
                        self._client = None
                        continue

                    # Start client and server socket handler threads.
                    self._client.start()
                    self._server.start()

                    self._connected = True

                    output.append(f'[{self}]: Connection established.')
            finally:
                self._outputHandler(output)
        # Shutdown
        if self._bindSocket is not None:
            self._bindSocket.close()

        if self._client is not None:
            self._client.stop()
            self._client.join()
            self._client = None

        if self._server is not None:
            self._server.stop()
            self._server.join()
            self._server = None
        return

    def shutdown(self) -> typing.NoReturn:
        self._isShutdown = True
        return

    def sendData(self, destination: ESocketRole, data: bytes) -> typing.NoReturn:
        sh = self._client if destination == ESocketRole.CLIENT else self._server
        if sh is None:
            return
        sh.send(data)
        return

    def sendToServer(self, data: bytes) -> typing.NoReturn:
        self.sendData(ESocketRole.SERVER, data)
        return

    def sendToClient(self, data: bytes) -> typing.NoReturn:
        self.sendData(ESocketRole.CLIENT, data)
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
            self._client = SocketHandler(sock, ESocketRole.CLIENT, self, self._outputHandler, self._packetHandler)
        except (OSError, TimeoutError) as e:
            self._outputHandler(f'[{self}]: New client tried to connect but exception occurred: {e}')
            return False
        return True

    def _connect(self) -> bool:
        if self._server is not None:
            raise RuntimeError(f'[{self}]: Already connected to {self._server}.')

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self._remoteAddr, self._remotePort))

            self._server = SocketHandler(sock, ESocketRole.SERVER, self, self._outputHandler, self._packetHandler)
            return True
        # pylint: disable=broad-except
        except Exception as e:
            self._outputHandler(f'[{self}]: Unable to connect to server {self._remoteAddr}:{self._remotePort}: {e}')
        return False

    def getIsConnected(self) -> bool:
        return self._connected

    def disconnect(self) -> typing.NoReturn:
        with self._lock:
            if self._client is not None:
                self._client.stop()
                self._client = None

            if self._server is not None:
                self._server.stop()
                self._server = None

            self._connected = False
        return

###############################################################################


# This class owns a socket, receives all it's data and accepts data into a queue to be sent to that socket.
class SocketHandler(Thread):
    def __init__(self, sock: socket.socket, role: ESocketRole, proxy: Proxy,
                 outputHandler: OHType, packetHandler: PHType, readBufferSize: int = 0xFFFF):

        self._sock = sock                # The socket
        self._ROLE = role                # Either client or server
        self._proxy = proxy              # To disconnect on error
        self._READ_BUFFER_SIZE = readBufferSize
        self._outputHandler = outputHandler
        self._packetHandler = packetHandler

        # Get this once, so there is no need to check for validity of the socket later.
        self._host, self._port = sock.getpeername()

        # Set thread name and initialize thread base class.
        super().__init__(name=self._getName())

        # Simple, thread-safe data structure for our messages to the socket to be queued into.
        self._dataQueue = SimpleQueue()

        self._running = False

        # Set socket non-blocking. recv() will return if there is no data available.
        self._sock.setblocking(True)

        self._lock = Lock()

    def _getName(self) -> str:
        return ('C' if self._ROLE == ESocketRole.CLIENT else 'S') + f'_{self._proxy.name}'

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

    def _sendQueue(self, output: list[str]) -> bool:
        abort = False
        try:
            # Send any data which may be in the queue
            while not self._dataQueue.empty():
                message = self._dataQueue.get()
                self._sock.sendall(message)
        # pylint: disable=broad-except
        except Exception as e:
            output.append(f'[EXCEPT] - xmit data to {self}: {e}')
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

        # run until stop() is called.
        while localRunning:
            output = []
            data = False
            abort = False

            # Update thread title
            if _SETPROCTITLE_AVAILABLE and setproctitle.getthreadtitle() != self._getName()[:_PROCTITLE_MAX_CHARS]:
                setproctitle.setthreadtitle(self._getName()[:_PROCTITLE_MAX_CHARS])

            try:  # Try-Finally block for output.
                readyToRead, readyToWrite, _ = self._getSocketStatus()

                # Receive data from the host.
                if readyToRead:
                    data, abort = self._recvData(output)

                # Send the queue
                queueEmpty = self._dataQueue.empty()
                abort2 = False
                if not queueEmpty and readyToWrite:
                    abort2 = self._sendQueue(output)

                if abort or abort2:
                    self._proxy.disconnect()

                # Prevent the CPU from Melting
                # Sleep if we didn't get any data and if we don't have anything to send or can't send
                if not data and (queueEmpty or not readyToWrite):
                    sleep(0.001)

                with self._lock:
                    localRunning = self._running
            finally:
                self._outputHandler(output)
        output = []
        try:
            # Stopped, clean up socket.
            # Send all remaining messages.
            sleep(0.1)
            self._sendQueue(output)
            sleep(0.1)

            self._sock.close()
            self._sock = None
        finally:
            self._outputHandler(output)
        return

    def _recvData(self, output: list[str]) -> bool:
        data = False
        abort = False

        # pylint: disable=broad-except
        try:
            data = self._sock.recv(self._READ_BUFFER_SIZE)
            if len(data) == 0:
                raise IOError('Socket Disconnected')
        except BlockingIOError:
            # No data was available at the time.
            pass
        except Exception as e:
            output.append(f'[EXCEPT] - recv data from {self}: {e}')
            abort = True

        # If we got data, parse it.
        if data:
            try:
                self._packetHandler(data, self._proxy, self._ROLE)
            # pylint: disable=broad-except
            except Exception as e:
                output.extend([f'[EXCEPT] - parse data from {self}: {e}', traceback.format_exc()])
                self._proxy.disconnect()
        return data, abort
