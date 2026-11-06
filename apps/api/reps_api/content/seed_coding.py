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
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(7)
    return [[rng.randint(0, 50) for _ in range(100_000)], 5_000]
""",
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
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(7)
    n = 200_000
    return [n, [[rng.randrange(n), rng.randrange(n)] for _ in range(300_000)]]
""",
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
    scale_generator="""
def generate_large():
    return [[7, 13, 29, 31], 200_000]
""",
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
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(7)
    return [sorted(rng.randint(-1_000_000, 1_000_000) for _ in range(200_000)), 0]
""",
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
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(7)
    scores = sorted(rng.randint(0, 10_000_000) for _ in range(1_000_000))
    return [scores, scores[900_000]]
""",
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
    scale_generator="""
def generate_large():
    return ["(" * 100_000 + ")" * 100_000]
""",
)

BEST_STUDY_STRETCH = CodingProblemSpec(
    title="Best Study Stretch",
    pattern="dynamic programming",
    difficulty="medium",
    statement=(
        "focus holds your focus score for each half hour of a study day. Scores can be negative when you got distracted. "
        "Return the largest total of any non-empty run of consecutive half hours. (Known elsewhere as maximum subarray.) Aim for O(n)."
    ),
    signature="def solve(focus: list[int]) -> int",
    reference_solution="""
def solve(focus):
    best = current = focus[0]
    for x in focus[1:]:
        current = max(x, current + x)
        best = max(best, current)
    return best
""",
    brute_force_solution="""
def solve(focus):
    best = None
    for i in range(len(focus)):
        total = 0
        for j in range(i, len(focus)):
            total += focus[j]
            if best is None or total > best:
                best = total
    return best
""",
    generator="""
def generate(rng):
    n = rng.randint(1, 30)
    return [[rng.randint(-20, 20) for _ in range(n)]]
""",
    edge_cases=[[[5]], [[-3]], [[-8, -2, -5]], [[0, 0, 0]], [[2, -1, 2, -1, 2]]],
    public_examples=[[[-2, 3, 4, -1, 2, -6, 5]], [[-4, -1, -7]]],
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(11)
    return [[rng.randint(-1000, 1000) for _ in range(300_000)]]
""",
)

LONGEST_FRESH_RUN = CodingProblemSpec(
    title="Longest Fresh Run",
    pattern="sliding window",
    difficulty="medium",
    statement=(
        "s is the sequence of flashcard tags you reviewed, one character per card. Return the length of the longest stretch "
        "of consecutive cards with no tag repeated. (Known elsewhere as longest substring without repeating characters.) Aim for O(n)."
    ),
    signature="def solve(s: str) -> int",
    reference_solution="""
def solve(s):
    last = {}
    start = best = 0
    for i, ch in enumerate(s):
        if ch in last and last[ch] >= start:
            start = last[ch] + 1
        last[ch] = i
        best = max(best, i - start + 1)
    return best
""",
    brute_force_solution="""
def solve(s):
    best = 0
    for i in range(len(s)):
        seen = set()
        for j in range(i, len(s)):
            if s[j] in seen:
                break
            seen.add(s[j])
            best = max(best, j - i + 1)
    return best
""",
    generator="""
def generate(rng):
    n = rng.randint(0, 30)
    alphabet = "abcdefgh"[: rng.randint(1, 8)]
    return ["".join(rng.choice(alphabet) for _ in range(n))]
""",
    edge_cases=[[""], ["a"], ["aaaa"], ["abcdef"], ["abba"], ["dvdf"]],
    public_examples=[["abcabcbb"], ["pwwkew"]],
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(5)
    return ["".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(400_000))]
""",
)

MERGE_STUDY_BLOCKS = CodingProblemSpec(
    title="Merge Study Blocks",
    pattern="intervals",
    difficulty="medium",
    statement=(
        "blocks is a list of [start, end] study sessions in minutes, in any order. Sessions that overlap or touch "
        "(one ends exactly when the next starts) count as one block. Return the merged blocks sorted by start time."
    ),
    signature="def solve(blocks: list[list[int]]) -> list[list[int]]",
    reference_solution="""
def solve(blocks):
    merged = []
    for start, end in sorted(blocks):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
""",
    brute_force_solution="""
def solve(blocks):
    minutes = set()
    edges = set()
    for start, end in blocks:
        edges.add((start, end))
        for m in range(start, end):
            minutes.add(m)
    points = sorted(minutes)
    result = []
    for m in points:
        if result and m <= result[-1][1]:
            result[-1][1] = max(result[-1][1], m + 1)
        else:
            result.append([m, m + 1])
    # zero-length blocks still appear on their own unless they touch another block
    for start, end in sorted(edges):
        if start == end and not any(a <= start <= b for a, b in result):
            result.append([start, end])
    return sorted(result)
""",
    generator="""
def generate(rng):
    n = rng.randint(0, 9)
    blocks = []
    for _ in range(n):
        a = rng.randint(0, 40)
        blocks.append([a, a + rng.randint(1, 12)])
    return [blocks]
""",
    edge_cases=[[[]], [[[1, 3]]], [[[1, 3], [3, 5]]], [[[5, 8], [1, 2]]], [[[1, 10], [2, 3], [4, 5]]]],
    public_examples=[[[[1, 3], [2, 6], [8, 10], [15, 18]]], [[[1, 4], [4, 5]]]],
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(9)
    blocks = []
    for _ in range(200_000):
        a = rng.randint(0, 10_000_000)
        blocks.append([a, a + rng.randint(1, 60)])
    return [blocks]
""",
)

STREAK_SUMS = CodingProblemSpec(
    title="Streaks That Hit the Goal",
    pattern="prefix sums",
    difficulty="medium",
    statement=(
        "points[i] is the XP you earned on day i (it can be negative after a penalty). Count how many runs of one or more "
        "consecutive days add up to exactly goal. Aim for O(n)."
    ),
    signature="def solve(points: list[int], goal: int) -> int",
    reference_solution="""
def solve(points, goal):
    seen = {0: 1}
    total = count = 0
    for p in points:
        total += p
        count += seen.get(total - goal, 0)
        seen[total] = seen.get(total, 0) + 1
    return count
""",
    brute_force_solution="""
def solve(points, goal):
    count = 0
    for i in range(len(points)):
        total = 0
        for j in range(i, len(points)):
            total += points[j]
            if total == goal:
                count += 1
    return count
""",
    generator="""
def generate(rng):
    n = rng.randint(0, 25)
    return [[rng.randint(-5, 8) for _ in range(n)], rng.randint(-5, 15)]
""",
    edge_cases=[[[], 0], [[0, 0, 0], 0], [[5], 5], [[1, -1, 1, -1], 0], [[3, 4, 7], 7]],
    public_examples=[[[1, 1, 1], 2], [[1, 2, 3], 3]],
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(11)
    return [[rng.randint(-20, 30) for _ in range(300_000)], 50]
""",
)

WEAKEST_TOPICS = CodingProblemSpec(
    title="Weakest Topics First",
    pattern="heap",
    difficulty="easy",
    statement=(
        "mastery[i] is your mastery score for topic i. Return the indices of the k weakest topics, weakest first. "
        "When two topics tie, the lower index comes first. If k is larger than the number of topics, return them all."
    ),
    signature="def solve(mastery: list[int], k: int) -> list[int]",
    reference_solution="""
def solve(mastery, k):
    import heapq
    return [i for _, i in heapq.nsmallest(k, ((m, i) for i, m in enumerate(mastery)))]
""",
    brute_force_solution="""
def solve(mastery, k):
    order = sorted(range(len(mastery)), key=lambda i: (mastery[i], i))
    return order[:k]
""",
    generator="""
def generate(rng):
    n = rng.randint(0, 20)
    return [[rng.randint(0, 10) for _ in range(n)], rng.randint(0, 25)]
""",
    edge_cases=[[[], 3], [[7], 0], [[4, 4, 4], 2], [[9, 1, 5], 5]],
    public_examples=[[[80, 35, 60, 35, 90], 2], [[50, 20, 70], 1]],
    scale_generator="""
def generate_large():
    import random
    rng = random.Random(13)
    return [[rng.randint(0, 100) for _ in range(500_000)], 10]
""",
)

PREREQ_PLAN = CodingProblemSpec(
    title="Can You Finish the Plan",
    pattern="topological sort",
    difficulty="medium",
    statement=(
        "There are n topics, numbered 0 to n-1. Each pair [a, b] in prereqs means you must study b before a. "
        "Return True if there is an order that covers every topic, or False if the prerequisites form a loop."
    ),
    signature="def solve(n: int, prereqs: list[list[int]]) -> bool",
    reference_solution="""
def solve(n, prereqs):
    from collections import deque
    indeg = [0] * n
    after = [[] for _ in range(n)]
    for a, b in prereqs:
        after[b].append(a)
        indeg[a] += 1
    queue = deque(i for i in range(n) if indeg[i] == 0)
    done = 0
    while queue:
        node = queue.popleft()
        done += 1
        for nxt in after[node]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    return done == n
""",
    brute_force_solution="""
def solve(n, prereqs):
    need = {i: set() for i in range(n)}
    for a, b in prereqs:
        need[a].add(b)
    finished = set()
    progress = True
    while progress:
        progress = False
        for i in range(n):
            if i not in finished and need[i] <= finished:
                finished.add(i)
                progress = True
    return len(finished) == n
""",
    generator="""
def generate(rng):
    n = rng.randint(1, 8)
    pairs = []
    for _ in range(rng.randint(0, 10)):
        a, b = rng.randrange(n), rng.randrange(n)
        if rng.random() < 0.8 and a == b:
            continue
        pairs.append([a, b])
    return [n, pairs]
""",
    edge_cases=[[1, []], [2, [[1, 0]]], [2, [[1, 0], [0, 1]]], [3, [[0, 0]]], [4, [[1, 0], [2, 1], [3, 2]]]],
    public_examples=[[2, [[1, 0]]], [2, [[1, 0], [0, 1]]]],
    scale_generator="""
def generate_large():
    n = 200_000
    return [n, [[i, i - 1] for i in range(1, n)]]
""",
)

SEED_PROBLEMS = [PAIR_UP, FIRST_PASSING, BALANCED_NOTES, LONGEST_BUDGET_WINDOW, LONGEST_FRESH_RUN, BEST_STUDY_STRETCH, ISLAND_GROUPS, FEWEST_PROBLEM_SETS,
                 WEAKEST_TOPICS, MERGE_STUDY_BLOCKS, STREAK_SUMS, PREREQ_PLAN]
