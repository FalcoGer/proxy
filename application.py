#!/bin/python3

from __future__ import annotations
import typing

import os
import sys
import argparse
import traceback
import time

# prompt_toolkit allows custom inputs and formatted outputs as well as provide some
# neat functionality such as toolbars, button prompts, progress bars and more
# REF: https://python-prompt-toolkit.readthedocs.io/en/stable/pages/getting_started.html
import prompt_toolkit as pt
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import ProgressBar

from proxy import Proxy
# pylint: disable=wrong-import-order
from parser_container import ParserContainer
from enum_socket_role import ESocketRole

if typing.TYPE_CHECKING:
    from core_parser import Parser


class Application():
    def __init__(self):
        self.DEFAULT_PARSER_MODULE = 'passthrough_parser'
        self.START_TIME = time.time()

        self._HISTORY_FILE = 'history.log'
        self._variables: dict[(str, str)] = {}
        self._running = True
        self._selectedProxyName: str = None
        self._proxies: dict[(str, Proxy)] = {}
        self._parsers: dict[(Proxy, ParserContainer)] = {
            None: ParserContainer('core_parser', self)}

        # parse command line arguments.
        arg_parser = argparse.ArgumentParser(
            description='Create multiple proxy connections. Provide multiple proxy parameters to create multiple proxies.')
        arg_parser.add_argument('-b', '--bind', metavar=('binding_address'), required=False,
                                help='Bind IP-address for the listening socket. Default \'0.0.0.0\'', default='0.0.0.0')
        arg_parser.add_argument('-p', '--proxy', nargs=3, metavar=('lp', 'rp', 'host'), action='append', required=False,
                                help='Local port to listen on as well as the remote port and host ip address or hostname for the proxy to connect to.')

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
                print(f'Error: {e}')
                arg_parser.print_usage()
                raise e

        # Setup the input system
        self.setupInput()

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

    def stop(self) -> typing.NoReturn:
        self._running = False
        return

    def _buildToolbarAndGetCmd(self) -> str:
        cmd = None
        try:
            # Set toolbar
            self._sess.bottom_toolbar = f'{self.getSelectedProxy()}'
            # Fetch command
            proxyName = "None"
            if self.getSelectedProxy() is not None:
                proxyName = self.getSelectedProxy().name
            escapedProxyName = self.escapeHTML(proxyName)
            escapedParserName = self.escapeHTML(str(self.getSelectedParser()))
            prompt = f'<lime><b>{escapedProxyName}</b></lime> <green>({escapedParserName})</green>&gt; '
            cmd = self._sess.prompt(HTML(prompt))
        except KeyboardInterrupt:
            # Allow clearing the buffer with ctrl+c
            # TODO: find out how to check for empty buffer
            if True:
                print('Type \'exit\' or \'quit\' to exit or use CTRL+D to force quit.')
        except EOFError:
            # User hits Ctrl + D
            print('Received EOF, quitting.')
            self.stop()
        return cmd

    def _expandCommand(self, cmd: str) -> str:
        historyExpandedCmd = cmd
        variableExpandedCmd = None
        try:
            # Expand !<histIdx>
            historyExpandedCmd = self.expandHistoryCommand(cmd)
            # Expand variable substitution
            variableExpandedCmd = self.expandVariableCommand(historyExpandedCmd)
        except (ValueError, IndexError) as e:
            print(f'Error during history expansion: {e}')
            return None
        except KeyError as e:
            print(f'Error during variable expansion: {e}')
            return None
        finally:
            # add to the history either way.
            self.addToHistory(historyExpandedCmd)
        # Print if different
        if cmd != variableExpandedCmd:
            print(f'Expanded: {variableExpandedCmd}')
        return variableExpandedCmd

    def main(self) -> typing.NoReturn:
        # Accept user input and parse it.
        while self._running:
            try:
                cmd = self._buildToolbarAndGetCmd()
                if cmd is None:
                    continue

                # resolve escaped ! and $.
                expandedCmd = self._expandCommand(cmd)
                # abort if error
                if expandedCmd is None:
                    continue

                # Handle the command
                cmdReturn = self.runCommand(expandedCmd)
                if cmdReturn != 0:
                    print(f'Error: {cmdReturn}')
            # pylint: disable=broad-except
            except Exception as e:
                print(f'[EXCEPT] - User Input: {e}')
                print(traceback.format_exc())

        # Shutdown proxies and then wait for the threads to finish.
        with ProgressBar(title='Shutdown proxy') as pb:
            for proxy in pb(self._proxies.values()):
                proxy.shutdown()

        with ProgressBar(title='Joining proxy threads') as pb:
            for proxy in pb(self._proxies.values()):
                proxy.join()
        return

    def runCommand(self, cmd: str) -> typing.Union[int, str]:
        if cmd.strip().startswith('#'):
            return 0
        if len(cmd.strip()) == 0:
            return 0

        cmd = cmd.replace('\\!', '!').replace('\\$', '$')
        return self.getSelectedParser().handleUserInput(cmd, self.getSelectedProxy())

    def addToHistory(self, command: str) -> typing.NoReturn:
        lastHistoryItem = None
        if len(self._sess.history.get_strings()) > 0:
            lastHistoryItem = self._sess.history.get_strings()[-1]
        # Add the item to the history if not already in it.
        if command != lastHistoryItem and len(command) > 0:
            self._sess.history.append_string(command)
        return

    def getSelectedProxy(self) -> Proxy:
        return self.getProxyByName(self._selectedProxyName)

    def getSelectedParser(self) -> Parser:
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
            if proxy.getBind()[1] == num:
                return proxy
        raise IndexError(f'No proxy found with either local port or index {num}.')

    def getProxyList(self) -> list[Proxy]:
        return list(self._proxies.values())

    def getProxyNameList(self) -> list[str]:
        return list(self._proxies)

    def getParserByProxy(self, proxy: Proxy) -> Parser:
        return self._parsers[proxy].getInstance()

    def getParserByProxyName(self, name: str) -> Parser:
        proxy = self.getProxyByName(name)
        return self.getParserByProxy(proxy)

    def setParserForProxy(self, proxy: Proxy, parserName: str) -> typing.NoReturn:
        # Save old settings to put them into the new parser when applicable
        oldParser = self.getParserByProxy(proxy)
        settings = oldParser.settings

        # Create new parser and set it
        newParserContainer = ParserContainer(parserName, self)
        newParserContainer.setSettings(settings)
        self._parsers[proxy] = newParserContainer

        # Need to reload the completer if the current proxy got it's parser changed
        if proxy.name == self._selectedProxyName:
            self.setCompleter(newParserContainer.getInstance().completer)
        return

    def setParserForProxyByName(self, proxyName: str, parserName: str) -> typing.NoReturn:
        proxy = self.getProxyByName(proxyName)
        self.setParserForProxy(proxy, parserName)
        return

    def selectProxy(self, proxy: Proxy) -> typing.NoReturn:
        if proxy is None:
            self._selectedProxyName = None
        else:
            self._selectedProxyName = proxy.name

        # reload the correct completer
        self.setCompleter(self.getSelectedParser().completer)
        return

    def selectProxyByName(self, name: str) -> typing.NoReturn:
        self.selectProxy(self.getProxyByName(name))
        return

    def selectProxyByNumber(self, num: int) -> typing.NoReturn:
        proxy = self.getProxyByNumber(num)
        self.selectProxy(proxy)
        return

    def createProxy(self, proxyName: str, localPort: int, remotePort: int, remoteHost: str) -> typing.NoReturn:
        if proxyName is None:
            raise ValueError('proxyName must not be none.')
        if len(proxyName) == 0:
            raise ValueError('proxyName must not be empty.')
        if ord(proxyName[0]) in range(ord('0'), ord('9') + 1):
            raise ValueError('proxyName must not start with a digit.')

        if proxyName in self._proxies:
            raise KeyError(f'There already is a proxy with the name {proxyName}.')

        # Create proxy and default parser
        proxy = Proxy(self._args.bind, remoteHost, localPort, remotePort,
                      proxyName, self.packetHandler, self.outputHandlerPlain)
        parser = ParserContainer(self.DEFAULT_PARSER_MODULE, self)

        # Add them to their dictionaries
        self._proxies[proxy.name] = proxy
        self._parsers[proxy] = parser

        # Start the proxy thread
        proxy.start()
        return

    def killProxy(self, proxy: Proxy) -> typing.NoReturn:
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

    def killProxyByName(self, proxyName: str) -> typing.NoReturn:
        self.killProxy(self.getProxyByName(proxyName))
        return

    def renameProxy(self, proxy: Proxy, newName: str) -> typing.NoReturn:
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

    def renameProxyByName(self, oldName: str, newName: str) -> typing.NoReturn:
        proxy = self.getProxyByName(oldName)
        self.renameProxy(proxy, newName)
        return

    def getVariableNames(self) -> list[str]:
        return list(self._variables)

    def getVariable(self, variableName: str) -> str:
        if not self.checkVariableName(variableName):
            raise ValueError(f'Bad variable name: "{variableName}"')

        return self._variables.get(variableName, None)

    def setVariable(self, variableName: str, value: str) -> typing.NoReturn:
        if not self.checkVariableName(variableName):
            raise ValueError(f'Bad variable name: "{variableName}"')

        self._variables[variableName] = value
        return

    def unsetVariable(self, variableName: str) -> bool:
        if not self.checkVariableName(variableName):
            raise ValueError(f'Bad variable name: "{variableName}"')

        if variableName not in self._variables:
            return False

        self._variables.pop(variableName)
        return True

    def clearVariables(self) -> typing.NoReturn:
        self._variables: dict[str, str] = {}

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
        words = cmd.split(' ')

        # Expand history substitution
        for idx, word in enumerate(words):
            if word.startswith('!'):
                # Let it throw ValueError to notify user.
                histIdx = int(word[1:])
                if not 0 <= histIdx < len(self._sess.history.get_strings()):
                    raise IndexError(f'History index {histIdx} is out of range.')

                historyItem = self._sess.history.get_strings()[histIdx]
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
                if word.startswith('$'):
                    varname = word[1:]
                    # Let it throw KeyError to notify user.
                    words[idx] = self._variables[varname]
        except KeyError as e:
            raise KeyError(f'Variable {word} does not exist: {e}') from e

        # reassemble cmd
        variableExpandedCmd = ' '.join(words)
        return variableExpandedCmd

    def getHistoryList(self) -> list[str]:
        return self._sess.history.get_strings()

    def getHistoryItem(self, idx: int) -> str:
        if not 0 <= idx < len(self._sess.history.get_strings()):
            raise IndexError(f'{idx} is not a valid history index.')
        return self._sess.history.get_strings()[idx]

    def deleteHistoryItem(self, idx: int) -> typing.NoReturn:
        if not 0 <= idx < len(self._sess.history.get_strings()):
            raise IndexError(f'{idx} is not a valid history index.')
        # Store the list, remove the item, delete the file
        # and rewrite the file with all entries except the one removed.
        historyList = self.getHistoryList()
        os.remove(self._HISTORY_FILE)
        self.setupInput()
        for i, historyItem in enumerate(historyList):
            if i == idx:
                continue
            self.addToHistory(historyItem)
        return

    def clearHistory(self) -> typing.NoReturn:
        os.remove(self._HISTORY_FILE)
        self.setupInput()
        return

    def getCompleter(self) -> typing.Callable[[str, int], str]:
        return self._sess.completer

    def setCompleter(self, completer: pt.completion.Completer) -> typing.NoReturn:
        self._sess.completer = completer
        return

    def packetHandler(self, data: bytes, proxy: Proxy, origin: ESocketRole) -> typing.NoReturn:
        parser = self.getParserByProxy(proxy)
        output = parser.parse(data, proxy, origin)
        self.outputHandlerFancy(output)
        return

    def outputHandlerPlain(self, output: list[str]) -> typing.NoReturn:
        # Don't print a new prompt if there is no output
        if output is None or len(output) == 0:
            return
        # Print the output we were given to print
        if isinstance(output, list):
            print_formatted_text('\n'.join(output))
        else:
            print_formatted_text(output)
        self._sess.bottom_toolbar = f'{str(self.getSelectedProxy())}'
        sys.stdout.flush()
        return

    def outputHandlerFancy(self, output: list[str]) -> typing.NoReturn:
        # Don't print a new prompt if there is no output
        if output is None or len(output) == 0:
            return
        # Print the output we were given to print
        if isinstance(output, list):
            print_formatted_text(HTML('\n'.join(output)))
        else:
            print_formatted_text(HTML(output))
        self._sess.bottom_toolbar = f'{str(self.getSelectedProxy())}'
        sys.stdout.flush()
        return

    def setupInput(self) -> typing.NoReturn:
        # Enable history file
        try:
            history = pt.history.FileHistory(filename=self._HISTORY_FILE)
        except (OSError, PermissionError, IsADirectoryError, IOError) as e:
            print(f'Error while trying to open history: {e}')
            # This is done to prevent messing with the file after there has been an error with it.
            self._HISTORY_FILE = None
            history = pt.history.InMemoryHistory()
        self._sess: pt.PromptSession = pt.PromptSession(history=history)

        # Set completer
        self._sess.completer = self.getSelectedParser().completer

        # Automatically suggest from history
        self._sess.auto_suggest = pt.auto_suggest.AutoSuggestFromHistory()

        # Disable mouse support to allow scrolling of
        # the text in the console via terminal emulator.
        self._sess.mouse_support = False

        # Allow async completion
        self._sess.complete_in_thread = True
        return

    def escapeHTML(self, s: str) -> str:
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# Run
if __name__ == '__main__':
    application = Application()
    application.main()
