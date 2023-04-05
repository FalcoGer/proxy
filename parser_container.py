import core_parser as Parser
from dynamic_loader import DynamicLoader

# This class holds parser items imported from module name.
# When the parser is requested from this class, it will be reloaded if required

# pylint: disable=too-few-public-methods
class ParserContainer():
    def __init__(self, moduleName: str, application):
        self.application = application
        self.dynamicLoader: DynamicLoader = DynamicLoader(moduleName)
        self.instance: Parser.Parser = self.dynamicLoader.getModule().Parser(self.application, {})
        return

    def __str__(self) -> str:
        return self.dynamicLoader.moduleName

    def getInstance(self) -> Parser.Parser:
        if self.dynamicLoader.checkNeedsReload():
            # Save settings
            settings = self.instance.settings
            
            # Check if we need to reset the readline completer also
            # since the completer class, which holds the completer function, is stored in the Parser.
            readline = self.application.getReadlineModule()
            completerFunction = readline.get_completer()
            needToSetCompleter = completerFunction == self.instance.completer.complete
            
            # Actually reload the module and create new instance with restored settings.
            self.dynamicLoader.reloadModule()
            self.instance = self.dynamicLoader.getModule().Parser(self.application, settings)
            
            # Set the completer if required
            if needToSetCompleter:
                readline.set_completer(self.instance.completer.complete)

        return self.instance

