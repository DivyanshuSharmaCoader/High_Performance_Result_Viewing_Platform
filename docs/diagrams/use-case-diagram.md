# Use-Case Diagram

> Textual use-case specifications (pre/post-conditions, main and alternate flows) are in the [SRS §3](../SRS.md#3-use-cases).

## 1. Overall system use cases

```mermaid
flowchart LR
    Student(["👤 Student"])
    Faculty(["👤 Faculty / Result Operator"])
    Admin(["👤 Institution Admin"])
    Owner(["👤 Institution Owner"])
    PAdmin(["👤 Platform Admin"])
    Verifier(["👤 Verifier (anonymous)"])
    Email[["✉ Email Provider"]]
    Pay[["₹ Payment Provider (V1)"]]

    subgraph SC["ScoreCode Platform"]
        direction TB
        UC1(["UC-01 Register institution"])
        UC2(["UC-02 Log in / log out"])
        UC3(["UC-03 Activate account"])
        UC4(["UC-04 Configure institution and branding"])
        UC5(["UC-05 Manage staff and roles"])
        UC6(["UC-06 Manage academic structure"])
        UC7(["UC-07 Manage students / import roster"])
        UC8(["UC-08 Configure examination and grading"])
        UC9(["UC-09 Enter marks"])
        UC10(["UC-10 Import marks file"])
        UC11(["UC-11 Process results and preview"])
        UC12(["UC-12 Approve results"])
        UC13(["UC-13 Publish / schedule / withdraw"])
        UC14(["UC-14 Correct and re-publish"])
        UC15(["UC-15 View result and history"])
        UC16(["UC-16 Download marksheet"])
        UC17(["UC-17 Verify marksheet"])
        UC18(["UC-18 Receive notifications"])
        UC19(["UC-19 View analytics"])
        UC20(["UC-20 View audit log"])
        UC21(["UC-21 Manage subscription"])
        UC22(["UC-22 Manage tenants and plans"])
        UC23(["UC-23 Monitor platform health"])
        UC24(["UC-24 Export tenant data"])
    end

    Owner --- UC1
    Owner --- UC21
    Owner --- UC24
    Owner -. "inherits all admin use cases" .- Admin

    Admin --- UC2
    Admin --- UC4
    Admin --- UC5
    Admin --- UC6
    Admin --- UC7
    Admin --- UC8
    Admin --- UC10
    Admin --- UC11
    Admin --- UC12
    Admin --- UC13
    Admin --- UC14
    Admin --- UC19
    Admin --- UC20

    Faculty --- UC2
    Faculty --- UC9
    Faculty --- UC10
    Faculty --- UC19

    Student --- UC3
    Student --- UC2
    Student --- UC15
    Student --- UC16
    Student --- UC18

    Verifier --- UC17

    PAdmin --- UC22
    PAdmin --- UC23

    UC13 --- Email
    UC18 --- Email
    UC21 --- Pay
```

## 2. Include / extend relationships (result pipeline)

```mermaid
flowchart TB
    UC10(["UC-10 Import marks file"]) -->|include| V(["Validate file"])
    UC10 -->|include| M(["Map columns"])
    E(["Download error report"]) -.->|extend| UC10
    UC11(["UC-11 Process results"]) -->|include| C(["Compute grades"])
    UC11 -->|include| A(["Detect anomalies"])
    UC12(["UC-12 Approve results"]) -->|include| R(["Pre-render marksheets"])
    UC13(["UC-13 Publish"]) -->|include| S(["Create result snapshots"])
    UC13 -->|include| VR(["Activate verification records"])
    N(["Notify students"]) -.->|extend| UC13
    SCH(["Schedule publication"]) -.->|extend| UC13
    UC14(["UC-14 Correct and re-publish"]) -->|include| UC11
    UC14 -->|include| UC12
    UC14 -->|include| UC13
    UC16(["UC-16 Download marksheet"]) -->|include| AUTH(["Authorize own result"])
```

## 3. Actor generalisation

```mermaid
flowchart BT
    Owner(["Institution Owner"]) -->|is a| Admin(["Institution Admin"])
    Admin -->|is a| Staff(["Tenant Staff User"])
    Faculty(["Faculty"]) -->|is a| Staff
    Staff -->|is a| TUser(["Tenant User"])
    Student(["Student"]) -->|is a| TUser
    PAdmin(["Platform Admin"]) -->|is a| PUser(["Platform User - separate realm"])
```
