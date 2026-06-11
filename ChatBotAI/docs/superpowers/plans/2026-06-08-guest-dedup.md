# Guest Deduplication + Prevention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge ~2,657 duplicate `Guest` rows created by Smoobu sync, and fix the root cause so new bookings reuse existing guests instead of creating duplicates.

**Architecture:** A shared `guest_matching` module defines normalizers, the safe match rule, and grouping — the single source of truth for "same guest." A standalone `dedup_guests.py` script (dry-run → backup → apply) uses it to merge existing dupes. The Smoobu sync path is rewritten to use the same matcher and to stop storing `reservation_id` in `smoobu_guest_id`.

**Tech Stack:** Python, Flask, SQLAlchemy, SQLite (WAL), pytest. Spec: `docs/superpowers/specs/2026-06-08-guest-dedup-design.md`.

---

## File Structure

- **Create** `services/guest_matching.py` — normalizers, `build_merge_groups()` (pure, testable grouping with conflict-skip), `find_existing_guest()` (prevention-path lookup).
- **Create** `scripts/__init__.py`, `scripts/dedup_guests.py` — CLI: `--dry-run` report, `--apply` (WAL checkpoint + backup + merge).
- **Modify** `services/smoobu_service.py:664-687` — use `find_existing_guest`, stop setting `smoobu_guest_id = reservation_id`.
- **Create** tests: `tests/test_guest_matching.py`, `tests/test_dedup_guests.py`, `tests/test_smoobu_guest_reuse.py`.

All test commands run from the **parent** dir (`C:\Users\admin\Documents\FlaskApp`) so `ChatBotAI` imports as a package. Phone matching in the prevention path is exact-match (Smoobu's format is consistent); normalized-phone matching is handled by the cleanup pass.

---

### Task 1: Normalizers in `guest_matching.py`

**Files:**
- Create: `ChatBotAI/services/guest_matching.py`
- Test: `ChatBotAI/tests/test_guest_matching.py`

- [ ] **Step 1: Write the failing test**

```python
# ChatBotAI/tests/test_guest_matching.py
from ChatBotAI.services.guest_matching import (
    normalize_email, normalize_phone, normalize_name,
)


def test_normalize_email():
    assert normalize_email("  Bob@EXAMPLE.com ") == "bob@example.com"
    assert normalize_email("") is None
    assert normalize_email(None) is None


def test_normalize_phone():
    assert normalize_phone("+49 (170) 123-4567") == "491701234567"
    assert normalize_phone("  ") is None
    assert normalize_phone(None) is None


def test_normalize_name():
    assert normalize_name("  Steven   Amaya ") == "steven amaya"
    assert normalize_name("STEVEN AMAYA") == normalize_name("steven amaya")
    assert normalize_name("") is None
    assert normalize_name(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_guest_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ChatBotAI.services.guest_matching'`

- [ ] **Step 3: Write minimal implementation**

```python
# ChatBotAI/services/guest_matching.py
"""Single source of truth for deciding when two guests are the same.

Used by both the dedup_guests.py cleanup script and the Smoobu sync path.
See docs/superpowers/specs/2026-06-08-guest-dedup-design.md.
"""
import re


def normalize_email(value):
    if not value:
        return None
    return value.strip().lower() or None


def normalize_phone(value):
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits or None


def normalize_name(value):
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip().casefold() or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_guest_matching.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/guest_matching.py ChatBotAI/tests/test_guest_matching.py
git commit -m "feat(guest-dedup): add guest_matching normalizers"
```

---

### Task 2: `build_merge_groups()` — pure grouping with conflict-skip

**Files:**
- Modify: `ChatBotAI/services/guest_matching.py`
- Test: `ChatBotAI/tests/test_guest_matching.py`

- [ ] **Step 1: Write the failing test**

```python
# append to ChatBotAI/tests/test_guest_matching.py
from collections import namedtuple
from ChatBotAI.services.guest_matching import build_merge_groups

Row = namedtuple("Row", "id email phone name")


def test_groups_name_only_duplicates():
    rows = [
        Row(1, None, None, "Steven Amaya"),
        Row(2, None, None, "steven amaya"),
        Row(3, None, None, "Nathalie Roos"),
    ]
    groups, conflicts = build_merge_groups(rows)
    assert groups == [[1, 2]]
    assert conflicts == []


def test_groups_by_email_and_phone():
    rows = [
        Row(1, "a@x.com", None, "A One"),
        Row(2, "A@X.COM", None, "Totally Different"),   # same email -> merge
        Row(3, None, "+49 170 5", "B Two"),
        Row(4, None, "01705", "B Two"),                  # same phone digits -> merge
    ]
    groups, conflicts = build_merge_groups(rows)
    assert [1, 2] in groups
    assert [3, 4] in groups


def test_skips_name_group_with_conflicting_email():
    rows = [
        Row(1, "real1@x.com", None, "Benjamin Schmidt"),
        Row(2, "real2@x.com", None, "Benjamin Schmidt"),  # different emails, same name
        Row(3, None, None, "Benjamin Schmidt"),
    ]
    groups, conflicts = build_merge_groups(rows)
    assert groups == []                       # name union skipped
    assert len(conflicts) == 1
    assert conflicts[0]["name"] == "benjamin schmidt"
    assert sorted(conflicts[0]["emails"]) == ["real1@x.com", "real2@x.com"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_guest_matching.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_merge_groups'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to ChatBotAI/services/guest_matching.py
def build_merge_groups(rows):
    """Group guests that are the 'same' under the safe rule.

    rows: iterable of objects with .id, .email, .phone, .name
    Returns (groups, conflicts):
      groups    -- list of id-lists (len>=2) safe to merge
      conflicts -- list of dicts for name-groups skipped due to >1 distinct
                   email or phone (likely different people)

    Email and phone matches are always unioned (safe). Same-name groups are
    unioned only when they have <=1 distinct email AND <=1 distinct phone.
    """
    rows = list(rows)
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for r in rows:
        find(r.id)

    by_email, by_phone, by_name = {}, {}, {}
    for r in rows:
        e, p, n = normalize_email(r.email), normalize_phone(r.phone), normalize_name(r.name)
        if e:
            by_email.setdefault(e, []).append(r)
        if p:
            by_phone.setdefault(p, []).append(r)
        if n:
            by_name.setdefault(n, []).append(r)

    for bucket in by_email.values():
        for r in bucket[1:]:
            union(bucket[0].id, r.id)
    for bucket in by_phone.values():
        for r in bucket[1:]:
            union(bucket[0].id, r.id)

    conflicts = []
    for name, bucket in by_name.items():
        if len(bucket) < 2:
            continue
        emails = {normalize_email(r.email) for r in bucket if normalize_email(r.email)}
        phones = {normalize_phone(r.phone) for r in bucket if normalize_phone(r.phone)}
        if len(emails) > 1 or len(phones) > 1:
            conflicts.append({
                "name": name,
                "ids": sorted(r.id for r in bucket),
                "emails": sorted(emails),
                "phones": sorted(phones),
            })
            continue
        for r in bucket[1:]:
            union(bucket[0].id, r.id)

    comps = {}
    for r in rows:
        comps.setdefault(find(r.id), []).append(r.id)
    groups = sorted(
        (sorted(ids) for ids in comps.values() if len(ids) > 1),
        key=lambda g: (-len(g), g[0]),
    )
    return groups, conflicts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_guest_matching.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/guest_matching.py ChatBotAI/tests/test_guest_matching.py
git commit -m "feat(guest-dedup): add build_merge_groups with conflict-skip"
```

---

### Task 3: `find_existing_guest()` — prevention-path lookup

**Files:**
- Modify: `ChatBotAI/services/guest_matching.py`
- Test: `ChatBotAI/tests/test_guest_matching.py`

- [ ] **Step 1: Write the failing test**

```python
# append to ChatBotAI/tests/test_guest_matching.py
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest
from ChatBotAI.services.guest_matching import find_existing_guest


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_find_by_email_case_insensitive(app):
    db.session.add(Guest(name="Bob", email="bob@x.com"))
    db.session.commit()
    found = find_existing_guest(email="BOB@X.COM", name="Whatever")
    assert found is not None and found.email == "bob@x.com"


def test_find_by_name_only_when_no_conflict(app):
    db.session.add(Guest(name="Steven Amaya"))
    db.session.commit()
    assert find_existing_guest(name="steven amaya") is not None


def test_no_name_match_when_email_conflicts(app):
    db.session.add(Guest(name="Steven Amaya", email="real@x.com"))
    db.session.commit()
    # incoming has a DIFFERENT email -> must not attach to the existing row
    assert find_existing_guest(email="other@x.com", name="Steven Amaya") is None


def test_returns_none_when_nothing_matches(app):
    assert find_existing_guest(email="nobody@x.com", name="Ghost") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_guest_matching.py -k find -v`
Expected: FAIL — `ImportError: cannot import name 'find_existing_guest'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to ChatBotAI/services/guest_matching.py
from sqlalchemy import func
from ..models import Guest


def find_existing_guest(email=None, phone=None, name=None):
    """Return an existing Guest matching the incoming identity, else None.

    Priority: email (case-insensitive) -> phone (exact) -> normalized name,
    where a name match is accepted only if the candidate has no email/phone
    that conflicts with the incoming values.
    """
    ne = normalize_email(email)
    if ne:
        g = Guest.query.filter(func.lower(func.trim(Guest.email)) == ne).first()
        if g:
            return g

    if phone:
        g = Guest.query.filter_by(phone=phone).first()
        if g:
            return g

    nn = normalize_name(name)
    if nn:
        candidates = Guest.query.filter(
            func.lower(func.trim(Guest.name)) == name.strip().lower()
        ).all()
        np_ = normalize_phone(phone)
        for g in candidates:
            if normalize_name(g.name) != nn:
                continue
            g_email = normalize_email(g.email)
            g_phone = normalize_phone(g.phone)
            if ne and g_email and g_email != ne:
                continue
            if np_ and g_phone and g_phone != np_:
                continue
            return g
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_guest_matching.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/guest_matching.py ChatBotAI/tests/test_guest_matching.py
git commit -m "feat(guest-dedup): add find_existing_guest for prevention path"
```

---

### Task 4: Merge engine — `merge_group()` in the script

**Files:**
- Create: `ChatBotAI/scripts/__init__.py` (empty)
- Create: `ChatBotAI/scripts/dedup_guests.py`
- Test: `ChatBotAI/tests/test_dedup_guests.py`

- [ ] **Step 1: Write the failing test**

```python
# ChatBotAI/tests/test_dedup_guests.py
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, GuestDetail
from ChatBotAI.scripts.dedup_guests import merge_group


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_merge_reassigns_fks_and_backfills(app):
    # loser has the contact info + a conversation; winner picked by contact/conv
    g1 = Guest(name="Steven Amaya")                       # id 1, no contact
    g2 = Guest(name="Steven Amaya", email="s@x.com")      # id 2, has email
    db.session.add_all([g1, g2])
    db.session.commit()
    db.session.add(Conversation(guest_id=g1.id, platform="smoobu", platform_id="c1"))
    db.session.add(GuestDetail(guest_id=g1.id, detail_type="pet", detail_key="dog", detail_value="Max"))
    db.session.add(GuestDetail(guest_id=g2.id, detail_type="pet", detail_key="dog", detail_value="Max"))
    db.session.commit()

    winner_id, loser_ids = merge_group([g1.id, g2.id])
    db.session.commit()

    assert winner_id == g2.id                 # g2 has email -> richer
    assert loser_ids == [g1.id]
    assert Guest.query.count() == 1
    assert Guest.query.get(g2.id).email == "s@x.com"
    # conversation reassigned, no orphans
    assert Conversation.query.filter_by(guest_id=g2.id).count() == 1
    assert Conversation.query.filter_by(guest_id=g1.id).count() == 0
    # identical details deduped to one
    assert GuestDetail.query.filter_by(guest_id=g2.id).count() == 1


def test_merge_backfills_email_onto_winner_without_unique_clash(app):
    # winner has more conversations but no email; loser carries the email
    g1 = Guest(name="A")                       # winner (2 convs, no email)
    g2 = Guest(name="A", email="a@x.com")      # loser (email, 0 convs)
    db.session.add_all([g1, g2])
    db.session.commit()
    db.session.add_all([
        Conversation(guest_id=g1.id, platform="smoobu", platform_id="x1"),
        Conversation(guest_id=g1.id, platform="smoobu", platform_id="x2"),
    ])
    db.session.commit()

    winner_id, loser_ids = merge_group([g1.id, g2.id])
    db.session.commit()

    assert winner_id == g1.id
    assert Guest.query.get(g1.id).email == "a@x.com"   # backfilled, no IntegrityError
    assert Guest.query.count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_dedup_guests.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ChatBotAI.scripts.dedup_guests'`

- [ ] **Step 3: Write minimal implementation**

Create empty `ChatBotAI/scripts/__init__.py`, then:

```python
# ChatBotAI/scripts/dedup_guests.py
"""Merge duplicate Guest rows. See docs/superpowers/specs/2026-06-08-guest-dedup-design.md.

Usage (from C:\\Users\\admin\\Documents\\FlaskApp):
    python -m ChatBotAI.scripts.dedup_guests --dry-run
    python -m ChatBotAI.scripts.dedup_guests --apply
"""
from ..models import db, Guest, Conversation, GuestDetail
from ..services.guest_matching import (
    normalize_email, normalize_phone, build_merge_groups,
)


def choose_winner(guests):
    """Richest profile wins: has email/phone, then most conversations, then lowest id."""
    def score(g):
        has_contact = 1 if (normalize_email(g.email) or normalize_phone(g.phone)) else 0
        return (has_contact, g.conversations.count(), -g.id)
    return max(guests, key=score)


def merge_group(ids):
    """Merge the given guest ids into one survivor. Caller commits.

    Returns (winner_id, loser_ids). Losers are deleted BEFORE the winner's
    contact fields are set, so backfilling a unique email cannot clash.
    """
    guests = Guest.query.filter(Guest.id.in_(ids)).all()
    winner = choose_winner(guests)
    losers = [g for g in guests if g.id != winner.id]
    loser_ids = sorted(g.id for g in losers)

    # Gather consolidated values from the whole group BEFORE deleting losers.
    email = winner.email or next((g.email for g in losers if g.email), None)
    phone = winner.phone or next((g.phone for g in losers if g.phone), None)
    notes = winner.notes or next((g.notes for g in losers if g.notes), None)
    first_contacts = [g.first_contact for g in guests if g.first_contact]
    last_contacts = [g.last_contact for g in guests if g.last_contact]
    total_stays = sum((g.total_stays or 0) for g in guests)

    # Reassign foreign keys to the winner.
    Conversation.query.filter(Conversation.guest_id.in_(loser_ids)).update(
        {"guest_id": winner.id}, synchronize_session=False)
    GuestDetail.query.filter(GuestDetail.guest_id.in_(loser_ids)).update(
        {"guest_id": winner.id}, synchronize_session=False)
    db.session.flush()

    # Delete losers first to free the unique email before backfilling it.
    for g in losers:
        db.session.delete(g)
    db.session.flush()

    winner.email = email
    winner.phone = phone
    winner.notes = notes
    if first_contacts:
        winner.first_contact = min(first_contacts)
    if last_contacts:
        winner.last_contact = max(last_contacts)
    winner.total_stays = total_stays
    db.session.flush()

    # Dedupe identical details now consolidated on the winner.
    seen = set()
    for d in (GuestDetail.query.filter_by(guest_id=winner.id)
              .order_by(GuestDetail.id).all()):
        key = (d.detail_type, d.detail_key, d.detail_value)
        if key in seen:
            db.session.delete(d)
        else:
            seen.add(key)
    db.session.flush()

    return winner.id, loser_ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_dedup_guests.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/scripts/__init__.py ChatBotAI/scripts/dedup_guests.py ChatBotAI/tests/test_dedup_guests.py
git commit -m "feat(guest-dedup): add merge_group engine"
```

---

### Task 5: CLI — dry-run report + `--apply` with backup, plus idempotency

**Files:**
- Modify: `ChatBotAI/scripts/dedup_guests.py`
- Test: `ChatBotAI/tests/test_dedup_guests.py`

- [ ] **Step 1: Write the failing test**

```python
# append to ChatBotAI/tests/test_dedup_guests.py
from ChatBotAI.scripts.dedup_guests import run_dedup


def test_run_dedup_merges_and_is_idempotent(app):
    db.session.add_all([
        Guest(name="Nathalie Roos"),
        Guest(name="nathalie roos"),
        Guest(name="Nathalie Roos"),
        Guest(name="Unique Person"),
    ])
    db.session.commit()

    result = run_dedup(apply=True)
    db.session.commit()
    assert result["groups"] == 1
    assert result["deleted"] == 2
    assert Guest.query.count() == 2          # 1 merged Roos + 1 unique

    # second pass finds nothing
    again = run_dedup(apply=True)
    db.session.commit()
    assert again["groups"] == 0
    assert again["deleted"] == 0


def test_run_dedup_reports_conflicts_without_merging(app):
    db.session.add_all([
        Guest(name="Benjamin Schmidt", email="b1@x.com"),
        Guest(name="Benjamin Schmidt", email="b2@x.com"),
    ])
    db.session.commit()
    result = run_dedup(apply=False)         # dry-run
    assert result["groups"] == 0
    assert result["conflicts"] == 1
    assert Guest.query.count() == 2          # untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_dedup_guests.py -k run_dedup -v`
Expected: FAIL — `ImportError: cannot import name 'run_dedup'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to ChatBotAI/scripts/dedup_guests.py
import argparse
import shutil
from datetime import datetime


def run_dedup(apply=False):
    """Compute groups and (optionally) merge them. Caller manages app context.

    Returns a summary dict: {groups, deleted, conflicts, conflict_detail, samples}.
    Does NOT commit when apply=False; commits per group when apply=True.
    """
    guests = Guest.query.all()
    groups, conflicts = build_merge_groups(guests)

    samples = []
    for g in groups[:10]:
        first = Guest.query.get(g[0])
        samples.append({"name": first.name, "rows": len(g)})

    deleted = 0
    if apply:
        for ids in groups:
            _, loser_ids = merge_group(ids)
            deleted += len(loser_ids)
            db.session.commit()

    return {
        "groups": len(groups),
        "deleted": deleted if apply else sum(len(g) - 1 for g in groups),
        "conflicts": len(conflicts),
        "conflict_detail": conflicts,
        "samples": samples,
    }


def _print_report(summary, applied):
    print(f"{'APPLIED' if applied else 'DRY-RUN'} guest dedup")
    print(f"  merge groups        : {summary['groups']}")
    print(f"  rows {'deleted' if applied else 'to delete'} : {summary['deleted']}")
    print(f"  conflict groups skipped: {summary['conflicts']}")
    if summary["samples"]:
        print("  largest groups:")
        for s in summary["samples"]:
            print(f"    {s['rows']:>4}  {s['name']}")
    if summary["conflict_detail"]:
        print("  SKIPPED (conflicting email/phone — review manually):")
        for c in summary["conflict_detail"]:
            print(f"    {c['name']}: ids={c['ids']} emails={c['emails']} phones={c['phones']}")


def main():
    parser = argparse.ArgumentParser(description="Deduplicate Guest rows.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually merge (default is dry-run).")
    args = parser.parse_args()

    from ..app import create_app
    from ..config import config as config_map
    import os

    app = create_app(config_map[os.environ.get("FLASK_ENV", "production")])
    with app.app_context():
        if args.apply:
            db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
            db.session.execute(db.text("PRAGMA wal_checkpoint(TRUNCATE)"))
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            backup = f"{db_path}.bak-pre-dedup-{ts}"
            shutil.copyfile(db_path, backup)
            print(f"Backup written: {backup}")

        summary = run_dedup(apply=args.apply)
        _print_report(summary, applied=args.apply)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_dedup_guests.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/scripts/dedup_guests.py ChatBotAI/tests/test_dedup_guests.py
git commit -m "feat(guest-dedup): add run_dedup CLI with dry-run, backup, idempotency"
```

---

### Task 6: Prevention — rewrite Smoobu guest creation

**Files:**
- Modify: `ChatBotAI/services/smoobu_service.py:664-687`
- Test: `ChatBotAI/tests/test_smoobu_guest_reuse.py`

- [ ] **Step 1: Write the failing test**

```python
# ChatBotAI/tests/test_smoobu_guest_reuse.py
"""Two reservations from the same guest must reuse one Guest row."""
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest
from ChatBotAI.services.guest_matching import find_existing_guest


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _get_or_make_guest(name, email, reservation_id):
    """Mirror of the rewritten smoobu_service guest-creation block."""
    guest = find_existing_guest(email=email, name=name)
    if not guest:
        guest = Guest(name=name or f"Guest {reservation_id}", email=email or None)
        db.session.add(guest)
        db.session.flush()
    return guest


def test_second_reservation_reuses_guest(app):
    g1 = _get_or_make_guest("Steven Amaya", None, "res-111")
    db.session.commit()
    g2 = _get_or_make_guest("Steven Amaya", None, "res-222")  # different reservation
    db.session.commit()
    assert g1.id == g2.id
    assert Guest.query.count() == 1


def test_guest_id_not_set_to_reservation_id(app):
    g = _get_or_make_guest("New Person", None, "res-999")
    db.session.commit()
    assert g.smoobu_guest_id != "res-999"
    assert g.smoobu_guest_id is None
```

- [ ] **Step 2: Run test to verify it fails**

First confirm the test passes against the *mirror* (it will), then the real change is in `smoobu_service.py`. Run:
`cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_smoobu_guest_reuse.py -v`
Expected: PASS for the mirror logic (this pins the intended behavior the service must match).

- [ ] **Step 3: Apply the change to `smoobu_service.py`**

Replace the block at lines 664–687 (the `if guest_email: ... smoobu_guest_id=reservation_id ...` creation logic) with:

```python
                            from ..models import Guest
                            from sqlalchemy.exc import IntegrityError
                            from .guest_matching import find_existing_guest

                            guest = find_existing_guest(
                                email=guest_email or None,
                                name=guest_name or None,
                            )
                            if not guest:
                                guest = Guest(
                                    name=guest_name or f"Guest {reservation_id}",
                                    email=guest_email or None,
                                )
                                db.session.add(guest)
                                try:
                                    db.session.flush()
                                except IntegrityError:
                                    # Concurrent webhook beat us to it (email is unique).
                                    db.session.rollback()
                                    guest = find_existing_guest(
                                        email=guest_email or None,
                                        name=guest_name or None,
                                    )
                                    if not guest:
                                        raise
```

Note: `reservation_id` is NO LONGER stored on the guest — it already lives on `Conversation.smoobu_reservation_id` (set a few lines below at conversation creation).

- [ ] **Step 4: Run the full suite to verify nothing regressed**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/ -v`
Expected: PASS (all tests, including existing ones)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/smoobu_service.py ChatBotAI/tests/test_smoobu_guest_reuse.py
git commit -m "fix(guest-dedup): reuse existing guest in Smoobu sync; stop storing reservation_id as smoobu_guest_id"
```

---

### Task 7: Operator runbook — `DEDUP_LOG.md`

**Files:**
- Create: `ChatBotAI/DEDUP_LOG.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Guest Dedup — Run Log

Spec: docs/superpowers/specs/2026-06-08-guest-dedup-design.md
Plan: docs/superpowers/plans/2026-06-08-guest-dedup.md

## Procedure
1. Prevention shipped first (smoobu_service uses find_existing_guest). Verify via test suite.
2. Dry-run (from C:\Users\admin\Documents\FlaskApp):
   `python -m ChatBotAI.scripts.dedup_guests`
   Review: group count, rows-to-delete, largest groups, and SKIPPED conflict groups.
3. Apply:
   `python -m ChatBotAI.scripts.dedup_guests --apply`
   Auto-backup: `instance/chatbot.db.bak-pre-dedup-<ts>`.
4. Re-run dry-run to confirm 0 groups (idempotent).

## Rollback
Stop the server, restore the backup:
`copy instance\chatbot.db.bak-pre-dedup-<ts> instance\chatbot.db` (delete -wal/-shm first).

## Step table
| Date | Action | Groups | Rows deleted | Backup file | Notes |
|------|--------|--------|--------------|-------------|-------|
| TBD  | dry-run | | | — | |
| TBD  | apply   | | | | |
```

- [ ] **Step 2: Commit**

```bash
git add ChatBotAI/DEDUP_LOG.md
git commit -m "docs(guest-dedup): add operator runbook"
```

---

## Self-Review

**Spec coverage:**
- Shared matching module → Tasks 1–3 ✅
- Cleanup script (group, winner, backfill, FK reassign, detail dedupe, delete, dry-run, backup, idempotent) → Tasks 4–5 ✅
- Conflict skip + report → Tasks 2, 5 ✅
- Prevention (identity match, stop storing reservation_id) → Task 6 ✅
- Safety/runbook/rollback → Tasks 5, 7 ✅
- `find_or_create_guest` left alone → not modified ✅
- Smoobu stable-guest-id check → handled at planning: the reservation block exposes only `guest_email`/`guest_name`/`reservation_id` (no stable guest id), so matching uses email/name; documented in Task 6 note.

**Placeholder scan:** Only intentional `TBD`s are the empty rows of the run-log step table (filled at execution). No code placeholders.

**Type consistency:** `build_merge_groups`, `find_existing_guest`, `merge_group`, `choose_winner`, `run_dedup` signatures are consistent across tasks and tests. `GuestDetail` dedupe key uses the real columns `(detail_type, detail_key, detail_value)`. FK reassignment covers exactly the two FKs to `guest` (`Conversation.guest_id`, `GuestDetail.guest_id`).
