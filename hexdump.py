from enum import Enum, auto
from copy import deepcopy

_COLOR_AVAILABLE = False

try:
    from termcolor import colored
    _COLOR_AVAILABLE = True
except ImportError:
    pass

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
        raise ValueError("Can not compare.")

    def __hash__(self):
        return int.__hash__(self.value)

# Returns a list of lines of a hexdump.
# Set colorSettings to {} if you don't want to print colors, leave None if you want default colors.
# Set provide termcolor.colored tuples for colorSettings
# setting[EColorSettingKey] = (foreground, blackground, oddAttributes, evenAttributes)
# if you want custom colors.
def hexdump(src: bytes, bytesPerLine: int = 16, bytesPerGroup: int = 4, colorSettings: dict = None, sep: str = '.', printHighAscii = False) -> list:
    lines = []
    maxAddrLen = len(hex(len(src)))
    
    if 8 > maxAddrLen:
        maxAddrLen = 8

    global _COLOR_AVAILABLE
    if not _COLOR_AVAILABLE:
        colorSettings = None
    elif colorSettings is None:
        # color available but not set
        colorSettings = {}
        # Formatting
        colorSettings[EColorSettingKey.ADDRESS]                 = ("yellow", None, ['bold'], None)
        colorSettings[EColorSettingKey.SPACER_MAJOR]            = (None, None, [], None)
        colorSettings[EColorSettingKey.SPACER_MINOR]            = (None, None, [], None)
        colorSettings[EColorSettingKey.BYTE_TOTAL]              = (None, None, ['bold', 'underline'], None)
        # Data
        colorSettings[EColorSettingKey.CONTROL]                 = ("magenta", None, [], ['dark'])
        colorSettings[EColorSettingKey.DIGITS]                  = ("blue", None, [], ['dark'])
        colorSettings[EColorSettingKey.LETTERS]                 = ("green", None, [], ['dark'])
        colorSettings[EColorSettingKey.PRINTABLE]               = ("cyan", None, [], ['dark'])
        colorSettings[EColorSettingKey.SPACE]                   = ("green", None, ['underline'], ['underline'])
        colorSettings[EColorSettingKey.PRINTABLE_HIGH_ASCII]    = ("yellow", None, [], ['dark'])
        colorSettings[EColorSettingKey.NON_PRINTABLE]           = ("red", None, [], ['dark'])
        colorSettings[EColorSettingKey.NULL_BYTE]               = ("white", None, [], ['dark'])

    for addr in range(0, len(src), bytesPerLine):
        # The chars we need to process for this line
        byteArray = src[addr : addr + bytesPerLine]
        lines.append(constructLine(addr, maxAddrLen, byteArray, bytesPerLine, bytesPerGroup, printHighAscii, colorSettings, sep))
    lines.append(constructByteTotal(len(src), maxAddrLen, colorSettings))
    return lines

def constructLine(address: int, maxAddrLen: int, byteArray: bytes, bytesPerLine: int, bytesPerGroup: int, printHighAscii: bool, colorSettings: dict, sep: str) -> str:
    addr = constructAddress(address, maxAddrLen, colorSettings)
    hexString = constructHexString(byteArray, bytesPerLine, bytesPerGroup, printHighAscii, colorSettings)
    printableString = constructPrintableString(byteArray, bytesPerLine, bytesPerGroup, printHighAscii, colorSettings, sep)
    majorSpacer = constructMajorSpacer('   ', colorSettings)
    return f"{addr}{majorSpacer}{hexString}{majorSpacer}{printableString}"

def constructAddress(address: int, maxAddrLen: int, colorSettings: dict) -> str:
    addrString = f"{address:0{maxAddrLen}X}"
    if colorSettings is not None and EColorSettingKey.ADDRESS in colorSettings.keys():
        fg, bg, attr, _ = colorSettings[EColorSettingKey.ADDRESS]
        addrString = colored(addrString, fg, bg, attr)
    return addrString

def constructMinorSpacer(spacerStr: str, colorSettings: dict) -> str:
    if colorSettings is None or EColorSettingKey.SPACER_MINOR not in colorSettings.keys():
        return spacerStr
    fg, bg, attr, _ = colorSettings[EColorSettingKey.SPACER_MINOR]
    return colored(spacerStr, fg, bg, attr)

def constructMajorSpacer(spacerStr: str, colorSettings: dict) -> str:
    if colorSettings is None or EColorSettingKey.SPACER_MINOR not in colorSettings.keys():
        return spacerStr
    fg, bg, attr, _ = colorSettings[EColorSettingKey.SPACER_MINOR]
    return colored(spacerStr, fg, bg, attr)

def constructHexString(byteArray: bytes, bytesPerLine: int, bytesPerGroup: int, printHighAscii: bool, colorSettings: dict) -> str:
    ret = ""
    minorSpacerStr = ' '
    minorSpacer = constructMinorSpacer(minorSpacerStr, colorSettings)
    numMinorSpacers = 0

    idx = 0
    for b in byteArray:
        byteRepr = f"{b:02X}"
        if colorSettings is not None:
            fg, bg, attrOdd, attrEven = getColorSetting(b, printHighAscii, colorSettings)
            attr = attrEven if idx % 2 == 0 else attrOdd
            if b == 0x20 and 'underline' in attr:
                attr = attr.remove('underline')
            byteRepr = colored(byteRepr, fg, bg, attr)
        ret += byteRepr
        idx += 1

        # Add spacers, skip the last spacer if end of byte array
        if idx % bytesPerGroup == 0 and idx < bytesPerLine:
            ret += minorSpacer
            numMinorSpacers += 1
    
    # Pad out the line to fill up the line to take up the right amount of space to line up with a full line.
    # normalLength is the length of a full sized byteArray.
    normalSpacerCount = int(bytesPerLine / bytesPerGroup)
    if bytesPerLine % bytesPerGroup == 0:
        # Remove the last spacer normally added if it would've been added at the end of the line.
        normalSpacerCount -= 1
    normalLength = bytesPerLine * 2 + normalSpacerCount
    
    requiredPaddingLength = normalLength - (len(byteArray) * 2) - numMinorSpacers
    ret += ' ' * requiredPaddingLength

    return ret

def constructPrintableString(byteArray: bytes, bytesPerLine: int, bytesPerGroup: int, printHighAscii: bool, colorSettings: dict, sep: str) -> str:
    # If the length of a representation of a string is of length 3 (example "'A'") then it is printable
    # otherwise the representation would be something like "'\xff'" (len 6).
    # So this creates a list of character representations for every possible byte value.
    representationArray = ''.join([(len(repr(chr(b))) == 3 or repr(chr(b)) == '\'\\\\\'') and chr(b) or sep for b in range(256)])
    ret = ""
    minorSpacer = constructMinorSpacer(' ', colorSettings)
    idx = 0
    for b in byteArray:
        # store character representation into c
        c = ""
        if printHighAscii or b <= 127:
            c = representationArray[b]
        else:
            # byte > 127 and don't print high ascii
            c = sep
        
        # colorize c
        if colorSettings is not None:
            fg, bg, attrOdd, attrEven = getColorSetting(b, printHighAscii, colorSettings)
            # Underline and bolden if underscore to make it thicker
            attr = attrEven if idx % 2 == 0 else attrOdd
            if c == '_':
                if attr is None:
                    attr = []
                extraAttributes = ['underline', 'bold']
                for extraAttribute in extraAttributes:
                    if extraAttribute not in attr:
                        attrOdd.append(extraAttribute)
            c = colored(c, fg, bg, attr)
        ret += c
        idx += 1
        
        # Add spacers, skip the last spacer if end of byte array
        if idx % bytesPerGroup == 0 and idx < bytesPerLine:
            ret += minorSpacer
    
    return f"|{ret}|"

# figure out which color setting is to be used for the byte
def getColorSetting(byte: int, printHighAscii: bool, colorSettings: dict) -> (str, str, str, str):
    if colorSettings is None:
        return None

    colorSetting = (None, None, None, None)
    
    # Find out which color setting to use.
    isPrintable = len(repr(chr(byte))) == 3 or repr(chr(byte)) == '\'\\\\\''
    isHighAscii = byte >= 0x80
    isControl = byte < 0x20
    isDigit = ord('0') <= byte <= ord('9')
    isLetter = (ord('a') <= byte <= ord('z')) or (ord('A') <= byte <= ord('Z'))
    
    # Find out which color setting to use.
    colorSettingKey = None
    if byte == 0x00:
        # null byte
        colorSettingKey = EColorSettingKey.NULL_BYTE
    elif byte == 0x20:
        # space
        colorSettingKey = EColorSettingKey.SPACE
    elif (not isPrintable and not isControl) or (not printHighAscii and isHighAscii):
        # non printable, non control
        colorSettingKey = EColorSettingKey.NON_PRINTABLE
    elif isPrintable and isHighAscii and printHighAscii:
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
        raise ValueError(f"Can't figure out which color setting to use for {byte:02X}")
    
    colorSetting = None if colorSettingKey not in colorSettings.keys() else colorSettings[colorSettingKey]
    if colorSetting is None:
        colorSetting = (None, None, None, None)
    
    return deepcopy(colorSetting)

def constructByteTotal(totalBytes: int, maxAddrLen: int, colorSettings: dict) -> str:
    maxAddr = constructAddress(totalBytes, maxAddrLen, colorSettings)
    majorSpacer = constructMajorSpacer('   ', colorSettings)
    totalBytesString = f"({totalBytes} Bytes)"
    if colorSettings is not None and EColorSettingKey.BYTE_TOTAL in colorSettings.keys():
        fg, bg, attr, _ = colorSettings[EColorSettingKey.BYTE_TOTAL]
        totalBytesString = colored(totalBytesString, fg, bg, attr)
    ret = f"{maxAddr}{majorSpacer}{totalBytesString}"
    return ret

