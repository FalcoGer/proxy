#/bin/python3

# struct is used to decode bytes into primitive data types
import struct
from proxy import Proxy
from hexdump import hexdump

def buildCommandDict() -> dict:
    ret = {}
    ret['quit']         = (cmd_quit, 'Stop the proxy and quit.')
    ret['exit']         = ret['quit']
    ret['disconnect']   = (cmd_disconnect, 'Disconnect from the client and server and wait for a new connection.')
    ret['help']         = (cmd_help, 'Print available commands.')
    ret['sh']           = (cmd_sh, 'Send arbitrary hex values to the server.\nUsage: "sh" hexstring \nExample: sh 41424344')
    ret['ss']           = (cmd_ss, 'Send arbitrary strings to the server.\nUsage: "ss" string\nExample: ss hello!\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.')
    ret['sf']           = (cmd_sf, 'Send arbitrary files to the server.\nUsage: "sf" filename\nExample: sf /home/user/.bashrc')
    ret['ch']           = (cmd_ch, 'Send arbitrary hex values to the client.\nUsage: "ch" hexstring \nExample: ch 41424344')
    ret['cs']           = (cmd_cs, 'Send arbitrary strings to the client.\nUsage: "cs" string\nExample: cs hello!\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.')
    ret['cf']           = (cmd_cf, 'Send arbitrary files to the client.\nUsage: "cf" filename\nExample: cf /home/user/.bashrc')
    return ret
    
def parse(data: bytes, src: (str, int), dest: (str, int), origin: str, proxy: Proxy) -> None:
    # Print out the data in a nice format.
    sh, sp = src
    dh, dp = dest
    srcStr = f"{sh}:{sp}"
    destStr = f"{dh}:{dp}"
    maxLen = len(srcStr) if len(srcStr) > len(destStr) else len(destStr)

    srcStr = srcStr.rjust(maxLen)
    destStr = destStr.ljust(maxLen)
    hd = "\n".join(hexdump(data, 24, 8))

    print(f"{srcStr}->{destStr} ({len(data)} Bytes)\n{hd}")

    # Do interesting stuff with the data here!
    #if data == b'ABCD\n' and origin == 'c':
    #    data = b'DCBA\n'

    # A construct like this may be used to drop packets. 
    #if data.find(b'\xFF\xFF\xFF\xFF') >= 0:
    #    print("Dropped")
    #    return

    # By default, append the data as is to the queue to send it to the client/server.
    proxy.sendData('s' if origin == 'c' else 'c', data)
    return

def cmd_help(userInput: str, proxy: Proxy) -> bool:
    commandDict = buildCommandDict()
    # find the longest key for neat formatting.
    maxLen = 0
    for key in commandDict.keys():
        if len(key) > maxLen:
            maxLen = len(key)

    for key in commandDict.keys():
        function, helptext = commandDict[key]
        helptext = helptext.replace("\n", "\n" + (" " * (maxLen + 8))).strip()
        print(f"{key.rjust(maxLen)} - {helptext}")
    return True

def cmd_quit(userInput: str, proxy: Proxy) -> bool:
    return False

def cmd_sh(userInput: str, proxy: Proxy) -> bool:
    pkt = bytes.fromhex(userInput)
    if proxy.running:
        proxy.sendToServer(pkt)
    return True

def cmd_ss(userInput: str, proxy: Proxy) -> bool:
    pkt = str.encode(userInput, 'utf-8')
    if proxy.running:
        proxy.sendToServer(pkt)
    return True

def cmd_sf(userInput: str, proxy: Proxy) -> bool:
    print("TBD")
    return True

def cmd_ch(userInput: str, proxy: Proxy) -> bool:
    pkt = bytes.fromhex(userInput)
    if proxy.running:
        proxy.sendToClient(pkt)
    return True

def cmd_cs(userInput: str, proxy: Proxy) -> bool:
    pkt = str.encode(userInput, 'utf-8')
    if proxy.running:
        proxy.sendToClient(pkt)
    return True

def cmd_cf(userInput: str, proxy: Proxy) -> bool:
    print("TBD")
    return True

def cmd_disconnect(userInput: str, proxy: Proxy) -> bool:
    if proxy.running:
        proxy.disconnect()
    return True

def handleUserInput(userInput: str, proxy: Proxy) -> bool:
    userInput = userInput.lstrip()
    cmd = userInput.split(' ')[0].strip().lower()
    if userInput.find(' ') >= 0 and userInput.find(' ') != len(userInput):
        userInput = userInput[userInput.find(' ') + 1:]
    else:
        userInput = ''

    cmdList = buildCommandDict()
    if cmd == '':
        pass
        # Skip empty commands
    elif cmd in cmdList.keys():
        function, helptext = cmdList[cmd]
        return function(userInput, proxy)
    else:
        print(f"Undefined command: \"{cmd}\"")
    
    # Keep going.
    return True

