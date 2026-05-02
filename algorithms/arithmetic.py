from collections import Counter

def get_probabilities(text):
    total = len(text)
    freq = Counter(text)
    return {k: v / total for k, v in freq.items()}


def get_ranges(probs):
    ranges = {}
    low = 0.0

    for char in sorted(probs):
        high = low + probs[char]
        ranges[char] = (low, high)
        low = high

    return ranges


def encode(text):
    probs = get_probabilities(text)
    ranges = get_ranges(probs)

    low, high = 0.0, 1.0
    steps = []

    for ch in text:
        r_low, r_high = ranges[ch]
        range_width = high - low

        new_high = low + range_width * r_high
        new_low = low + range_width * r_low

        low, high = new_low, new_high
        steps.append((ch, low, high))

    value = (low + high) / 2
    return value, ranges, steps


def decode(value, ranges, length):
    result = ""

    for _ in range(length):
        for ch, (low, high) in ranges.items():
            if low <= value < high:
                result += ch
                value = (value - low) / (high - low)
                break

    return result