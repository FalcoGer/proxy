from __future__ import annotations
import typing

import traceback

import prompt_toolkit as pt
from prompt_toolkit.completion import Completer, Completion
from buffer_status import BufferStatus

if typing.TYPE_CHECKING:
    from application import Application
    from core_parser import Parser, CommandDictType
    from prompt_toolkit.document import Document

class CustomCompleter(Completer):
    def __init__(self, application: Application, parser: Parser):
        self.application = application
        self.parser = parser

        self.candidates: list[str] = []        # Functions append strings that would complete the current word here.
        return

    # pylint: disable=unused-argument
    def get_completions(self, document: Document, complete_event: pt.completion.base.CompleteEvent) -> Completion:
        try:
            cmdDict: CommandDictType = self.parser.commandDictionary
            bufferStatus: BufferStatus = BufferStatus(document)

            self.candidates = []

            prevChar = None
            if bufferStatus.begin > 0:
                prevChar = document.current_line[bufferStatus.begin - 1]

            if bufferStatus.being_completed.startswith('!'):
                # completing history substitution
                self.getHistIdxCandidates(True, document)
            elif prevChar == '!':
                # completing history substitution
                self.getHistIdxCandidates(False, document)
            elif bufferStatus.being_completed.startswith('$'):
                # completing variable
                self.getVariableCandidates(True, bufferStatus)
            elif bufferStatus.wordIdx == 0:
                # Completing commands
                for cmd in cmdDict:
                    if cmd.startswith(bufferStatus.being_completed):
                        self.candidates.append(cmd)
            else:
                # Completing command argument
                if bufferStatus.words[0] not in cmdDict.keys():
                    # Can't complete if command is invalid
                    return None

                # retrieve which completer functions are available
                _, _, completerFunctionArray = cmdDict[bufferStatus.words[0]]

                if completerFunctionArray is None or len(completerFunctionArray) == 0:
                    # Can't complete if there is no completer function defined
                    # For example for commands without arguments
                    return None

                if bufferStatus.wordIdx - 1 < len(completerFunctionArray):
                    # Use the completer function with the index of the current word.
                    # -1 for the command itself.
                    completerFunction = completerFunctionArray[bufferStatus.wordIdx - 1]
                else:
                    # Last completer will be used if currently completed word index is higher than
                    # the amount of completer functions defined for that command
                    completerFunction = completerFunctionArray[-1]

                # Don't complete anything if there is no such function defined.
                if completerFunction is None:
                    return None

                # Get candidates.
                completerFunction(bufferStatus)

            # Return the answer!
            try:
                pos, _ = document.find_boundaries_of_current_word()
                # expand the history completion to the full line

                if len(self.candidates) == 1 and self.candidates[0] is not None and prevChar == '!':
                    histIdx = int(self.candidates[0])
                    yield Completion(text=self.application.getHistoryItem(histIdx), start_position=pos - 1)
                else:
                    for candidate in self.candidates:
                        yield Completion(text=candidate, start_position=pos)
                return None
            except IndexError:
                return None
            # pylint: disable=broad-except
        except Exception as e:
            print(e)
            print(traceback.format_exc())

        return None

    def getHistIdxCandidates(self, includePrefix: bool, document: Document) -> typing.NoReturn:
        # Complete possible values only if there is not a complete match.
        # If there is a complete match, return that one only.
        # For example if completing '!3' but '!30' and '!31' are also available
        # then return only '!3'.

        bufferStatus = BufferStatus(document)

        historyLines = self.application.getHistoryList()
        historyIndexes = list(idx for idx, _ in enumerate(historyLines))

        if len(bufferStatus.being_completed) > (1 if includePrefix else 0):
            historyIdx = -1
            try:
                historyIdx = int(bufferStatus.being_completed[(1 if includePrefix else 0):])
            except ValueError:
                pass

            # if there is a complete and valid (not None) match, return that match only.
            if historyIdx in historyIndexes \
                    and self.application.getHistoryItem(historyIdx) is not None \
                    and str(historyIdx) == bufferStatus.being_completed[(1 if includePrefix else 0):]:
                if includePrefix:
                    self.candidates.append(bufferStatus.being_completed)
                else:
                    self.candidates.append(bufferStatus.being_completed[(1 if includePrefix else 0):])
                return

        # If there has not been a complete match, look for other matches.
        for historyIdx in historyIndexes:
            historyLine = self.application.getHistoryItem(historyIdx)
            if historyLine is None or len(historyLine) == 0:
                # Skip invalid options.
                continue

            if str(historyIdx).startswith(bufferStatus.being_completed[(1 if includePrefix else 0):]):
                self.candidates.append(('!' if includePrefix else '') + str(historyIdx))
        return

    def getVariableCandidates(self, includePrefix: bool, bufferStatus: BufferStatus) -> typing.NoReturn:
        # TODO: allow for $(varname) format also
        # make sure that $(varname)$(varname) also works.
        for variableName in self.application.getVariableNames():
            if (('$' if includePrefix else '') + variableName).startswith(bufferStatus.being_completed):
                self.candidates.append(('$' if includePrefix else '') + variableName)
        return


