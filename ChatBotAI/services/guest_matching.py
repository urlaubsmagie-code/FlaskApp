"""Single source of truth for deciding when two guests are the same.

Used by both the dedup_guests.py cleanup script and the Smoobu sync path.
See docs/superpowers/specs/2026-06-08-guest-dedup-design.md.
"""
import re

from sqlalchemy import func
from ..models import Guest


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
