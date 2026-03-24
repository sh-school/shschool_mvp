# Data Protection Impact Assessment (DPIA)
## SchoolOS — مدرسة الشحانية الإعدادية الثانوية للبنين

| | |
|---|---|
| **Document ID** | DPIA-SCHOOLOS-2026-001 |
| **Version** | 1.0 |
| **Date** | 2026-03-25 |
| **DPO** | سفيان أحمد محمد مسيف |
| **Legal Basis** | PDPPL (Law 13/2016) — Article 11, 13 |
| **Status** | DRAFT — Pending DPO Approval |

---

## 1. Description of Processing Activities

### 1.1 System Overview
SchoolOS is a school management platform processing personal data of students (minors),
parents, teachers, and administrative staff for Al Shahaniya Preparatory Secondary Boys School.

### 1.2 Data Categories Processed

| Category | Data Types | Data Subjects | Volume |
|----------|-----------|---------------|--------|
| **Identity** | National ID (encrypted), full name, email, phone | All users | ~2,000 |
| **Academic** | Grades, attendance, assessments, class enrollment | Students | ~1,500 |
| **Health** | Allergies, chronic diseases, medications (encrypted) | Students | ~1,500 |
| **Behavioral** | Infractions, points, disciplinary actions | Students | Variable |
| **Transport** | Bus routes, driver info, GPS tracking links | Students/Staff | ~200 |
| **Authentication** | Passwords (hashed), TOTP secrets (encrypted) | All users | ~2,000 |
| **Communication** | Email addresses, phone numbers, SMS records | Parents/Staff | ~1,000 |

### 1.3 Processing Purposes

| Purpose | Legal Basis | Retention |
|---------|------------|-----------|
| Student enrollment and academic management | Legitimate interest (education) | Duration of enrollment + 5 years |
| Health record management | Explicit consent (parent) | Duration of enrollment |
| Attendance tracking | Legal obligation (MoEHE) | Academic year + 3 years |
| Behavioral discipline | Legitimate interest (school safety) | Academic year + 1 year |
| Parent communication | Consent | Duration of enrollment |
| Staff performance evaluation | Employment contract | Employment + 3 years |

### 1.4 Data Flows

```
[Student/Parent] → [Web Browser] → [HTTPS/TLS 1.2+] → [Nginx]
  → [Django App] → [PostgreSQL (encrypted fields)]
                 → [Redis (session cache)]
                 → [Celery (async tasks)] → [Email/SMS via Twilio]
                 → [S3 (file storage, me-south-1 region)]
```

---

## 2. Risk Assessment

### 2.1 Risk Matrix

| Risk | Likelihood | Impact | Inherent Risk | Controls | Residual Risk |
|------|-----------|--------|---------------|----------|---------------|
| Unauthorized access to student records | Medium | High | HIGH | RBAC + 2FA + rate limiting + IDOR protection | LOW |
| Database breach exposing PII | Low | Critical | HIGH | Fernet encryption + HMAC hashing + HTTPS | LOW |
| National ID exposure | Low | Critical | CRITICAL | Dual encryption (HMAC + Fernet) + encrypted DB column | LOW |
| Health data exposure | Low | Critical | CRITICAL | Fernet encryption + consent management | LOW |
| Brute-force attack on login | Medium | Medium | MEDIUM | Rate limiting (10/min) + account lockout (5 attempts) | LOW |
| TOTP replay attack | Low | High | MEDIUM | Cache-based replay protection (90s window) | LOW |
| Teacher accessing unauthorized student data | Medium | Medium | MEDIUM | IDOR checks on all API endpoints | LOW |
| Parent accessing other children's data | Low | High | MEDIUM | ParentStudentLink verification + consent middleware | LOW |
| Backup data theft | Low | High | MEDIUM | Gzip + checksum + S3 encryption (STANDARD_IA) | LOW |
| Insider threat (admin abuse) | Low | High | MEDIUM | Immutable audit logs (DB trigger) + role separation | LOW |
| SMS/Email spoofing via Twilio | Low | Medium | MEDIUM | Twilio credentials encrypted (Fernet) | LOW |
| Cross-site scripting (XSS) | Low | Medium | MEDIUM | CSP nonce-based + template auto-escape + |safe documentation | LOW |

### 2.2 Risk Summary

| Risk Level | Count | Percentage |
|-----------|-------|------------|
| LOW (after controls) | 12 | 100% |
| MEDIUM (after controls) | 0 | 0% |
| HIGH (after controls) | 0 | 0% |

---

## 3. Mitigation Measures

### 3.1 Technical Controls

| Control | Implementation | Standard |
|---------|---------------|----------|
| Encryption at rest | Fernet AES-128 (national_id, health, Twilio) | PDPPL Art. 19 |
| Encryption in transit | TLS 1.2+ with HSTS preload | NIST SP 800-52 |
| Access control | 10+ roles with middleware enforcement | OWASP ASVS V4 |
| Authentication | HMAC backend + TOTP 2FA + replay protection | NIST SP 800-63B |
| Audit logging | Immutable AuditLog with DB trigger | ISO 27001 A.12 |
| Consent management | ConsentRecord + ParentConsentMiddleware | PDPPL Art. 5 |
| Breach notification | BreachReport with 72-hour NCSA deadline | PDPPL Art. 11 |
| Right to erasure | ErasureRequest workflow with anonymization | PDPPL Art. 18 |
| File upload security | Extension + MIME + magic bytes validation | OWASP ASVS V12 |
| Rate limiting | Multi-tier (login/2FA/API) | OWASP ASVS V11 |
| Key rotation | MultiFernet + management command | ISO 27001 A.10 |

### 3.2 Organizational Controls

| Control | Status |
|---------|--------|
| DPO appointed | Configured in settings (DPO_NAME, DPO_EMAIL, DPO_PHONE) |
| Privacy policy | Available on platform (parent consent page) |
| Staff training | Pending — NCSA cybersecurity curricula available |
| Incident response plan | Documented in RUNBOOK.md v2.0 |
| Backup and recovery | Daily automated + DR drill template |
| Vendor assessment | Twilio, AWS S3 — standard contractual clauses needed |

---

## 4. Data Subject Rights

| Right | PDPPL Article | Implementation | Status |
|-------|--------------|---------------|--------|
| Right to access | Art. 8 | Parent portal with grade/attendance/behavior views | IMPLEMENTED |
| Right to rectification | Art. 9 | Admin can update records; audit trail preserved | IMPLEMENTED |
| Right to erasure | Art. 18 | ErasureRequest API with anonymization | IMPLEMENTED |
| Right to withdraw consent | Art. 16 | ConsentRecord.withdrawn_at + middleware enforcement | IMPLEMENTED |
| Right to data portability | Art. 10 | Excel export for grades, attendance, certificates | IMPLEMENTED |
| Right to object | Art. 15 | Contact DPO via configured email/phone | AVAILABLE |

---

## 5. Third-Party Processors

| Processor | Purpose | Data Shared | Location | Safeguards |
|-----------|---------|-------------|----------|------------|
| Twilio | SMS notifications | Phone numbers, message content | USA | Encrypted credentials, TLS |
| AWS S3 | File storage | Uploaded documents, digital books | me-south-1 (Bahrain) | Signed URLs, private ACL, STANDARD_IA |
| Sentry | Error tracking | Stack traces (NO PII) | EU/USA | send_default_pii=False |
| GitHub | Source code hosting | Application code (NO data) | USA | Private repository |

---

## 6. DPO Review and Approval

### Assessment Outcome
Based on this DPIA, the residual risks after implementing all technical and organizational
controls are **LOW** across all identified risk scenarios. The processing activities are
compliant with PDPPL requirements.

### Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| DPO | سفيان أحمد محمد مسيف | __________ | __________ |
| School Principal | __________ | __________ | __________ |

### Review Schedule
- **Next review:** September 2026 (beginning of academic year 2026-2027)
- **Trigger review:** Any significant change in data processing activities

---

*Document prepared in accordance with PDPPL (Law 13/2016) Article 11 and PDPPL Guidelines (2021)*
