"""Email-only chat reconstruction — a TEST/PREVIEW, not wired into the inbox.

Fetches Booking/Airbnb notification emails from Gmail, parses each, groups them
into chats, and renders a chat-style HTML page so you can SEE what email-only
chats look like. Read-only: touches no conversations, inserts nothing, and makes
NO production changes (all the two-sided Airbnb parsing lives here in the script).

What it reconstructs:
  * Booking  -> guest side only (Booking never emails host replies).
  * Airbnb   -> BOTH sides. Airbnb emails the account about co-host replies
                ('Co-Gastgeber:in'), so we render guest + host bubbles. Grouped
                by reservation (concept-code + stay dates) so a guest question and
                the host answer land in the same chat despite being separate emails.

Usage (from FlaskApp parent dir):
    python -u -m ChatBotAI.scripts.email_chat_preview --days 90 --out preview.html
    python -u -m ChatBotAI.scripts.email_chat_preview --selftest
"""
import argparse
import datetime as _dt
import html
import re
import sys
from collections import defaultdict
from types import SimpleNamespace as NS

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map

_MIN = _dt.datetime.min


def _iso(d):
    return d.isoformat()[:10] if hasattr(d, 'isoformat') else (str(d)[:10] if d else '?')


def reservation_key(m, normalize):
    """Group key that unifies a reservation's guest + host messages.
    Airbnb: concept-code + dates. Booking: reservation ref. Else: guest name."""
    if m.platform == 'airbnb' and m.code and m.check_in:
        return f'a:{m.code}:{_iso(m.check_in)}:{_iso(m.check_out)}'
    if m.platform == 'booking' and m.booking_ref:
        return f'b:{m.booking_ref}'
    return 'n:' + (normalize(m.sender_name) or '?')


def group_by_reservation(msgs, normalize):
    """msgs -> {key: [msg,...]} time-sorted within each reservation."""
    buckets = defaultdict(list)
    for m in msgs:
        buckets[reservation_key(m, normalize)].append(m)
    for items in buckets.values():
        items.sort(key=lambda m: m.sent_at or _MIN)
    return dict(buckets)


# ---- Airbnb two-sided parse (preview-local; production keeps guest-only) ------
def parse_airbnb_two_sided(email, er):
    """Return a list of guest AND co-host messages from one Airbnb email."""
    body = email.get('body') or ''
    subject = email.get('subject') or ''
    lines = [ln.strip() for ln in body.splitlines()]

    prop = None
    m = re.search(r'Buchung für\s+[„"]?([^"\n]+?)[""]?(?:,|$)', subject)
    if m:
        prop = m.group(1).strip().strip('„""')
    codes = er.codes_from_property_text(prop) if prop else set()
    code = sorted(codes)[0] if codes else None
    check_in, check_out = er._airbnb_dates(body)
    ts = er._parse_email_date(email.get('date'))

    out = []
    for i, s in enumerate(lines):
        if s == 'Buchende Person':
            side = 'guest'
        elif s.startswith('Co-Gastgeber'):
            side = 'host'
        else:
            continue
        name = next((lines[j] for j in range(i - 1, -1, -1) if lines[j]), None)
        msg = er._collect_message(lines, i + 1, er._is_airbnb_stop)
        if not msg:
            continue
        out.append(NS(platform='airbnb', side=side, sender_name=name, message_text=msg,
                      sent_at=ts, property_name=prop, check_in=check_in, check_out=check_out,
                      booking_ref=None, code=code, thread_id=email.get('thread_id')))
    return out


def _booking_msg(email, er):
    n = er.parse_booking_notification(email)
    if not (n and n.message_text and n.sent_at):
        return None
    codes = er.codes_from_property_text(n.property_name) if n.property_name else set()
    return NS(platform='booking', side='guest', sender_name=n.guest_name,
              message_text=n.message_text, sent_at=n.sent_at, property_name=n.property_name,
              check_in=n.check_in, check_out=n.check_out, booking_ref=n.booking_ref,
              code=(sorted(codes)[0] if codes else None), thread_id=n.thread_id)


# ---- rendering ---------------------------------------------------------------
_BADGE = {'booking': ('#003580', 'Booking.com'), 'airbnb': ('#e0165f', 'Airbnb')}


def _fmt_ts(dt):
    return dt.strftime('%Y-%m-%d %H:%M') if dt else '—'


def _label(items):
    guest_names = [m.sender_name for m in items if m.side == 'guest' and m.sender_name]
    if guest_names:
        return guest_names[0]
    prop = next((m.property_name for m in items if m.property_name), None)
    return prop or 'Unbekannt'


def render_html(groups):
    chats = sorted(groups.values(), key=lambda it: max((m.sent_at or _MIN) for m in it), reverse=True)
    total = sum(len(v) for v in groups.values())
    host_ct = sum(1 for it in groups.values() for m in it if m.side == 'host')
    two_sided = sum(1 for it in groups.values()
                    if any(m.side == 'guest' for m in it) and any(m.side == 'host' for m in it))
    parts = [f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Email-only Chat Preview</title><style>
:root{{--wine:#7B2332;--bg:#f4f1ee;--card:#fff;--ink:#2a2226;--mut:#8a7f84}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.5 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--ink)}}
header{{background:var(--wine);color:#fff;padding:16px 20px}}header h1{{margin:0;font-size:18px}}
header p{{margin:4px 0 0;opacity:.9;font-size:13px}}
.wrap{{max-width:860px;margin:0 auto;padding:20px}}
.note{{background:#fff6e5;border:1px solid #f0d9a8;border-radius:8px;padding:10px 14px;font-size:13px;margin-bottom:18px}}
.chat{{background:var(--card);border:1px solid #e6dfe0;border-radius:12px;margin:0 0 22px;overflow:hidden}}
.chat>h2{{margin:0;padding:12px 16px;font-size:15px;background:#faf7f5;border-bottom:1px solid #eee;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.meta{{font-weight:400;color:var(--mut);font-size:12px}}
.badge{{color:#fff;border-radius:20px;padding:1px 9px;font-size:11px;font-weight:600}}
.pill{{font-size:11px;color:var(--mut);border:1px solid #e6dfe0;border-radius:20px;padding:1px 8px}}
.body{{padding:14px 16px;display:flex;flex-direction:column;gap:10px}}
.row{{display:flex}}.row.host{{justify-content:flex-end}}
.bub{{max-width:78%;border-radius:14px 14px 14px 4px;padding:8px 12px;font-size:14px}}
.row.guest .bub{{background:#efe7e9}}
.row.host .bub{{background:var(--wine);color:#fff;border-radius:14px 14px 4px 14px}}
.who{{font-size:11px;font-weight:600;opacity:.85;display:block;margin-bottom:2px}}
.t{{white-space:pre-wrap;word-wrap:break-word}}
.ts{{display:block;margin-top:4px;font-size:11px;opacity:.7}}
</style></head><body>
<header><h1>Email-only Chat Preview</h1>
<p>{len(chats)} Chats · {total} Nachrichten · davon {host_ct} Gastgeber-Antworten · {two_sided} zweiseitige Airbnb-Chats</p></header>
<div class="wrap">
<div class="note"><b>Test-Ansicht.</b> Booking = nur Gast-Seite (Booking mailt keine eigenen Antworten).
Airbnb = <b>beide Seiten</b> — Gast (links) und Gastgeber/Co-Host (rechts), rekonstruiert nur aus E-Mails.
Nichts hiervon wird in den echten Posteingang geschrieben.</div>"""]

    for items in chats:
        label = _label(items)
        latest = _fmt_ts(max((m.sent_at or _MIN) for m in items))
        plats = sorted({m.platform for m in items})
        props = {m.property_name for m in items if m.property_name}
        code = next((m.code for m in items if m.code), None)
        refs = {m.booking_ref for m in items if m.booking_ref}
        chk = next((m for m in items if m.check_in), None)
        meta = []
        if props:
            meta.append('· '.join(sorted(props)))
        if code:
            meta.append(f'Code {code}')
        if refs:
            meta.append('Ref ' + ', '.join(sorted(refs)))
        if chk:
            meta.append(f'{_iso(chk.check_in)}→{_iso(chk.check_out)}')
        meta.append(f'letzte: {latest}')
        badges = ''.join(f'<span class="badge" style="background:{_BADGE[p][0]}">{_BADGE[p][1]}</span>' for p in plats)
        parts.append(f'<div class="chat"><h2>{html.escape(label)} {badges}'
                     f'<span class="pill">{len(items)} Nachr.</span>'
                     f'<span class="meta">{html.escape(" · ".join(meta))}</span></h2><div class="body">')
        for m in items:
            who = html.escape((m.sender_name or ('Gastgeber' if m.side == 'host' else 'Gast')))
            txt = html.escape(m.message_text or '(kein Text)')
            parts.append(f'<div class="row {m.side}"><div class="bub">'
                         f'<span class="who">{who}</span><div class="t">{txt}</div>'
                         f'<span class="ts">{_fmt_ts(m.sent_at)}</span></div></div>')
        parts.append('</div></div>')
    parts.append('</div></body></html>')
    return ''.join(parts)


def _selftest():
    def norm(s):
        return (s or '').strip().lower()
    a = NS(platform='airbnb', side='guest', sender_name='Laura', message_text='Dankeschön',
           sent_at=_dt.datetime(2026, 7, 1), property_name='Honigfels', check_in=_dt.date(2026, 7, 3),
           check_out=_dt.date(2026, 7, 5), booking_ref=None, code='HW2', thread_id='t1')
    b = NS(platform='airbnb', side='host', sender_name='Elena', message_text='Bankverbindung?',
           sent_at=_dt.datetime(2026, 7, 2), property_name='Honigfels', check_in=_dt.date(2026, 7, 3),
           check_out=_dt.date(2026, 7, 5), booking_ref=None, code='HW2', thread_id='t2')
    c = NS(platform='booking', side='guest', sender_name='Marco', message_text='Hallo',
           sent_at=_dt.datetime(2026, 6, 9), property_name='Rotmilan', check_in=None,
           check_out=None, booking_ref='6617282635', code='R1', thread_id='t3')
    g = group_by_reservation([a, b, c], norm)
    assert len(g) == 2, g.keys()                                   # a+b (same code+dates) merge; c separate
    both = g['a:HW2:2026-07-03:2026-07-05']
    assert [m.side for m in both] == ['guest', 'host'], both       # two-sided, time-ordered
    assert _label(both) == 'Laura'                                 # labelled by the guest
    print('selftest OK')


def main(days, max_per, out):
    prod = config_map['production']

    class _NoDaemon(prod):
        DEBUG = True

    app = create_app(_NoDaemon)
    with app.app_context():
        from ChatBotAI.services.gmail_service import get_gmail_service
        from ChatBotAI.services import email_reconcile as er

        gmail = get_gmail_service()
        if not gmail or not gmail.is_authenticated():
            print('Gmail not authenticated — cannot fetch.')
            return 1

        msgs = []
        b_emails = gmail.get_recent_emails(max_results=max_per, query=f'from:guest.booking.com newer_than:{days}d', apply_filter=False)
        print(f'booking: fetched {len(b_emails)} emails')
        for e in b_emails:
            m = _booking_msg(e, er)
            if m:
                msgs.append(m)
        a_emails = gmail.get_recent_emails(max_results=max_per, query=f'from:airbnb.com newer_than:{days}d', apply_filter=False)
        print(f'airbnb: fetched {len(a_emails)} emails')
        for e in a_emails:
            msgs.extend(parse_airbnb_two_sided(e, er))

        host_ct = sum(1 for m in msgs if m.side == 'host')
        print(f'parsed {len(msgs)} messages ({host_ct} host-side)')

        groups = group_by_reservation(msgs, er.normalize_name)
        print(f'grouped into {len(groups)} chats')

        with open(out, 'w', encoding='utf-8') as f:
            f.write(render_html(groups))
        print(f'wrote {out}')
        return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=90)
    ap.add_argument('--max', type=int, default=200)
    ap.add_argument('--out', default='email_chat_preview.html')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        sys.exit(0)
    sys.exit(main(a.days, a.max, a.out))
