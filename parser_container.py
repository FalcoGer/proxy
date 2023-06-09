from __future__ import annotations
import typing

from dynamic_loader import DynamicLoader

if typing.TYPE_CHECKING:
    from application import Application
    import core_parser as Parser
    from enum import Enum


# This class holds parser items imported from module name.
# When the parser is requested from this class, it will be reloaded if required
class ParserContainer():
    def __init__(self, moduleName: str, application: Application):
        self.application = application
        self.dynamicLoader: DynamicLoader = DynamicLoader(moduleName)
        self.instance: Parser.Parser = self.dynamicLoader.getModule().Parser(self.application, {})
        return

    def __str__(self) -> str:
        return self.dynamicLoader.moduleName

    def setSettings(self, settings: dict[Enum, typing.Any]) -> typing.NoReturn:
        completer = self.application.getCompleter()
        needToSetCompleter = completer == self.instance.completer
        self.instance = self.dynamicLoader.getModule().Parser(self.application, settings)

        if needToSetCompleter:
            self.application.setCompleter(self.instance.completer)

    def getInstance(self) -> Parser.Parser:
        if self.dynamicLoader.checkNeedsReload():
            # Save settings
            settings = self.instance.settings

            # Check if we need to reset the completer also
            # Compare the current completer with the one we have stored.
            # If they are the same then we need to reload the completer also.
            completer = self.application.getCompleter()
            needToSetCompleter = completer == self.instance.completer

            # Actually reload the module and create new instance with restored settings.
            self.dynamicLoader.reloadModule()
            self.instance = self.dynamicLoader.getModule().Parser(self.application, settings)

            # Set the completer if required
            if needToSetCompleter:
                self.application.setCompleter(self.instance.completer)

        return self.instance
