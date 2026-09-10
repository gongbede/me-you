# Education Learning Core

Step 11 adds the learning layer on top of the Education Foundation:

`Course -> CourseTeacher -> Lessons -> Exercises`

`Course -> Assessments -> Student Submissions -> Results`

`Student -> LessonProgress`

Migration: `0005_education_learning_core`.

All protected routes use `get_current_postgres_user` and `AsyncSession`. Teacher mutations require assignment to the specific course. Students can read published lessons/assessments only when enrolled, submit only as their own Student record, and update only their own draft submissions. Results are teacher-managed and score validation against `Assessment.max_score` is performed in application logic because cross-table CHECK constraints are unsafe.

Lesson progress is stored per student/lesson. Course progress is computed from completed published lessons divided by published lessons, returning zero safely when a course has no published lessons.

Messages, AI generation, automatic grading, certificates, accreditation, payments, live classrooms, realtime delivery, and external education integrations remain deferred.

Live PostgreSQL validation remains blocked when no PostgreSQL server and `ME_YOU_DATABASE_URL` are available. Offline mapper, metadata, migration, and test validation is required before live execution.
