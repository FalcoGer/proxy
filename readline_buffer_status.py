class ReadlineBufferStatus():
    def __init__(self, readlineModule):
        self._readlineModule = readlineModule
        self.update()
        return

    def update(self) -> None:
        # This containes the whole line in the line buffer
        self.origline           = self._readlineModule.get_line_buffer()

        # This is the index of the first character in the line buffer that is considered for completion
        self.begin              = self._readlineModule.get_begidx()

        # This is the index of the last character in the line buffer that is considered for completion
        self.end                = self._readlineModule.get_endidx()
        # For example "wordone wordtwo wordth[tab] more words here"
        #                              ^ begin
        #                                   ^ end
        # This is the whole word that is being considered for completion
        self.being_completed    = self.origline[self.begin : self.end]
        # being_completed = "wordth"
        self.words              = self.origline.split(' ')

        # The word index in the line, in the example it's 3.
        self.wordIdx            = self._getWordIdx()
        return

    def _getWordIdx(self) -> int:
        # Which word are we currently completing
        # Words based on spaces, not readline separators
        
        if self.begin == 0:
            return 0

        if self.begin > len(self.origline):
            # readline.get_beginidx only updates when completion is requested
            # return 0 to avoid index error
            return 0

        wordIdx = 0
        # Walk backwards through the line and count spaces.
        for idx in range(self.begin - 1, -1, -1):
            if self.origline[idx] == ' ':
                wordIdx += 1
        return wordIdx

