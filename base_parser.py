# This file contains base functionality that requires a proxy to be running.
# This file is the base class for custom parsers

# will be default in python 3.11.
# This is required for there to be no errors in the type hints.
from __future__ import annotations
import typing

# struct is used to decode bytes into primitive data types
# https://docs.python.org/3/library/struct.html
import struct
import os
from enum import Enum, auto
import time
try:
    import termcolor
    _COLOR_AVAILABLE = True
except ImportError:
    _COLOR_AVAILABLE = False

# This is the base class for the base parser
import core_parser

from eSocketRole import ESocketRole
from hexdump import Hexdump

# For type hints only
if typing.TYPE_CHECKING:
    from proxy import Proxy
    from application import Application
    from core_parser import CommandDictType
    from readline_buffer_status import ReadlineBufferStatus as RBS

###############################################################################
# Define which settings are available here.

class EBaseSettingKey(Enum):
    HEXDUMP_ENABLED             = auto()
    HEXDUMP                     = auto()
    PACKETNOTIFICATION_ENABLED  = auto()
    PACKET_NUMBER               = auto()

    def __eq__(self, other: typing.Any) -> bool:
        if other is int:
            return self.value == other
        if other is str:
            return self.name == other
        if repr(type(self)) == repr(type(other)):
            return self.value == other.value
        return False

    def __gt__(self, other: typing.Any) -> bool:
        if other is int:
            return self.value > other
        if other is str:
            return self.name > other
        if repr(type(self)) == repr(type(other)):
            return self.value > other.value
        raise ValueError('Can not compare.')

    def __hash__(self):
        return self.value.__hash__()

class Parser(core_parser.Parser):
    def __init__(self, application: Application, settings: dict[(Enum, typing.Any)]):
        super().__init__(application, settings)
        return

    def __str__(self) -> str:
        # The base parser doesn't forward packets, so using it would drop them all.
        return 'BASE/DROP'

    # Return a list of setting keys. Make sure to also include the base classes keys.
    def getSettingKeys(self) -> list[Enum]:
        settingKeys = super().getSettingKeys()
        settingKeys.extend(list(EBaseSettingKey))
        return settingKeys

    # Define the defaults for each setting here.
    def getDefaultSettings(self) -> dict[(Enum, typing.Any)]:
        defaultSettings = {
                EBaseSettingKey.HEXDUMP_ENABLED: True,
                EBaseSettingKey.HEXDUMP: Hexdump(),
                EBaseSettingKey.PACKETNOTIFICATION_ENABLED: True,
                EBaseSettingKey.PACKET_NUMBER: -1
            }
        # Return the base class defaults as well
        return super().getDefaultSettings() | defaultSettings

    ###############################################################################
    # Packet parsing stuff goes here.

    # Define what should happen when a packet arrives here
    def parse(self, data: bytes, proxy: Proxy, origin: ESocketRole) -> list[str]:
        output = []
        # Update packet number
        pktNr = self.getSetting(EBaseSettingKey.PACKET_NUMBER) + 1
        self.setSetting(EBaseSettingKey.PACKET_NUMBER, pktNr)
        
        # Output a packet notification if enabled.
        if self.getSetting(EBaseSettingKey.PACKETNOTIFICATION_ENABLED):
            # Print out the data in a nice format.
            ts = time.time() - self.application.START_TIME
            tsStr = f'{ts:>14.8f}'
            
            proxyStr = f'{proxy.name} ({self.application.getParserByProxy(proxy)})'
            
            pktNrStr = f'[PKT# {pktNr}]'

            directionStr = '[C -> S]' if origin == ESocketRole.client else '[C <- S]'

            dataLenStr = f'{len(data)} Byte{"s" if len(data) > 1 else ""}'
            
            if _COLOR_AVAILABLE:
                tsStr = termcolor.colored(tsStr, 'cyan')
                proxyStr = termcolor.colored(proxyStr, 'green', None, ['bold'])
                pktNrStr = termcolor.colored(pktNrStr, 'yellow', None)
                if origin == ESocketRole.client:
                    directionStr = termcolor.colored(directionStr, 'white', 'on_blue', ['bold'])
                else:
                    directionStr = termcolor.colored(directionStr, 'white', 'on_magenta')
                dataLenStr = termcolor.colored(dataLenStr, 'green', None, ['bold'])

            # TimeStamp Proxy PktNr Direction DataLength
            output.append(f'{tsStr} - {proxyStr} {pktNrStr} {directionStr} - {dataLenStr}')
        
        # Output a hexdump if enabled.
        if self.getSetting(EBaseSettingKey.HEXDUMP_ENABLED):
            hexdumpObj = self.getSetting(EBaseSettingKey.HEXDUMP)
            hexdumpLines = '\n'.join(hexdumpObj.hexdump(data))
            output.append(f'{hexdumpLines}')
        
        # Return the output.
        return output

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
    def _buildCommandDict(self) -> CommandDictType:
        ret = super()._buildCommandDict()

        sendHexNote = 'Usage: {0} <HexData> \nExample: {0} 41424344\nNote: Spaces in hex data are allowed and ignored.'
        sendStringNote = 'Usage: {0} <String>\nExample: {0} hello\\!\\n\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.\nEscape sequences are available.'
        sendFileNote = 'Usage: {0} filename\nExample: {0} /home/user/.bashrc'

        ret['hexdump']      = (self._cmd_hexdump, 'Configure the hexdump or show current configuration.\nUsage: {0} [yes|no] [<BytesPerLine>] [<BytesPerGroup>]', [self._yesNoCompleter, self._historyCompleter, self._historyCompleter, None])
        ret['notify']       = (self._cmd_notify, 'Configure packet notifications.\nUsage: {0} [yes|no]\nIf argument omitted, this will toggle the notifications.', [self._yesNoCompleter, None])
        ret['h2s']          = (self._cmd_h2s, f'Send arbitrary hex values to the server.\n{sendHexNote}', [self._historyCompleter])
        ret['s2s']          = (self._cmd_s2s, f'Send arbitrary strings to the server.\n{sendStringNote}', [self._historyCompleter])
        ret['f2s']          = (self._cmd_f2s, f'Send arbitrary files to the server.\n{sendFileNote}', [self._fileCompleter, None])
        ret['h2c']          = (self._cmd_h2c, f'Send arbitrary hex values to the client.\n{sendHexNote}', [self._historyCompleter])
        ret['s2c']          = (self._cmd_s2c, f'Send arbitrary strings to the client.\n{sendStringNote}', [self._historyCompleter])
        ret['f2c']          = (self._cmd_f2c, f'Send arbitrary files to the client.\n{sendFileNote}', [self._fileCompleter, None])

        return ret
    
    def _cmd_notify(self, args: list[str], _) -> typing.Union[int, str]:
        if not len(args) in [1, 2]:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        newState = not self.getSetting(EBaseSettingKey.PACKETNOTIFICATION_ENABLED)
        if len(args) == 2:
            if args[1] == 'yes':
                newState = True
            elif args[1] == 'no':
                newState = False
            else:
                print(self.getHelpText(args[0]))
                return 'Syntax error.'
        
        self.setSetting(EBaseSettingKey.PACKETNOTIFICATION_ENABLED, newState)
        print(f'Packet notifications are now {"enabled" if newState else "disabled"}.')

        return 0

    def _cmd_h2s(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        return self._aux_cmd_send_hex(args, ESocketRole.server, proxy)

    def _cmd_h2c(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        return self._aux_cmd_send_hex(args, ESocketRole.client, proxy)

    def _aux_cmd_send_hex(self, args: list[str], target: ESocketRole, proxy: Proxy) -> typing.Union[int, str]:
        if len(args) == 1:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        # Allow spaces in hex string, so join with empty string to remove them.
        userInput = ''.join(args[1:])
            
        pkt = bytes.fromhex(userInput)
        if proxy.getIsConnected():
            proxy.sendData(target, pkt)
            return 0
        return 'Not connected.'

    def _cmd_s2s(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        return self._aux_cmd_send_string(args, ESocketRole.server, proxy)

    def _cmd_s2c(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        return self._aux_cmd_send_string(args, ESocketRole.client, proxy)

    def _aux_cmd_send_string(self, args: list[str], target: ESocketRole, proxy: Proxy) -> typing.Union[int, str]:
        if len(args) == 1:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        userInput = ' '.join(args[1:])

        pkt = str.encode(userInput, 'utf-8')
        pkt = self._escape(pkt)
        if proxy.getIsConnected():
            proxy.sendData(target, pkt)
            return 0
        return 'Not connected.'

    def _cmd_f2s(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        return self._aux_cmd_send_file(args, ESocketRole.server, proxy)

    def _cmd_f2c(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        return self._aux_cmd_send_file(args, ESocketRole.client, proxy)

    def _aux_cmd_send_file(self, args: list[str], target: ESocketRole, proxy: Proxy) -> typing.Union[int, str]:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        filePath = ' '.join(args[1:])
        if not os.path.isfile(filePath):
            return f'File "{filePath}" does not exist.'
        
        byteArray = b''
        try:
            with open(filePath, 'rb') as file:
                while byte := file.read(1):
                    byteArray += byte
        # pylint: disable=broad-except
        except Exception as e:
            return f'Error reading file "{filePath}": {e}'

        if proxy.getIsConnected():
            proxy.sendData(target, byteArray)
            return 0
        return 'Not connected.'

    def _cmd_hexdump(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 4:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        enabled = self.getSetting(EBaseSettingKey.HEXDUMP_ENABLED)
        hexdumpObj: Hexdump = self.getSetting(EBaseSettingKey.HEXDUMP)
        bytesPerGroup = hexdumpObj.bytesPerGroup
        bytesPerLine = hexdumpObj.bytesPerLine

        if len(args) > 3:
            try:
                bytesPerGroup = self._strToInt(args[3])
            except ValueError as e:
                print(self.getHelpText(args[0]))
                return f'Syntax error: {e}'
        
        if len(args) > 2:
            try:
                bytesPerLine = self._strToInt(args[2])
                if bytesPerLine < 1:
                    raise ValueError('Can\'t have less than 1 byte per line.')
            except ValueError as e:
                print(self.getHelpText(args[0]))
                return f'Syntax error: {e}'
        
        if len(args) > 1:
            if args[1].lower() == 'yes':
                enabled = True
            elif args[1].lower() == 'no':
                enabled = False
            else:
                print(self.getHelpText(args[0]))
                return 'Syntax error: Must be "yes" or "no".'
        
        # Write back settings
        self.setSetting(EBaseSettingKey.HEXDUMP_ENABLED, enabled)
        hexdumpObj.setBytesPerLine(bytesPerLine)
        hexdumpObj.setBytesPerGroup(bytesPerGroup)

        # Show status
        if enabled:
            print(f'Printing hexdumps: {hexdumpObj}')
        else:
            print('Not printing hexdumps.')

        return 0

    ###############################################################################
    # Completers go here.

    def _yesNoCompleter(self, rbs: RBS) -> typing.NoReturn:
        options = ['yes', 'no']
        for option in options:
            if option.startswith(rbs.being_completed):
                self.completer.candidates.append(option)
        return
