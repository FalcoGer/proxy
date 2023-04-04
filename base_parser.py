# This file contains base functionality that requires a proxy to be running.
# This file is the base class for custom parsers

# struct is used to decode bytes into primitive data types
# https://docs.python.org/3/library/struct.html
import struct
import os
from enum import Enum, auto
from copy import copy

# This is the base class for the base parser
from core_parser import CoreParser

from eSocketRole import ESocketRole
from hexdump import Hexdump
from completer import Completer

###############################################################################
# Setting storage stuff goes here.

class EBaseSettingKey(Enum):
    HEXDUMP_ENABLED             = auto()
    HEXDUMP                     = auto()
    PACKETNOTIFICATION_ENABLED  = auto()

    def __eq__(self, other) -> bool:
        if other is int:
            return self.value == other
        if other is str:
            return self.name == other
        if repr(type(self)) == repr(type(other)):
            return self.value == other.value
        return False

    def __gt__(self, other) -> bool:
        if other is int:
            return self.value > other
        if other is str:
            return self.name > other
        if repr(type(self)) == repr(type(other)):
            return self.value > other.value
        raise ValueError("Can not compare.")

    def __hash__(self):
        return self.value.__hash__()

class BaseParser(CoreParser):
    def __init__(self, application, settings: dict[(Enum, object)]):
        super().__init__(application, settings)
        return

    def getSettingKeys(self) -> list[Enum]:
        settingKeys = super().getSettingKeys()
        settingKeys.extend(list(EBaseSettingKey))
        return settingKeys

    def getDefaultSettings(self) -> dict[(Enum, object)]:
        defaultSettings = super().getDefaultSettings()
        baseDefaultSettings = {
                EBaseSettingKey.HEXDUMP_ENABLED: True,
                EBaseSettingKey.HEXDUMP: Hexdump(),
                EBaseSettingKey.PACKETNOTIFICATION_ENABLED: True,
            }
        return defaultSettings | baseDefaultSettings

    ###############################################################################
    # Packet parsing stuff goes here.

    # Define what should happen when a packet arrives here
    def parse(self, data: bytes, proxy, origin: ESocketRole) -> None:
        if self.getSetting(EBaseSettingKey.PACKETNOTIFICATION_ENABLED):
            # Print out the data in a nice format.
            directionStr = "C -> S" if origin == ESocketRole.client else "C <- S"
            maxProxyNameLen = max(len(proxy.name) for proxy in self.application.proxies.values())
            print(f"{proxy.name.ljust(maxProxyNameLen)} [{directionStr}] - ({len(data)} Byte{'s' if len(data) > 1 else ''})")

        if self.getSetting(EBaseSettingKey.HEXDUMP_ENABLED):
            hexdumpObj = self.getSetting(EBaseSettingKey.HEXDUMP)
            hexdumpLines = "\n".join(hexdumpObj.hexdump(data))
            print(f"{hexdumpLines}")
        return

    ###############################################################################
    # CLI stuff goes here.

    # Define your custom commands here. Each command requires those arguments:
    # 1. args: list[str]
    #   A list of command arguments. args[0] is always the command string itself.
    # 2. proxy: Proxy
    #   This allows to make calls to the proxy API, for example to inject packets.
    # The functions should return 0 if they succeeded. Otherwise their return gets printed by the CLI handler.

    # Define which commands are available here and which function is called when it is entered by the user.
    # Return a dictionary with the command as the key and a tuple of (function, str, completerArray) as the value.
    # The function is called when the command is executed, the string is the help text for that command.
    # The last completer in the completer array will be used for all words if the word index is higher than the index in the completer array.
    # If you don't want to provide more completions, use None at the end.
    def buildCommandDict(self) -> dict:
        ret = super().buildCommandDict()

        ret['disconnect']   = (self._cmd_disconnect, 'Disconnect from the client and server and wait for a new connection.\n Usage: {0}', None)
        ret['hexdump']      = (self._cmd_hexdump, 'Configure the hexdump or show current configuration.\nUsage: {0} [yes|no] [bytesPerLine] [bytesPerGroup]', [self._yesNoCompleter, self._historyCompleter, self._historyCompleter, None])
        ret['sh']           = (self._cmd_sh, 'Send arbitrary hex values to the server.\nUsage: {0} hexstring \nExample: {0} 41424344\nNote: Spaces are allowed and ignored.', [self._historyCompleter])
        ret['ss']           = (self._cmd_ss, 'Send arbitrary strings to the server.\nUsage: {0} string\nExample: {0} hello\\!\\n\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.\nEscape sequences are available.', [self._historyCompleter])
        ret['sf']           = (self._cmd_sf, 'Send arbitrary files to the server.\nUsage: {0} filename\nExample: {0} /home/user/.bashrc', [self._fileCompleter, None])
        ret['ch']           = (self._cmd_ch, 'Send arbitrary hex values to the client.\nUsage: {0} hexstring \nExample: {0} 41424344', [self._historyCompleter])
        ret['cs']           = (self._cmd_cs, 'Send arbitrary strings to the client.\nUsage: {0} string\nExample: {0} hello!\\n\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.\nEscape sequences are available.', [self._historyCompleter])
        ret['cf']           = (self._cmd_cf, 'Send arbitrary files to the client.\nUsage: {0} filename\nExample: {0} /home/user/.bashrc', [self._fileCompleter, None])

        # Aliases
        return ret
    
    def _cmd_disconnect(self, args: list[str], proxy) -> object:
        if len(args) > 1:
            print(self.getHelpText(args[0]))
            return "Syntax error."
            
        if not proxy.connected:
            return "Not connected."

        proxy.disconnect()
        return 0

    def _cmd_sh(self, args: list[str], proxy) -> object:
        return self._aux_cmd_send_hex(args, ESocketRole.server, proxy)

    def _cmd_ch(self, args: list[str], proxy) -> object:
        return self._aux_cmd_send_hex(args, ESocketRole.client, proxy)

    def _aux_cmd_send_hex(self, args: list[str], target: ESocketRole, proxy) -> object:
        if len(args) == 1:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        # Allow spaces in hex string, so join with empty string to remove them.
        userInput = ''.join(args[1:])
            
        pkt = bytes.fromhex(userInput)
        if proxy.connected:
            proxy.sendData(target, pkt)
            return 0
        return "Not connected."

    def _cmd_ss(self, args: list[str], proxy) -> object:
        return self._aux_cmd_send_string(args, ESocketRole.server, proxy)

    def _cmd_cs(self, args: list[str], proxy) -> object:
        return self._aux_cmd_send_string(args, ESocketRole.client, proxy)

    def _aux_cmd_send_string(self, args: list[str], target: ESocketRole, proxy) -> object:
        if len(args) == 1:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        userInput = ' '.join(args[1:])

        pkt = str.encode(userInput, 'utf-8')
        pkt = self.escape(pkt)
        if proxy.connected:
            proxy.sendData(target, pkt)
            return 0
        return "Not connected."

    def _cmd_sf(self, args: list[str], proxy) -> object:
        return self._aux_cmd_send_file(args, ESocketRole.server, proxy)

    def _cmd_cf(self, args: list[str], proxy) -> object:
        return self._aux_cmd_send_file(args, ESocketRole.client, proxy)

    def _aux_cmd_send_file(self, args: list[str], target: ESocketRole, proxy) -> object:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        
        filePath = ' '.join(args[1:])
        if not os.path.isfile(filePath):
            return f"File \"{filePath}\" does not exist."
        
        byteArray = b''
        try:
            with open(filePath, "rb") as file:
                while byte := file.read(1):
                    byteArray += byte
        # pylint: disable=broad-except
        except Exception as e:
            return f"Error reading file \"{filePath}\": {e}"

        if proxy.connected:
            proxy.sendData(target, byteArray)
            return 0
        return "Not connected."

    def _cmd_hexdump(self, args: list[str], proxy) -> object:
        if len(args) > 4:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        enabled = self.getSetting(EBaseSettingKey.HEXDUMP_ENABLED)
        hexdumpObj: Hexdump = self.getSetting(EBaseSettingKey.HEXDUMP)
        bytesPerGroup = hexdumpObj.bytesPerGroup
        bytesPerLine = hexdumpObj.bytesPerLine

        if len(args) > 3:
            try:
                bytesPerGroup = self.strToInt(args[3])
            except ValueError as e:
                print(self.getHelpText(args[0]))
                return f"Syntax error: {e}"
        
        if len(args) > 2:
            try:
                bytesPerLine = self.strToInt(args[2])
                if bytesPerLine < 1:
                    raise ValueError("Can't have less than 1 byte per line.")
            except ValueError as e:
                print(self.getHelpText(args[0]))
                return f"Syntax error: {e}"
        
        if len(args) > 1:
            if args[1].lower() == 'yes':
                enabled = True
            elif args[1].lower() == 'no':
                enabled = False
            else:
                print(self.getHelpText(args[0]))
                return "Syntax error: Must be 'yes' or 'no'."
        
        # Write back settings
        self.setSetting(EBaseSettingKey.HEXDUMP_ENABLED, enabled)
        hexdumpObj.setBytesPerLine(bytesPerLine)
        hexdumpObj.setBytesPerGroup(bytesPerGroup)

        # Show status
        if enabled:
            print(f"Printing hexdumps: {hexdumpObj}")
        else:
            print("Not printing hexdumps.")

        return 0

    ###############################################################################
    # Completers go here.

    def _yesNoCompleter(self) -> None:
        options = ["yes", "no"]
        for option in options:
            if option.startswith(self.completer.being_completed):
                self.completer.candidates.append(option)
        return

    ###############################################################################
    # No need to edit the functions below

    # This function take the command line string and calls the relevant python function with the correct arguments.
    def handleUserInput(self, userInput: str, proxy) -> object:
        args = userInput.split(' ')

        if len(userInput.strip()) == 0:
            # Ignore empty commands
            return 0
        
        if args[0] not in self.commandDictionary:
            return f"Undefined command: \"{args[0]}\""

        function, _, _ = self.commandDictionary[args[0]]
        return function(args, proxy)

    def getHelpText(self, cmdString: str) -> str:
        _, helpText, _ = self.commandDictionary[cmdString]
        try:
            return helpText.format(cmdString)
        except ValueError as e:
            print(f"Unable to format helptext \"{helpText}\": {e}")
            return helpText

    # replaces escape sequences with the proper values
    def escape(self, data: bytes) -> bytes:
        idx = 0
        newData = b''
        while idx < len(data):
            b = self.intToByte(data[idx])
            if b == b'\\':
                idx += 1 # Add one to the index so we don't read the escape sequence byte as a normal byte.
                nextByte = self.intToByte(data[idx]) # May throw IndexError, pass it up to the user.
                if nextByte == b'\\':
                    newData += b'\\'
                elif nextByte == b'n':
                    newData += b'\n'
                elif nextByte == b'r':
                    newData += b'\r'
                elif nextByte == b't':
                    newData += b'\t'
                elif nextByte == b'b':
                    newData += b'\b'
                elif nextByte == b'f':
                    newData += b'\f'
                elif nextByte == b'v':
                    newData += b'\v'
                elif nextByte == b'0':
                    newData += b'\0'
                elif nextByte == b'x':
                    newData += bytes.fromhex(data[idx+1:idx+3].decode())
                    idx += 2 # skip 2 more bytes.
                elif ord(nextByte) in range(ord(b'0'), ord(b'7') + 1):
                    octalBytes = data[idx:idx+3]
                    num = int(octalBytes, 7)
                    newData += self.intToByte(num)
                    idx += 2 # skip 2 more bytes
                    
                elif nextByte == b'u':
                    raise Exception("\\uxxxx is not supported")
                elif nextByte == b'U':
                    raise Exception("\\Uxxxxxxxx is not supported")
                elif nextByte == b'N':
                    raise Exception("\\N{Name} is not supported")
                else:
                    raise ValueError(f"Invalid escape sequence at index {idx} in {data}: \\{repr(nextByte)[2:-1]}")
            else:
                # No escape sequence. Just add the byte as is
                newData += b
            idx += 1
        return newData

    def intToByte(self, i: int) -> bytes:
        return struct.pack('=b', i if i < 128 else i - 256)

    def strToInt(self, dataStr: str) -> int:
        if dataStr.startswith('0x'):
            return int(dataStr[2:], 16)
        if dataStr.startswith('x'):
            return int(dataStr[1:], 16)
        if dataStr.startswith('0o'):
            return int(dataStr[2:], 8)
        if (dataStr.startswith('0') and len(dataStr) > 1) or dataStr.startswith('o'):
            return int(dataStr[1:], 8)
        if dataStr.startswith('0b'):
            return int(dataStr[2:], 2)
        if dataStr.startswith('b'):
            return int(dataStr[1:], 2)

        return int(dataStr, 10)

