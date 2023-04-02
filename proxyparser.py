#/bin/python3

# struct is used to decode bytes into primitive data types
# https://docs.python.org/3/library/struct.html
import struct
from proxy import Proxy, ESocketRole, Completer
from hexdump import hexdump
from enum import Enum, auto
from copy import copy
import os

###############################################################################
# Setting storage stuff goes here.

class ESettingKey(Enum):
    printhexdump = auto()
    hexdumpBytesPerLine = auto()
    hexdumpBytesPerGroup = auto()
    hexdumpPrintHighAscii = auto()
    hexdumpNonprintableChar = auto()
    printPacketNotification = auto()

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
    	return int.__hash__(self.value)

    def fromName(name: str):
        for e in list(ESettingKey):
            if name == e.name:
                return e
        return None

# Use this to set sensible defaults for your stored variables.
def settingsDefaults(settingKey: ESettingKey) -> object:
    ret = None
    if settingKey == ESettingKey.printhexdump:
        return True
    if settingKey == ESettingKey.printPacketNotification:
        return True
    if settingKey == ESettingKey.hexdumpBytesPerLine:
        return 32
    if settingKey == ESettingKey.hexdumpBytesPerGroup:
        return 8
    if settingKey == ESettingKey.hexdumpPrintHighAscii:
        return False
    if settingKey == ESettingKey.hexdumpNonprintableChar:
        return "."
    return ret

###############################################################################
# Packet parsing stuff goes here.

# Define what should happen when a packet arrives here
def parse(data: bytes, src: (str, int), dest: (str, int), origin: ESocketRole, proxy: Proxy) -> None:
    if getSetting(ESettingKey.printPacketNotification, proxy):
        # Print out the data in a nice format.
        sh, sp = src
        dh, dp = dest
        srcStr = f"{sh}:{sp}"
        destStr = f"{dh}:{dp}"
        maxLen = len(srcStr) if len(srcStr) > len(destStr) else len(destStr)

        srcStr = srcStr.rjust(maxLen)
        destStr = destStr.ljust(maxLen)
        directionStr = "C -> S" if origin == ESocketRole.client else "C <- S"
        print(f"[{directionStr}] - {srcStr}->{destStr} ({len(data)} Byte{'s' if len(data) > 1 else ''})")

    if getSetting(ESettingKey.printhexdump, proxy):
        bytesPerLine = getSetting(ESettingKey.hexdumpBytesPerLine, proxy)
        bytesPerGroup = getSetting(ESettingKey.hexdumpBytesPerGroup, proxy)
        sep = getSetting(ESettingKey.hexdumpNonprintableChar, proxy)
        printHighAscii = getSetting(ESettingKey.hexdumpPrintHighAscii, proxy)
        hd = "\n".join(hexdump(data, bytesPerLine, bytesPerGroup, None, sep, printHighAscii))
        print(f"{hd}")

    # Do interesting stuff with the data here.
    #if data == b'ABCD\n' and origin == ESocketRole.client:
    #    data = b'DCBA\n'

    # A construct like this may be used to drop packets. 
    #if data.find(b'\xFF\xFF\xFF\xFF') >= 0:
    #    print("Dropped")
    #    return

    # By default, append the data as is to the queue to send it to the client/server.
    proxy.sendData(ESocketRole.server if origin == ESocketRole.client else ESocketRole.client, data)
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
def buildCommandDict() -> dict:
    ret = {}
    ret['quit']         = (cmd_quit, 'Stop the proxy and quit.\nUsage: {0}', None)
    ret['clearhistory'] = (cmd_clearhistory, 'Clear the command history or delete one entry of it.\nUsage: {0} [historyIndex].\nNote: The history file will instantly be overwritten.', None)
    ret['lshistory']    = (cmd_lshistory, 'Show the command history or display one entry of it.\nUsage: {0} [historyIndex]', None)
    ret['lssetting']    = (cmd_lssetting, 'Show the current settings or display a specific setting.\nUsage: {0} [settingName]', [settingsCompleter, None])
    ret['disconnect']   = (cmd_disconnect, 'Disconnect from the client and server and wait for a new connection.\n Usage: {0}', None)
    ret['help']         = (cmd_help, 'Print available commands. Or the help of a specific command.\nUsage: {0} [command]', [commandCompleter, None])
    ret['hexdump']      = (cmd_hexdump, 'Configure the hexdump or show current configuration.\nUsage: {0} [yes|no] [bytesPerLine] [bytesPerGroup]', [yesNoCompleter, historyCompleter, historyCompleter, None])
    ret['sh']           = (cmd_sh, 'Send arbitrary hex values to the server.\nUsage: {0} hexstring \nExample: {0} 41424344\nNote: Spaces are allowed and ignored.', [historyCompleter])
    ret['ss']           = (cmd_ss, 'Send arbitrary strings to the server.\nUsage: {0} string\nExample: {0} hello\\!\\n\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.\nEscape sequences are available.', [historyCompleter])
    ret['sf']           = (cmd_sf, 'Send arbitrary files to the server.\nUsage: {0} filename\nExample: {0} /home/user/.bashrc', [fileCompleter, None])
    ret['ch']           = (cmd_ch, 'Send arbitrary hex values to the client.\nUsage: {0} hexstring \nExample: {0} 41424344', [historyCompleter])
    ret['cs']           = (cmd_cs, 'Send arbitrary strings to the client.\nUsage: {0} string\nExample: {0} hello!\\n\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.\nEscape sequences are available.', [historyCompleter])
    ret['cf']           = (cmd_cf, 'Send arbitrary files to the client.\nUsage: {0} filename\nExample: {0} /home/user/.bashrc', [fileCompleter, None])
    ret['set']          = (cmd_set, 'Sets variable to a value\nUsage: {0} varname value\nExample: {0} httpGet GET / HTTP/1.0\\n', [variableCompleter, historyCompleter])
    ret['unset']        = (cmd_unset, 'Deletes a variable.\nUsage: {0} varname\nExample: {0} httpGet', [variableCompleter, None])
    ret['lsvar']        = (cmd_lsvar, 'Lists variables.\nUsage: {0} [varname]\nExample: {0}\nExample: {0} httpGet', [variableCompleter, None])
    ret['savevars']     = (cmd_savevars, 'Saves variables to a file.\nUsage: {0} filepath', [fileCompleter, None])
    ret['loadvars']     = (cmd_loadvars, 'Loads variables from a file\nUsage: loadvars {0}\nNote: Existing variables will be retained.\nUse clearvars before loading if you want the variables from that file only.', [fileCompleter, None])
    ret['clearvars']    = (cmd_clearvars, 'Clears variables.\nUsage: {0}', None)
    ret['pack']         = (cmd_pack, 'Packs data into a different format.\nUsage: {0} datatype format data [...]\nNote: Data is separated by spaces.\nExample: {0} int little_endian 255 0377 0xFF\nExample: {0} byte little_endian 41 42 43 44\nExample: {0} uchar little_endian x41 x42 x43 x44\nRef: https://docs.python.org/3/library/struct.html', [packDataTypeCompleter, packFormatCompleter, historyCompleter])
    ret['unpack']       = (cmd_unpack, 'Unpacks and displays data from a different format.\nUsage: {0} datatype format hexdata\nNote: Hex data may contain spaces, they are ignored.\nExample: {0} int little_endian 01000000 02000000\nRef: https://docs.python.org/3/library/struct.html', [packDataTypeCompleter, packFormatCompleter, historyCompleter])
    ret['convert']      = (cmd_convert, 'Converts numbers from one type to all others.\nUsage: {0} [sourceFormat] number\nExample: {0} dec 65\nExample: {0} 0x41', [convertTypeCompleter, historyCompleter, None])

    # Alises
    ret['exit']         = ret['quit']
    ret['lss']          = ret['lssetting']

    ret['lsh']          = ret['lshistory']
    ret['clh']          = ret['clearhistory']
    
    ret['lsv']          = ret['lsvar']
    ret['clv']          = ret['clearvars']
    return ret

def cmd_help(args: list[str], proxy: Proxy) -> object:
    commandDict = buildCommandDict()
    
    if len(args) > 2:
        print(getHelpText(args[0]))
        return "Syntax error."

    # If user wanted help for a specific command
    if len(args) == 2 and args[1] in commandDict.keys():
        print(getHelpText(args[1]))
        return 0
    
    if len(args) == 2:
        return f"No such command: {args[1]}."
    
    # Print all command helps strings.
    # Find the longest key for neat formatting.
    maxLen = 0
    for key in commandDict.keys():
        if len(key) > maxLen:
            maxLen = len(key)

    for key in commandDict.keys():
        helpText = getHelpText(key)
        helpText = helpText.replace("\n", "\n" + (" " * (maxLen + 4))).strip()
        print(f"{key.rjust(maxLen)} - {helpText}")
    
    # Print general CLI help also
    print("Readline extensions are available.")
    print("  Use TAB for auto completion")
    print("  Use CTRL+R for history search.")
    print("  Use !idx to execute a command from the history again.")
    print("  Use $varname to expand variables.")
    print("  To use a literal ! or $ use \\! and \\$ respectively.")
    print("  Where numbers are required, they may be prefixed:\n    - x or 0x for hex\n    - 0, o or 0o for octal\n    - b or 0b for binary\n    - No prefix for decimal.")
    return 0

def cmd_quit(args: list[str], proxy: Proxy) -> object:
    if len(args) > 1:
        print(getHelpText(args[0]))
        return "Syntax error."
    proxy.application.running = False
    return 0

def cmd_sh(args: list[str], proxy: Proxy) -> object:
    return cmd_send_hex(args, ESocketRole.server, proxy)

def cmd_ch(args: list[str], proxy: Proxy) -> object:
    return cmd_send_hex(args, ESocketRole.client, proxy)

def cmd_send_hex(args: list[str], target: ESocketRole, proxy: Proxy) -> object:
    if len(args) == 1:
        print(getHelpText(args[0]))
        return "Syntax error."

    # Allow spaces in hex string, so join with empty string to remove them.
    userInput = ''.join(args[1:])
        
    pkt = bytes.fromhex(userInput)
    if proxy.running:
        proxy.sendData(target, pkt)
    return 0

def cmd_ss(args: list[str], proxy: Proxy) -> object:
    return cmd_send_string(args, ESocketRole.server, proxy)

def cmd_cs(args: list[str], proxy: Proxy) -> object:
    return cmd_send_string(args, ESocketRole.client, proxy)

def cmd_send_string(args: list[str], target: ESocketRole, proxy: Proxy) -> object:
    if len(args) == 1:
        print(getHelpText(args[0]))
        return "Syntax error."

    userInput = ' '.join(args[1:])

    pkt = str.encode(userInput, 'utf-8')
    pkt = escape(pkt)
    if proxy.running:
        proxy.sendData(target, pkt)
    return 0

def cmd_sf(args: list[str], proxy: Proxy) -> object:
    return cmd_send_file(args, ESocketRole.server, proxy)

def cmd_cf(args: list[str], proxy: Proxy) -> object:
    return cmd_send_file(args, ESocketRole.client, proxy)

def cmd_send_file(args: list[str], target: ESocketRole, proxy: Proxy) -> object:
    if len(args) != 2:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    filePath = ' '.join(args[1:])
    if not os.path.isfile(filePath):
        return f"File \"{filePath}\" does not exist."
    
    byteArray = b''
    try:
        with open(filePath, "rb") as file:
            while byte := file.read(1):
                byteArray += byte
    except Exception as e:
        return f"Error reading file \"{filePath}\": {e}"

    if proxy.running:
        proxy.sendData(target, byteArray)

    return 0

def cmd_disconnect(args: list[str], proxy: Proxy) -> object:
    if len(args) != 1:
        print(getHelpText(args[0]))
        return "Syntax error."

    if proxy.running:
        proxy.disconnect()
    else:
        return "Not connected."
    return 0

def cmd_lshistory(args: list[str], proxy: Proxy) -> object:
    if len(args) > 2:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    readline = proxy.application.getReadlineModule()
    
    if len(args) == 2:
        try:
            idx = strToInt(args[1])
        except ValueError as e:
            print(getHelpText(args[0]))
            return f"Syntax error: {e}"

        if idx < readline.get_current_history_length():
            historyline = readline.get_history_item(idx)
            print(f"{idx} - \"{historyline}\"")
            return 0
        else:
            return f"Invalid history index {idx}."
    
    # Print them all.
    for idx in range(0, readline.get_current_history_length()):
        historyline = readline.get_history_item(idx)
        print(f"{idx} - \"{historyline}\"")
    return 0

def cmd_clearhistory(args: list[str], proxy: Proxy) -> object:
    readline = proxy.application.getReadlineModule()

    if len(args) > 2:
        print(getHelpText(args[0]))
        return "Syntax error."

    if len(args) == 2:
        try:
            idx = strToInt(args[1])
        except ValueError as e:
            print(getHelpText(args[0]))
            return f"Syntax error: {e}"

        if idx < readline.get_current_history_length():
            historyline = readline.get_history_item(idx)
            readline.remove_history_item(idx) # FIXME: Doesn't work?
            print(f"Item {idx} deleted: {historyline}")
        else:
            return f"Invalid history index {idx}"
    else:
        readline.clear_history()
        print("History deleted.")
    
    # Write back the history file.
    readline.write_history_file("history.log")
    return 0

def cmd_lssetting(args: list[str], proxy: Proxy) -> object:
    if len(args) > 2:
        print(getHelpText(args[0]))
        return "Syntax error."

    if len(args) == 2:
        if len(args[1]) == 0:
            print(getHelpText(args[0]))
            return "Syntax error"
        if not args[1] in [x.name for x in proxy.settings.keys()]:
            return f"{args[1]} is not a valid setting."
        value = getSetting(ESettingKey.fromName(args[1]), proxy)
        print(f"{args[1]}: {value}")
        return 0
    
    # Print them all
    longestKeyLength = 0
    for key in proxy.settings.keys():
        keyName = key.name
        lenKeyName = len(keyName)
        if lenKeyName > longestKeyLength:
            longestKeyLength = lenKeyName

    for key in proxy.settings.keys():
        keyName = key.name
        value = getSetting(key, proxy)
        keyStr = keyName.rjust(longestKeyLength)
        print(f"{keyStr}: {value}")
    return 0

def cmd_hexdump(args: list[str], proxy: Proxy) -> object:
    if len(args) > 4:
        print(getHelpText(args[0]))
        return "Syntax error."

    enabled = getSetting(ESettingKey.printhexdump, proxy)
    bytesPerLine = getSetting(ESettingKey.hexdumpBytesPerLine, proxy)
    bytesPerGroup = getSetting(ESettingKey.hexdumpBytesPerGroup, proxy)

    if len(args) > 3:
        try:
            bytesPerGroup = strToInt(args[3])
        except ValueError as e:
            print(getHelpText(args[0]))
            return f"Syntax error: {e}"
    
    if len(args) > 2:
        try:
            bytesPerLine = strToInt(args[2])
            if bytesPerLine < 1:
                raise ValueError("Can't have less than 1 byte per line.")
        except ValueError as e:
            print(getHelpText(args[0]))
            return f"Syntax error: {e}"
    
    if len(args) > 1:
        if args[1].lower() == 'yes':
            enabled = True
        elif args[1].lower() == 'no':
            enabled = False
        else:
            print(getHelpText(args[0]))
            return "Syntax error: Must be 'yes' or 'no'."
    
    # Write back settings
    setSetting(ESettingKey.printhexdump, enabled, proxy)
    setSetting(ESettingKey.hexdumpBytesPerLine, bytesPerLine, proxy)
    setSetting(ESettingKey.hexdumpBytesPerGroup, bytesPerGroup, proxy)

    # Show status
    if enabled:
        print(f"Printing hexdumps with {bytesPerLine} bytes per line and {bytesPerGroup} bytes per group.")
    else:
        print("Not printing hexdumps.")

    return 0

def cmd_set(args: list[str], proxy: Proxy) -> object:
    if len(args) < 3:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    varName = args[1]
    if len(varName) == 0:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    # variable values may have spaces in them.
    varValue = ' '.join(args[2:])
    proxy.application.setVariable(varName, varValue)
    return 0

def cmd_unset(args: list[str], proxy: Proxy) -> object:
    if len(args) != 2:
        print(getHelpText(args[0]))
        return "Syntax error."

    if (proxy.application.unsetVariable(args[1])):
        print(f"Deleted variable {args[1]}")
    else:
        return f"Variable {args[1]} doesn't exist."
    return 0

def cmd_lsvar(args: list[str], proxy: Proxy) -> object:
    if len(args) > 2:
        print(getHelpText(args[0]))
        return "Syntax error."

    # Print specific variable
    if len(args) == 2:
        varName = args[1]
        if varName in proxy.application.variables.keys():
            varValue = proxy.application.getVariable(varName)
            print(f"{varName} - \"{varValue}\"")
        else:
            return f"{varName} is not defined."
        return 0

    # print all variables
    maxVarNameLength = 0
    for varName in proxy.application.variables.keys():
        varNameLength = len(varName)
        if varNameLength > maxVarNameLength:
            maxVarNameLength = varNameLength

    for varName in proxy.application.variables.keys():
        varValue = proxy.application.getVariable(varName)
        print(f"{varName.rjust(maxVarNameLength)} - \"{varValue}\"")
    return 0

def cmd_savevars(args: list[str], proxy: Proxy) -> object:
    if len(args) != 2:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    filePath = ' '.join(args[1:])
    try:
        with open(filePath, "wt") as file:
            for varName in proxy.application.variables.keys():
                varValue = proxy.application.getVariable(varName)
                file.write(f"{varName} {varValue}")
    except Exception as e:
        return f"Error writing file \"{filePath}\": {e}"

    return 0

def cmd_loadvars(args: list[str], proxy: Proxy) -> object:
    if len(args) != 2:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    filePath = ' '.join(args[1:])
    try:
        loadedVars = {}
        with open(filePath, "rt") as file:
            lineNumber = 0
            for line in file.readlines():
                line = line.strip('\n')
                lineNumber += 1
                if len(line.strip()) == 0:
                    # skip empty lines
                    continue

                try:
                    if len(line.split(' ')) <= 1:
                        raise ValueError("Line does not contain a variable-value pair.")

                    varName = line.split(' ')[0]
                    if not proxy.application.checkVariableName(varName):
                        raise ValueError(f"Bad variable name: \"{varName}\"")

                    varValue = ' '.join(line.split(' ')[1:])
                    if len(varValue) == 0:
                        raise ValueError("Variable value is empty.")

                    if varName in loadedVars.keys():
                        raise KeyError(f"Variable \"{varName}\" already loaded from this file.")

                    loadedVars[varName] = varValue
                except (ValueError, KeyError) as e:
                    return f"Line {lineNumber} \"{line}\", could not extract variable from file \"{filePath}\": {e}"
        
        # Everything loaded successfully
        for varName in loadedVars.keys():
            proxy.application.setVariable(varName, loadedVars[varName])
        print(f"{len(loadedVars)} variables loaded successfully.")
    except Exception as e:
        return f"Error reading file \"{filePath}\": {e}"

    return 0

def cmd_clearvars(args: list[str], proxy: Proxy) -> object:
    proxy.application.variables = {}
    print("All variables deleted.")
    return 0

def cmd_pack(args: list[str], proxy: Proxy) -> object:
    # FIXME: cstring and pascal string not working correctly.
    if len(args) < 4:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    formatMapping = cmd_pack_getFormatMapping()
    dataTypeMapping = cmd_pack_getDataTypeMapping()

    dataCount = len(args) - 3 # Data is separated by spaces

    dataTypeMappingString = args[1]
    if dataTypeMappingString not in dataTypeMapping.keys():
        return f"Syntax error. Data type {dataTypeMappingString} unknown, must be one of {dataTypeMapping.keys()}."
    
    formatMappingString = args[2]
    if formatMappingString not in formatMapping.keys():
        return f"Syntax error. Format {formatMappingString} unknown, must be one of {formatMapping.keys()}."
    
    if dataTypeMapping[dataTypeMappingString] in ['n', 'N'] and formatMapping[formatMappingString] != formatMapping['native']:
        return f"format for data type {dataTypeMappingString} must be native (@)."

    formatString = f"{formatMapping[formatMappingString]}{dataCount}{dataTypeMapping[dataTypeMappingString]}"
    
    dataStrArray = args[3:]
    # Convert data according to the format
    convertedData = []
    for dataStr in dataStrArray:
        data = cmd_pack_convert(dataTypeMapping[dataTypeMappingString], dataStr)
        convertedData.append(data)
    try:
        packedValues = struct.pack(formatString, *convertedData)
    except struct.error as e:
        return f"Unable to pack {convertedData} with format {formatString}: {e}"
    
    print(f"Packed: {packedValues}")
    asHex = ''
    for byte in packedValues:
        asHex += f"{byte:02X}"
    print(f"Hex: {asHex}")
    return 0

def cmd_unpack(args: list[str], proxy: Proxy) -> object:
    # FIXME: cstring and pascal string not working correctly.
    if len(args) < 4:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    formatMapping = cmd_pack_getFormatMapping()
    dataTypeMapping = cmd_pack_getDataTypeMapping()
    
    dataTypeMappingString = args[1]
    if dataTypeMappingString not in dataTypeMapping.keys():
        return f"Syntax error. Data type {dataTypeMappingString} unknown, must be one of {dataTypeMapping.keys()}."
    
    formatMappingString = args[2]
    if formatMappingString not in formatMapping.keys():
        return f"Syntax error. Format {formatMappingString} unknown, must be one of {formatMapping.keys()}."
    
    if dataTypeMapping[dataTypeMappingString] in ['n', 'N'] and formatMapping[formatMappingString] != formatMapping['native']:
        return f"format for data type {dataTypeMappingString} must be native (@)."
    
    hexDataStr = ''.join(args[3:]) # Joining on '' eliminates spaces.
    byteArray = bytes.fromhex(hexDataStr)
    
    # calculate how many values we have
    dataTypeSize = struct.calcsize(f"{formatMapping[formatMappingString]}{dataTypeMapping[dataTypeMappingString]}")
    if len(byteArray) % dataTypeSize != 0:
        return f"Expecting a multiple of {dataTypeSize} Bytes, which is the size of type {dataTypeMappingString}, but got {len(byteArray)} Bytes in {byteArray}"
    dataCount = int(len(byteArray) / dataTypeSize)

    formatString = f"{formatMapping[formatMappingString]}{dataCount}{dataTypeMapping[dataTypeMappingString]}"

    try:
        unpackedValues = struct.unpack(formatString, byteArray)
    except struct.error as e:
        return f"Unable to unpack {byteArray} with format {formatString}: {e}"
    
    print(f"Unpacked: {unpackedValues}")
    return 0

# Converts the string data from the user's input into the correct data type for struct.pack
def cmd_pack_convert(dataTypeString: str, dataStr: str) -> object:
    if dataTypeString in ['c', 's', 'p']:
        # byte array formats
        return bytes.fromhex(dataStr)
    if dataTypeString in ['b', 'B', 'h', 'H', 'i', 'I', 'l', 'L', 'q', 'Q', 'n', 'N', 'P']:
        # integer formats
        return strToInt(dataStr)
    if dataTypeString in ['e', 'f', 'd']:
        # float formats
        return float(dataStr)
    raise ValueError(f"Format string {dataTypeString} unknown.")

def cmd_pack_getFormatMapping() -> dict:
    mapping = {
        'native': '@',
        'standard_size': '=',
        'little_endian': '<',
        'big_endian': '>',
        'network': '!'
    }

    # allow the raw input also
    values = copy(mapping).values()
    for value in values:
        mapping[value] = value

    return mapping

def cmd_pack_getDataTypeMapping() -> dict:
    mapping = {
        'byte': 'c',
        'char': 'b',
        'uchar': 'B',
        '_Bool': '?',
        'short': 'h',
        'ushort': 'H',
        'int': 'i',
        'uint': 'I',
        'long': 'l',
        'ulong': 'L',
        'long_long': 'q',
        'ulong_long': 'Q',
        'ssize_t': 'n',
        'size_t': 'N',
        'half_float_16bit': 'e',
        'float': 'f',
        'double': 'd',
        'pascal_string': 'p',
        'c_string': 's',
        'void_ptr': 'P'
    }
    
    # allow the raw values also
    values = copy(mapping).values()
    for value in values:
        mapping[value] = value

    return mapping

def cmd_convert(args: list[str], proxy: Proxy) -> object:
    if len(args) not in [2, 3]:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    # figure out the format
    if len(args) == 3:
        formatString = args[1]
        numberString = args[2]
   
        try:
            if formatString == 'dec':
                number = int(numberString, 10)
            elif formatString == 'hex':
                number = int(numberString, 16)
            elif formatString == 'oct':
                number = int(numberString, 8)
            elif formatString == 'bin':
                number = int(numberString, 2)
            else:
                raise ValueError("Unknown format string {formatString}")
        except ValueError as e:
            return f"Can't convert {numberString} as {formatString} to number: {e}"
    else:
        numberString = args[1]
        number = strToInt(numberString)
    # print the number
    print(f"DEC: {number}\nHEX: {hex(number)}\nOCT: {oct(number)}\nBIN: {bin(number)}")
    return 0

###############################################################################
# Completers go here.

def yesNoCompleter(completer: Completer) -> None:
    options = ["yes", "no"]
    for option in options:
        if option.startswith(completer.being_completed):
            completer.candidates.append(option)
    return

def convertTypeCompleter(completer: Completer) -> None:
    options = ['dec', 'bin', 'oct', 'hex']
    for option in options:
        if option.startswith(completer.being_completed):
            completer.candidates.append(option)
    return


def packDataTypeCompleter(completer: Completer) -> None:
    options = cmd_pack_getDataTypeMapping().keys()
    for option in options:
        if option.startswith(completer.being_completed):
            completer.candidates.append(option)
    return

def packFormatCompleter(completer: Completer) -> None:
    formatMapping = cmd_pack_getFormatMapping()
    dataTypeMapping = cmd_pack_getDataTypeMapping()
    # 'n' and 'N' only available in native.
    nativeOnlyList = []
    for dataTypeMappingString in dataTypeMapping.keys():
        if dataTypeMapping[dataTypeMappingString] in ['n', 'N']:
            nativeOnlyList.append(dataTypeMappingString)
    
    if completer.words[1] in nativeOnlyList:
        completer.candidates.append('native')
        # '@' also valid, but omit for quicker typing.
        # completer.candidates.append('@')
        return
    
    # Return all available options
    options = cmd_pack_getFormatMapping().keys()
    for option in options:
        if option.startswith(completer.being_completed):
            completer.candidates.append(option)
    return

def commandCompleter(completer: Completer) -> None:
    completer.getCommandCandidates()
    return

def fileCompleter(completer: Completer) -> None:
    completer.getFileCandidates()
    return

def settingsCompleter(completer: Completer) -> None:
    completer.getSettingsCandidates()
    return

def variableCompleter(completer: Completer) -> None:
    completer.getVariableCandidates(False)
    return

def historyCompleter(completer: Completer) -> None:
    completer.getHistoryCandidates()
    return


###############################################################################
# No need to edit the functions below

# This function take the command line string and calls the relevant python function with the correct arguments.
def handleUserInput(userInput: str, proxy: Proxy) -> object:
    args = userInput.split(' ')

    if len(userInput.strip()) == 0:
        # Ignore empty commands
        return 0
    
    cmdList = buildCommandDict()
    if args[0] not in cmdList.keys():
        return f"Undefined command: \"{args[0]}\""

    function, _, _ = cmdList[args[0]]
    return function(args, proxy)

def getHelpText(cmdString: str) -> str:
    _, helpText, _ = buildCommandDict()[cmdString]
    return helpText.format(cmdString)

# Wrapper for proxy.getSetting to handle default values. Use this function only in this file.
# Don't make calls to proxy.getSetting elsewhere.
def getSetting(settingKey: ESettingKey, proxy: Proxy) -> object:
    ret = proxy.getSetting(settingKey)
    if ret is None:
        ret = settingsDefaults(settingKey)
        if ret is not None:
            setSetting(settingKey, ret, proxy)
    return ret

# Wrapper for proxy.setSetting. Use this function only in this file.
# Don't make calls to proxy.setSetting elsewhere.
def setSetting(settingKey: ESettingKey, settingValue: object, proxy: Proxy) -> None:
    proxy.setSetting(settingKey, settingValue)
    return

# replaces escape sequences with the proper values
def escape(data: bytes) -> bytes:
    idx = 0
    newData = b''
    while idx < len(data):
        b = intToByte(data[idx])
        if b == b'\\':
            idx += 1 # Add one to the index so we don't read the escape sequence byte as a normal byte.
            nextByte = intToByte(data[idx]) # May throw IndexError, pass it up to the user.
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
                newData += intToByte(num)
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

def intToByte(i: int) -> bytes:
    return struct.pack('=b', i if i < 128 else i - 256)

def strToInt(dataStr: str) -> int:
    if dataStr.startswith('0x'):
        return int(dataStr[2:], 16)
    if dataStr.startswith('x'):
        return int(dataStr[1:], 16)
    if dataStr.startswith('0o'):
        return (int(dataStr[2:], 8))
    if (dataStr.startswith('0') and len(dataStr) > 1) or dataStr.startswith('o'):
        return int(dataStr[1:], 8)
    if dataStr.startswith('0b'):
        return (int(dataStr[2:], 2))
    if dataStr.startswith('b'):
        return (int(dataStr[1:], 2))

    return int(dataStr, 10)

