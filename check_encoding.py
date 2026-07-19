with open('src/governance/transformer.py', 'rb') as f:
    lines = f.readlines()
    for i, line in enumerate(lines[69:75], 70):
        print(f'{i}: {repr(line)}')
