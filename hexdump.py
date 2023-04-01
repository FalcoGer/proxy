from enum import Enum, auto
from copy import deepcopy

_colorAvailable = False

try:
    from termcolor import colored
    _colorAvailable = True
except Exception:
    pass

class EColorSettingKey(Enum):
    # For formatting:
    spacerMajor = auto()            # spacer between address, hex and printable sections, also
    spacerMinor = auto()            # spacer between byte groups
    address = auto()                # address at start of line
    byteTotal = auto()              # color of the byte total at the end
    
    # For data:
    digits = auto()                 # ascii digits
    letters = auto()                # ascii letters (a-z, A-Z)
    printable = auto()              # other ascii characters
    space = auto()                  # space character (0x20)
    printableHighAscii = auto()     # printable, but value > 127
    control = auto()                # ascii control characters (below 0x20)
    nonprintable = auto()           # everything else
    
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

    global _colorAvailable
    if not _colorAvailable:
        colorSettings = None
    elif colorSettings is None:
        # color available but not set
        colorSettings = {}
        # Formatting
        colorSettings[EColorSettingKey.address]             = ("yellow", None, ['bold'], None)
        colorSettings[EColorSettingKey.spacerMajor]         = (None, None, [], None)
        colorSettings[EColorSettingKey.spacerMinor]         = (None, None, [], None)
        colorSettings[EColorSettingKey.byteTotal]           = (None, None, ['bold', 'underline'], None)
        # Data
        colorSettings[EColorSettingKey.control]             = ("magenta", None, [], ['dark'])
        colorSettings[EColorSettingKey.digits]              = ("blue", None, [], ['dark'])
        colorSettings[EColorSettingKey.letters]             = ("green", None, [], ['dark'])
        colorSettings[EColorSettingKey.printable]           = ("cyan", None, [], ['dark'])
        colorSettings[EColorSettingKey.space]               = ("green", None, ['underline'], ['underline'])
        colorSettings[EColorSettingKey.printableHighAscii]  = ("yellow", None, [], ['dark'])
        colorSettings[EColorSettingKey.nonprintable]        = ("red", None, [], ['dark'])

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
    if colorSettings is not None and EColorSettingKey.address in colorSettings.keys():
        fg, bg, attr, _ = colorSettings[EColorSettingKey.address]
        addrString = colored(addrString, fg, bg, attr)
    return addrString

def constructMinorSpacer(spacerStr: str, colorSettings: dict) -> str:
    if colorSettings is None or EColorSettingKey.spacerMinor not in colorSettings.keys():
        return spacerStr
    else:
        fg, bg, attr, _ = colorSettings[EColorSettingKey.spacerMinor]
        return colored(spacerStr, fg, bg, attr)

def constructMajorSpacer(spacerStr: str, colorSettings: dict) -> str:
    if colorSettings is None or EColorSettingKey.spacerMinor not in colorSettings.keys():
        return spacerStr
    else:
        fg, bg, attr, _ = colorSettings[EColorSettingKey.spacerMinor]
        return colored(spacerStr, fg, bg, attr)

def constructHexString(byteArray: bytes, bytesPerLine: int, bytesPerGroup: int, printHighAscii: bool, colorSettings: dict) -> str:
    ret = ""
    minorSpacerStr = ' '
    lenMinorSpacerStr = len(minorSpacerStr)
    minorSpacer = constructMinorSpacer(minorSpacerStr, colorSettings)
    numMinorSpacers = 0

    idx = 0
    for b in byteArray:
        byteRepr = f"{b:02X}"
        if colorSettings is not None:
            fg, bg, attrOdd, attrEven = getColorSetting(b, printHighAscii, colorSettings)
            byteRepr = colored(byteRepr, fg, bg, attrEven if idx % 2 == 0 else attrOdd)
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
            if c == '_':
                if attrOdd is None:
                    attrOdd = []
                if attrEven is None:
                    attrEven = []
                extraAttributes = ['underline', 'bold']
                for extraAttribute in extraAttributes:
                    if extraAttribute not in attrOdd:
                        attrOdd.append(extraAttribute)
                    if extraAttribute not in attrEven:
                        attrEven.append(extraAttribute)
            c = colored(c, fg, bg, attrEven if idx % 2 == 0 else attrOdd)
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
    isDigit = byte >= ord('0') and byte <= ord('9')
    isLetter = (byte >= ord('a') and byte <= ord('z')) or (byte >= ord('A') and byte <= ord('Z'))
    
    # Find out which color setting to use.
    colorSettingKey = None
    if (not isPrintable and not isControl) or (not printHighAscii and isHighAscii):
        # non printable, non control
        colorSettingKey = EColorSettingKey.nonprintable
    elif isPrintable and isHighAscii and printHighAscii:
        # printable high ascii
        colorSettingKey = EColorSettingKey.printableHighAscii
    elif isControl:
        # control
        colorSettingKey = EColorSettingKey.control
    elif isDigit:
        # printable, digit
        colorSettingKey = EColorSettingKey.digits
    elif byte == 0x20:
        # space
        colorSettingKey = EColorSettingKey.space
    elif isLetter:
        # printable, letter
        colorSettingKey = EColorSettingKey.letters
    elif isPrintable:
        # other printable
        colorSettingKey = EColorSettingKey.printable
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
    if colorSettings is not None and EColorSettingKey.byteTotal in colorSettings.keys():
        fg, bg, attr, _ = colorSettings[EColorSettingKey.byteTotal]
        totalBytesString = colored(totalBytesString, fg, bg, attr)
    ret = f"{maxAddr}{majorSpacer}{totalBytesString}"
    return ret

