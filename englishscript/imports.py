def import_parts(tokens):
    end = len(tokens)
    while end and (tokens[end - 1].kind == "END" or tokens[end - 1].text == "."):
        end -= 1
    if not end:
        return None
    nouns = ("chapter", "chapters", "library", "libraries")
    marker = None
    if tokens[end - 1].low in nouns:
        marker = end - 1
    elif tokens[end - 1].low == "book":
        for i in range(1, end - 3):
            if tokens[i].low in ("chapter", "chapters") and tokens[i + 1].low == "of" and tokens[i + 2].low == "the":
                marker = i
                break
    if marker is None or marker == 0:
        return None
    kind = tokens[marker].low
    book = tokens[marker + 3:end - 1] if marker + 1 < end else []
    groups = [[]]
    error = None
    if kind in ("chapters", "libraries"):
        i = 0
        while i < marker:
            token = tokens[i]
            if token.text == "," or token.low == "and":
                if not groups[-1]:
                    error = token
                    break
                groups.append([])
                if token.text == "," and i + 1 < marker and tokens[i + 1].low == "and":
                    i += 1
            elif token.kind.lower() == "word":
                groups[-1].append(token)
            else:
                error = token
                break
            i += 1
        if error is None and not groups[-1]:
            error = tokens[marker - 1]
        if error is None and len(groups) < 2:
            error = tokens[marker]
    else:
        groups = [tokens[:marker]]
    return kind, groups, book, marker, error
