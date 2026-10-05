# Backend Feature Matrix

Audit baseline: `4c71b8f`; post-implementation state includes the uncommitted changes in this worktree. Product scope is drawn from `README.md`, `EDUCATION_CORE.md`, `EDUCATION_LEARNING_CORE.md`, and `MIGRATIONS.md`. Tests are primarily unit tests with fake sessions; none prove live PostgreSQL behavior. Priority A is core product, B is the broader documented/current vision, and C is a future/provider decision.

| Feature | Current state | Implemented? | Tested? | Production ready? | Priority | Missing work |
|---|---|---:|---:|---:|:---:|---|
| Authentication | Argon2 password hashing, JWT login, PostgreSQL user dependency | Yes | Partial | No | A | Email verification/reset, throttling, token revocation and live DB coverage |
| User accounts | Registration, login, account read, authenticated password change | Partial | Yes | No | A | Recovery/email verification, deletion and retention policy |
| Profiles | Self profile CRUD and institution-network discovery with field allowlist | Yes | Yes | No | A | Privacy controls and media upload |
| Institution/school system | Institution CRUD and academic hierarchy | Yes | Partial | No | A | Join/invitation/approval process is unspecified |
| Institution memberships | Membership roles, add/list/update/remove | Yes | Yes | Partial | A | PostgreSQL concurrency and API-level test coverage |
| Institution administration | Institution-scoped administrators and last-admin protection | Yes | Yes | Partial | A | Administrative audit workflows and production concurrency validation |
| Roles and permissions | ADMIN/TEACHER/STUDENT helpers and course assignment checks | Yes | Yes | Partial | A | Consolidate and extend HTTP-level authorization coverage |
| Social posts | Text post create/read/feed/update/delete | Yes | Partial | No | A | Moderation, privacy policy, and media support |
| Comments | Create/list/update/delete, owner checks, notification | Yes | Partial | No | A | Moderation and expanded route tests |
| Likes | Like/unlike/list with uniqueness and notification | Yes | Partial | No | A | Expanded API/concurrency tests |
| Follows | Follow/unfollow/list, self-follow guard and notification | Yes | Partial | No | A | Expanded API/concurrency tests |
| Feed | Own and followed-user posts, offset pagination | Yes | Partial | Partial | A | Cursor pagination and ranking/filter requirements |
| Notifications | Recipient-scoped list/read/unread count and in-app producers | Yes | Yes | Partial | A | Preferences, delivery channels and retention policy |
| Activity system | Safe internal events, actor-scoped service read | Partial | Yes | No | A | Not a security audit log; event coverage and retention are limited |
| Search | Membership-scoped institution/course search | Yes | Yes | Partial | A | People/content search requirements are unspecified |
| Direct messaging | Direct conversations, membership-scoped history, edit and soft delete | Yes | Partial | No | A | Realtime delivery and attachment support |
| Group conversations | Group creation and member-scoped read | Yes | Partial | No | A | Membership management, moderation and realtime delivery |
| Message read state | Per-member read timestamp and unread count | Yes | Partial | No | A | PostgreSQL concurrency and delivery integration tests |
| Education hierarchy | Institution → faculty → department → course | Yes | Partial | Partial | A | Full PostgreSQL/API validation |
| Faculties/departments | Scoped CRUD under institutions | Yes | Partial | Partial | A | Full PostgreSQL/API validation |
| Courses | Institution-admin CRUD and membership-scoped reads | Yes | Partial | Partial | A | More HTTP and uniqueness/concurrency tests |
| Course enrollment | Authenticated student self-enrollment, institution check | Yes | Partial | Partial | A | Database-level cross-parent invariant and live concurrency validation |
| Lessons | Assigned-teacher authoring; published enrolled-student reads | Yes | Partial | Partial | A | Broader integration tests and media content support |
| Exercises | Teacher-managed exercise instructions and published reads | Yes | Partial | Partial | A | Rich interactive exercise formats are unspecified |
| Exercise attempts/submissions | Numbered student attempts, private teacher review/feedback, notification/activity | Yes | Yes | No | A | Live PostgreSQL uniqueness/concurrency validation |
| Assessments | Teacher authoring and published enrolled-student access | Yes | Partial | Partial | A | Broader integration tests and question formats are unspecified |
| Assessment submissions | Student-owned draft/submitted workflow and teacher access | Yes | Partial | Partial | A | Race-safe update and PostgreSQL integration tests |
| Assessment results | Teacher grading, private student/teacher reads, score bounds | Yes | Partial | Partial | A | PostgreSQL validation of grading invariants |
| Student progress | Lesson completion and course percentage | Yes | Partial | Partial | A | Exercise/assessment progress requirements are unspecified |
| Teacher/student relationships | Institution records and course-teacher assignments | Yes | Partial | Partial | A | Workflow for vetting/approval is unspecified |
| School/institution registration | Any authenticated account may create an institution and becomes its admin | Yes | Partial | Partial | A | Verification/approval requirements are unspecified |
| Media/file foundations | No asset model or storage provider | No | No | No | B | Define storage provider, upload lifecycle, scanning and access policy |
| Live conferencing/recording | Explicitly deferred by education docs | No | No | No | B | Define provider, scheduling, recording consent and retention |
| Reels/media | No media-post/reels model or API | No | No | No | B | Product requirements and storage/transcoding provider |
| Church/media | No church-specific domain or media workflow | No | No | No | B | Product/domain contract required |
| Music functionality | Only `MUSIC_SCHOOL` as an institution type | No | No | No | B | Music product model and media/licensing requirements |
| Monetization | No payment, billing or ledger functionality; docs defer payments | No | No | No | B | Select provider and define ledger, refunds, tax and webhook contracts |
| AI integration | No AI integration; education docs defer AI generation | No | No | No | B | Provider, privacy, safety and cost requirements |
| Administrative functionality | Institution-level administration only | Partial | Partial | No | A/B | Platform administration, moderation and support workflows |
| Search/discovery | Course/institution search and institution-network profiles | Partial | Yes | Partial | A | Content/people discovery and visibility policy |
| Audit/activity/security | Activity metadata is constrained; core access checks exist | Partial | Partial | No | A | Dedicated security audit log, retention, rate limits and more HTTP tests |
| Database migrations | Linear PostgreSQL Alembic history through `0008` | Yes | Structural | Partial | A | Apply/rollback against a live PostgreSQL instance |
| API error handling | FastAPI defaults plus explicit domain errors | Partial | Partial | No | A | Standardized errors and production exception observability |
| Security hardening | JWT secret validation, hashed passwords, object/institution scoping | Partial | Yes | No | A | Rate limiting, token/session revocation and live PostgreSQL security tests |
| Production configuration | Environment-backed PostgreSQL URL and production JWT-secret check | Partial | Partial | No | A | CORS, readiness/liveness, deployment/TLS/pool settings and startup validation |
| Legacy database compatibility | SQLite/Mongo helpers remain separate from PostgreSQL application routes | Partial | Partial | No | C | Decide whether to remove or formally support legacy persistence |

## Priority And Blockers

**A — Core Me&You:** Social, profiles, accounts, institutional membership/administration, education and private communication are present. The exercise-attempt/review flow and password change were added in this pass; production confidence still needs real PostgreSQL and HTTP integration testing.

**B — Full current vision:** Media/file storage, reels, live conferencing/recording, church/media, music, monetization and AI have no defined backend contracts or provider choices in repository documentation. Implementing providers or claiming working endpoints without those decisions would be speculative. No provider abstractions are currently wired.

**C — Future/provider-dependent:** Email delivery for verification/recovery, realtime delivery, media processing, payments and AI require provider configuration and operational policies before implementation.

## Validation Limits

The current automated suite uses mocked sessions for most handler tests. The migration chain renders successfully in PostgreSQL offline mode, but no live PostgreSQL upgrade, query, constraint, transaction-race or rollback validation was available. A green unit suite is not production-readiness evidence.
