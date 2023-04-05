#!/bin/python3

import os
import argparse
import traceback

# This allows auto completion and history browsing
try:
    import gnureadline as readline
except ImportError:
    import readline

from proxy import Proxy
from parser_container import ParserContainer

class Application():
    def __init__(self):
        self.HISTORY_FILE = "history.log"
        self.DEFAULT_PARSER_MODULE = "passthrough_parser"
        
        self.variables: dict[(str, str)] = {}
        self.running = True
        self.selectedProxyName: str = None
        self.proxies: dict[(str, Proxy)] = {}
        self.parsers: dict[(Proxy, ParserContainer)] = {None: ParserContainer('core_parser', self)}
        
        # parse command line arguments.
        arg_parser = argparse.ArgumentParser(description='Create multiple proxy connections. Provide multiple proxy parameters to create multiple proxies.')
        arg_parser.add_argument('-b', '--bind', metavar=('binding_address'), required=False, help='Bind IP-address for the listening socket. Default \'0.0.0.0\'', default='0.0.0.0')
        arg_parser.add_argument('-p', '--proxy', nargs=3, metavar=('lp', 'rp', 'host'), action='append', required=False, help='Local port to listen on as well as the remote port and host ip address or hostname for the proxy to connect to.')

        self.args = arg_parser.parse_args()

        # Fix proxy argument Typing since nargs > 1 doesn't support multiple types such as (int, int, str)
        # REF: https://github.com/python/cpython/issues/82398
        if self.args.proxy is not None:
            try:
                idx = 0
                for proxyArgs in self.args.proxy:
                    localPort = int(proxyArgs[0])
                    remotePort = int(proxyArgs[1])
                    remoteHost = proxyArgs[2]

                    self.args.proxy[idx] = [localPort, remotePort, remoteHost]
                    idx += 1

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
        
        # Try to load history file or create it if it doesn't exist.
        try:
            if os.path.exists(self.HISTORY_FILE):
                readline.read_history_file(self.HISTORY_FILE)
            else:
                readline.write_history_file(self.HISTORY_FILE)
        except (PermissionError, FileNotFoundError, IsADirectoryError) as e:
            print(f"Can not read or create {self.HISTORY_FILE}: {e}")

        # Create a proxies and parsers based on arguments.
        if self.args.proxy is not None:
            idx = 0
            for proxyArgs in self.args.proxy:
                localPort = proxyArgs[0]
                remotePort = proxyArgs[1]
                remoteHost = proxyArgs[2]

                name = f'PROXY_{localPort}'
                self.createProxy(name, localPort, remotePort, remoteHost)
                # Select the first proxy
                if idx == 0:
                    self.selectProxyByName(name)
                idx += 1
        else:
            # To initialize the completer for the core_parser
            self.selectProxy(None)

    def main(self) -> None:
        # Accept user input and parse it.
        while self.running:
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
                historyExpandedCmd = self.expandHistoryCommand(cmd)
                
                # Expand variable substitution
                try:
                    variableExpandedCmd = self.expandVariableCommand(cmd)
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
        for proxy in self.proxies.values():
            proxy.shutdown()

        for proxy in self.proxies.values():
            proxy.join()
            
        readline.write_history_file(self.HISTORY_FILE)
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
            readline.append_history_file(1, self.HISTORY_FILE)
        return

    def getSelectedProxy(self) -> Proxy:
        return self.getProxyByName(self.selectedProxyName)

    def getSelectedParser(self):
        proxy = self.getSelectedProxy()
        return self.getParserByProxy(proxy)

    def getProxyByName(self, name: str) -> Proxy:
        if name is None:
            return None

        return self.proxies[name]

    def getProxyByNumber(self, num: int) -> Proxy:
        # By ID
        if num < len(self.proxies):
            return list(self.proxies.values())[num]
        # ID not found, maybe port number?
        for proxy in self.proxies.values():
            if proxy.localPort == num:
                return proxy
        raise IndexError(f'No proxy found with either local port or index {num}.')

    def getParserByProxy(self, proxy: Proxy):
        return self.parsers[proxy].getInstance()

    def getParserByProxyName(self, name: str):
        proxy = self.getProxyByName(name)
        return self.getParserByProxy(proxy)

    def setParserForProxy(self, proxy, parserName) -> None:
        newParser = ParserContainer(parserName, self)
        self.parsers[proxy] = newParser
        return

    def setParserForProxyByName(self, proxyName, parserName) -> None:
        proxy = self.getProxyByName(proxyName)
        self.setParserForProxy(proxy, parserName)
        return

    def selectProxy(self, proxy: Proxy) -> None:
        if proxy is None:
            self.selectedProxyName = None
        else:
            self.selectedProxyName = proxy.name
        
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
        
        if proxyName in self.proxies:
            raise KeyError(f'There already is a proxy with the name {proxyName}.')

        # Create proxy and default parser
        proxy = Proxy(self, self.args.bind, remoteHost, localPort, remotePort, proxyName)
        parser = ParserContainer(self.DEFAULT_PARSER_MODULE, self)
        
        # Add them to their dictionaries
        self.proxies[proxy.name] = proxy
        self.parsers[proxy] = parser
        
        # Start the proxy thread
        proxy.start()
        return

    def killProxy(self, proxy: Proxy) -> None:
        # pop proxy from he dict
        if self.getSelectedProxy() == proxy:
            self.selectProxy(None)

        proxy = self.proxies.pop(proxy.name)
        # Kill it
        proxy.shutdown()
        # Wait for the thread to finish
        proxy.join()

        # Delete Parser
        self.parsers.pop(proxy)
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
        
        if newName in self.proxies:
            raise KeyError(f'Proxy with name {newName} already exists.')
        
        self.proxies[newName] = self.proxies.pop(proxy.name)
        # Make sure we update the selected proxy if we rename the currently selected one.
        if self.selectedProxyName == proxy.name:
            self.selectedProxyName = newName
        proxy.name = newName
        return

    def renameProxyByName(self, oldName: str, newName: str) -> None:
        proxy = self.getProxyByName(oldName)
        self.renameProxy(proxy, newName)
        return

    def getVariable(self, variableName: str) -> str:
        if not self.checkVariableName(variableName):
            raise ValueError(f"Bad variable name: \"{variableName}\"")
        
        return self.variables.get(variableName, None)

    def setVariable(self, variableName: str, value: str) -> None:
        if not self.checkVariableName(variableName):
            raise ValueError(f"Bad variable name: \"{variableName}\"")

        self.variables[variableName] = value
        return

    def unsetVariable(self, variableName: str) -> bool:
        if not self.checkVariableName(variableName):
            raise ValueError(f"Bad variable name: \"{variableName}\"")
        
        if variableName not in self.variables:
            return False

        self.variables.pop(variableName)
        return True

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
    
    def getReadlineModule(self):
        return readline

    def expandHistoryCommand(self, cmd: str) -> str:
        words = cmd.split(" ")
        idx = 0

        # Expand history substitution
        for word in words:
            if word.startswith("!"):
                histIdx = int(word[1:]) # Let it throw ValueError to notify user.
                if not 0 <= histIdx < readline.get_current_history_length():
                    raise ValueError("History index {histIdx} is out of range.")
                
                historyItem = readline.get_history_item(histIdx)
                if historyItem is None:
                    raise ValueError("History index {histIdx} points to invalid history entry.")
                
                words[idx] = historyItem
            idx += 1

        # Save it to a different variable to save this modified command to the history.
        # This is done to preserve the variable expansion later in the history.
        historyExpandedCmd = ' '.join(words)
        return historyExpandedCmd

    def expandVariableCommand(self, cmd: str) -> str:
        # TODO: allow for $(varname) format
        words = cmd.split(' ')
        idx = 0
        word = None
        try:
            for word in words:
                if word.startswith("$"):
                    varname = word[1:]
                    words[idx] = self.variables[varname] # Let it throw KeyError to notify user.

                idx += 1
        except KeyError as e:
            raise KeyError(f'Variable {word} does not exist: {e}') from e
        
        # reassemble cmd
        variableExpandedCmd = ' '.join(words)
        return variableExpandedCmd


# Run
if __name__ == '__main__':
    application = Application()
    application.main()

