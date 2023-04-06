#!/bin/python3

import os
import sys
import argparse
import traceback
import time
from readline_buffer_status import ReadlineBufferStatus

# This allows auto completion and history browsing
try:
    import gnureadline as readline
except ImportError:
    import readline

from proxy import Proxy
from parser_container import ParserContainer
from eSocketRole import ESocketRole

class Application():
    def __init__(self):
        self.DEFAULT_PARSER_MODULE = "passthrough_parser"
        self.START_TIME = time.time()

        self._HISTORY_FILE = "history.log" 
        self._variables: dict[(str, str)] = {}
        self._running = True
        self._selectedProxyName: str = None
        self._proxies: dict[(str, Proxy)] = {}
        self._parsers: dict[(Proxy, ParserContainer)] = {None: ParserContainer('core_parser', self)}
        
        # parse command line arguments.
        arg_parser = argparse.ArgumentParser(description='Create multiple proxy connections. Provide multiple proxy parameters to create multiple proxies.')
        arg_parser.add_argument('-b', '--bind', metavar=('binding_address'), required=False, help='Bind IP-address for the listening socket. Default \'0.0.0.0\'', default='0.0.0.0')
        arg_parser.add_argument('-p', '--proxy', nargs=3, metavar=('lp', 'rp', 'host'), action='append', required=False, help='Local port to listen on as well as the remote port and host ip address or hostname for the proxy to connect to.')

        self._args = arg_parser.parse_args()

        # Fix proxy argument Typing since nargs > 1 doesn't support multiple types such as (int, int, str)
        # REF: https://github.com/python/cpython/issues/82398
        if self._args.proxy is not None:
            try:
                for idx, proxyArgs in enumerate(self._args.proxy):
                    localPort = int(proxyArgs[0])
                    remotePort = int(proxyArgs[1])
                    remoteHost = proxyArgs[2]

                    self._args.proxy[idx] = [localPort, remotePort, remoteHost]
            except TypeError as e:
                print(f"Error: {e}")
                arg_parser.print_usage()
                raise e
        
        # Setup readline
        readline.parse_and_bind('tab: complete')
        readline.parse_and_bind('set editing-mode vi')
        readline.set_auto_history(False)
        readline.set_history_length(512)
        # allow for completion of !<histIdx> and $<varname>
        # readline.set_completer_delims(readline.get_completer_delims().replace("!", "").replace("$", ""))
        readline.set_completer_delims(' /')
        self._rbs: ReadlineBufferStatus = ReadlineBufferStatus(readline)
        # Try to load history file or create it if it doesn't exist.
        try:
            if os.path.exists(self._HISTORY_FILE):
                readline.read_history_file(self._HISTORY_FILE)
            else:
                readline.write_history_file(self._HISTORY_FILE)
        except (PermissionError, FileNotFoundError, IsADirectoryError) as e:
            print(f"Can not read or create {self._HISTORY_FILE}: {e}")

        # Create a proxies and parsers based on arguments.
        if self._args.proxy is not None:
            for idx, proxyArgs in enumerate(self._args.proxy):
                localPort = proxyArgs[0]
                remotePort = proxyArgs[1]
                remoteHost = proxyArgs[2]

                name = f'PROXY_{localPort}'
                self.createProxy(name, localPort, remotePort, remoteHost)
                # Select the first proxy
                if idx == 0:
                    self.selectProxyByName(name)
        else:
            # To initialize the completer for the core_parser
            self.selectProxy(None)
        return

    def stop(self) -> None:
        self._running = False
        return

    def main(self) -> None:
        # Accept user input and parse it.
        while self._running:
            try:
                try:
                    print() # Empty line
                    cmd = None
                    prompt = self.getPromptString()                    
                    cmd = input(f'{prompt}')
                except KeyboardInterrupt:
                    # Allow clearing the buffer with ctrl+c
                    if not readline.get_line_buffer():
                        print("Type 'exit' or 'quit' to exit.")

                if cmd is None:
                    continue

                # Expand !<histIdx>
                try:
                    historyExpandedCmd = self.expandHistoryCommand(cmd)
                except (ValueError, IndexError) as e:
                    print(f"Error during history expansion: {e}")
                    continue
                
                # Expand variable substitution
                try:
                    variableExpandedCmd = self.expandVariableCommand(historyExpandedCmd)
                except KeyError as e:
                    print(f"Error during variable expansion: {e}")
                    continue
                finally:
                    # add to the history either way.
                    self.addToHistory(historyExpandedCmd)

                escapedCmd = variableExpandedCmd.replace('\\!', '!').replace('\\$', '$') 
                
                # resolve escaped ! and $.
                if cmd != escapedCmd:
                    print(f"Expanded: {escapedCmd}")

                # Handle the command
                cmdReturn = self.getSelectedParser().handleUserInput(escapedCmd, self.getSelectedProxy())
                if cmdReturn != 0:
                    print(f"Error: {cmdReturn}")
            # pylint: disable=broad-except
            except Exception as e:
                print(f'[EXCEPT] - User Input: {e}')
                print(traceback.format_exc())
        
        # Save the history file.
        for proxy in self._proxies.values():
            proxy.shutdown()

        for proxy in self._proxies.values():
            proxy.join()
            
        readline.write_history_file(self._HISTORY_FILE)
        return

    def getPromptString(self) -> str:
        return f'[{self.getSelectedProxy()}] {self.getSelectedParser()}> '

    def addToHistory(self, command: str) -> None:
        # FIXME: For some reason history completion is not available on the last item sent.
        lastHistoryItem = readline.get_history_item(readline.get_current_history_length())
        # Add the item to the history if not already in it.
        if command != lastHistoryItem and len(command) > 0:
            # Reloading the history file doesn't seem to fix it.
            readline.add_history(command)
            readline.append_history_file(1, self._HISTORY_FILE)
        return

    def getSelectedProxy(self) -> Proxy:
        return self.getProxyByName(self._selectedProxyName)

    def getSelectedParser(self):
        proxy = self.getSelectedProxy()
        return self.getParserByProxy(proxy)

    def getProxyByName(self, name: str) -> Proxy:
        if name is None:
            return None

        return self._proxies[name]

    def getProxyByNumber(self, num: int) -> Proxy:
        # By ID
        if num < len(self._proxies):
            return list(self._proxies.values())[num]
        # ID not found, maybe port number?
        for proxy in self._proxies.values():
            if proxy.localPort == num:
                return proxy
        raise IndexError(f'No proxy found with either local port or index {num}.')

    def getProxyList(self) -> list[Proxy]:
        return list(self._proxies.values())

    def getProxyNameList(self) -> list[str]:
        return list(self._proxies)

    def getParserByProxy(self, proxy: Proxy):
        return self._parsers[proxy].getInstance()

    def getParserByProxyName(self, name: str):
        proxy = self.getProxyByName(name)
        return self.getParserByProxy(proxy)

    def setParserForProxy(self, proxy, parserName) -> None:
        newParser = ParserContainer(parserName, self)
        self._parsers[proxy] = newParser

        # Need to reload the completer if the current proxy got it's parser changed
        if proxy.name == self._selectedProxyName:
            readline.set_completer(self.getSelectedParser().completer.complete)
        return

    def setParserForProxyByName(self, proxyName, parserName) -> None:
        proxy = self.getProxyByName(proxyName)
        self.setParserForProxy(proxy, parserName)
        return

    def selectProxy(self, proxy: Proxy) -> None:
        if proxy is None:
            self._selectedProxyName = None
        else:
            self._selectedProxyName = proxy.name
        
        # reload the correct completer
        readline.set_completer(self.getSelectedParser().completer.complete)
        return

    def selectProxyByName(self, name: str) -> None:
        self.selectProxy(self.getProxyByName(name))
        return

    def selectProxyByNumber(self, num: int) -> None:
        proxy = self.getProxyByNumber(num)
        self.selectProxy(proxy)

    def createProxy(self, proxyName: str, localPort: int, remotePort: int, remoteHost: str):
        if proxyName is None:
            raise ValueError('proxyName must not be none.')
        if len(proxyName) == 0:
            raise ValueError('proxyName must not be empty.')
        if ord(proxyName[0]) in range(ord('0'), ord('9') + 1):
            raise ValueError('proxyName must not start with a digit.')
        
        if proxyName in self._proxies:
            raise KeyError(f'There already is a proxy with the name {proxyName}.')

        # Create proxy and default parser
        proxy = Proxy(self._args.bind, remoteHost, localPort, remotePort, proxyName, self.packetHandler)
        parser = ParserContainer(self.DEFAULT_PARSER_MODULE, self)
        
        # Add them to their dictionaries
        self._proxies[proxy.name] = proxy
        self._parsers[proxy] = parser
        
        # Start the proxy thread
        proxy.start()
        return

    def killProxy(self, proxy: Proxy) -> None:
        # pop proxy from he dict
        if self.getSelectedProxy() == proxy:
            self.selectProxy(None)

        proxy = self._proxies.pop(proxy.name)
        # Kill it
        proxy.shutdown()
        # Wait for the thread to finish
        proxy.join()

        # Delete Parser
        self._parsers.pop(proxy)
        return

    def killProxyByName(self, proxyName: str) -> None:
        self.killProxy(self.getProxyByName(proxyName))
        return

    def renameProxy(self, proxy: Proxy, newName: str) -> None:
        if newName is None:
            raise ValueError('newName must not be none.')
        if len(newName) == 0:
            raise ValueError('newName must not be empty.')
        if ord(newName[0]) in range(ord('0'), ord('9') + 1):
            raise ValueError('newName must not start with a digit.')
        
        if newName in self._proxies:
            raise KeyError(f'Proxy with name {newName} already exists.')
        
        self._proxies[newName] = self._proxies.pop(proxy.name)
        # Make sure we update the selected proxy if we rename the currently selected one.
        if self._selectedProxyName == proxy.name:
            self._selectedProxyName = newName
        proxy.name = newName
        return

    def renameProxyByName(self, oldName: str, newName: str) -> None:
        proxy = self.getProxyByName(oldName)
        self.renameProxy(proxy, newName)
        return
    
    def getVariableNames(self) -> list[str]:
        return list(self._variables)

    def getVariable(self, variableName: str) -> str:
        if not self.checkVariableName(variableName):
            raise ValueError(f"Bad variable name: \"{variableName}\"")
        
        return self._variables.get(variableName, None)

    def setVariable(self, variableName: str, value: str) -> None:
        if not self.checkVariableName(variableName):
            raise ValueError(f"Bad variable name: \"{variableName}\"")

        self._variables[variableName] = value
        return

    def unsetVariable(self, variableName: str) -> bool:
        if not self.checkVariableName(variableName):
            raise ValueError(f"Bad variable name: \"{variableName}\"")
        
        if variableName not in self._variables:
            return False

        self._variables.pop(variableName)
        return True

    def clearVariables(self) -> None:
        self._variables = {}

    def checkVariableName(self, variableName: str) -> bool:
        if len(variableName) == 0:
            # Prevent empty variable names
            return False

        # Those are forbidden characters in the variable names
        invalidChars = [' ', '$', '\\', '(', ')']
        
        # Check if they occur
        for invalidChar in invalidChars:
            if invalidChar in list(variableName):
                return False
        return True
    
    def expandHistoryCommand(self, cmd: str) -> str:
        words = cmd.split(" ")

        # Expand history substitution
        for idx, word in enumerate(words):
            if word.startswith("!"):
                histIdx = int(word[1:]) # Let it throw ValueError to notify user.
                if not 0 <= histIdx < readline.get_current_history_length():
                    raise IndexError(f"History index {histIdx} is out of range.")
                
                historyItem = readline.get_history_item(histIdx)
                if historyItem is None:
                    raise ValueError(f"History index {histIdx} points to invalid history entry.")
                
                words[idx] = historyItem

        # Save it to a different variable to save this modified command to the history.
        # This is done to preserve the variable expansion later in the history.
        historyExpandedCmd = ' '.join(words)
        return historyExpandedCmd

    def expandVariableCommand(self, cmd: str) -> str:
        # TODO: allow for $(varname) format
        words = cmd.split(' ')
        word = None
        try:
            for idx, word in enumerate(words):
                if word.startswith("$"):
                    varname = word[1:]
                    words[idx] = self._variables[varname] # Let it throw KeyError to notify user.
        except KeyError as e:
            raise KeyError(f'Variable {word} does not exist: {e}') from e
        
        # reassemble cmd
        variableExpandedCmd = ' '.join(words)
        return variableExpandedCmd
    
    def getReadlineBufferStatus(self) -> ReadlineBufferStatus:
        self._rbs.update()
        return self._rbs

    def getHistoryList(self) -> list[str]:
        return list(self.getHistoryItem(x) for x in range(0, readline.get_history_length()))

    def getHistoryItem(self, idx: int) -> str:
        if not 0 <= idx < readline.get_history_length():
            raise IndexError(f'{idx} is not a valid history index.')
        return readline.get_history_item(idx)

    def deleteHistoryItem(self, idx: int) -> None:
        if not 0 <= idx < readline.get_history_length():
            raise IndexError(f'{idx} is not a valid history index.')
        # FIXME: Doesn't work
        readline.remove_history_item(idx)

        readline.write_history_file(self._HISTORY_FILE)
        return

    def clearHistory(self) -> None:
        readline.clear_history()
        readline.write_history_file(self._HISTORY_FILE)
        return

    def getCompleterFunction(self):
        return readline.get_completer()

    def setCompleterFunction(self, func) -> None:
        readline.set_completer(func)
        return

    def packetHandler(self, data: bytes, proxy: Proxy, origin: ESocketRole) -> None:
        parser = self.getParserByProxy(proxy)
        output = parser.parse(data, proxy, origin)
        if len(output) == 0:
            return

        # Get off the current line (with a prompt on it)
        print()
        for line in output:
            print(line)
        # Make some space between the output and the new prompt
        print()

        # Print a new prompt with the line we currently have in the buffer
        self._rbs.update()
        print(self.getPromptString() + self._rbs.origline, end='')
        sys.stdout.flush()

# Run
if __name__ == '__main__':
    application = Application()
    application.main()

