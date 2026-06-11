# Security Audit Report — ChatBotAI
**Date:** 2026-05-21  
**Scope:** Flask blueprint application with Smoobu, Gmail, Ollama integration  
**Assessment Level:** Full codebase review  

---

## Executive Summary

**Total Findings:** 15  
- **CRITICAL:** 0  
- **HIGH:** 5  
- **MEDIUM:** 7  
- **LOW:** 3  

**Key Risks:** Multiple sensitive API endpoints missing @login_required, no CSRF protection, hardcoded SECRET_KEY fallback, unverified webhook signature.

---

## FINDINGS

### [HIGH] Missing Authentication on Sensitive API Endpoints

#### 1. Message Approval API Missing @login_required
- **File:** routes.py:2054
- **Issue:** `/api/messages/<int:message_id>/approve` (POST) allows unauthenticated approval and platform send
- **Impact:** Attacker bypasses approval queue, sends malicious messages to guests
- **Evidence:** `@chatbot_bp.route('/api/messages/<int:message_id>/approve', methods=['POST'])` with NO `@login_required`, proceeds to `message.approval_status = 'approved'` and sends via Gmail/Smoobu
- **Suggested fix:** Add `@login_required` decorator before @chatbot_bp.route

#### 2. Message Rejection API Missing @login_required  
- **File:** routes.py:2120
- **Issue:** `/api/messages/<int:message_id>/reject` (POST) allows unauthenticated draft deletion
- **Impact:** Attacker discards AI responses, disrupting conversation flow
- **Suggested fix:** Add `@login_required` decorator

#### 3. Conversation Modification APIs Missing @login_required
- **File:** routes.py:1988, 2013, 2025
- **Issue:** `/api/conversations/<int:conversation_id>/assign`, `/toggle-ai`, `/toggle-auto-respond` modify state without auth
- **Impact:** Attacker reassigns conversations, disables AI protections, enables auto-respond spam
- **Suggested fix:** Add `@login_required` to all three routes

#### 4. Push Subscription Endpoints Missing @login_required
- **File:** routes.py:2609, 2646, 2665, 2746
- **Issue:** `/api/push/subscribe`, `/unsubscribe`, `/test`, `/reset` use `current_user.id` without auth check
- **Impact:** Attacker registers/modifies/resets subscriptions as anonymous NULL user
- **Suggested fix:** Add `@login_required` to all push endpoints

#### 5. Knowledge Base CRUD Missing @login_required
- **File:** routes.py:4220, 4267, 4312, 4183
- **Issue:** `/api/knowledge` (POST/PUT/DELETE), `/api/messages/<id>/extract-knowledge` (POST) lack authentication
- **Impact:** Attacker modifies knowledge base, poisons AI responses and guest profiles
- **Suggested fix:** Add `@login_required` to all knowledge endpoints

---

### [MEDIUM] No CSRF Protection Implemented

#### 6. Flask-WTF Not Installed, CSRF Disabled
- **File:** requirements.txt, config.py, app.py:385-426
- **Issue:** Flask-WTF not in requirements; no CSRFProtect initialization; no CSRF token generation
- **Impact:** All 49 POST/PUT/PATCH/DELETE endpoints vulnerable to CSRF from attacker-controlled sites
- **Suggested fix:** Install Flask-WTF>=1.2.1, initialize CSRFProtect(app), add {% csrf_token() %} to forms

#### 7. Page Routes Missing @login_required
- **File:** routes.py:370 (/knowledge), 355 (/statistics), 323 (/guest/<id>)
- **Issue:** Three page routes render sensitive data without @login_required
- **Impact:** Unauthenticated users view guest profiles, memory data, statistics, property info
- **Suggested fix:** Add `@login_required` decorator to knowledge_base(), statistics(), guest_profile()

#### 8. Smoobu Webhook Signature Not Verified
- **File:** routes.py:3566-3741
- **Issue:** `/api/webhooks/smoobu` (POST/GET) accepts webhook data without signature verification
- **Impact:** Attacker sends forged webhooks to inject messages, cancel reservations, trigger syncs
- **Suggested fix:** Verify HMAC-SHA256(body, SMOOBU_API_KEY) against X-Smoobu-Signature header

#### 9. Hardcoded Default SECRET_KEY for Production
- **File:** config.py:16
- **Issue:** `SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')`
- **Impact:** If SECRET_KEY env var forgotten in production, session tokens become predictable
- **Suggested fix:** Remove default; raise RuntimeError if SECRET_KEY missing in ProductionConfig

#### 10. No Session Cookie Security Headers
- **File:** app.py:405-426
- **Issue:** Flask-Login initialized without HttpOnly, Secure, SameSite flags
- **Impact:** Session cookies can be stolen via XSS; no inherent CSRF protection without SameSite=Strict
- **Suggested fix:** Add app.config['SESSION_COOKIE_HTTPONLY']=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Strict'

---

### [LOW] Unsafe innerHTML Usage

#### 11. innerHTML Assignment in Debug Page
- **File:** templates/chatbot/debug.html (lines ~215-250, 380-400)
- **Issue:** Multiple `innerHTML +=` assignments without escaping (grid.innerHTML, result.innerHTML, etc.)
- **Impact:** Admin-only page, low immediate risk; unsafe pattern
- **Suggested fix:** Use textContent for plain text, createElement+appendChild for HTML

#### 12. onclick Handler with innerHTML in Conversation
- **File:** templates/chatbot/conversation.html
- **Issue:** `onclick="document.getElementById('playtestEventList').innerHTML=''"` directly modifies innerHTML
- **Impact:** Low (clears own element); demonstrates unsafe pattern
- **Suggested fix:** Use event listener with textContent='' or element.remove()

#### 13. Unvalidated sort_order Integer Assignment
- **File:** routes.py:4305
- **Issue:** `entry.sort_order = int(data['sort_order'])` with no bounds validation
- **Impact:** Attacker sets sort_order to 999999999 or -1, breaking UI ordering
- **Suggested fix:** Validate `0 <= sort_order <= 10000` before assignment

---

## Remediation Priority

**IMMEDIATE (This week):**
1. Add @login_required to findings 1-5 (message approval, push, knowledge APIs)
2. Add @login_required to findings 7 (page routes)

**SHORT-TERM (2-4 weeks):**
3. Install Flask-WTF, implement CSRF protection (finding 6)
4. Implement Smoobu webhook signature verification (finding 8)
5. Force SECRET_KEY environment variable (finding 9)
6. Configure secure session cookies (finding 10)

**MEDIUM-TERM (next sprint):**
7. Replace innerHTML patterns (findings 11-12)
8. Add sort_order validation (finding 13)
9. Implement rate limiting on expensive endpoints
10. Add CSP headers

---

**Report Generated:** 2026-05-21
