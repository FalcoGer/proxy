import traceback

class Completer():
    def __init__(self, application, parser):
        self.application = application
        self.readline = self.application.getReadlineModule()
        self.parser = parser

        self.origline = ""          # The whole line in the buffer
        self.begin = 0              # Index of the first character of the currently completed word
        self.end = 0                # Index of the last character of the currently completed word
        self.being_completed = ""   # The currently completed word
        self.words = []             # All words in the buffer.
        self.wordIdx = 0            # The index of the current word in the buffer
        
        self.candidates = []        # Functions append strings that would complete the current word here.
    
    # pylint: disable=unused-argument
    def complete(self, text: str, state: int) -> str:
        response = None
        try:
            # First tab press for this string (state is 0), build the list of candidates.
            if state == 0:
                # Get line buffer info
                self.origline = self.readline.get_line_buffer()
                self.begin = self.readline.get_begidx()
                self.end = self.readline.get_endidx()
                self.being_completed = self.origline[self.begin:self.end]
                self.words = self.origline.split(' ')
                self.wordIdx = self.getWordIdx()

                self.candidates = []
                
                cmdDict = self.parser.commandDictionary

                if self.being_completed.startswith("!"):
                    # completing history substitution
                    self.getHistIdxCandidates(True)
                elif self.being_completed.startswith("$"):
                    # completing variable
                    self.getVariableCandidates(True)
                elif self.wordIdx == 0:
                    # Completing commands
                    for cmd in cmdDict:
                        if cmd.startswith(self.being_completed):
                            self.candidates.append(cmd)
                else:
                    # Completing command argument
                    if self.words[0] not in cmdDict.keys():
                        # Can't complete if command is invalid
                        return None
                    
                    # retrieve which completer functions are available
                    _, _, completerFunctionArray = cmdDict[self.words[0]]

                    if completerFunctionArray is None or len(completerFunctionArray) == 0:
                        # Can't complete if there is no completer function defined
                        # For example for commands without arguments
                        return None
                    
                    if self.wordIdx - 1 < len(completerFunctionArray):
                        # Use the completer function with the index of the current word.
                        # -1 for the command itself.
                        completerFunction = completerFunctionArray[self.wordIdx - 1]
                    else:
                        # Last completer will be used if currently completed word index is higher than
                        # the amount of completer functions defined for that command
                        completerFunction = completerFunctionArray[-1]

                    # Don't complete anything if there is no such function defined.
                    if completerFunction is None:
                        return None
                    
                    # Get candidates.
                    completerFunction()

            # Return the answer!
            try:
                response = self.candidates[state]
                # expand the history completion to the full line
                if len(self.candidates) == 1 and response is not None and len(response) > 0 and response[0] == "!":
                    histIdx = int(response[1:])
                    response = self.readline.get_history_item(histIdx)
            except IndexError:
                response = None
        # pylint: disable=broad-except
        except Exception as e:
            print(e)
            print(traceback.format_exc())
        
        return response
    
    def getHistIdxCandidates(self, includePrefix: bool) -> None:
        # Complete possible values only if there is not a complete match.
        # If there is a complete match, return that one only.
        # For example if completing "!3" but "!30" and "!31" are also available
        # then return only "!3".

        historyIndexes = list(range(0, self.readline.get_current_history_length()))
        
        if len(self.being_completed) > (1 if includePrefix else 0):
            historyIdx = -1
            try:
                historyIdx = int(self.being_completed[(1 if includePrefix else 0):])
            except ValueError:
                pass
            
            # if there is a complete and valid (not None) match, return that match only.
            if historyIdx in historyIndexes \
                    and self.readline.get_history_item(historyIdx) is not None \
                    and str(historyIdx) == self.being_completed[(1 if includePrefix else 0):]:
                if includePrefix:
                    self.candidates.append(self.being_completed)
                else:
                    self.candidates.append(self.being_completed[(1 if includePrefix else 0):])
                return

        # If there has not been a complete match, look for other matches.
        for historyIdx in historyIndexes:
            historyLine = self.readline.get_history_item(historyIdx)
            if historyLine is None or historyLine == "":
                # Skip invalid options.
                continue

            if str(historyIdx).startswith(self.being_completed[(1 if includePrefix else 0):]):
                self.candidates.append(("!" if includePrefix else "") + str(historyIdx))
        return
    
    def getVariableCandidates(self, includePrefix: bool) -> None:
        # TODO: allow for $(varname) format also
        for variableName in self.application.variables.keys():
            if (("$" if includePrefix else "") + variableName).startswith(self.being_completed):
                self.candidates.append(("$" if includePrefix else "") + variableName)
        return

    def getWordIdx(self) -> int:
        # Which word are we currently completing
        wordIdx = 0
        for idx in range(self.begin - 1, -1, -1):
            if self.origline[idx] == ' ':
                wordIdx += 1
        return wordIdx

