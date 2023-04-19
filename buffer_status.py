from __future__ import annotations
import typing

if typing.TYPE_CHECKING:
    from prompt_toolkit.document import Document


class BufferStatus():
    def __init__(self, doc: Document):
        self._doc = doc

        # This containes the whole line in the line buffer
        self.origline           = self._doc.current_line

        self.cursorPos          = self._doc.cursor_position
        # This is the index of the first character in the line buffer that is considered for completion
        # This is the index of the last character in the line buffer that is considered for completion
        self.begin, self.end    = self._doc.find_boundaries_of_current_word()
        self.begin += self.cursorPos
        self.end += self.cursorPos

        # For example 'wordone wordtwo wordth[tab] more words here'
        #                              ^ begin
        #                                   ^ end
        # This is the whole word that is being considered for completion
        self.being_completed    = self.origline[self.begin : self.end]
        # being_completed = 'wordth'
        self.words              = self.origline.split(' ')

        # The word index in the line, in the example it's 3.
        self.wordIdx            = self._getWordIdx()
        return

    def __str__(self) -> str:
        return f'{self.origline=}\n{self.begin=}\n{self.end=}\n{self.being_completed=}\n{self.wordIdx=}'

    def getDocument(self) -> Document:
        return self._doc

    def _getWordIdx(self) -> int:
        # Which word are we currently completing
        # Words based on spaces, not completion separators

        if self.begin == 0:
            return 0

        if self.begin > len(self.origline):
            # begin only updates when completion is requested
            # return 0 to avoid index error
            return 0

        wordIdx = 0
        # Walk backwards through the line and count spaces.
        for idx in range(self.begin - 1, -1, -1):
            if self.origline[idx] == ' ':
                wordIdx += 1
        return wordIdx

