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
from importlib import reload

from proxy import Proxy
import customParser as Parser


class Application():
    def __init__(self):
        self.variables: dict[(str, str)] = {}
        self.running = True
        self.HISTORY_FILE = "history.log"
        self.proxyList: list[Proxy] = []
        self.selectedProxyIdx = 0
        self.currentParser: Parser = Parser.CustomParser(self)

    def main(self) -> None:
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
        try:
            if os.path.exists(self.HISTORY_FILE):
                readline.read_history_file(self.HISTORY_FILE)
            else:
                readline.write_history_file(self.HISTORY_FILE)
        except (PermissionError, FileNotFoundError, IsADirectoryError) as e:
            print(f"Can not read or create {self.HISTORY_FILE}: {e}")

        # Create a proxy with, binding on all interfaces.
        
        localPorts = [x[0] for x in args.port]
        remotePorts = [x[1] for x in args.port]
        self.proxyList = [Proxy(self, args.bind, args.remote, *ports) for ports in zip(localPorts, remotePorts)]

        for proxy in self.proxyList:
            proxy.start()
        
        # readline.set_completer_delims(readline.get_completer_delims().replace("!", "").replace("$", ""))
        readline.set_completer_delims(' /')

        # Accept user input and parse it.
        while self.running:
            try:
                mustReload = True # TODO: make better check
                if mustReload:
                    reload(Parser)
                    
                    # Update parser
                    self.currentParser = Parser.CustomParser(self)

                    # Update completer
                    readline.set_completer(self.currentParser.completer.complete)

                try:
                    print() # Empty line
                    cmd = None
                    
                    proxyIdxStrMaxLen = len(str(len(self.proxyList) - 1)) # kept here to keep it all in one place
                    # Need to recalculate since proxy identifier may change due to reconnect
                    proxyIdentStrMaxLen = max(len(proxy.identifier) for proxy in self.proxyList)
                    
                    proxyIdxStr = str(self.selectedProxyIdx).rjust(proxyIdxStrMaxLen)
                    proxyIdentStr = self.getSelectedProxy().identifier.ljust(proxyIdentStrMaxLen)
                    prompt = f'[{proxyIdxStr}] ({proxyIdentStr}) $ '
                    cmd = input(f'{prompt}')
                except KeyboardInterrupt:
                    # Allow clearing the buffer with ctrl+c
                    if not readline.get_line_buffer():
                        print("Type 'exit' or 'quit' to exit.")

                if cmd is None:
                    continue

                expanded = False # Used to check if there is a need to print a modified command
                
                # Expand !<histIdx>
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
                        expanded = True
                    idx += 1

                # Save it to a different variable to save this modified command to the history.
                # This is done to preserve the variable expansion later in the history.
                historyExpandedCmd = ' '.join(words)

                # Expand variable substitution
                words = historyExpandedCmd.split(' ')
                idx = 0
                word = None
                # On error set true, but add to history anyway.
                # This is used to not send the command but add it to the history anyway.
                doHandleCommand = True
                try:
                    for word in words:
                        if word.startswith("$"):
                            varname = word[1:]
                            words[idx] = self.variables[varname] # Let it throw KeyError to notify user.
                            expanded = True

                        idx += 1
                except KeyError as e:
                    print(f'Variable {word} does not exist: {e}')
                    doHandleCommand = False
                
                # reassemble cmd
                variableExpandedCmd = ' '.join(words)
                
                # resolve escaped ! and $.
                escapedCmd = variableExpandedCmd.replace('\\!', '!').replace('\\$', '$') 
                if expanded or cmd != escapedCmd:
                    print(f"Expanded: {escapedCmd}")
                
                self.addToHistory(historyExpandedCmd)
                if not doHandleCommand:
                    continue
                                
                # Handle the command
                cmdReturn = self.currentParser.handleUserInput(escapedCmd, self.getSelectedProxy())
                if cmdReturn != 0:
                    print(f"Error: {cmdReturn}")
            except Exception as e:
                print(f'[EXCEPT] - User Input: {e}')
                print(traceback.format_exc())
        
        # Save the history file.
        for proxy in self.proxyList:
            proxy.shutdown()

        for proxy in self.proxyList:
            proxy.join()
            
        readline.write_history_file(self.HISTORY_FILE)
        return

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
        return self.proxyList[self.selectedProxyIdx]

    def selectProxy(self, idx: int) -> None:
        if not 0 <= idx < len(self.proxyList):
            raise IndexError(f"Selected proxy index {idx} out of bounds.")
        self.selectedProxyIdx = idx

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
            # Prevent nonsense
            return False
        if '$' in list(variableName):
            # Prevent errors
            return False
        if '\\' in list(variableName):
            # Prevent errors
            return False
        if ' ' in list(variableName):
            # Prevent herrasy
            return False
        # Everything else is fine.
        return True
    
    def getReadlineModule(self):
        return readline

# Run
if __name__ == '__main__':
    application = Application()
    application.main()

