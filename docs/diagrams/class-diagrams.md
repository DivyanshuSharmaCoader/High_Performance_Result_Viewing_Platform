# Class Diagrams

> Domain model and key design patterns. Table-level detail is in [07 Database](../07-database-design.md); module structure in [08 Backend](../08-backend-architecture.md).

## 1. Core domain model (simplified)

```mermaid
classDiagram
    direction LR
    class Tenant {
        +UUID id
        +str slug
        +str name
        +TenantType type
        +TenantStatus status
        +str timezone
        +suspend(reason)
        +reactivate()
    }
    class Subscription {
        +UUID id
        +Plan plan
        +SubscriptionStatus status
        +date period_start
        +date period_end
        +is_effective() bool
    }
    class Plan {
        +str code
        +str name
        +int price_paise_yearly
    }
    class FeatureValue {
        +str feature_key
        +Json value
    }
    class User {
        +UUID id
        +str login_id
        +str email
        +UserKind kind
        +UserStatus status
        +set_password(raw)
        +verify_password(raw) bool
    }
    class RoleGrant {
        +Role role
        +UUID department_id
    }
    class Student {
        +UUID id
        +str enrollment_no
        +str full_name
        +StudentStatus status
        +archive()
    }
    class Program {
        +str code
        +str name
    }
    class Cohort {
        +str code
        +str name
    }
    class Course {
        +str code
        +str name
        +Decimal credits
    }
    class AcademicSession {
        +str code
        +date starts_on
        +date ends_on
    }
    class Term {
        +str code
        +int sequence
    }
    class Examination {
        +UUID id
        +str name
        +ExamStatus status
        +datetime scheduled_publish_at
        +open_marks_entry()
        +close_marks_entry()
        +transition(event)
    }
    class ExamPaper {
        +list~Component~ components
        +Decimal max_total
        +Decimal pass_total
        +Decimal credits
    }
    class MarkEntry {
        +dict components
        +Decimal total
        +Attendance attendance
        +int version
    }
    class GradingSchemeVersion {
        +int version
        +str strategy
        +Json config
    }
    class ResultRun {
        +int revision
        +str input_hash
        +RunStatus status
    }
    class StudentExamResult {
        +Decimal total
        +Decimal percentage
        +str grade
        +Decimal sgpa
        +Outcome outcome
    }
    class Publication {
        +int version
        +PublicationStatus status
        +datetime published_at
        +publish()
        +withdraw(reason)
        +supersede()
    }
    class PublishedResult {
        +Json payload
        +str payload_hash
    }
    class VerificationRecord {
        +str code
        +str document_sha256
        +VerificationStatus status
        +revoke(reason)
    }
    class AuditEvent {
        +str action
        +str entity_type
        +UUID entity_id
        +Json before
        +Json after
        +datetime occurred_at
    }

    Tenant "1" *-- "many" Subscription
    Subscription "many" --> "1" Plan
    Plan "1" *-- "many" FeatureValue
    Tenant "1" *-- "many" User
    User "1" *-- "many" RoleGrant
    Tenant "1" *-- "many" Student
    Student "0..1" -- "1" User : account
    AcademicSession "1" *-- "many" Term
    Program "1" *-- "many" Cohort
    Cohort "many" -- "many" Student : membership
    Term "1" o-- "many" Examination
    Examination "1" *-- "many" ExamPaper
    ExamPaper "many" --> "1" Course
    Examination "many" -- "many" Cohort : sits
    ExamPaper "1" *-- "many" MarkEntry
    MarkEntry "many" --> "1" Student
    Examination "1" *-- "many" ResultRun
    ResultRun "many" --> "1" GradingSchemeVersion
    ResultRun "1" *-- "many" StudentExamResult
    Examination "1" *-- "many" Publication
    Publication "1" --> "1" ResultRun
    Publication "1" *-- "many" PublishedResult
    PublishedResult "1" -- "1" VerificationRecord
    Tenant "1" *-- "many" AuditEvent
```

## 2. Grading engine — Strategy pattern (open/closed principle)

```mermaid
classDiagram
    class GradingStrategy {
        <<interface>>
        +str code
        +validate_config(config) GradingConfig
        +grade_paper(paper, marks, cfg) PaperResult
        +aggregate(papers, cfg) ExamResult
    }
    class PercentageBandsStrategy {
        +grade_paper(paper, marks, cfg) PaperResult
        +aggregate(papers, cfg) ExamResult
    }
    class CreditGpaStrategy {
        +grade_paper(paper, marks, cfg) PaperResult
        +aggregate(papers, cfg) ExamResult
        -sgpa(papers) Decimal
    }
    class MarksOnlyStrategy {
        +grade_paper(paper, marks, cfg) PaperResult
        +aggregate(papers, cfg) ExamResult
        -rank(results) list
    }
    class RelativeGradingStrategy {
        <<future plugin>>
    }
    class GradingEngine {
        -dict registry
        +compute(inputs, scheme_version) list~ExamResult~
    }
    class ResultProcessor {
        -MarksQuery marks
        -GradingEngine engine
        -ResultRepository repo
        +run(exam_id) ResultRun
    }
    GradingStrategy <|.. PercentageBandsStrategy
    GradingStrategy <|.. CreditGpaStrategy
    GradingStrategy <|.. MarksOnlyStrategy
    GradingStrategy <|.. RelativeGradingStrategy
    GradingEngine o-- GradingStrategy
    ResultProcessor --> GradingEngine
```

## 3. Import pipeline — Template Method + profiles

```mermaid
classDiagram
    class ImportPipeline {
        <<abstract>>
        +run(job) ImportResult
        #parse(file) RowStream
        #map(rows, mapping) MappedRows
        #validate(rows, ctx) list~RowOutcome~
        #commit(rows, ctx) CommitSummary
    }
    class ImportProfile {
        <<interface>>
        +kind str
        +required_fields() list
        +load_context(tenant, target) ValidationContext
        +rules() list~ValidationRule~
        +apply(valid_rows, ctx) CommitSummary
    }
    class StudentImportProfile
    class CourseImportProfile
    class MarksImportProfile
    class ValidationRule {
        <<interface>>
        +code str
        +check(row, ctx) list~Issue~
    }
    class OutOfRangeRule
    class UnknownStudentRule
    class DuplicateInFileRule
    class TotalMismatchRule
    class FileParser {
        <<interface>>
        +rows(stream) RowStream
    }
    class CsvParser
    class XlsxParser

    ImportPipeline --> ImportProfile
    ImportPipeline --> FileParser
    ImportProfile <|.. StudentImportProfile
    ImportProfile <|.. CourseImportProfile
    ImportProfile <|.. MarksImportProfile
    ImportProfile o-- ValidationRule
    ValidationRule <|.. OutOfRangeRule
    ValidationRule <|.. UnknownStudentRule
    ValidationRule <|.. DuplicateInFileRule
    ValidationRule <|.. TotalMismatchRule
    FileParser <|.. CsvParser
    FileParser <|.. XlsxParser
```

## 4. Application layer — services, repositories, dependency inversion

```mermaid
classDiagram
    class TenantContext {
        +UUID tenant_id
        +str slug
        +TenantStatus status
    }
    class Principal {
        +UUID user_id
        +UUID tenant_id
        +set roles
        +has(permission) bool
    }
    class UnitOfWork {
        +begin(ctx)
        +commit()
        +rollback()
    }
    class TenantScopedRepository~T~ {
        <<abstract>>
        #TenantContext ctx
        +get(id) T
        +list(filter) list~T~
        +add(entity)
    }
    class PublicationService {
        -UnitOfWork uow
        -Entitlements ent
        -AuditLog audit
        -JobQueue jobs
        +publish(exam_id, when) Publication
        +withdraw(pub_id, reason)
    }
    class Entitlements {
        <<interface>>
        +has(feature) bool
        +require(feature)
        +check_limit(key, delta)
    }
    class AuditLog {
        <<interface>>
        +record(event)
    }
    class JobQueue {
        <<interface>>
        +enqueue(job, payload)
    }
    class FileStore {
        <<interface>>
        +put(key, bytes)
        +signed_url(key, ttl) str
    }
    class S3FileStore
    class PgJobQueue
    PublicationService --> UnitOfWork
    PublicationService --> Entitlements
    PublicationService --> AuditLog
    PublicationService --> JobQueue
    TenantScopedRepository --> TenantContext
    FileStore <|.. S3FileStore
    JobQueue <|.. PgJobQueue
```
