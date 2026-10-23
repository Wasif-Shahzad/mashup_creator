# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""Pick random Codeforces problems that none of the configured users have solved."""

from __future__ import annotations

import random
import re
import sys
import time
from collections import defaultdict
from typing import Any

import requests

API_BASE = "https://codeforces.com/api"

# One problem will be picked for each difficulty in this list.
DIFFICULTIES = [1600, 1700, 1800, 1900]

# Problems solved by any of these users will be excluded.
USERS = ["Wasif_Shahzad", "wasif2397"]

DIV_3_OR_4 = re.compile(r"\bDiv(?:ision)?\.?\s*[34]\b", re.IGNORECASE)
MAX_RETRIES = 5


def api_get(session: requests.Session, method: str, **params: Any) -> Any:
    """Call a Codeforces API method, retrying transient failures."""
    url = f"{API_BASE}/{method}"
    last_error = "unknown error"

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)
        else:
            if payload.get("status") == "OK":
                return payload["result"]
            last_error = payload.get("comment", "Codeforces API returned an error")

        if attempt < MAX_RETRIES - 1:
            time.sleep(2**attempt)

    raise RuntimeError(f"Codeforces API call '{method}' failed: {last_error}")


def solved_problem_ids(session: requests.Session, handle: str) -> set[str]:
    """Return IDs (contestId + index) of all problems the user has solved."""
    submissions = api_get(session, "user.status", handle=handle)
    solved: set[str] = set()

    for submission in submissions:
        problem = submission.get("problem", {})
        contest_id = problem.get("contestId")
        if submission.get("verdict") == "OK" and contest_id is not None:
            solved.add(f"{contest_id}{problem['index']}")

    return solved


def div_3_or_4_contest_ids(session: requests.Session) -> set[int]:
    """Return contest IDs for all Div. 3 and Div. 4 rounds."""
    contests = api_get(session, "contest.list")
    return {
        contest["id"]
        for contest in contests
        if DIV_3_OR_4.search(contest.get("name", ""))
    }


def pick_problems() -> list[tuple[str, dict[str, Any]]]:
    session = requests.Session()
    session.headers["User-Agent"] = "codeforces-mashup-fetcher/1.0"

    problemset = api_get(session, "problemset.problems")["problems"]
    excluded_contests = div_3_or_4_contest_ids(session)

    solved: set[str] = set()
    for handle in USERS:
        solved |= solved_problem_ids(session, handle)

    wanted_ratings = set(DIFFICULTIES)
    by_rating: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)

    for problem in problemset:
        contest_id = problem.get("contestId")
        rating = problem.get("rating")

        if (
            problem.get("type") != "PROGRAMMING"
            or contest_id is None
            or contest_id in excluded_contests
            or rating not in wanted_ratings
        ):
            continue

        problem_id = f"{contest_id}{problem['index']}"
        if problem_id in solved:
            continue

        by_rating[rating].append((problem_id, problem))

    rng = random.SystemRandom()
    picked_ids: set[str] = set()
    picked: list[tuple[str, dict[str, Any]]] = []

    for difficulty in DIFFICULTIES:
        candidates = [
            item for item in by_rating[difficulty] if item[0] not in picked_ids
        ]
        if not candidates:
            raise RuntimeError(
                f"No eligible unsolved problems found with difficulty {difficulty}."
            )

        problem_id, problem = rng.choice(candidates)
        picked_ids.add(problem_id)
        picked.append((problem_id, problem))

    return picked


def main() -> None:
    try:
        problems = pick_problems()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    for problem_id, problem in problems:
        url = (
            "https://codeforces.com/problemset/problem/"
            f"{problem['contestId']}/{problem['index']}"
        )
        print(f"{problem_id} {url}")


if __name__ == "__main__":
    main()
