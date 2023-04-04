#!/bin/python3

import os
import argparse
import traceback

# This allows auto completion and history browsing
try:
    import gnureadline as readline
except ImportError:
    import readline

# This allows live reloading of modules
import importlib

from proxy import Proxy
import customParser as Parser


class Application():
    def __init__(self):
        self.variables: dict[(str, str)] = {}
        self.running = True
        self.HISTORY_FILE = "history.log"
        self.selectedProxyName: str = None
        self.proxies: dict[(str, Proxy)] = {}
        self.parsers: dict[(Proxy, Parser.CustomParser)] = {}
        
        # parse command line arguments.
        arg_parser = argparse.ArgumentParser(description='Create multiple proxy connections. Provide multiple port parameters to create multiple proxies.')
        arg_parser.add_argument('-b', '--bind', required=False, help='Bind IP-address for the listening socket. Default \'0.0.0.0\'', default='0.0.0.0')
        arg_parser.add_argument('-r', '--remote', type=str, required=True, help='Host IP-address or hostname to connect to.')
        arg_parser.add_argument('-p', '--port', type=int, nargs=2, metavar=('localport', 'remoteport'), action='append', required=True, help='Local and remote port')

        args = arg_parser.parse_args()
        
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
        idx = 0
        for localPort, remotePort in zip([x[0] for x in args.port], [x[1] for x in args.port]):
            name = f'PROXY_{localPort}'
            proxy = Proxy(self, args.bind, args.remote, localPort, remotePort, name)
            parser = Parser.CustomParser(self, {})
            self.proxies[name] = proxy
            self.parsers[proxy] = parser
            proxy.start()
            # Select the first proxy
            if idx == 0:
                self.selectProxy(name)
            idx += 1

    def main(self) -> None:
        # Accept user input and parse it.
        while self.running:
            try:
                for proxy, parser in self.parsers.items():
                    mustReload = True # TODO: make better check
                    if mustReload:
                        # Save the settings before reloading
                        parserSettings = parser.settings
                        importlib.reload(Parser)

                        # Create new parser with the old settings
                        # TODO: create the same parser type as the last one
                        newParser = Parser.CustomParser(self, parserSettings)
                        self.parsers[proxy] = newParser

                        # Reload completer if the new parser is the one in use.
                        if self.getSelectedProxy() == proxy:
                            readline.set_completer(newParser.completer.complete)
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
        return f'[{self.getSelectedProxy()}] $ '

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

    def getSelectedParser(self) -> Parser.CustomParser:
        proxy = self.getSelectedProxy()
        return self.getParserByProxy(proxy)

    def getProxyByName(self, name: str) -> Proxy:
        return self.proxies[name]

    def getParserByProxy(self, proxy: Proxy) -> Parser.CustomParser:
        return self.parsers[proxy]

    def getParserByProxyName(self, name: str) -> Parser.CustomParser:
        proxy = self.getProxyByName(name)
        return self.getParserByProxy(proxy)

    def selectProxy(self, name: str) -> None:
        if name not in self.proxies:
            raise KeyError(f"{name} is not a valid proxy name.")
        self.selectedProxyName = name
        # reload the correct completer
        readline.set_completer(self.getSelectedParser().completer.complete)
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

