#/bin/python3

# struct is used to decode bytes into primitive data types
import struct
from socket import socket
from proxy import Proxy

def parse(data: bytes, src: socket, dest: socket, origin: str, proxy: Proxy) -> None:
    sh, sp = src.getpeername()
    dh, dp = dest.getpeername()
    srcStr = f"{sh}:{sp}"
    destStr = f"{dh}:{dp}"
    maxLen = len(srcStr) if len(srcStr) > len(destStr) else len(destStr)

    srcStr = srcStr.rjust(maxLen)
    destStr = destStr.ljust(maxLen)

    print(f"{srcStr}->{destStr} : {data}")

    # Do interesting stuff with the data here!
    if data == b'ABCD\n' and origin == 'c':
        data = b'DCBA\n'

    # A construct like this may be used to drop packets. 
    #if data.find(b'\xFF\xFF\xFF\xFF') >= 0:
    #    print("Dropped")
    #    return

    # By default, append the data as is to the queue to send it to the client/server.
    proxy.sendData('s' if origin == 'c' else 'c', data)

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
        for _ in range(0, 10):
            proxy.sendToClient(b'EXAMPLE\n')
    
    # Empty command to avoid errors on empty commands.
    elif len(cmd.strip()) == 0:
        pass
    else:
        print(f"Undefined command: \"{cmd}\"")
    
    # Keep going.
    return True

