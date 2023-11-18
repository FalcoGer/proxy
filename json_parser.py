# This parser simply passes the data through and prints formatted json data

from __future__ import annotations
import typing
import json

# This is the base class for the custom parser class
import base_parser

# import stuff for API calls
from enum_socket_role import ESocketRole
from base_parser import EBaseSettingKey
from plaintext_parser import Parser as PlainTextParser

if typing.TYPE_CHECKING:
    from proxy import Proxy
    from application import Application
    from enum import Enum


class Parser(base_parser.Parser):

    # Define the parser name here as it should appear in the prompt
    def __str__(self) -> str:
        return 'JSON'

    def parse(self, data: bytes, proxy: Proxy, origin: ESocketRole) -> list[str]:
        output = super().parse(data, proxy, origin)

        output.append(Parser.format_json(data, True))

        # Pass data through to the target.
        if origin == ESocketRole.CLIENT:
            proxy.sendToServer(data)
        else:
            proxy.sendToClient(data)
        return output

    # Turns a string into an array of strings by carving out json objects
    # and appending them separately from normal text.
    @staticmethod
    def find_json(string: str) -> list[str]:
        result = [""]
        idx = 0  # where we are in the result array
        bracketCount = 0  # used to track how many braces are open
        stringDelimiter = None  # used to prevent false termination when curly brace is inside a json object's string.
        for char in string:
            if bracketCount > 0 and char == stringDelimiter and result[idx][-1] != "\\":
                # exiting a string, was unescaped and matches stringDelimiter
                stringDelimiter = None
            elif bracketCount > 0 and char in ("\"", "'") and stringDelimiter is None:
                # entering a string
                stringDelimiter = char
            elif char == "{" and stringDelimiter is None:
                # open bracket outside of a string
                bracketCount += 1
                if bracketCount == 1:
                    # is now a new json object
                    # Append to result if result is empty, otherwise start a new result string
                    if result[idx] != "":
                        idx += 1
                        result.append("")
                    else:
                        result[idx] += "{"
                        continue
            elif char == "}" and bracketCount > 0 and stringDelimiter is None:
                # closing brace outside of string
                bracketCount -= 1
                # if it is the last closing brace, start a new result object
                if bracketCount == 0:
                    result[idx] += "}"
                    result.append("")
                    idx += 1
                    continue
            result[idx] += char
        # remove all empty ones
        return [item for item in result if item]

    # Takes in the raw data and turns it into a formatted output.
    @staticmethod
    def format_json(byte_array: bytes, use_colors: bool) -> str:
        plainString = PlainTextParser.bytes_to_escaped_string(byte_array)
        jsonObjectArray = Parser.find_json(plainString)
        result = ""

        for potentialJsonString in jsonObjectArray:
            try:
                formatted_json = json.dumps(json.loads(potentialJsonString), indent=2, ensure_ascii=True)
                if not use_colors:
                    result += formatted_json + "\n"

                NORMAL_OPEN = "<lime>"
                NORMAL_CLOSE = "</lime>"
                QUOTE_OPEN = "<orange>"
                QUOTE_CLOSE = "</orange>"
                STRING_OPEN = "<yellow>"
                STRING_CLOSE = "</yellow>"
                NUMBER_OPEN = "<cyan>"
                NUMBER_CLOSE = "</cyan>"

                result += NORMAL_OPEN
                stringDelimiter = None
                inNumber = False
                prevChar = "\x00"
                for char in formatted_json:
                    if char in ("\"", "'") and prevChar != "\\":
                        if stringDelimiter is None:
                            # entering a string
                            stringDelimiter = char
                            result += f"{NORMAL_CLOSE}{QUOTE_OPEN}{char}{QUOTE_CLOSE}{STRING_OPEN}"
                        elif stringDelimiter == char:
                            # exiting a string
                            stringDelimiter = None
                            result += f"{STRING_CLOSE}{QUOTE_OPEN}{char}{QUOTE_CLOSE}{NORMAL_OPEN}"
                        else:
                            # double quote in single quote string or the other way around
                            result += char
                    elif (char.isnumeric() or char == '.') and not inNumber and stringDelimiter is None:
                        # entering a number outside a string
                        inNumber = True
                        result += f"{NORMAL_CLOSE}{NUMBER_OPEN}{char}"
                    elif not (char.isnumeric() or char == '.') and inNumber and stringDelimiter is None:
                        # exiting a number outside a string
                        inNumber = False
                        result += f"{NUMBER_CLOSE}{NORMAL_OPEN}{char}"
                    else:
                        result += char
                    prevChar = char

                result += f"{NORMAL_CLOSE}\n"
            except json.decoder.JSONDecodeError as ex:
                divider = "=" * 20
                if use_colors:
                    result += f"<red><b>Unable to format JSON</b></red>: <orange>{ex}</orange>\n"
                else:
                    result += f"Unable to format JSON: {ex}\n"
                result += (
                    f"{divider} START OF RAW STRING {divider}\n"
                    f"{potentialJsonString}\n"
                    f"{divider} END OF RAW STRING {divider}"
                )
        return result

    def __init__(self, application: Application, settings: dict[Enum, typing.Any]):
        super().__init__(application, settings)
        self.setSetting(EBaseSettingKey.HEXDUMP_ENABLED, False)
        return
