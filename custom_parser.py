# This file contains the user defined parser commands and functionality

# struct is used to decode bytes into primitive data types
# https://docs.python.org/3/library/struct.html
import struct
from enum import Enum, auto

# Allows pretty printing of bytes in a hexdump format
from hexdump import Hexdump

# This is the base class for the custom parser class
from base_parser import BaseParser

# import stuff for API calls
from eSocketRole import ESocketRole

# For more examples of commands, completers and api calls check core and base parser file.

###############################################################################
# Setting storage stuff goes here.

class ESettingKey(Enum):
    EXAMPLE_SETTING = auto()

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

class CustomParser(BaseParser):
    # Use this to set sensible defaults for your stored variables.
    def getDefaultSettings(self) -> dict[(Enum, object)]:
        defaultSettings = super().getDefaultSettings()
        userDefaultSettings = {
                ESettingKey.EXAMPLE_SETTING: 'ExAmPlE'
            }
        return defaultSettings | userDefaultSettings

    ###############################################################################
    # Packet parsing stuff goes here.

    # Define what should happen when a packet arrives here
    def parse(self, data: bytes, proxy, origin: ESocketRole) -> None:
        super().parse(data, proxy, origin)

        # Do interesting stuff with the data here.
        #if data == b'ABCD\n' and origin == ESocketRole.client:
        #    data = b'DCBA\n'

        # A construct like this may be used to drop packets. 
        #if data.find(b'\xFF\xFF\xFF\xFF') >= 0:
        #    print("Dropped")
        #    return

        # By default, append the data as is to the queue to send it to the client/server.
        target = ESocketRole.server if origin == ESocketRole.client else ESocketRole.client
        proxy.sendData(target, data)
        return

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
    def buildCommandDict(self) -> dict:
        ret = super().buildCommandDict()
        
        # Add your custom commands here
        ret['example']      = (self._cmd_example, 'Sends the string in the example setting n times to the client.\nUsage: {0} [upper | lower | as_is] count\nExample {0} as_is 10.', [self._exampleCompleter, self._historyCompleter, None])
        # Alises
        ret['ex']           = ret['example']
        return ret

    ###############################################################################
    # Command callbacks go here.

    def _cmd_example(self, args: list[str], proxy) -> object:
        if len(args) != 3:
            print(self._getHelpText(args[0]))
            return "Syntax error."
        
        dataStr = str(self.getSetting(ESettingKey.EXAMPLE_SETTING))
        
        if args[1] == 'upper':
            dataStr = dataStr.upper()
        elif args[1] == 'lower':
            dataStr = dataStr.lower()
        elif args[1] == 'as_is':
            pass
        else:
            print(self.getHelpText(args[0]))
            return f"Capitalize must be 'upper', 'lower' or 'as_is', but was {args[1]}"
        
        count = self._strToInt(args[2]) # this allows hex, bin and oct notations also
        data = dataStr.encode('utf-8')
        
        # xmit count times
        if not proxy.connected:
            return "Not connected"

        for _ in range(0, count):
            proxy.sendToClient(data)

        return 0

    ###############################################################################
    # Completers go here.
    # See proxy.py for which values are available in the completer object.
    # Append any options you want to be in the auto completion list to completer.candidates

    def _exampleCompleter(self) -> None:
        options = ["upper", "lower", "as_is"]
        for option in options:
            if option.startswith(self.completer.being_completed):
                self.completer.candidates.append(option)
        return

    ###########################################################################
    # No need to touch anything below here.

    def __init__(self, application, settings):
        super().__init__(application, settings)
        return
    
    def getSettingKeys(self) -> list[Enum]:
        settingKeys = super().getSettingKeys()
        settingKeys.extend(list(ESettingKey))
        return settingKeys

