"""Original seed problems for the Arena. Each must pass differential verification
before it is published (see scripts/verify_seed_problems.py)."""

from reps_api.verification.coding_engine import CodingProblemSpec

LONGEST_BUDGET_WINDOW = CodingProblemSpec(
    title="Longest Study Streak on a Budget",
    pattern="sliding window",
    difficulty="medium",
    statement=(
        "minutes[i] is how long you studied on day i. You can only count a run of "
        "consecutive days if its total is at most budget. Return the length of the "
        "longest such run (0 if none)."
    ),
    signature="def solve(minutes: list[int], budget: int) -> int",
    reference_solution="""
def solve(minutes, budget):
    best = 0
    left = 0
    total = 0
    for right, m in enumerate(minutes):
        total += m
        while total > budget and left <= right:
            total -= minutes[left]
            left += 1
        best = max(best, right - left + 1)
    return best
""",
    brute_force_solution="""
def solve(minutes, budget):
    n = len(minutes)
    longest = 0
    for i in range(n):
        for j in range(i, n):
            if sum(minutes[i:j + 1]) <= budget:
                longest = max(longest, j - i + 1)
    return longest
""",
    generator="""
def generate(rng):
    n = rng.randint(0, 25)
    return [[rng.randint(0, 50) for _ in range(n)], rng.randint(0, 200)]
""",
    edge_cases=[[[], 10], [[5], 4], [[5], 5], [[0, 0, 0], 0], [[100, 1, 1, 1], 2]],
    public_examples=[[[30, 10, 20, 50, 5], 60], [[90, 90], 50]],
)

ISLAND_GROUPS = CodingProblemSpec(
    title="Count the Study Groups",
    pattern="graphs",
    difficulty="medium",
    statement=(
        "There are n students labeled 0..n-1. pairs lists who studies with whom "
        "(the relation is symmetric). Students connected through any chain of pairs "
        "are in the same group. Return the number of groups."
    ),
    signature="def solve(n: int, pairs: list[list[int]]) -> int",
    reference_solution="""
def solve(n, pairs):
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    groups = n
    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            groups -= 1
    return groups
""",
    brute_force_solution="""
def solve(n, pairs):
    adjacency = {i: set() for i in range(n)}
    for a, b in pairs:
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen = set()
    count = 0
    for start in range(n):
        if start in seen:
            continue
        count += 1
        stack = [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(adjacency[node] - seen)
    return count
""",
    generator="""
def generate(rng):
    n = rng.randint(1, 20)
    m = rng.randint(0, n * 2)
    return [n, [[rng.randrange(n), rng.randrange(n)] for _ in range(m)]]
""",
    edge_cases=[[1, []], [3, []], [2, [[0, 0]]], [4, [[0, 1], [1, 2], [2, 3]]]],
    public_examples=[[5, [[0, 1], [1, 2], [3, 4]]], [3, []]],
)

FEWEST_PROBLEM_SETS = CodingProblemSpec(
    title="Fewest Problem Sets",
    pattern="dynamic programming",
    difficulty="medium",
    statement=(
        "Problem sets come in the sizes listed in sizes (unlimited copies of each). "
        "Return the fewest sets that add up to exactly target problems, or -1 if it "
        "can't be done."
    ),
    signature="def solve(sizes: list[int], target: int) -> int",
    reference_solution="""
def solve(sizes, target):
    INF = float("inf")
    best = [0] + [INF] * target
    for amount in range(1, target + 1):
        for s in sizes:
            if s <= amount and best[amount - s] + 1 < best[amount]:
                best[amount] = best[amount - s] + 1
    return -1 if best[target] == INF else best[target]
""",
    brute_force_solution="""
from collections import deque

def solve(sizes, target):
    if target == 0:
        return 0
    seen = {0}
    queue = deque([(0, 0)])
    while queue:
        total, used = queue.popleft()
        for s in sizes:
            nxt = total + s
            if nxt == target:
                return used + 1
            if nxt < target and nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, used + 1))
    return -1
""",
    generator="""
def generate(rng):
    sizes = sorted({rng.randint(1, 12) for _ in range(rng.randint(1, 4))})
    return [sizes, rng.randint(0, 60)]
""",
    edge_cases=[[[1], 0], [[2], 3], [[5, 3], 7], [[7], 7]],
    public_examples=[[[1, 3, 4], 6], [[2], 3]],
)

PAIR_UP = CodingProblemSpec(
    title="Pair Up for the Project",
    pattern="two pointers",
    difficulty="easy",
    statement=("skills is sorted in non-decreasing order. Count the pairs of positions i < j where skills[i] + skills[j] equals target exactly."),
    signature="def solve(skills: list[int], target: int) -> int",
    reference_solution="""
def solve(skills, target):
    lo, hi = 0, len(skills) - 1
    pairs = 0
    while lo < hi:
        s = skills[lo] + skills[hi]
        if s < target:
            lo += 1
        elif s > target:
            hi -= 1
        elif skills[lo] == skills[hi]:
            n = hi - lo + 1
            pairs += n * (n - 1) // 2
            break
        else:
            left_run = 1
            while lo + left_run < hi and skills[lo + left_run] == skills[lo]:
                left_run += 1
            right_run = 1
            while hi - right_run > lo and skills[hi - right_run] == skills[hi]:
                right_run += 1
            pairs += left_run * right_run
            lo += left_run
            hi -= right_run
    return pairs
""",
    brute_force_solution="""
def solve(skills, target):
    count = 0
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            if skills[i] + skills[j] == target:
                count += 1
    return count
""",
    generator="""
def generate(rng):
    n = rng.randint(0, 20)
    return [sorted(rng.randint(-10, 10) for _ in range(n)), rng.randint(-15, 15)]
""",
    edge_cases=[[[], 0], [[5], 10], [[2, 2, 2, 2], 4], [[1, 1, 3, 3], 4], [[-3, 0, 3], 0]],
    public_examples=[[[1, 2, 3, 4, 5], 6], [[2, 2, 2], 4]],
)

FIRST_PASSING = CodingProblemSpec(
    title="First Passing Score",
    pattern="binary search",
    difficulty="easy",
    statement=("scores is sorted in non-decreasing order. Return the index of the first score that is at least cutoff, or -1 if no score passes. Aim for O(log n)."),
    signature="def solve(scores: list[int], cutoff: int) -> int",
    reference_solution="""
def solve(scores, cutoff):
    lo, hi = 0, len(scores)
    while lo < hi:
        mid = (lo + hi) // 2
        if scores[mid] >= cutoff:
            hi = mid
        else:
            lo = mid + 1
    return lo if lo < len(scores) else -1
""",
    brute_force_solution="""
def solve(scores, cutoff):
    for index, value in enumerate(scores):
        if value >= cutoff:
            return index
    return -1
""",
    generator="""
def generate(rng):
    n = rng.randint(0, 30)
    return [sorted(rng.randint(0, 100) for _ in range(n)), rng.randint(-5, 105)]
""",
    edge_cases=[[[], 50], [[70], 70], [[70], 71], [[60, 60, 60], 60], [[1, 2, 3], 0]],
    public_examples=[[[42, 55, 61, 61, 90], 60], [[10, 20], 95]],
)

BALANCED_NOTES = CodingProblemSpec(
    title="Balanced Margin Notes",
    pattern="stacks",
    difficulty="easy",
    statement=("s contains only the characters ()[]{}. Return True if every bracket is closed by the matching type in the right order, otherwise False."),
    signature="def solve(s: str) -> bool",
    reference_solution="""
def solve(s):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for ch in s:
        if ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
        else:
            stack.append(ch)
    return not stack
""",
    brute_force_solution="""
def solve(s):
    previous = None
    while previous != s:
        previous = s
        s = s.replace("()", "").replace("[]", "").replace("{}", "")
    return s == ""
""",
    generator="""
def generate(rng):
    n = rng.randint(0, 12)
    if rng.random() < 0.5:
        out = []
        opens = []
        for _ in range(n):
            if opens and rng.random() < 0.5:
                out.append({"(": ")", "[": "]", "{": "}"}[opens.pop()])
            else:
                ch = rng.choice("([{")
                opens.append(ch)
                out.append(ch)
        while opens and rng.random() < 0.8:
            out.append({"(": ")", "[": "]", "{": "}"}[opens.pop()])
        return ["".join(out)]
    return ["".join(rng.choice("()[]{}") for _ in range(n))]
""",
    edge_cases=[[""], ["("], [")"], ["([)]"], ["{[()]}"], ["(()"]],
    public_examples=[["([]{})"], ["(]"]],
)

SEED_PROBLEMS = [PAIR_UP, FIRST_PASSING, BALANCED_NOTES, LONGEST_BUDGET_WINDOW, ISLAND_GROUPS, FEWEST_PROBLEM_SETS]
