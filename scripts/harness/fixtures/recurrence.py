# Harness fixture (scenario S5/S8). An IRREGULAR recurrence on purpose: its
# value cannot be read off the code, so a correct answer is evidence of a run.
def f(n):
    a, b = 1, 1
    for i in range(n):
        a, b = b, (a * 31 + b * 17 + i) % 1009
    return a
