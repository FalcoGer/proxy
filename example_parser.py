# This file contains the user defined parser commands and functionality.
# Use it as a template for your own stuff.

# The module will be reloaded as soon as this file has changed on disk
# and when the module is next requested. This happens when either
# the parse or handleUserInput function is called from application.
# The magic happens because the module is stored in a
# DynamicLoader object. See dynamic_loader.py

# WARNING:
# Only the Parser.settings dictionary is stored persistently.
# If the module gets reloaded, every other attribute
# that is stored in the class instance will get reset
# If you want to store values you need to:
# - create a key in ESettingKey
# - assign a default value in getDefaultSettings
# - use the setSetting(key, value) and getSetting(key) functions
# Removing a key from ESettingKey will cause
# that key to be deleted on the next module reload.

# will be default in python 3.11.
# This is required for there to be no errors in the type hints.
from __future__ import annotations
import typing

from enum import Enum, auto

from prompt_toolkit import print_formatted_text as print
from prompt_toolkit.formatted_text import HTML, to_formatted_text

# struct is used to decode bytes into primitive data types
# https://docs.python.org/3/library/struct.html
import struct

# Allows pretty printing of bytes in a hexdump format
# One such class instance is available in the base parser settings.
# But you might want to make your own
# instance for your custom configuration
from hexdump import Hexdump

# This is the base class for the custom parser class
import base_parser

# import stuff for API calls
from eSocketRole import ESocketRole

# For type hints only
if typing.TYPE_CHECKING:
    from proxy import Proxy
    from application import Application
    from buffer_status import BufferStatus
    from core_parser import CommandDictType

# For more examples of commands, completers and api calls check core and base parser file.

###############################################################################
# Create keys for settings that should have a default value here.

class ESettingKey(Enum):
    EXAMPLE_SETTING = auto()

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

# Class name must be Parser
class Parser(base_parser.Parser):

    # Define the parser name here as it should appear in the prompt
    def __str__(self) -> str:
        return 'Example'

    # Use this to set sensible defaults for your stored variables.
    def getDefaultSettings(self) -> dict[(Enum, typing.Any)]:
        userDefaultSettings = {
                ESettingKey.EXAMPLE_SETTING: 'ExAmPlE'
            }

        # Make sure to include the base class settings as well.
        defaultSettings = super().getDefaultSettings()
        return defaultSettings | userDefaultSettings

    ###############################################################################
    # Packet parsing stuff goes here.

    # Define what should happen when a packet arrives here
    # Do not print here, instead append any console output you want to the output array, one line per entry.
    def parse(self, data: bytes, proxy: Proxy, origin: ESocketRole) -> list[str]:
        output = super().parse(data, proxy, origin)

        # A construct like this may be used to drop packets.
        if data.find(b'drop') >= 0:
            output.append('Dropped')
            return output

        # Do interesting stuff with the data here.
        data = data.replace(b'ding', b'dong')

        # By default, send the data to the client/server.
        if origin == ESocketRole.client:
            proxy.sendToServer(data)
        else:
            proxy.sendToClient(data)
        return output

    ###############################################################################
    # CLI stuff goes here.

    # Define your custom commands here. Each command requires those arguments:
    # 1. args: list[str]
    #   A list of command arguments. args[0] is always the command string itself.
    # 2. proxy: Proxy
    #   This allows to make calls to the proxy API, for example to inject packets or get settings.
    # The functions should return 0 if they succeeded. Otherwise their return gets printed by the CLI handler.

    # Define which commands are available here and which function is called when it is entered by the user.
    # Return a dictionary with the command as the key and a tuple of (function, str, completerArray) as the value.
    # The function is called when the command is executed, the string is the help text for that command.
    # The last completer in the completer array will be used for all words if the word index is higher than the index in the completer array.
    # If you don't want to provide more completions, use None at the end.
    def _buildCommandDict(self) -> CommandDictType:
        ret = super()._buildCommandDict()

        # Add your custom commands here
        ret['example']      = (self._cmd_example, 'Sends the string in the example setting count times to the client.\nUsage: {0} [upper | lower | as_is] <count>\nExample {0} as_is 10.', [self._exampleCompleter, None])
        # Alises
        ret['ex']           = ret['example']
        return ret

    ###############################################################################
    # Command callbacks go here.

    # If a command doesn't need to know which proxy it is
    # working on, simply use '_' as the third argument name

    # Sends the example setting string a few times to the client.
    def _cmd_example(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        # args: transformation, count
        if len(args) != 3:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        dataStr = str(self.getSetting(ESettingKey.EXAMPLE_SETTING))

        if args[1] == 'upper':
            dataStr = dataStr.upper()
        elif args[1] == 'lower':
            dataStr = dataStr.lower()
        elif args[1] == 'as_is':
            pass
        else:
            print(self.getHelpText(args[0]))
            return f'Capitalize must be "upper", "lower" or "as_is", but was {args[1]}'

        count = self._strToInt(args[2]) # this allows hex, bin and oct notations also
        data = dataStr.encode('utf-8')

        # xmit count times
        if not proxy.getIsConnected():
            return 'Not connected'

        for _ in range(0, count):
            proxy.sendToClient(data)

        return 0

    ###############################################################################
    # Completers go here.
    # See buffer_status.py for which values are available
    # Append any options you want to be in the auto completion list to completer.candidates
    # See core_parser.py for examples

    def _exampleCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        options = ['upper', 'lower', 'as_is']
        for option in options:
            if option.startswith(bufferStatus.being_completed):
                self.completer.candidates.append(option)
        return

    ###########################################################################
    # No need to touch anything below here.

    def __init__(self, application: Application, settings: dict[Enum, typing.Any]):
        super().__init__(application, settings)
        return

    def getSettingKeys(self) -> list[Enum]:
        settingKeys = super().getSettingKeys()
        settingKeys.extend(list(ESettingKey))
        return settingKeys
