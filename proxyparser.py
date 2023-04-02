#/bin/python3

# struct is used to decode bytes into primitive data types
# https://docs.python.org/3/library/struct.html
import struct
from proxy import Proxy, ESocketRole, Completer
from hexdump import hexdump
from enum import Enum, auto

# TODO:
# - Add support for variables in CLI
#     ex. httpRequest=GET / HTTP/1.0\n\n
# - Add debug commands to use struct to unpack hex data and print out values to help analyzing traffic
#     ex "unpack_int_le 41000000" -> struct.unpack(">I", b'41000000') -> DEC: 65, HEX: 41, ...
# - FIXME completers

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
        directionStr = "C -> S" if origin == ESocketRole.server else "C <- S"
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
    ret['quit']         = (cmd_quit, 'Stop the proxy and quit.', None)
    ret['exit']         = ret['quit']
    ret['clhist']       = (cmd_clhist, 'Clear the command history or delete one entry of it.\nUsage: clhist [historyIndex].\nNote: The history file will instantly be overwritten.', None)
    ret['lshist']       = (cmd_lshist, 'Show the command history or display one entry of it.\nUsage: lshist [historyIndex]', None)
    ret['lssetting']    = (cmd_lssetting, 'Show the current settings or display a specific setting.\nUsage: lssetting [settingName]', [settingsCompleter, None])
    ret['disconnect']   = (cmd_disconnect, 'Disconnect from the client and server and wait for a new connection.', None)
    ret['help']         = (cmd_help, 'Print available commands. Or the help of a specific command.\nUsage: help [command]', [commandCompleter, None])
    ret['hexdump']      = (cmd_hexdump, 'Configure the hexdump or show current configuration.\nUsage: hexdump [yes|no] [bytesPerLine] [bytesPerGroup]', [yesNoCompleter, historyCompleter, historyCompleter, None])
    ret['sh']           = (cmd_sh, 'Send arbitrary hex values to the server.\nUsage: sh hexstring \nExample: sh 41424344\nNote: Spaces are allowed and ignored.', [historyCompleter])
    ret['ss']           = (cmd_ss, 'Send arbitrary strings to the server.\nUsage: ss string\nExample: ss hello!\\n\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.\nEscape sequences are available.', [historyCompleter])
    ret['sf']           = (cmd_sf, 'Send arbitrary files to the server.\nUsage: sf filename\nExample: sf /home/user/.bashrc', [fileCompleter, None])
    ret['ch']           = (cmd_ch, 'Send arbitrary hex values to the client.\nUsage: ch hexstring \nExample: ch 41424344', [historyCompleter])
    ret['cs']           = (cmd_cs, 'Send arbitrary strings to the client.\nUsage: cs string\nExample: cs hello!\\n\nNote: Leading spaces in the string are sent\nexcept for the space between the command and\nthe first character of the string.\nEscape sequences are available.', [historyCompleter])
    ret['cf']           = (cmd_cf, 'Send arbitrary files to the client.\nUsage: cf filename\nExample: cf /home/user/.bashrc', [fileCompleter, None])
    ret['set']          = (cmd_set, 'Sets variable to a value\nUsage: set varname value\nExample: set httpGet GET / HTTP/1.0\\n', [variableCompleter, historyCompleter])
    ret['unset']        = (cmd_unset, 'Deletes a variable\nUsage: "unset varname"\nExample: unset httpGet', [variableCompleter, None])
    ret['lsvar']        = (cmd_lsvar, 'Lists variables\nUsage: "lsvar [varname]"\nExample: lsvar\nExample: lsvar httpGet', [variableCompleter, None])
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
    print("  Use $varname to exapnd variables.")
    print("  To use a literal ! or $ use \\! and \\$ respectively.")
    return 0

def cmd_quit(args: list[str], proxy: Proxy) -> object:
    if len(args) > 1:
        print(getHelpText(args[0]))
        return "Syntax error."
    proxy.application.running = False
    return 0

def cmd_sh(args: list[str], proxy: Proxy) -> object:
    if len(args) == 1:
        print(getHelpText(args[0]))
        return "Syntax error."

    # Allow spaces in hex string, so join with empty string to remove them.
    userInput = ''.join(args[1:])
        
    pkt = bytes.fromhex(userInput)
    if proxy.running:
        proxy.sendToServer(pkt)
    return 0

def cmd_ss(args: list[str], proxy: Proxy) -> object:
    if len(args) == 1:
        print(getHelpText(args[0]))
        return "Syntax error."

    userInput = ' '.join(args[1:])

    pkt = str.encode(userInput, 'utf-8')
    pkt = escape(pkt)
    if proxy.running:
        proxy.sendToServer(pkt)
    return 0

def cmd_sf(args: list[str], proxy: Proxy) -> object:
    print("TODO") # TODO
    return "Not implemented"

def cmd_ch(args: list[str], proxy: Proxy) -> object:
    if len(args) == 1:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    # Allow spaces in input, so join with empty string to remove them.
    userInput = ''.join(args[1:])

    pkt = bytes.fromhex(userInput)
    if proxy.running:
        proxy.sendToClient(pkt)
    return 0

def cmd_cs(args: list[str], proxy: Proxy) -> object:
    if len(args) == 1:
        print(getHelpText(args[0]))
        return "Syntax error."

    userInput = ' '.join(args[1:])

    pkt = str.encode(userInput, 'utf-8')
    pkt = escape(pkt)
    if proxy.running:
        proxy.sendToClient(pkt)
    return 0

def cmd_cf(args: list[str], proxy: Proxy) -> object:
    print("TODO") # TODO
    return "Not implemented."

def cmd_disconnect(args: list[str], proxy: Proxy) -> object:
    if len(args) != 1:
        print(getHelpText(args[0]))
        return "Syntax error."

    if proxy.running:
        proxy.disconnect()
    else:
        return "Not connected."
    return 0

def cmd_lshist(args: list[str], proxy: Proxy) -> object:
    if len(args) > 2:
        print(getHelpText(args[0]))
        return "Syntax error."
    
    readline = proxy.application.getReadlineModule()
    
    if len(args) == 2:
        try:
            idx = int(args[1])
        except ValueError as e:
            print(getHelpText(args[0]))
            return f"Syntax error: {e}"

        if idx < readline.get_current_history_length():
            historyline = readline.get_history_item(idx)
            return f"{idx} - \"{historyline}\""
        else:
            return f"Invalid history index {idx}."
    
    # Print them all.
    for idx in range(0, readline.get_current_history_length()):
        historyline = readline.get_history_item(idx)
        print(f"{idx} - \"{historyline}\"")
    return 0

def cmd_clhist(args: list[str], proxy: Proxy) -> object:
    readline = proxy.application.getReadlineModule()

    if len(args) > 2:
        print(getHelpText(args[0]))
        return "Syntax error."

    if len(args) == 2:
        try:
            idx = int(args[1])
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
            bytesPerGroup = int(args[3])
        except ValueError as e:
            print(getHelpText(args[0]))
            return f"Syntax error: {e}"
    
    if len(args) > 2:
        try:
            bytesPerLine = int(args[2])
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

###############################################################################
# Completers go here.

def yesNoCompleter(completer: Completer) -> None:
    options = ["yes", "no"]
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
    return helpText

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

