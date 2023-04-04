# The core parser contains the core functionality of the CLI
# Only commands that don't require a proxy are ran in here.
# This is the base class for BaseParser, which in turn is the base class for custom parsers

# struct is used to decode bytes into primitive data types
# https://docs.python.org/3/library/struct.html
import struct
import os
from enum import Enum, auto
from copy import copy

from completer import Completer

###############################################################################
# Setting storage stuff goes here.

class ECoreSettingKey(Enum):
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

class CoreParser():
    def __init__(self, application, settings: dict[(Enum, object)]):
        self.application = application
        self.completer = Completer(application, self)
        self.commandDictionary = self.buildCommandDict()

        # Populate settings
        self.settings = settings
        # If a setting is not set, it shall be set now
        for settingKey in self.getSettingKeys():
            if settingKey not in self.settings:
                self.settings[settingKey] = self.getDefaultSettings()[settingKey]
        # Remove any settings that are no longer in the list
        for settingKey in list(filter(lambda settingKey: settingKey not in self.getSettingKeys(), self.settings.keys())):
            self.settings.pop(settingKey) 

    def getSettingKeys(self) -> list[Enum]:
        return list(ECoreSettingKey)

    def getDefaultSettings(self) -> dict[(Enum, object)]:
        return {
        }

    def getSetting(self, settingKey: Enum) -> object:
        if settingKey not in self.getSettingKeys():
            raise IndexError(f'Setting Key {settingKey} was not found.')
        settingValue = self.settings.get(settingKey, None)
        if settingValue is None:
            # This should throw is the key is not in the default settings.
            settingValue = self.getDefaultSettings().get(settingKey, None)
            self.settings[settingKey] = settingValue
        return settingValue

    def setSetting(self, settingKey: Enum, settingValue: object) -> None:
        if settingKey not in self.getSettingKeys():
            raise IndexError(f'Setting Key {settingKey} was not found.')
        self.settings[settingKey] = settingValue
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
        ret = {}
        ret['help']         = (self._cmd_help, 'Print available commands. Or the help of a specific command.\nUsage: {0} [command]', [self._commandCompleter, None])
        ret['quit']         = (self._cmd_quit, 'Stop the proxy and quit.\nUsage: {0}', None)
        ret['select']       = (self._cmd_select, 'Select a different proxy to give commands to.\nUsage: {0} ID\nNote: Use \"lsproxy\" to figure out the ID.', [self._proxyNameCompleter, None])
        ret['lsproxy']      = (self._cmd_lsproxy, 'Display all configured proxies and their status.\nUsage: {0}', None)
        ret['clearhistory'] = (self._cmd_clearhistory, 'Clear the command history or delete one entry of it.\nUsage: {0} [historyIndex].\nNote: The history file will instantly be overwritten.', None)
        ret['lshistory']    = (self._cmd_lshistory, 'Show the command history or display one entry of it.\nUsage: {0} [historyIndex]', None)
        ret['lssetting']    = (self._cmd_lssetting, 'Show the current settings or display a specific setting.\nUsage: {0} [settingName]', [self._settingsCompleter, None])
        ret['set']          = (self._cmd_set, 'Sets variable to a value\nUsage: {0} varname value\nExample: {0} httpGet GET / HTTP/1.0\\n', [self._variableCompleter, self._historyCompleter])
        ret['unset']        = (self._cmd_unset, 'Deletes a variable.\nUsage: {0} varname\nExample: {0} httpGet', [self._variableCompleter, None])
        ret['lsvars']        = (self._cmd_lsvars, 'Lists variables.\nUsage: {0} [varname]\nExample: {0}\nExample: {0} httpGet', [self._variableCompleter, None])
        ret['savevars']     = (self._cmd_savevars, 'Saves variables to a file.\nUsage: {0} filepath', [self._fileCompleter, None])
        ret['loadvars']     = (self._cmd_loadvars, 'Loads variables from a file\nUsage: {0} filename\nNote: Existing variables will be retained.\nUse clearvars before loading if you want the variables from that file only.', [self._fileCompleter, None])
        ret['clearvars']    = (self._cmd_clearvars, 'Clears variables.\nUsage: {0}', None)
        ret['pack']         = (self._cmd_pack, 'Packs data into a different format.\nUsage: {0} datatype format data [...]\nNote: Data is separated by spaces.\nExample: {0} int little_endian 255 0377 0xFF\nExample: {0} byte little_endian 41 42 43 44\nExample: {0} uchar little_endian x41 x42 x43 x44\nRef: https://docs.python.org/3/library/struct.html', [self._packDataTypeCompleter, self._packFormatCompleter, self._historyCompleter])
        ret['unpack']       = (self._cmd_unpack, 'Unpacks and displays data from a different format.\nUsage: {0} datatype format hexdata\nNote: Hex data may contain spaces, they are ignored.\nExample: {0} int little_endian 01000000 02000000\nExample: {0} c_string native 41424344\nRef: https://docs.python.org/3/library/struct.html', [self._packDataTypeCompleter, self._packFormatCompleter, self._historyCompleter])
        ret['convert']      = (self._cmd_convert, 'Converts numbers from one type to all others.\nUsage: {0} [sourceFormat] number\nExample: {0} dec 65\nExample: {0} 0x41', [self._convertTypeCompleter, self._historyCompleter, None])

        # Aliases
        ret['exit']         = ret['quit']
        ret['lsp']          = ret['lsproxy']
        ret['lss']          = ret['lssetting']

        ret['lsh']          = ret['lshistory']
        ret['clh']          = ret['clearhistory']
        
        ret['lsv']          = ret['lsvars']
        ret['clv']          = ret['clearvars']
        
        return ret

    def _cmd_help(self, args: list[str], proxy) -> object:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        # If user wanted help for a specific command
        if len(args) == 2 and args[1] in self.commandDictionary:
            print(self.getHelpText(args[1]))
            return 0
        
        if len(args) == 2:
            return f"No such command: {args[1]}."
        
        # Print
        # Find the longest key for neat formatting.
        maxLen = max(len(key) for key in self.commandDictionary)

        for key in self.commandDictionary:
            helpText = self.getHelpText(key)
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

    def _cmd_select(self, args: list[str], proxy) -> object:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        
        try:
            self.application.selectProxy(args[1])
        except IndexError as e:
            return f"Unable to select proxy {args[1]}: {e}"
        
        return 0

    def _cmd_lsproxy(self, args: list[str], proxy) -> object:
        if len(args) > 1:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        idx = 0
        
        for p in self.application.proxies.values():
            print(f'[{idx}] - {p}')
            idx += 1
        return 0

    def _cmd_quit(self, args: list[str], proxy) -> object:
        if len(args) > 1:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        self.application.running = False
        return 0

    def _cmd_lshistory(self, args: list[str], proxy) -> object:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        
        readline = self.application.getReadlineModule()
        
        if len(args) == 2:
            try:
                idx = self._strToInt(args[1])
            except ValueError as e:
                print(self.getHelpText(args[0]))
                return f"Syntax error: {e}"

            if idx < readline.get_current_history_length():
                historyline = readline.get_history_item(idx)
                print(f"{idx} - \"{historyline}\"")
                return 0
            return f"Invalid history index {idx}."
        
        # Print them all.
        for idx in range(0, readline.get_current_history_length()):
            historyline = readline.get_history_item(idx)
            print(f"{idx} - \"{historyline}\"")
        return 0

    def _cmd_clearhistory(self, args: list[str], proxy) -> object:
        readline = self.application.getReadlineModule()

        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        if len(args) == 2:
            try:
                idx = self._strToInt(args[1])
            except ValueError as e:
                print(self.getHelpText(args[0]))
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
        readline.write_history_file(self.application.HISTORY_FILE)
        return 0

    def _cmd_lssetting(self, args: list[str], proxy) -> object:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        if len(args) == 2:
            if len(args[1]) == 0:
                print(self.getHelpText(args[0]))
                return "Syntax error"
            if not args[1] in [x.name for x in self.getSettingKeys()]:
                return f"{args[1]} is not a valid setting."
            
            settingKey = None
            for settingKey in self.getSettingKeys():
                if settingKey.name == args[1]:
                    break
            value = self.getSetting(settingKey)
            print(f"{settingKey.name}: {value}")
            return 0
        
        # Print them all
        longestKeyLength = max(len(str(x)) for x in self.getSettingKeys())

        for key in self.getSettingKeys():
            keyNameStr = str(key).rjust(longestKeyLength)
            value = self.getSetting(key)
            print(f"{keyNameStr}: {value}")
        return 0

    def _cmd_set(self, args: list[str], proxy) -> object:
        if len(args) < 3:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        
        varName = args[1]
        if len(varName) == 0:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        
        # variable values may have spaces in them.
        varValue = ' '.join(args[2:])
        self.application.setVariable(varName, varValue)
        return 0

    def _cmd_unset(self, args: list[str], proxy) -> object:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        if self.application.unsetVariable(args[1]):
            print(f"Deleted variable {args[1]}")
        else:
            return f"Variable {args[1]} doesn't exist."
        return 0

    def _cmd_lsvars(self, args: list[str], proxy) -> object:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."

        # Print specific variable
        if len(args) == 2:
            varName = args[1]
            if varName in self.application.variables.keys():
                varValue = self.application.getVariable(varName)
                print(f"{varName} - \"{varValue}\"")
            else:
                return f"{varName} is not defined."
            return 0

        # print all variables
        maxVarNameLength = 0
        for varName in self.application.variables.keys():
            varNameLength = len(varName)
            if varNameLength > maxVarNameLength:
                maxVarNameLength = varNameLength

        for varName in self.application.variables.keys():
            varValue = self.application.getVariable(varName)
            print(f"{varName.rjust(maxVarNameLength)} - \"{varValue}\"")
        return 0

    def _cmd_savevars(self, args: list[str], proxy) -> object:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        
        filePath = ' '.join(args[1:])
        try:
            with open(filePath, "wt") as file:
                for varName in self.application.variables.keys():
                    varValue = self.application.getVariable(varName)
                    file.write(f"{varName} {varValue}\n")
        except (IsADirectoryError, PermissionError, FileNotFoundError) as e:
            return f"Error writing file \"{filePath}\": {e}"

        return 0

    def _cmd_loadvars(self, args: list[str], proxy) -> object:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
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
                        if not self.application.checkVariableName(varName):
                            raise ValueError(f"Bad variable name: \"{varName}\"")

                        varValue = ' '.join(line.split(' ')[1:])
                        if len(varValue) == 0:
                            raise ValueError("Variable value is empty.")

                        if varName in loadedVars:
                            raise KeyError(f"Variable \"{varName}\" already loaded from this file.")

                        loadedVars[varName] = varValue
                    except (ValueError, KeyError) as e:
                        return f"Line {lineNumber} \"{line}\", could not extract variable from file \"{filePath}\": {e}"
            
            # Everything loaded successfully
            for kvp in loadedVars.items():
                self.application.setVariable(kvp[0], kvp[1])
            print(f"{len(loadedVars)} variables loaded successfully.")
        except (IsADirectoryError, PermissionError, FileNotFoundError) as e:
            return f"Error reading file \"{filePath}\": {e}"

        return 0

    def _cmd_clearvars(self, args: list[str], proxy) -> object:
        if len(args) != 1:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        self.application.variables = {}
        print("All variables deleted.")
        return 0

    def _cmd_pack(self, args: list[str], proxy) -> object:
        # FIXME: cstring and pascal string not working correctly.
        if len(args) < 4:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        
        formatMapping = self._aux_pack_getFormatMapping()
        dataTypeMapping = self._aux_pack_getDataTypeMapping()

        dataCount = len(args) - 3 # Data is separated by spaces

        dataTypeMappingString = args[1]
        if dataTypeMappingString not in dataTypeMapping:
            return f"Syntax error. Data type {dataTypeMappingString} unknown, must be one of {dataTypeMapping.keys()}."
        
        formatMappingString = args[2]
        if formatMappingString not in formatMapping:
            return f"Syntax error. Format {formatMappingString} unknown, must be one of {formatMapping.keys()}."
        
        if dataTypeMapping[dataTypeMappingString] in ['n', 'N'] and formatMapping[formatMappingString] != formatMapping['native']:
            return f"format for data type {dataTypeMappingString} must be native (@)."

        formatString = f"{formatMapping[formatMappingString]}{dataCount}{dataTypeMapping[dataTypeMappingString]}"
        
        dataStrArray = args[3:]
        # Convert data according to the format
        convertedData = []
        for dataStr in dataStrArray:
            data = self._aux_pack_convert(dataTypeMapping[dataTypeMappingString], dataStr)
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

    def _cmd_unpack(self, args: list[str], proxy) -> object:
        if len(args) < 4:
            print(self.getHelpText(args[0]))
            return "Syntax error."
        
        formatMapping = self._aux_pack_getFormatMapping()
        dataTypeMapping = self._aux_pack_getDataTypeMapping()
        
        dataTypeMappingString = args[1]
        if dataTypeMappingString not in dataTypeMapping:
            return f"Syntax error. Data type {dataTypeMappingString} unknown, must be one of {dataTypeMapping.keys()}."
        
        formatMappingString = args[2]
        if formatMappingString not in formatMapping:
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
    def _aux_pack_convert(self, dataTypeString: str, dataStr: str) -> object:
        if dataTypeString in ['c', 's', 'p']:
            # byte array formats
            return bytes.fromhex(dataStr)
        if dataTypeString in ['b', 'B', 'h', 'H', 'i', 'I', 'l', 'L', 'q', 'Q', 'n', 'N', 'P']:
            # integer formats
            return self._strToInt(dataStr)
        if dataTypeString in ['e', 'f', 'd']:
            # float formats
            return float(dataStr)
        raise ValueError(f"Format string {dataTypeString} unknown.")

    def _aux_pack_getFormatMapping(self) -> dict:
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

    def _aux_pack_getDataTypeMapping(self) -> dict:
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

    def _cmd_convert(self, args: list[str], proxy) -> object:
        if len(args) not in [2, 3]:
            print(self.getHelpText(args[0]))
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
            number = self._strToInt(numberString)
        # print the number
        print(f"DEC: {number}\nHEX: {hex(number)}\nOCT: {oct(number)}\nBIN: {bin(number)}")
        return 0

    ###############################################################################
    # Completers go here.

    def _convertTypeCompleter(self) -> None:
        options = ['dec', 'bin', 'oct', 'hex']
        for option in options:
            if option.startswith(self.completer.being_completed):
                self.completer.candidates.append(option)
        return

    def _packDataTypeCompleter(self) -> None:
        options = self.aux_pack_getDataTypeMapping().keys()
        for option in options:
            if option.startswith(self.completer.being_completed):
                self.completer.candidates.append(option)
        return

    def _packFormatCompleter(self) -> None:
        formatMapping = self.aux_pack_getFormatMapping()
        dataTypeMapping = self.aux_pack_getDataTypeMapping()
        # 'n' and 'N' only available in native.
        nativeOnlyList = list(filter(lambda x: dataTypeMapping[x] in ['n', 'N'], dataTypeMapping.keys()))
        
        if self.completer.words[1] in nativeOnlyList:
            self.completer.candidates.append('native')
            # '@' also valid, but omit for quicker typing.
            # self.completer.candidates.append('@')
            return
        
        # Return all available options
        options = formatMapping.keys()
        for option in options:
            if option.startswith(self.completer.being_completed):
                self.completer.candidates.append(option)
        return

    def _commandCompleter(self) -> None:
        self.completer.candidates.extend( [
                s
                for s in self.commandDictionary.keys()
                if s and s.startswith(self.completer.being_completed)
            ]
        )
        return

    def _fileCompleter(self) -> None:
        # FIXME: fix completion for paths with spaces

        # Append candidates for files
        # Find which word we are current completing
        # This is the space separated word, being_completed would start at the last '/'
        word = self.completer.words[self.completer.getWordIdx()]

        # Find which directory we are in
        directory = "./"
        filenameStart = ""
        if word:
            # There is at least some text being completed.
            if word.find("/") >= 0:
                # There is a path delimiter in the string, we need to assign the directory and the filename start both.
                directory = word[:word.rfind("/")] + "/"
                filenameStart = word[word.rfind("/") + 1:]
            else:
                # There is no path delimiters in the string. We're only searching the current directory for the file name.
                filenameStart = word

        # Find all files and directories in that directory
        if os.path.isdir(directory):
            files = os.listdir(directory)
            # Find which of those files matches the end of the path
            for file in files:
                if os.path.isdir(os.path.join(directory, file)):
                    file += "/"
                if file.startswith(filenameStart):
                    self.completer.candidates.append(file)
        return

    def _settingsCompleter(self) -> None:
        for settingName in [x.name for x in self.getSettingKeys()]:
            if settingName.startswith(self.completer.being_completed):
                self.completer.candidates.append(settingName)
        return

    def _variableCompleter(self) -> None:
        self.completer.getVariableCandidates(False)
        return

    def _historyCompleter(self) -> None:
        # Get candidates from the history
        history = [self.completer.readline.get_history_item(i) for i in range(0, self.completer.readline.get_current_history_length())]
        for historyline in history:
            if historyline is None or historyline == "":
                continue
            
            # Get the whole line.
            if historyline.startswith(self.completer.origline):
                # Must only append to the part that is currently being completed
                # otherwise the whole line may be added again.
                self.completer.candidates.append(historyline[self.completer.begin:])
            
        return

    def _proxyNameCompleter(self) -> None:
        for proxyName in self.application.proxies:
            if proxyName.startswith(self.completer.being_completed):
                self.completer.candidates.append(proxyName)
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
    def _escape(self, data: bytes) -> bytes:
        idx = 0
        newData = b''
        while idx < len(data):
            b = self._intToByte(data[idx])
            if b == b'\\':
                idx += 1 # Add one to the index so we don't read the escape sequence byte as a normal byte.
                nextByte = self._intToByte(data[idx]) # May throw IndexError, pass it up to the user.
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
                    newData += self._intToByte(num)
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

    def _intToByte(self, i: int) -> bytes:
        return struct.pack('=B', i)

    def _strToInt(self, dataStr: str) -> int:
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

