---
name: edtech-platform-analyzer
description: 'Guide for analyzing educational technology platforms, including code review, compliance with legal/educational policies (e.g., Qatar PDPPL), and proposing technical and UX improvements. Use for: comprehensive platform assessment, legal compliance checks, and modernization recommendations.'
license: Complete terms in LICENSE.txt
---

# EdTech Platform Analyzer Skill

This skill provides a structured workflow for conducting a comprehensive analysis of educational technology (EdTech) platforms. It covers technical architecture, code quality, compliance with relevant legal and educational policies, security posture, and user experience, culminating in actionable recommendations for improvement and modernization.

## Workflow for Platform Analysis

Follow these steps to perform a thorough analysis of an EdTech platform:

### Phase 1: Initial Project Setup and Overview

1.  **Unzip Project Files:** Extract the provided platform codebase into a designated directory.
2.  **Explore General Structure:** Review the project's directory layout, identify key applications (Django apps), and understand the overall modularity.
3.  **Identify Core Technologies:** Examine `requirements.txt`, `Dockerfile`, and configuration files (e.g., `settings/base.py`) to determine the primary technologies and frameworks used (e.g., Django, DRF, HTMX, PostgreSQL).

### Phase 2: Codebase Analysis (Backend & Frontend)

1.  **Backend Architecture Review:**
    *   **Django Apps:** Analyze the purpose and interdependencies of each Django application (e.g., `core`, `operations`, `assessments`, `quality`).
    *   **Service Layer:** Examine the implementation of service layers (e.g., `operations/services.py`) to understand business logic separation, testability, and reusability.
    *   **API Design:** Review Django REST Framework (DRF) implementations (e.g., `operations/api_views.py`) for structure, authentication, authorization, and data serialization.
    *   **Database Models:** Analyze `models.py` files across applications to understand data schema, relationships, and multi-tenancy implementation.
2.  **Frontend Architecture Review:**
    *   **Template Structure:** Understand how Django templates are organized and rendered.
    *   **HTMX Integration:** Assess the use of HTMX for interactivity, evaluating its effectiveness for the platform's specific needs and identifying areas where it might be stretched.
    *   **JavaScript Usage:** Review any custom JavaScript for complexity, performance, and maintainability.

### Phase 3: Compliance Review

1.  **Legal & Data Privacy Compliance:**
    *   **Review Relevant Regulations:** Analyze provided legal documents (e.g., `references/04_قانون_13_2016_PDPPL_حماية_البيانات.pdf` for Qatar's PDPPL) to identify key requirements for data collection, processing, storage, and consent.
    *   **Cross-reference with Platform:** Evaluate how the platform's data handling practices (e.g., encryption, consent mechanisms) align with these legal requirements. Identify gaps and potential non-compliance.
2.  **Educational Policy Compliance:**
    *   **Review Educational Standards:** Analyze documents like `references/10_لائحة_السلوك_المدرسي_القطرية.pdf` and `references/12_معايير_MOEHE_أوزان_التقييم_40_60.pdf` to understand specific educational policies (e.g., behavior management, assessment weighting).
    *   **Platform Alignment:** Assess how the platform's features (e.g., `BehaviorInfraction`, `AssessmentPackage`) implement or support these policies. Identify areas for closer alignment or feature development.

### Phase 4: Security Assessment

1.  **Authentication & Authorization:** Review `core/middleware.py` and authentication backends for custom permission systems, role-based access control (RBAC), and multi-factor authentication (MFA).
2.  **Data Protection:** Verify encryption mechanisms for sensitive data (e.g., `FERNET_KEY` usage, `encrypt_field` application).
3.  **Configuration Security:** Examine `settings/production.py` for secure defaults (e.g., HTTPS enforcement, cookie security) and proper handling of secrets.
4.  **Vulnerability Identification:** Look for common web vulnerabilities (e.g., XSS, CSRF, SQL Injection) and assess existing mitigations.

### Phase 5: Improvement & Modernization Recommendations

1.  **Technical Enhancements:**
    *   **Performance & Scalability:** Suggest optimizations for database queries, caching strategies (e.g., Redis), asynchronous task processing (e.g., Celery), and potential real-time features (e.g., Django Channels).
    *   **Code Quality & Maintainability:** Recommend refactoring, comprehensive testing strategies, and improved documentation (e.g., API docs with Swagger/OpenAPI).
2.  **Legal & Compliance Enhancements:** Propose specific technical and procedural changes to achieve full compliance with data privacy laws (e.g., DPIA, breach notification workflows, robust consent management).
3.  **User Experience (UX) & User Interface (UI) Modernization:**
    *   **Design Refresh:** Suggest updates to the visual design for a more contemporary look and feel.
    *   **Interactivity:** Recommend enhancements to HTMX usage or selective integration of lightweight JavaScript frameworks for complex interactions.
    *   **Responsiveness & Accessibility:** Ensure full responsiveness across devices and adherence to accessibility guidelines (WCAG).
4.  **AI-Powered & Advanced Features:** Propose integration of AI for early warning systems (academic/behavioral), personalized learning recommendations, sentiment analysis, or virtual assistants.

### Phase 6: Reporting

1.  **Generate Detailed Reports:** Compile findings from each phase into structured reports, highlighting strengths, weaknesses, and actionable recommendations. Ensure clarity, conciseness, and professional presentation.

## Key Considerations

*   **Context is King:** Always consider the specific context of the platform, its target users, and its operational environment when making assessments and recommendations.
*   **Balance:** Strive for a balance between technical excellence, legal compliance, and practical implementation. Not all improvements need to be implemented simultaneously.
*   **Iterative Approach:** Emphasize that modernization is an ongoing process, and an iterative approach is often most effective.

## References

*   **Example Legal Documents:**
    *   `references/04_قانون_13_2016_PDPPL_حماية_البيانات.pdf`
    *   `references/10_لائحة_السلوك_المدرسي_القطرية.pdf`
    *   `references/12_معايير_MOEHE_أوزان_التقييم_40_60.pdf`
*   **Example Analysis Reports (Outputs of this skill):**
    *   `references/shschool_analysis_report.md`
    *   `references/shschool_security_analysis.md`
    *   `references/shschool_backend_frontend_analysis.md`
    *   `references/shschool_modernization_report.md`
    *   `references/pdp_compliance_roadmap.md`
