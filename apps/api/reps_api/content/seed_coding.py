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

SEED_PROBLEMS = [LONGEST_BUDGET_WINDOW, ISLAND_GROUPS, FEWEST_PROBLEM_SETS]
