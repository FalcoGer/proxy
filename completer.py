import os
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
                    # Completing arguments
                    self.getCommandCandidates()
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
            except IndexError as e:
                response = None
        except Exception as e:
            print(e)
            print(traceback.format_exc())
        
        # print(f"Completion.\n  stage: {state}\n  response: {response}\n  candidates: {self.candidates}\n  being_completed: {self.being_completed}\n  origline: {self.origline}\n  start/end: {self.begin}/{self.end}\n")

        return response

    def getCommandCandidates(self) -> None:
        self.candidates.extend( [
                s
                for s in self.parser.commandDictionary.keys()
                if s and s.startswith(self.being_completed)
            ]
        )
        return

    def getHistoryCandidates(self) -> None:
        # Get candidates from the history
        history = [self.readline.get_history_item(i) for i in range(0, self.readline.get_current_history_length())]
        for historyline in history:
            if historyline is None or historyline == "":
                continue
            
            # Get the whole line.
            if historyline.startswith(self.origline):
                # Must only append to the part that is currently being completed
                # otherwise the whole line may be added again.
                self.candidates.append(historyline[self.begin:])
            
        return
    
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
            except ValueError as e:
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
        for variableName in self.application.variables.keys():
            if (("$" if includePrefix else "") + variableName).startswith(self.being_completed):
                self.candidates.append(("$" if includePrefix else "") + variableName)
        return

    def getSettingsCandidates(self) -> None:
        for settingName in [x.name for x in self.parser.getSettingKeys()]:
            if settingName.startswith(self.being_completed):
                self.candidates.append(settingName)
        return

    def getFileCandidates(self) -> None:
        # FIXME: fix completion for paths with spaces
        
        # Append candidates for files
        # Find which word we are current completing
        word = self.words[self.getWordIdx()]
        
        # Find which directory we are in
        directory = "./"
        filenameStart = ""
        if word:
            # There is at least some text being completed.
            if word.find("/") >= 0:
                # There is a path delimiter in the string, we need to assign the directory and the filename start both.
                directory = word[:word.rfind("/")] + "/"
                filenameStart = word[word.rfind("/") + 1:]
            else:
                # There is no path delimiters in the string. We're only searching the current directory for the file name.
                filenameStart = word
                
        # Find all files and directories in that directory
        if os.path.isdir(directory):
            files = os.listdir(directory)
            # Find which of those files matches the end of the path
            for file in files:
                if os.path.isdir(os.path.join(directory, file)):
                    file += "/"
                if file.startswith(filenameStart):
                    self.candidates.append(file)
        return

    def getWordIdx(self) -> int:
        # Which word are we currently completing
        wordIdx = 0
        for idx in range(self.begin - 1, -1, -1):
            if self.origline[idx] == ' ':
                wordIdx += 1
        return wordIdx

