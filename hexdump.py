from __future__ import annotations

from enum import Enum, auto
import typing

from prompt_toolkit.formatted_text import HTML, to_formatted_text

class ERepresentation(Enum):
    HEX = auto()
    PRINTABLE = auto()

class ColorSetting:
    def __init__(self, hexTagsOdd: str = None, hexTagsEven: str = None, printableTagsOdd: str = None, printableTagsEven: str = None):
        if hexTagsOdd is None:
            hexTagsOdd = ''
        self._hexTagsOdd = (hexTagsOdd, self._getClosingTags(hexTagsOdd))
        
        if hexTagsEven is None:
            hexTagsEven = hexTagsOdd
        self._hexTagsEven = (hexTagsEven, self._getClosingTags(hexTagsEven))
        
        if printableTagsOdd is None:
            printableTagsOdd = hexTagsOdd
        self._printableTagsOdd = (printableTagsOdd, self._getClosingTags(printableTagsOdd))
        
        if printableTagsEven is None:
            printableTagsEven = hexTagsEven
        self._printableTagsEven = (printableTagsEven, self._getClosingTags(printableTagsEven))
        
        self._hexAttributes = (self._hexTagsOdd, self._hexTagsEven)
        self._printableAttributes = (self._printableTagsOdd, self._printableTagsEven)
        return

    def _getClosingTags(self, tags: str) -> str:
        if not tags:
            return ''
        closingTags = []
        tagStart = 0
        tagEnd = -1
        for idx, c in enumerate(tags):
            if c == '<':
                tagStart = idx + 1
            if c == '>':
                tagEnd = idx 
            if tagStart <= tagEnd:
                tagContent = tags[tagStart:tagEnd]
                tagStart = 0
                tagEnd = -1
                tag = tagContent.split()[0]
                closingTags.insert(0,f'</{tag}>')
        return ''.join(closingTags)
    
    def __str__(self):
        return f'ColorSetting: {self._hexAttributes=}, {self._printableAttributes=}'

    def colorize(self, dataStr: str, isEven: bool = False, representation: ERepresentation = ERepresentation.HEX) -> str:
        attr = None
        if representation == ERepresentation.HEX:
            if self._hexAttributes is not None:
                if isEven and len(self._hexAttributes) == 2:
                    attr = self._hexAttributes[1]
                else:
                    # odd or not enough attributes in the tuple (only gave the odd one)
                    attr = self._hexAttributes[0]
        else:
            if self._printableAttributes is not None:
                if isEven and len(self._printableAttributes) == 2:
                    attr = self._printableAttributes[1]
                else:
                    # odd or not enough attributes in the tuple (only gave the odd one)
                    attr = self._printableAttributes[0]
        
        try:
            dataStr = dataStr.replace('&', '&amp;').replace('<', '&lt;').replace('>','&gt;')
            return f'{attr[0]}{dataStr}{attr[1]}'
        except Exception as e:
            print(f'Unable to color {repr(dataStr)} with {self}: {e}')
            return dataStr

class EColorSettingKey(Enum):
    # For formatting:
    SPACER_MAJOR = auto()           # spacer between address, hex and printable sections, also
    SPACER_MINOR = auto()           # spacer between byte groups
    ADDRESS = auto()                # address at start of line
    BYTE_TOTAL = auto()             # color of the byte total at the end
    
    # For data:
    DIGITS = auto()                 # ascii digits
    LETTERS = auto()                # ascii letters (a-z, A-Z)
    PRINTABLE = auto()              # other ascii characters
    SPACE = auto()                  # space character (0x20)
    PRINTABLE_HIGH_ASCII = auto()   # printable, but value > 127
    CONTROL = auto()                # ascii control characters (below 0x20)
    NULL_BYTE = auto()              # null byte
    NON_PRINTABLE = auto()          # everything else
    
    def __eq__(self, other) -> bool:
        if other is int:
            return self.value == other
        if other is str:
            return self.name == other
        if repr(type(self)) == repr(type(other)):
            return self.value == other.value
        return False

    def __gt__(self, other) -> bool:
        if other is int:
            return self.value > other
        if other is str:
            return self.name > other
        if repr(type(self)) == repr(type(other)):
            return self.value > other.value
        raise ValueError('Can not compare.')

    def __hash__(self):
        return int.__hash__(self.value)


class Hexdump():
    def __init__(self, bytesPerLine: int = 16, bytesPerGroup: int = 4, printHighAscii: bool = False, sep: str = '.', defaultColors: bool = True):
        self.setBytesPerLine(bytesPerLine)
        self.setBytesPerGroup(bytesPerGroup)
        self.setSep(sep)
        self.setPrintHighAscii(printHighAscii)
        
        # If the length of a representation of a string is of length 3 (example "'A'") then it is printable
        # otherwise the representation would be something like "'\xff'" (len 6).
        # So this creates a list of character representations for every possible byte value.
        # Special case is the backslash since it's representation string is "'\\\\'" (len 6)
        self.REPRESENTATION_ARRAY = ''.join([(len(repr(chr(b))) == 3 or repr(chr(b)) == '\'\\\\\'') and chr(b) or self.sep for b in range(256)])

        self.colorSettings: dict[(typing.Union[EColorSettingKey, int], ColorSetting)] = {}
        
        if defaultColors and self.colorSettings is not None:
            # FIXME: Colors
            # color available but not set
            # Formatting
            self.colorSettings[EColorSettingKey.ADDRESS]                = ColorSetting('<yellow><b>')
            self.colorSettings[EColorSettingKey.SPACER_MAJOR]           = ColorSetting()
            self.colorSettings[EColorSettingKey.SPACER_MINOR]           = ColorSetting()
            self.colorSettings[EColorSettingKey.BYTE_TOTAL]             = ColorSetting('<b><u>')
            # Data
            self.colorSettings[EColorSettingKey.CONTROL]                = ColorSetting('<violet>', '<magenta>')
            self.colorSettings[EColorSettingKey.DIGITS]                 = ColorSetting('<turquoise>', '<teal>')
            self.colorSettings[EColorSettingKey.LETTERS]                = ColorSetting('<lime>','<green>')
            self.colorSettings[EColorSettingKey.PRINTABLE]              = ColorSetting('<cyan>','<darkcyan>')
            self.colorSettings[EColorSettingKey.PRINTABLE_HIGH_ASCII]   = ColorSetting('<yellow>','<orange>')
            self.colorSettings[EColorSettingKey.NON_PRINTABLE]          = ColorSetting('<red>','<darkred>')
            self.colorSettings[ord(' ')]                                = ColorSetting('<lime>','<green>','<lime><u>','<green><u>')
            self.colorSettings[ord('_')]                                = ColorSetting('<cyan>','<darkcyan>','<cyan><u><b>','<darkcyan><u><b>')
            self.colorSettings[0x00]                                    = ColorSetting('<white><b>','<lightgray><b>')
        return

    def __str__(self):
        return f'Grouping {self.bytesPerLine}/{self.bytesPerGroup}, PrintHighAscii: {self.printHighAscii}, Sep: {repr(self.sep)}. {len(self.colorSettings)} Colors defined.'

    def setBytesPerLine(self, bytesPerLine: int = 16) -> typing.NoReturn:
        if not isinstance(bytesPerLine, int):
            raise TypeError(f'{repr(bytesPerLine)} is not {int}')
        if bytesPerLine <= 0:
            raise ValueError('Can\'t set bytesPerLine below 1. Got {bytesPerLine}')

        self.bytesPerLine = bytesPerLine
        return

    def setBytesPerGroup(self, bytesPerGroup: int = 4) -> typing.NoReturn:
        if not isinstance(bytesPerGroup, int):
            raise TypeError(f'{repr(bytesPerGroup)} is not {int}')
        if bytesPerGroup <= 0:
            raise ValueError(f'Can\'t set bytesPerLine below 1. Got {bytesPerGroup}')

        self.bytesPerGroup = bytesPerGroup
        return
    
    def setSep(self, sep: str = '.') -> typing.NoReturn:
        if not isinstance(sep, str):
            raise TypeError(f'{repr(sep)} is not {str}')
        if len(sep) != 1:
            raise ValueError(f'sep must be a string of length 1. Got {repr(sep)}')
        self.sep = sep
        return

    def setPrintHighAscii(self, printHighAscii: bool = False) -> typing.NoReturn:
        if not isinstance(printHighAscii, bool):
            raise TypeError(f'{repr(printHighAscii)} is not {bool}')

        self.printHighAscii = printHighAscii
        return

    def setColorSetting(self, key: typing.Union[EColorSettingKey, int], colorSetting: ColorSetting) -> typing.NoReturn:
        if not isinstance(key, EColorSettingKey) and not isinstance(key, int):
            raise ValueError(f'Key must be of type {repr(EColorSettingKey)} or {repr(int)}')
        if isinstance(key, int) and not 0x00 >= key >= 0xFF:
            raise ValueError(f'Key must be within the range of bytes [0x00 .. 0xFF] but was {hex(key)}')

        if self.colorSettings is not None:
            self.colorSettings = colorSetting
        return

    def unsetColorSetting(self, key: typing.Any) -> typing.NoReturn:
        if not isinstance(key,  EColorSettingKey) and not isinstance(key, int):
            raise TypeError(f'Key must be of type {repr(EColorSettingKey)} or {repr(int)}')
        if isinstance(key, int) and not 0x00 >= key >= 0xFF:
            raise ValueError(f'Key must be within the range of bytes [0x00 .. 0xFF] but was {key:X}')

        if self.colorSettings is not None and key in self.colorSettings:
            self.colorSettings.pop(key)
        return

    # Returns a list of lines of a hexdump.
    def hexdump(self, src: bytes) -> list[str]:
        lines = []
        maxAddrLen = len(f'{(len(src)):X}')
        
        # Round up to the nearest multiple of 4
        maxAddrLen = (int((maxAddrLen - 1) / 4) + 1) * 4

        for addr in range(0, len(src), self.bytesPerLine):
            # The chars we need to process for this line
            byteArray = src[addr : addr + self.bytesPerLine]
            lines.append(self.constructLine(addr, maxAddrLen, byteArray))
        lines.append(self.constructByteTotal(len(src), maxAddrLen))
        return lines

    def constructLine(self, address: int, maxAddrLen: int, byteArray: bytes) -> str:
        addr = self.constructAddress(address, maxAddrLen)
        hexString = self.constructHexString(byteArray)
        printableString = self.constructPrintableString(byteArray)
        majorSpacer = self.constructMajorSpacer('   ')
        return f'{addr}{majorSpacer}{hexString}{majorSpacer}{printableString}'

    def constructAddress(self, address: int, maxAddrLen: int) -> str:
        addrString = f'{address:0{maxAddrLen}X}'
        if self.colorSettings is None or EColorSettingKey.ADDRESS not in self.colorSettings:
            return addrString
        return self.colorSettings[EColorSettingKey.ADDRESS].colorize(addrString)

    def constructMinorSpacer(self, spacerStr: str) -> str:
        if self.colorSettings is None or EColorSettingKey.SPACER_MINOR not in self.colorSettings:
            return spacerStr
        return self.colorSettings[EColorSettingKey.SPACER_MINOR].colorize(spacerStr)

    def constructMajorSpacer(self, spacerStr: str) -> str:
        if self.colorSettings is None or EColorSettingKey.SPACER_MINOR not in self.colorSettings:
            return spacerStr
        return self.colorSettings[EColorSettingKey.SPACER_MINOR].colorize(spacerStr)

    def constructHexString(self, byteArray: bytes) -> str:
        ret = ''
        minorSpacerStr = ' '
        minorSpacer = self.constructMinorSpacer(minorSpacerStr)

        for idx, b in enumerate(byteArray):
            byteRepr = f'{b:02X}'
            colorSetting = self.getColorSetting(b)
            if colorSetting is not None:
                byteRepr = colorSetting.colorize(byteRepr, idx % 2 == 0, ERepresentation.HEX)
            ret += byteRepr

            # Add spacers, skip the last spacer if end of byte array
            if (idx + 1) % self.bytesPerGroup == 0 and (idx + 1) < self.bytesPerLine:
                ret += minorSpacer
        
        # Line up all the lines properly
        ret += minorSpacer * self.getRequiredPaddingLength(byteArray, 2)

        return ret

    def constructPrintableString(self, byteArray: bytes) -> str:
        ret = ''
        minorSpacer = self.constructMinorSpacer(' ')
        for idx, b in enumerate(byteArray):
            # store character representation into c
            c = ''
            if self.printHighAscii or b <= 127:
                c = self.REPRESENTATION_ARRAY[b]
            else:
                # byte > 127 and don't print high ascii
                c = self.sep
            
            # colorize c
            colorSetting = self.getColorSetting(b)
            if colorSetting is not None:
                c = colorSetting.colorize(c, idx % 2 == 0, ERepresentation.PRINTABLE)
            ret += c
            
            # Add spacers, skip the last spacer if end of byte array
            if (idx + 1) % self.bytesPerGroup == 0 and (idx + 1) < self.bytesPerLine:
                ret += minorSpacer

        # Add padding to line it all up
        ret += minorSpacer * self.getRequiredPaddingLength(byteArray, 1)
        
        return f'|{ret}|'

    # figure out which color setting is to be used for the byte
    def getColorSetting(self, byte: int) -> ColorSetting:
        if self.colorSettings is None:
            return None

        colorSetting = ColorSetting()
        
        # Direct setting is available
        if byte in self.colorSettings:
            return self.colorSettings[byte]

        # Find out which color setting to use.
        isPrintable = len(repr(chr(byte))) == 3 or repr(chr(byte)) == '\'\\\\\''
        isHighAscii = byte >= 0x80
        isControl = byte < 0x20
        isDigit = ord('0') <= byte <= ord('9')
        isLetter = (ord('a') <= byte <= ord('z')) or (ord('A') <= byte <= ord('Z'))
        
        # Find out which color setting to use.
        colorSettingKey = None
        if (not isPrintable and not isControl) or (not self.printHighAscii and isHighAscii):
            # non printable, non control
            colorSettingKey = EColorSettingKey.NON_PRINTABLE
        elif isPrintable and isHighAscii and self.printHighAscii:
            # printable high ascii
            colorSettingKey = EColorSettingKey.PRINTABLE_HIGH_ASCII
        elif isControl:
            # control
            colorSettingKey = EColorSettingKey.CONTROL
        elif isDigit:
            # printable, digit
            colorSettingKey = EColorSettingKey.DIGITS
        elif isLetter:
            # printable, letter
            colorSettingKey = EColorSettingKey.LETTERS
        elif isPrintable:
            # other printable
            colorSettingKey = EColorSettingKey.PRINTABLE
        else:
            raise ValueError(f'Can\'t figure out which color setting to use for {byte:02X}')
        
        colorSetting = self.colorSettings.get(colorSettingKey, None)
        if colorSetting is None:
            colorSetting = ColorSetting()
        
        return colorSetting

    def constructByteTotal(self, totalBytes: int, maxAddrLen: int) -> str:
        maxAddr = self.constructAddress(totalBytes, maxAddrLen)
        majorSpacer = self.constructMajorSpacer('   ')
        totalBytesString = f'({totalBytes} Bytes)'
        if self.colorSettings is not None and EColorSettingKey.BYTE_TOTAL in self.colorSettings:
            totalBytesString = self.colorSettings[EColorSettingKey.BYTE_TOTAL].colorize(totalBytesString)
        ret = f'{maxAddr}{majorSpacer}{totalBytesString}'
        return ret

    def getRequiredPaddingLength(self, byteArray: bytes, lenOfByteRepresentation: int) -> int:
        # The amount of spacers usually in a line and actually in the current line
        normalSpacerCount = int(self.bytesPerLine / self.bytesPerGroup)
        actualSpacerCount = int(len(byteArray) / self.bytesPerGroup)
        if self.bytesPerLine % self.bytesPerGroup == 0:
            # Remove the last spacer normally added if it would've been added at the end of the line.
            normalSpacerCount -= 1
        
        normalLength = self.bytesPerLine * lenOfByteRepresentation + normalSpacerCount
        actualLength = (len(byteArray) * lenOfByteRepresentation) + actualSpacerCount

        requiredPaddingLength = normalLength - actualLength
        return requiredPaddingLength

