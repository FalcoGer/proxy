# This class loads a module dynamically
# It provides a facility to check if it needs to
# be reloaded and a function to actually reload it.

import importlib
import hashlib

class DynamicLoader:
    def __init__(self, moduleName):
        self.moduleName = moduleName
        self.originHash: bytes = None
        self.moduleSpec = None
        self.module = None

        self.loadModule()

    def checkNeedsReload(self) -> bool:
        if self.moduleSpec is None or self.module is None or self.originHash is None:
            return True

        newModuleSpec = importlib.util.find_spec(self.moduleName)
        if self.moduleSpec.origin != newModuleSpec.origin:
            return True

        if self.originHash != self.calculateFileHash():
            return True
        
        return False

    def __str__(self) -> str:
        return str(self.moduleSpec)

    def getModule(self):
        return self.module

    def loadModule(self):
        self.moduleSpec = importlib.util.find_spec(self.moduleName)
        if self.moduleSpec is None:
            raise ImportError(f'Module {self.moduleName} not found.')
        self.module = importlib.import_module(self.moduleSpec.name)
        self.originHash = self.calculateFileHash()
        return

    def reloadModule(self):
        # print(f'Reload called on {self.moduleSpec}')
        importlib.reload(self.module)
        self.originHash = self.calculateFileHash()

    def calculateFileHash(self) -> bytes:
        BUFF_SIZE = 4096
        with open(self.moduleSpec.origin, "rb") as file:
            hashFunction = hashlib.md5()
            while buf := file.read(BUFF_SIZE):
                hashFunction.update(buf)
            return hashFunction.digest()


