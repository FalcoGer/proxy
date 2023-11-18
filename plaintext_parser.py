# This parser simply passes the data through and prints plain text instead of hexdump

from __future__ import annotations
import typing

# This is the base class for the custom parser class
import base_parser

# import stuff for API calls
from enum_socket_role import ESocketRole
from base_parser import EBaseSettingKey

if typing.TYPE_CHECKING:
    from proxy import Proxy
    from application import Application
    from enum import Enum


class Parser(base_parser.Parser):

    # Define the parser name here as it should appear in the prompt
    def __str__(self) -> str:
        return 'PLAIN'

    def parse(self, data: bytes, proxy: Proxy, origin: ESocketRole) -> list[str]:
        output = super().parse(data, proxy, origin)

        output.append(Parser.bytes_to_escaped_string(data))

        # Pass data through to the target.
        if origin == ESocketRole.CLIENT:
            proxy.sendToServer(data)
        else:
            proxy.sendToClient(data)
        return output

    @staticmethod
    def bytes_to_escaped_string(byte_array: bytes) -> str:
        result = ""

        PRINTABLE_ASCII_START = 0x20
        PRINTABLE_ASCII_END = 0x7E
        WHITESPACE_CHARACTERS = {0x09, 0x0A, 0x0D}
        BACKSLASH_ASCII = 0x5C

        for byte in byte_array:
            if byte == BACKSLASH_ASCII:
                result += "\\\\"
            elif PRINTABLE_ASCII_START <= byte <= PRINTABLE_ASCII_END or byte in WHITESPACE_CHARACTERS:
                result += chr(byte)
            else:
                result += f"\\x{byte:02X}"

        return result

    def __init__(self, application: Application, settings: dict[Enum, typing.Any]):
        super().__init__(application, settings)
        self.setSetting(EBaseSettingKey.HEXDUMP_ENABLED, False)
        return
