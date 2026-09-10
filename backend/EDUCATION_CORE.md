# Education Core

Education Core provides the initial academic structure for Me&You:

`Institution -> Faculty -> Department -> Course`

Authenticated users can register their own Teacher or Student membership for an institution, and current students can enroll in courses. Teacher/student records reference the existing User identity and do not duplicate account fields.

The schema is introduced by Alembic revision `0004_education_core`. The academic hierarchy cascades from institutions through faculties, departments, and courses. Teacher/student memberships and enrollments use restrictive parent foreign keys so academic history is not silently deleted. Institution administration roles are intentionally deferred; current institution mutations require authentication but do not claim administrative authorization.

Lessons, exercises, assessments, grades, certificates, accreditation, payments, live classes, and external LMS integrations are deferred to later domain steps.
