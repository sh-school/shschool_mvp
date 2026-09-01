"""The tenant surface of the database, classified table by table.

Row-level security policies are column predicates. A table that carries no
`school_id` cannot be policed by one, and — because migration 0037's reconcile
loop selects on that column — such a table is not merely unprotected but
*invisible* to the mechanism that protects everything else. `DeadLetterMessage`
sat in exactly that blind spot until migration 0008 pulled it out.

A physical audit of the models (including the join tables Django creates for
`ManyToManyField`, which `apps.get_models()` omits by default) puts every table
in one of four classes:

    DIRECT_SCHOOL           carries school_id; policed by core/0037's reconcile
    PARENT_DERIVED          no school_id; policed by a predicate on its parent
    GLOBAL_INFRASTRUCTURE   holds no tenant rows
    SPECIAL_UNRESOLVED      holds tenant data with no derivable owner

`DIRECT_SCHOOL` is not listed here — it is computed from the models, so a new
school-scoped table joins it without anyone editing this file. The other three
are declared, and the coverage guard fails on any table that appears in none of
the four. That failure is the point: it forces a ruling instead of letting a new
table default into the blind spot.

`SPECIAL_UNRESOLVED` is not an allowlist. Each entry names the decision that
blocks it and the track that owns it. A third entry should not be added without
the same.
"""

# ── Parent-derived: the school comes from a parent row ───────────────────────
#
# Adding a duplicate `school_id` to each of these would create twenty second
# copies of a fact that already exists — twenty chances to disagree with the
# parent. Reading the parent instead means there is only ever one answer.
#
# The value records the derivation the policy implements, so a reviewer can
# check the SQL against the intent without reconstructing it from the models.

PARENT_DERIVED = {
    # behavior
    "core_behaviorpointrecovery": "infraction -> core_behaviorinfraction.school_id",
    # core
    "core_studentenrollment": "class_group -> core_classgroup.school_id",
    "core_semester": "academic_year -> core_academicyear.school_id",
    "core_calendarevent": "academic_year -> core_academicyear.school_id",
    # exam_control — six tables, all resolving to ExamSession.school
    "exam_control_examroom": "session -> exam_control_examsession.school_id",
    "exam_control_examschedule": "session -> exam_control_examsession.school_id (+ room consistency)",
    "exam_control_examsupervisor": "session -> exam_control_examsession.school_id (+ room consistency)",
    "exam_control_examincident": "session -> exam_control_examsession.school_id (+ room, behavior_link consistency)",
    "exam_control_examenvelope": "schedule -> session -> exam_control_examsession.school_id",
    "exam_control_examgradesheet": "schedule -> session -> exam_control_examsession.school_id",
    # library
    "core_bookborrowing": "book -> core_librarybook.school_id",
    "core_libraryactivity_participants": (
        "libraryactivity -> core_libraryactivity.school_id "
        "(+ participant must hold a core_membership here, on write)"
    ),
    # operations
    "operations_permissionauditlog": "temp_permission -> operations_temporarypermission.school_id",
    # quality
    "quality_evaluationaxis": "template -> quality_roleevaluationtemplate.school_id",
    "quality_evaluationscore": "evaluation -> quality_employeeevaluation.school_id",
    "quality_observationscore": (
        "observation -> quality_classroomobservation.school_id (+ criterion consistency)"
    ),
    "quality_operationaltarget": "domain -> quality_operationaldomain.school_id",
    "quality_operationalindicator": "target -> domain -> quality_operationaldomain.school_id",
    "quality_procedureevidence": "procedure -> quality_operationalprocedure.school_id",
    "quality_procedurestatuslog": "procedure -> quality_operationalprocedure.school_id",
    # operations
    "operations_schedulingresource_subjects": (
        "schedulingresource -> operations_schedulingresource.school_id "
        "(+ subject must belong to the same school, on write)"
    ),
    # academic_management
    "academic_management_teacherworkloadallocation": (
        "workload_plan -> academic_management_teacherworkloadplan.school_id"
    ),
    # transport
    "core_busroute": "bus -> core_schoolbus.school_id",
    "core_busroute_students": (
        "busroute -> bus -> core_schoolbus.school_id "
        "(+ student must hold a core_membership here, on write)"
    ),
}


# ── Global: no tenant rows ───────────────────────────────────────────────────
#
# A table belongs here because its rows are not owned by a school, not because
# nobody has got round to policing it.

GLOBAL_INFRASTRUCTURE = {
    "auth_group": "Django auth groups are platform-wide; tenant RBAC is core_membership/core_role",
    "auth_group_permissions": "join table over two global tables",
    "auth_permission": "permission catalogue, created by Django from the models",
    "axes_accessattempt": "login throttling state, keyed on username/IP before a tenant is known",
    "axes_accessfailurelog": "login throttling state, keyed on username/IP before a tenant is known",
    "axes_accesslog": "login throttling state, keyed on username/IP before a tenant is known",
    "behavior_violationcategory": "shared catalogue of violation types, not per school",
    "core_customuser": "a person may hold memberships in more than one school; tenancy lives in core_membership",
    "core_customuser_groups": "join table between a global user and a global group",
    "core_customuser_user_permissions": "join table between a global user and a global permission",
    "core_profile": "extends core_customuser one-to-one; inherits its platform-wide scope",
    "core_school": "the tenant itself; scoping it to itself is meaningless",
    "developer_feedback_auditlog": "developer channel, deliberately cross-school",
    "developer_feedback_developermessage": "developer channel, deliberately cross-school",
    "developer_feedback_developermessagenotification": "developer channel, deliberately cross-school",
    "developer_feedback_legalonboardingconsent": "consent given by a person to the platform, not to a school",
    "developer_feedback_messageedithistory": "developer channel, deliberately cross-school",
    "developer_feedback_messagestatuslog": "developer channel, deliberately cross-school",
    "django_admin_log": "Django admin audit trail, keyed on user and content type",
    "django_content_type": "model registry",
    "django_session": "session store, keyed on session id",
    "notifications_usernotificationpreference": "a person's own channel preferences, held once across schools",
    "token_blacklist_blacklistedtoken": "JWT revocation list, keyed on token",
    "token_blacklist_outstandingtoken": "JWT revocation list, keyed on token",
}


# ── Unresolved: tenant data, no derivable owner ──────────────────────────────

SPECIAL_UNRESOLVED = {
    "core_healthrecord": (
        "Student health data (blood type, allergies, chronic diseases, medications) "
        "hanging off core_customuser only. A person's tenancy is a many-to-many "
        "through core_membership, so a parent predicate would show one health "
        "record to every school the student is enrolled in. Whether that is "
        "correct is a data-ownership question, not an engineering one. "
        "Tracked as HEALTH_RECORD_TRACK; encryption of the write path is a "
        "separate open item on the same track."
    ),
    "core_storedfile": (
        "The DatabaseStorage backing table: name, content, size, content_type and "
        "nothing else — no foreign key of any kind. Django's Storage interface "
        "addresses a file by name alone, so isolation here needs ownership "
        "metadata that does not exist yet rather than a policy over columns that "
        "do. Tracked as STORED_FILE_TRACK, alongside P2-D FileReference."
    ),
}


# ── Tables migration 0037 leaves to grants rather than to a policy ───────────
#
# `core_membership` and `core_role` answer "which school is this?" and so cannot
# be filtered by the answer. `app_rls_role_school` is the mapping that
# `app_rls_school()` reads; a policy on it would call the function that reads it.
# All three are protected by revoked write privileges instead, and 0037 excludes
# them from the reconcile loop by name.

BOOTSTRAP_EXCLUDED = frozenset(
    {
        "core_membership",
        "core_role",
        "app_rls_role_school",
    }
)


def direct_school_tables():
    """Tables carrying a `school_id` column, read from the models."""
    from django.apps import apps

    return {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if "school_id" in {field.attname for field in model._meta.local_fields}
    }


def tenant_reachable_tables():
    """Tables that are school-scoped, directly or through a chain of relations.

    `include_auto_created=True` is not optional here. Django's default omits the
    join tables it generates for `ManyToManyField`, and two of those hold tenant
    associations — an inventory without them reports a surface it has not seen.
    """
    from django.apps import apps

    models = apps.get_models(include_auto_created=True)
    direct = direct_school_tables()
    reachable = {m for m in models if m._meta.db_table in direct}

    grew = True
    while grew:
        grew = False
        for model in models:
            if model in reachable:
                continue
            if any(
                field.is_relation and field.related_model in reachable
                for field in model._meta.local_fields
            ):
                reachable.add(model)
                grew = True

    return {model._meta.db_table for model in reachable}


def policy_required_tables():
    """Every table that must carry a `school_isolation` policy.

    Only the bootstrap three are excluded, because a policy on them would be
    circular. The unresolved two are absent by consequence, not by exemption:
    they carry no `school_id` and have no derivation, so they never enter the
    set. Should either of them acquire a tenant column, it joins this set the
    same day — subtracting them by name would instead have exempted them
    silently, which is how the blind spot was created in the first place.
    """
    return (direct_school_tables() | set(PARENT_DERIVED)) - BOOTSTRAP_EXCLUDED
