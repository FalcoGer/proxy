# The core parser contains the core functionality of the CLI
# Only commands that don't require a proxy are ran in here.
# This is the base class for BaseParser, which in turn is the base class for custom parsers

# will be default in python 3.11.
# This is required for there to be no errors in the type hints.
from __future__ import annotations
import typing

# struct is used to decode bytes into primitive data types
# https://docs.python.org/3/library/struct.html
import struct
import os
from enum import Enum, auto
from copy import copy
from prompt_toolkit import print_formatted_text as print

from eSocketRole import ESocketRole
from completer import CustomCompleter

# For type hints only
if typing.TYPE_CHECKING:
    from proxy import Proxy
    from application import Application
    from buffer_status import BufferStatus
    CommandDictType = dict[
            str, # Key (command name)
            typing.Tuple[ # Value
                typing.Callable[[list[str], Proxy], typing.Union[str, int]], # Command callback
                str, # Help text
                typing.Iterable[typing.Callable[[BufferStatus], typing.NoReturn]] # Completer functions
            ]
        ]

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
        raise ValueError('Can not compare.')

    def __hash__(self):
        return self.value.__hash__()

class Parser():
    def __str__(self) -> str:
        return 'CORE'

    def __init__(self, application: Application, settings: dict[(Enum, typing.Any)]):
        self.application = application
        self.completer = CustomCompleter(application, self)
        self.commandDictionary: CommandDictType = self._buildCommandDict()

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

    def getDefaultSettings(self) -> dict[(Enum, typing.Any)]:
        return {
        }

    def getSetting(self, settingKey: Enum) -> typing.Any:
        if settingKey not in self.getSettingKeys():
            raise IndexError(f'Setting Key {settingKey} was not found.')
        settingValue = self.settings.get(settingKey, None)
        if settingValue is None:
            # This should throw is the key is not in the default settings.
            settingValue = self.getDefaultSettings().get(settingKey, None)
            self.settings[settingKey] = settingValue
        return settingValue

    def setSetting(self, settingKey: Enum, settingValue: typing.Any) -> typing.NoReturn:
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
    def _buildCommandDict(self) -> CommandDictType:
        proxySelectionNote = 'Note: Proxy may be selected by ID, LocalPort or it\'s name.\nThe ID has preference over LocalPort.'

        ret = {}
        ret['help']         = (self._cmd_help, 'Print available commands. Or the help of a specific command.\nUsage: {0} [command]', [self._commandCompleter, None])
        ret['quit']         = (self._cmd_quit, 'Stop the proxy and quit.\nUsage: {0}', None)
        ret['select']       = (self._cmd_select, f'Select a different proxy to give commands to.\nUsage: {{0}} <Proxy>\n{proxySelectionNote}', [self._proxyNameCompleter, None])
        ret['deselect']     = (self._cmd_deselect, 'Deselect the currently selected proxy.\nUsage: {0}', None)
        ret['new']          = (self._cmd_new, 'Create a new proxy.\nUsage: {0} <LocalPort> <RemotePort> <host> [<ProxyName>] [<ParserModule>]', [None, None, None, None, self._parserNameCompleter, None])
        ret['kill']         = (self._cmd_kill, f'Stop a proxy.\nUsage: {{0}} [<Proxy>]\nIf Proxy is omitted, this kills the currently selected proxy.\n{proxySelectionNote}', [self._proxyNameCompleter])
        ret['rename']       = (self._cmd_rename, f'Rename a proxy.\nUsage: {{0}} [<Proxy>] <NewName>\nIf Proxy is omitted, this renames the currently selected proxy.\n{proxySelectionNote}', [self._proxyNameCompleter, None, None])
        ret['disconnect']   = (self._cmd_disconnect, f'Disconnect from the client and server.\nUsage: {{0}} [<Proxy>]\n{proxySelectionNote}', [self._proxyNameCompleter, None])
        ret['loadparser']   = (self._cmd_loadparser, f'Load a custom parser for proxy.\nUsage: {{0}} [<Proxy>] <ParserName>\nExample: {{0}} PROXY_8080 example_parser\nIf Proxy is omitted, this changes the parser of the currently selected proxy.\n{proxySelectionNote}', [self._proxyNameCompleter, self._parserNameCompleter, None])
        ret['lsproxy']      = (self._cmd_lsproxy, 'Display all configured proxies and their status.\nUsage: {0}', None)
        ret['run']          = (self._cmd_run, 'Runs a script file.\nUsage: {0} <FilePath> [<LineNumber>]\nIf line number is given, the script will start execution on that line.\nLines starting with "#" will be ignored.', [self._fileCompleter, None, None])
        ret['clearhistory'] = (self._cmd_clearhistory, 'Clear the command history or delete one entry of it.\nUsage: {0} [<HistoryIndex>].\nNote: The history file will written only on exit.', None)
        ret['lshistory']    = (self._cmd_lshistory, 'Show the command history or display one entry of it.\nUsage: {0} [<HistoryIndex>]', None)
        ret['lssetting']    = (self._cmd_lssetting, 'Show the current settings or display a specific setting.\nUsage: {0} [<SettingName>]', [self._settingsCompleter, None])
        ret['set']          = (self._cmd_set, 'Sets variable to a value\nUsage: {0} <VariableName> <Value>\nExample: {0} httpGet GET / HTTP/1.0\\n', [self._variableCompleter, None])
        ret['unset']        = (self._cmd_unset, 'Deletes a variable.\nUsage: {0} <VariableName>\nExample: {0} httpGet', [self._variableCompleter, None])
        ret['lsvars']       = (self._cmd_lsvars, 'Lists variables.\nUsage: {0} [<VariableName>]\nExample: {0}\nExample: {0} httpGet', [self._variableCompleter, None])
        ret['savevars']     = (self._cmd_savevars, 'Saves variables to a file.\nUsage: {0} <FilePath>', [self._fileCompleter, None])
        ret['loadvars']     = (self._cmd_loadvars, 'Loads variables from a file\nUsage: {0} <FilePath>\nNote: Existing variables will be retained.', [self._fileCompleter, None])
        ret['clearvars']    = (self._cmd_clearvars, 'Clears variables.\nUsage: {0}', None)
        ret['pack']         = (self._cmd_pack, 'Packs data into a different format.\nUsage: {0} <DataType> <Format> <Data> [<Data> ...]\nNote: Data is separated by spaces.\nExample: {0} int little_endian 255 0377 0xFF\nExample: {0} byte little_endian 41 42 43 44\nExample: {0} uchar little_endian x41 x42 x43 x44\nRef: https://docs.python.org/3/library/struct.html\nNote: Use auto-complete.', [self._packDataTypeCompleter, self._packFormatCompleter, None])
        ret['unpack']       = (self._cmd_unpack, 'Unpacks and displays data from a different format.\nUsage: {0} <DataType> <Format> <HexData>\nNote: Hex data may contain spaces, they are ignored.\nExample: {0} int little_endian 01000000 02000000\nExample: {0} c_string native 41424344\nRef: https://docs.python.org/3/library/struct.html\nNote: Use auto-complete.', [self._packDataTypeCompleter, self._packFormatCompleter, None])
        ret['convert']      = (self._cmd_convert, 'Converts numbers from one type to all others.\nUsage: {0} [<SourceFormat>] <Number>\nExample: {0} dec 65\nExample: {0} 0x41\nNote: If source format is not specified, it will be derrived from the format of the number itself.', [self._convertTypeCompleter, None, None])

        # Aliases
        ret['exit']         = ret['quit']
        ret['lsp']          = ret['lsproxy']
        ret['lss']          = ret['lssetting']

        ret['lsh']          = ret['lshistory']
        ret['clh']          = ret['clearhistory']
        
        ret['lsv']          = ret['lsvars']
        ret['clv']          = ret['clearvars']
        
        return ret

    def _cmd_help(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        # If user wanted help for a specific command
        if len(args) == 2 and args[1] in self.commandDictionary:
            print(self.getHelpText(args[1]))
            return 0
        
        if len(args) == 2:
            return f'No such command: {args[1]}.'
        
        # Print
        # Find the longest key for neat formatting.
        maxLen = max(len(key) for key in self.commandDictionary)
        termColumns = os.get_terminal_size().columns
        SPACES_BETWEEN_CMDS = 3
        maxLen += SPACES_BETWEEN_CMDS
        maxCmdsPerLine = max([int(termColumns / maxLen), 1])
        print() # Make some space.
        for idx, cmdname in enumerate(self.commandDictionary):
            print(f'{cmdname.ljust(maxLen)}', end=('' if (idx + 1) % maxCmdsPerLine != 0 else '\n'))
        
        print('\n\nUse "help <cmdName>" to find out more about how to use a command.')
        # Print general CLI help also
        print('Prompt toolkit extensions are available.')
        print('  Use TAB for auto completion')
        print('  Use CTRL+R for history search.')
        print('More CLI features are available:')
        print('  Use !idx to execute a command from the history again.')
        print('  Use $varname to expand variables.')
        print('  To use a literal ! or $ use \\! and \\$ respectively.')
        print('  Where numbers are required, they may be prefixed:\n    - x or 0x for hex\n    - 0, o or 0o for octal\n    - b or 0b for binary\n    - No prefix for decimal.')
        return 0

    def _cmd_disconnect(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        if len(args) not in [1, 2]:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        proxyToDisconnect = proxy
        if len(args) == 2:
            try:
                proxyToDisconnect = self._aux_get_proxy_by_arg(args[1])
            except (IndexError, KeyError) as e:
                return f'Could not find proxy by {args[1]}: {e}'
        elif proxyToDisconnect is None:
            print(self.getHelpText(args[0]))
            return 'No proxy selected.'

        if not proxyToDisconnect.getIsConnected():
            return 'Not connected.'

        proxyToDisconnect.disconnect()
        return 0

    def _cmd_select(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        try:
            proxy: Proxy = self._aux_get_proxy_by_arg(args[1])
            self.application.selectProxy(proxy)
        except (IndexError, KeyError) as e:
            return f'Unable to select proxy {args[1]}: {e}'
        
        return 0

    def _cmd_deselect(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 1:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        self.application.selectProxy(None)
        return 0

    def _cmd_new(self, args: list[str], _) -> typing.Union[int, str]:
        # args: lp rp host [proxyname] [parsername]
        if len(args) not in [4, 5, 6]:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        try:
            lp = self._strToInt(args[1])
        except ValueError as e:
            return f'Could not convert {args[1]} into a number: {e}'
        
        try:
            rp = self._strToInt(args[2])
        except ValueError as e:
            return f'Could not convert {args[2]} into a number: {e}'
        
        host = args[3]
        name = f'PROXY_{lp}'
        parserName = self.application.DEFAULT_PARSER_MODULE
        if len(args) >= 5:
            name = args[4]
        if len(args) >= 6:
            parserName = args[5]
        
        try:
            self.application.createProxy(name, lp, rp, host)
        except (ValueError, KeyError) as e:
            return f'Bad name: {e}'
        except OSError as e:
            return f'Could not create proxy: {e}'

        try:
            self.application.setParserForProxyByName(name, parserName)
        except ImportError as e:
            return f'Could not set parser {repr(parserName)} for {name}: {e}'

        return 0

    def _cmd_kill(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        if len(args) not in [1, 2]:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        proxyToKill = proxy
        if len(args) == 2:
            try:
                proxyToKill = self._aux_get_proxy_by_arg(args[1])
            except (IndexError, KeyError) as e:
                return f'Could not select proxy by {args[1]}: {e}'
        elif proxyToKill is None:
            print(self.getHelpText(args[0]))
            return 'No proxy selected.'
        
        print(f'Shutting down {proxyToKill}.')
        print(f'This can take up to {proxyToKill.BIND_SOCKET_TIMEOUT} seconds.')
        self.application.killProxy(proxyToKill)
        
        return 0

    def _cmd_rename(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        # args: [proxy], newName
        if len(args) not in [2, 3]:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        proxyToRename = proxy
        if len(args) == 3:
            try:
                proxyToRename = self._aux_get_proxy_by_arg(args[1])
            except (KeyError, IndexError) as e:
                return f'Could not select proxy by {args[1]}: {e}'
        elif proxyToRename is None:
            print(self.getHelpText(args[0]))
            return 'No proxy selected.'
        try:
            self.application.renameProxy(proxyToRename, args[-1])
        except (ValueError, KeyError) as e:
            return f'Could not rename proxy to {args[-1]}: {e}'

        return 0
    
    def _aux_get_proxy_by_arg(self, arg: str) -> Proxy:
        try:
            num = self._strToInt(arg) # Raises ValueError
            return self.application.getProxyByNumber(num) # Raises IndexError
        except ValueError:
            # Failed to convert to a number
            pass
        return self.application.getProxyByName(arg) # Raises KeyError

    def _cmd_loadparser(self, args: list[str], proxy: Proxy) -> typing.Union[int, str]:
        # args: [proxy], newParser
        if len(args) not in [2, 3]:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        parserName = args[-1]
        try:
            proxyToReloadParser = proxy
            if len(args) == 3:
                proxyToReloadParser = self._aux_get_proxy_by_arg(args[1])
            elif proxyToReloadParser is None:
                print(self.getHelpText(args[0]))
                return 'No proxy selected.'
            self.application.setParserForProxy(proxyToReloadParser, parserName)
        except ImportError as e:
            return f'Could not load {parserName}: {e}'
        except KeyError as e:
            return f'Could not find proxy by {args[1]}: {e}'
            
        return 0

    def _cmd_lsproxy(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 1:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        for idx, proxy in enumerate(self.application.getProxyList()):
            parser = self.application.getParserByProxy(proxy)
            print(f'[{idx}] - {proxy} ({parser})')
        return 0

    def _cmd_run(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 3:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        # args: file, [linenr]
        filePath = ' '.join(args[1:])
        firstTryPath = filePath
        lineNr = 1
        if not os.path.exists(filePath):
            filePath = ' '.join(args[1:-1])
            lineNr = self._strToInt(args[-1])
            try:
                if lineNr <= 0:
                    print(self.getHelpText(args[0]))
                    raise ValueError('Line number can not be <=0 but was {lineNr}.')
            except ValueError as e:
                return f'Syntax error: {e}'
        if not os.path.exists(filePath):
            return f'Could not locate {repr(firstTryPath)} or {repr(filePath)}.'
        
        with open(filePath, 'rt', encoding='utf-8') as file:
            # pop lineNr lines off the buffer
            for x in range(1, lineNr):
                line = file.readline()
                if line is None:
                    return f'File reached EOF before {lineNr} at line {x}.'

            while line := file.readline():
                # strip leading spaces and trailing new line
                cmdToExecute = line.lstrip()[:-1]
                
                # Expand variable names
                try:
                    cmdToExecute = self.application.expandVariableCommand(cmdToExecute)
                except KeyError as e:
                    return f'Error during variable expansion at line {lineNr} in {repr(filePath)}: {e}'
                
                # execute command
                try:
                    cmdReturn = self.application.runCommand(cmdToExecute)
                except RecursionError as e:
                    return f'Called self too many times at {lineNr} in {repr(filePath)}: {e}'
                if cmdReturn != 0:
                    return f'Error: {cmdReturn} at line {lineNr} in {repr(filePath)}.'
                lineNr += 1
        return 0

    def _cmd_quit(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 1:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        self.application.stop()
        return 0

    def _cmd_lshistory(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        if len(args) == 2:
            try:
                idx = self._strToInt(args[1])
            except ValueError as e:
                print(self.getHelpText(args[0]))
                return f'Syntax error: {e}'

            try:
                historyLine = self.application.getHistoryItem(idx)
                print(f'{idx} - {repr(historyLine)}')
                return 0
            except IndexError as e:
                return f'Invalid history index {idx}: {e}'
        
        # Print them all.
        for idx, historyLine in enumerate(self.application.getHistoryList()):
            if historyLine is None:
                continue
            print(f'{idx} - {repr(historyLine)}')
        return 0

    def _cmd_clearhistory(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        if len(args) == 2:
            try:
                idx = self._strToInt(args[1])
            except ValueError as e:
                print(self.getHelpText(args[0]))
                return f'Syntax error: {e}'

            try:
                historyLine = self.application.getHistoryItem(idx)
                self.application.deleteHistoryItem(idx)
                print(f'Item {idx} deleted: {historyLine}')
                return 0
            except IndexError as e:
                return f'Invalid history index {idx}: {e}'
        else:
            self.application.clearHistory()
            print('History deleted.')
        return 0

    def _cmd_lssetting(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        if len(args) == 2:
            if len(args[1]) == 0:
                print(self.getHelpText(args[0]))
                return 'Syntax error'
            if not args[1] in [x.name for x in self.getSettingKeys()]:
                return f'{args[1]} is not a valid setting.'
            
            settingKey = None
            for settingKey in self.getSettingKeys():
                if settingKey.name == args[1]:
                    break
            value = self.getSetting(settingKey)
            print(f'{settingKey.name}: {value}')
            return 0
        
        if len(self.getSettingKeys()) == 0:
            print('There are no settings for this parser.')
            return 0

        # Print them all
        longestKeyLength = max(len(str(x)) for x in self.getSettingKeys())

        for key in self.getSettingKeys():
            keyNameStr = str(key).rjust(longestKeyLength)
            value = self.getSetting(key)
            print(f'{keyNameStr}: {value}')
        return 0

    def _cmd_set(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) < 3:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        varName = args[1]
        if len(varName) == 0:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        # variable values may have spaces in them.
        varValue = ' '.join(args[2:])
        self.application.setVariable(varName, varValue)
        return 0

    def _cmd_unset(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        if self.application.unsetVariable(args[1]):
            print(f'Deleted variable {args[1]}')
        else:
            return f'Variable {args[1]} doesn\'t exist.'
        return 0

    def _cmd_lsvars(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) > 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'

        # Print specific variable
        if len(args) == 2:
            varName = args[1]
            if varName in self.application.getVariableNames():
                varValue = self.application.getVariable(varName)
                print(f'{varName} - {repr(varValue)}')
            else:
                return f'{varName} is not defined.'
            return 0
        
        variableNames = self.application.getVariableNames()
        if len(variableNames) == 0:
            print('No variables defined.')
            return 0

        # print all variables
        maxVarNameLength = max(len(varName) for varName in self.application.getVariableNames())

        for varName in variableNames:
            varValue = self.application.getVariable(varName)
            print(f'{varName.rjust(maxVarNameLength)} - {repr(varValue)}')
        return 0

    def _cmd_savevars(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        filePath = ' '.join(args[1:])
        try:
            with open(filePath, 'wt', encoding='utf-8') as file:
                for varName in self.application.variables.keys():
                    varValue = self.application.getVariable(varName)
                    file.write(f'{varName} {varValue}\n')
        except (IsADirectoryError, PermissionError, FileNotFoundError) as e:
            return f'Error writing file {repr(filePath)}: {e}'

        return 0

    def _cmd_loadvars(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) != 2:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        filePath = ' '.join(args[1:])
        try:
            loadedVars = {}
            with open(filePath, 'rt', encoding='utf-8') as file:
                lineNumber = 0
                for line in file.readlines():
                    line = line.strip('\n')
                    lineNumber += 1
                    if len(line.strip()) == 0:
                        # skip empty lines
                        continue

                    try:
                        if len(line.split(' ')) <= 1:
                            raise ValueError('Line does not contain a variable-value pair.')

                        varName = line.split(' ')[0]
                        if not self.application.checkVariableName(varName):
                            raise ValueError(f'Bad variable name: {repr(varName)}')

                        varValue = ' '.join(line.split(' ')[1:])
                        if len(varValue) == 0:
                            raise ValueError('Variable value is empty.')

                        if varName in loadedVars:
                            raise KeyError(f'Variable {repr(varName)} already loaded from this file.')

                        loadedVars[varName] = varValue
                    except (ValueError, KeyError) as e:
                        return f'Line {lineNumber} {repr(line)}, could not extract variable from file {repr(filePath)}: {e}'
            
            # Everything loaded successfully
            for kvp in loadedVars.items():
                self.application.setVariable(kvp[0], kvp[1])
            print(f'{len(loadedVars)} variables loaded successfully.')
        except (IsADirectoryError, PermissionError, FileNotFoundError) as e:
            return f'Error reading file {repr(filePath)}: {e}'

        return 0

    def _cmd_clearvars(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) != 1:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        self.application.clearVariables()
        print('All variables deleted.')
        return 0

    def _cmd_pack(self, args: list[str], _) -> typing.Union[int, str]:
        # FIXME: cstring and pascal string not working correctly.
        if len(args) < 4:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        formatMapping = self._aux_pack_getFormatMapping()
        dataTypeMapping = self._aux_pack_getDataTypeMapping()

        dataCount = len(args) - 3 # Data is separated by spaces

        dataTypeMappingString = args[1]
        if dataTypeMappingString not in dataTypeMapping:
            return f'Syntax error. Data type {dataTypeMappingString} unknown, must be one of {dataTypeMapping.keys()}.'
        
        formatMappingString = args[2]
        if formatMappingString not in formatMapping:
            return f'Syntax error. Format {formatMappingString} unknown, must be one of {formatMapping.keys()}.'
        
        if dataTypeMapping[dataTypeMappingString] in ['n', 'N'] and formatMapping[formatMappingString] != formatMapping['native']:
            return f'format for data type {dataTypeMappingString} must be native (@).'

        formatString = f'{formatMapping[formatMappingString]}{dataCount}{dataTypeMapping[dataTypeMappingString]}'
        
        dataStrArray = args[3:]
        # Convert data according to the format
        convertedData = []
        for dataStr in dataStrArray:
            data = self._aux_pack_convert(dataTypeMapping[dataTypeMappingString], dataStr)
            convertedData.append(data)
        try:
            packedValues = struct.pack(formatString, *convertedData)
        except struct.error as e:
            return f'Unable to pack {convertedData} with format {formatString}: {e}'
        
        print(f'Packed: {packedValues}')
        asHex = ''
        for byte in packedValues:
            asHex += f'{byte:02X}'
        print(f'Hex: {asHex}')
        return 0

    def _cmd_unpack(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) < 4:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
        formatMapping = self._aux_pack_getFormatMapping()
        dataTypeMapping = self._aux_pack_getDataTypeMapping()
        
        dataTypeMappingString = args[1]
        if dataTypeMappingString not in dataTypeMapping:
            return f'Syntax error. Data type {dataTypeMappingString} unknown, must be one of {dataTypeMapping.keys()}.'
        
        formatMappingString = args[2]
        if formatMappingString not in formatMapping:
            return f'Syntax error. Format {formatMappingString} unknown, must be one of {formatMapping.keys()}.'
        
        if dataTypeMapping[dataTypeMappingString] in ['n', 'N'] and formatMapping[formatMappingString] != formatMapping['native']:
            return f'format for data type {dataTypeMappingString} must be native (@).'
        
        hexDataStr = ''.join(args[3:]) # Joining on '' eliminates spaces.
        byteArray = bytes.fromhex(hexDataStr)
        
        # calculate how many values we have
        dataTypeSize = struct.calcsize(f'{formatMapping[formatMappingString]}{dataTypeMapping[dataTypeMappingString]}')
        if len(byteArray) % dataTypeSize != 0:
            return f'Expecting a multiple of {dataTypeSize} Bytes, which is the size of type {dataTypeMappingString}, but got {len(byteArray)} Bytes in {byteArray}'
        dataCount = int(len(byteArray) / dataTypeSize)

        formatString = f'{formatMapping[formatMappingString]}{dataCount}{dataTypeMapping[dataTypeMappingString]}'

        try:
            unpackedValues = struct.unpack(formatString, byteArray)
        except struct.error as e:
            return f'Unable to unpack {byteArray} with format {formatString}: {e}'
        
        print(f'Unpacked: {unpackedValues}')
        return 0

    # Converts the string data from the user's input into the correct data type for struct.pack
    def _aux_pack_convert(self, dataTypeString: str, dataStr: str) -> typing.Union[bytes, int, float]:
        if dataTypeString in ['c', 's', 'p']:
            # byte array formats
            return bytes.fromhex(dataStr)
        if dataTypeString in ['b', 'B', 'h', 'H', 'i', 'I', 'l', 'L', 'q', 'Q', 'n', 'N', 'P']:
            # integer formats
            return self._strToInt(dataStr)
        if dataTypeString in ['e', 'f', 'd']:
            # float formats
            return float(dataStr)
        raise ValueError(f'Format string {dataTypeString} unknown.')

    def _aux_pack_getFormatMapping(self) -> dict[str, str]:
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

    def _aux_pack_getDataTypeMapping(self) -> dict[str, str]:
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

    def _cmd_convert(self, args: list[str], _) -> typing.Union[int, str]:
        if len(args) not in [2, 3]:
            print(self.getHelpText(args[0]))
            return 'Syntax error.'
        
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
                    raise ValueError('Unknown format string {formatString}')
            except ValueError as e:
                return f'Can\'t convert {numberString} as {formatString} to number: {e}'
        else:
            numberString = args[1]
            number = self._strToInt(numberString)
        
        # Also get a byte array out of it.
        hexString = f'{number:2X}'
        if len(hexString) % 2 == 1:
            hexString = '0' + hexString
        byteArray = bytes.fromhex(hexString)
        
        # print the number
        print(f'DEC: {number}\nHEX: {hex(number)}\nOCT: {oct(number)}\nBIN: {bin(number)}\nBytes: {byteArray}')
        return 0

    ###############################################################################
    # Completers go here.

    def _convertTypeCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        options = ['dec', 'bin', 'oct', 'hex']
        for option in options:
            if option.startswith(bufferStatus.being_completed):
                self.completer.candidates.append(option)
        return

    def _packDataTypeCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        options = self._aux_pack_getDataTypeMapping().keys()
        for option in options:
            if option.startswith(bufferStatus.being_completed):
                self.completer.candidates.append(option)
        return

    def _packFormatCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        formatMapping = self._aux_pack_getFormatMapping()
        dataTypeMapping = self._aux_pack_getDataTypeMapping()
        # 'n' and 'N' only available in native.
        nativeOnlyList = list(filter(lambda x: dataTypeMapping[x] in ['n', 'N'], dataTypeMapping.keys()))
        
        if bufferStatus.words[1] in nativeOnlyList:
            self.completer.candidates.append('native')
            # '@' also valid, but omit for quicker typing.
            # self.completer.candidates.append('@')
            return
        
        # Return all available options
        options = formatMapping.keys()
        for option in options:
            if option.startswith(bufferStatus.being_completed):
                self.completer.candidates.append(option)
        return

    def _commandCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        self.completer.candidates.extend( [
                s
                for s in self.commandDictionary
                if s and s.startswith(bufferStatus.being_completed)
            ]
        )
        return

    def _fileCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        # FIXME: fix completion for paths with spaces

        # Append candidates for files
        # Find which word we are current completing
        # This is the space separated word, being_completed would start at the last '/'

        # Find which directory we are in
        directory = os.curdir + '/'
        filenameStart = ''
        word = bufferStatus.words[bufferStatus.wordIdx]
        if word:
            # There is at least some text being completed.
            if word.find('/') >= 0:
                # There is a path delimiter in the string, we need to assign the directory and the filename start both.
                directory = word[:word.rfind('/')] + '/'
                filenameStart = word[word.rfind('/') + 1:]
            else:
                # There is no path delimiters in the string. We're only searching the current directory for the file name.
                filenameStart = word

        # Find all files and directories in that directory
        if os.path.isdir(directory):
            files = os.listdir(directory)
            # Find which of those files matches the end of the path
            for file in files:
                if os.path.isdir(os.path.join(directory, file)):
                    file += '/'
                if file.startswith(filenameStart):
                    self.completer.candidates.append(file)
        return

    def _settingsCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        for settingName in [x.name for x in self.getSettingKeys()]:
            if settingName.startswith(bufferStatus.being_completed):
                self.completer.candidates.append(settingName)
        return

    def _variableCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        self.completer.getVariableCandidates(False, bufferStatus)
        return

    def _proxyNameCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        # Find listening port numbers only if we started with a number.
        if len(bufferStatus.being_completed) > 0 and ord(bufferStatus.being_completed[0]) in range(ord('0'), ord('9') + 1):
            for proxy in self.application.getProxyList():
                _, lp = proxy.getBind()
                if str(lp).startswith(bufferStatus.being_completed):
                    self.completer.candidates.append(str(lp))
            return
        
        # Find Names otherwise. (Names can't start with a number)
        for proxy in self.application.getProxyList():
            if proxy.name.startswith(bufferStatus.being_completed):
                self.completer.candidates.append(proxy.name)
        return

    def _parserNameCompleter(self, bufferStatus: BufferStatus) -> typing.NoReturn:
        FILE_SIZE_LIMIT_FOR_CHECK = 50 * (2 ** 10) # 50 KiB
        # find all files in directory
        for fileName in os.listdir(os.curdir):
            isCandidate = False
            try:
                if not fileName.startswith(bufferStatus.being_completed):
                    # Skip filenames that don't match.
                    continue

                if not fileName.endswith('.py'):
                    # Skip non python modules
                    continue
                
                if os.path.getsize(fileName) > FILE_SIZE_LIMIT_FOR_CHECK:
                    # Skip files that are too large to check
                    continue

                with open(fileName, 'rt', encoding='utf-8') as file:
                    # Find the 'class Parser(' string in the file
                    # Need to do it in steps because there may be any number of whitespaces
                    while line := file.readline():
                        line = line.strip()
                        if not line.startswith('class'):
                            continue
                        line = line[len('class'):].strip()
                        if not line.startswith('Parser'):
                            continue
                        line = line[len('Parser'):].strip()
                        if not line.startswith('('):
                            continue
                        isCandidate = True
                        break
            except (IOError, PermissionError, IsADirectoryError):
                continue
            
            if not isCandidate:
                # Check next file
                continue
            
            self.completer.candidates.append(fileName[:-3])
        return

    ###############################################################################
    # No need to edit the functions below

    def parse(self, data: bytes, proxy: Proxy, origin: ESocketRole) -> list[str]:
        raise RuntimeError('Core parser is not meant to parse packets. Use derived parser instead.')

    # This function take the command line string and calls the relevant python function with the correct arguments.
    def handleUserInput(self, userInput: str, proxy: Proxy) -> typing.Union[int, str]:
        args = userInput.split(' ')

        if len(userInput.strip()) == 0:
            # Ignore empty commands
            return 0
        
        if args[0] not in self.commandDictionary:
            return f'Undefined command: {repr(args[0])}'

        function, _, _ = self.commandDictionary[args[0]]
        return function(args, proxy)

    def getHelpText(self, cmdString: str) -> str:
        _, helpText, _ = self.commandDictionary[cmdString]
        try:
            return helpText.format(cmdString)
        except ValueError as e:
            print(f'Unable to format helptext {repr(helpText)}: {e}')
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
                    raise Exception('\\uxxxx is not supported')
                elif nextByte == b'U':
                    raise Exception('\\Uxxxxxxxx is not supported')
                elif nextByte == b'N':
                    raise Exception('\\N{Name} is not supported')
                else:
                    raise ValueError(f'Invalid escape sequence at index {idx} in {data}: \\{repr(nextByte)[2:-1]}')
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

