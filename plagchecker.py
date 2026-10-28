from difflib import SequenceMatcher

with open('pg1.txt') as onef , open('pg2.txt') as twof:
    file1 = onef.read()
    file2 = twof.read()

    matchcheck = SequenceMatcher(None,file1,file2).ratio()

    print(f"ur plag rate is {matchcheck}")



