# Education Learning Core

Step 11 adds the learning layer on top of the Education Foundation:

`Course -> CourseTeacher -> Lessons -> Exercises`

`Course -> Assessments -> Student Submissions -> Results`

`Student -> LessonProgress`

Migration: `0005_education_learning_core`.

Revision `0008_exercise_submissions` adds numbered student exercise attempts. Students must be enrolled in the course and the lesson must be published; only the student owner and assigned course teachers can read an attempt. Assigned teachers can attach private feedback. Attempt creation, activity recording, and teacher notifications share one database transaction.

All protected routes use `get_current_postgres_user` and `AsyncSession`. Teacher mutations require assignment to the specific course. Students can read published lessons/assessments only when enrolled, submit only as their own Student record, and update only their own draft submissions. Results are teacher-managed and score validation against `Assessment.max_score` is performed in application logic because cross-table CHECK constraints are unsafe.

Lesson progress is stored per student/lesson. Course progress is computed from completed published lessons divided by published lessons, returning zero safely when a course has no published lessons.

Messages, AI generation, automatic grading, certificates, accreditation, payments, live classrooms, realtime delivery, and external education integrations remain deferred.

Live PostgreSQL validation remains blocked when no PostgreSQL server and `ME_YOU_DATABASE_URL` are available. Offline mapper, metadata, migration, and test validation is required before live execution.
