# struct is used to decode bytes into primitive data types
import struct
# queue is used as a thread safe data structure for packets to be sent to the client or server
import queue

from proxy import Proxy


def parse(data: bytes, port: int, origin: str, proxy: Proxy) -> None:
    sign = '->' if origin == 'client' else '<-'
    print(f"c{sign}s: {data}")

    # Do interesting stuff with the data here!

    # A construct like this may be used to drop packets. 
    #if data.find(b'\xFF\xFF\xFF\xFF') >= 0:
    #    print("Dropped")
    #    return

    # By default, append the data as is to the queue to send it to the client/server.
    if (origin == 'client'):
        proxy.sendToServer(data)
    elif (origin == 'server'):
        proxy.sendToClient(data)

def handleUserInput(cmd: str, proxy: Proxy) -> bool:
    if cmd.upper() == 'QUIT' or cmd.upper() == 'EXIT':
        return False
    
    # Send arbitrary bytes to the server.
    if cmd[0:2].upper() == 'S ':
        pkt = bytes.fromhex(cmd[2:])
        if proxy.running:
            proxy.sendToServer(pkt)
    
    # Send arbitrary bytes to the client.
    elif cmd[0:2].upper() == 'C ':
        pkt = bytes.fromhex(cmd[2:])
        if proxy.running:
            proxy.sendToClient(pkt)

    # More commands go here.
    elif cmd.upper() == 'EXAMPLE':
        print('Example text goes here.')
        for _ in range(0, 10):
            proxy.sendToClient(b'EXAMPLE\n')
    
    # Empty command to avoid errors on empty commands.
    elif len(cmd.strip()) == 0:
        pass
    else:
        print(f"Undefined command: \"{cmd}\"")
    
    # Keep going.
    return True

