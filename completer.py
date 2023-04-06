import traceback
from readline_buffer_status import ReadlineBufferStatus as RBS

class Completer():
    def __init__(self, application, parser):
        self.application = application
        self.parser = parser

        self.candidates = []        # Functions append strings that would complete the current word here.
    
    # pylint: disable=unused-argument
    def complete(self, text: str, state: int) -> str:
        response = None
        try:
            # First tab press for this string (state is 0), build the list of candidates.
            if state == 0:
                # Get line buffer info
                rbs = self.application.getReadlineBufferStatus()

                self.candidates = []
                
                cmdDict = self.parser.commandDictionary

                if rbs.being_completed.startswith("!"):
                    # completing history substitution
                    self.getHistIdxCandidates(True, rbs)
                elif rbs.being_completed.startswith("$"):
                    # completing variable
                    self.getVariableCandidates(True, rbs)
                elif rbs.wordIdx == 0:
                    # Completing commands
                    for cmd in cmdDict:
                        if cmd.startswith(rbs.being_completed):
                            self.candidates.append(cmd)
                else:
                    # Completing command argument
                    if rbs.words[0] not in cmdDict.keys():
                        # Can't complete if command is invalid
                        return None
                    
                    # retrieve which completer functions are available
                    _, _, completerFunctionArray = cmdDict[rbs.words[0]]

                    if completerFunctionArray is None or len(completerFunctionArray) == 0:
                        # Can't complete if there is no completer function defined
                        # For example for commands without arguments
                        return None
                    
                    if rbs.wordIdx - 1 < len(completerFunctionArray):
                        # Use the completer function with the index of the current word.
                        # -1 for the command itself.
                        completerFunction = completerFunctionArray[rbs.wordIdx - 1]
                    else:
                        # Last completer will be used if currently completed word index is higher than
                        # the amount of completer functions defined for that command
                        completerFunction = completerFunctionArray[-1]

                    # Don't complete anything if there is no such function defined.
                    if completerFunction is None:
                        return None
                    
                    # Get candidates.
                    completerFunction(rbs)

            # Return the answer!
            try:
                response = self.candidates[state]
                # expand the history completion to the full line
                if len(self.candidates) == 1 and response is not None and len(response) > 0 and response[0] == "!":
                    histIdx = int(response[1:])
                    response = self.application.getHistoryItem(histIdx)
            except IndexError:
                response = None
        # pylint: disable=broad-except
        except Exception as e:
            print(e)
            print(traceback.format_exc())
        
        return response
    
    def getHistIdxCandidates(self, includePrefix: bool, rbs: RBS) -> None:
        # Complete possible values only if there is not a complete match.
        # If there is a complete match, return that one only.
        # For example if completing "!3" but "!30" and "!31" are also available
        # then return only "!3".

        historyLines = self.application.getHistoryLines()
        historyIndexes = list(idx for idx, _ in enumerate(historyLines))

        if len(rbs.being_completed) > (1 if includePrefix else 0):
            historyIdx = -1
            try:
                historyIdx = int(rbs.being_completed[(1 if includePrefix else 0):])
            except ValueError:
                pass
            
            # if there is a complete and valid (not None) match, return that match only.
            if historyIdx in historyIndexes \
                    and self.application.getHistoryItem(historyIdx) is not None \
                    and str(historyIdx) == rbs.being_completed[(1 if includePrefix else 0):]:
                if includePrefix:
                    self.candidates.append(rbs.being_completed)
                else:
                    self.candidates.append(rbs.being_completed[(1 if includePrefix else 0):])
                return

        # If there has not been a complete match, look for other matches.
        for historyIdx in historyIndexes:
            historyLine = self.application.getHistoryItem(historyIdx)
            if historyLine is None or historyLine == "":
                # Skip invalid options.
                continue

            if str(historyIdx).startswith(rbs.being_completed[(1 if includePrefix else 0):]):
                self.candidates.append(("!" if includePrefix else "") + str(historyIdx))
        return
    
    def getVariableCandidates(self, includePrefix: bool, rbs: RBS) -> None:
        # TODO: allow for $(varname) format also
        # make sure that $(varname)$(varname) also works.
        for variableName in self.application.getVariableNames():
            if (("$" if includePrefix else "") + variableName).startswith(rbs.being_completed):
                self.candidates.append(("$" if includePrefix else "") + variableName)
        return


