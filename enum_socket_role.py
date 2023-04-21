from enum import Enum, auto
import typing

class ESocketRole(Enum):
    SERVER = auto()
    CLIENT = auto()

    def __eq__(self, other: typing.Any) -> bool:
        if other is int:
            return self.value == other
        if other is str:
            return self.name == other
        if repr(type(self)) == repr(type(other)):
            return self.value == other.value
        return False

    def __gt__(self, other: typing.Any) -> bool:
        if other is int:
            return self.value > other
        if other is str:
            return self.name > other
        if repr(type(self)) == repr(type(other)):
            return self.value > other.value
        raise ValueError('Can not compare.')

    def __hash__(self):
        return hash(self.value)

