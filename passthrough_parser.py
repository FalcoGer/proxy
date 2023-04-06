# This parser simply passes the data through and is the default for new parsers

# This is the base class for the custom parser class
import base_parser

# import stuff for API calls
from eSocketRole import ESocketRole

class Parser(base_parser.Parser):
    
    # Define the parser name here as it should appear in the prompt
    def __str__(self) -> str:
        return "PASS"

    def parse(self, data: bytes, proxy, origin: ESocketRole) -> list[str]:
        output = super().parse(data, proxy, origin)
        
        # Pass data through to the target.
        if origin == ESocketRole.client:
            proxy.sendToServer(data)
        else:
            proxy.sendToClient(data)
        return output

    def __init__(self, application, settings):
        super().__init__(application, settings)
        return
    
