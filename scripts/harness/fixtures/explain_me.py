# Harness fixture (scenario S6): a short function to be explained.
def unique_in_order(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
