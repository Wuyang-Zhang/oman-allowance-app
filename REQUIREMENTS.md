

## Oman Students Allowance Calculator – Specification v1.1

------

## 1. Project Overview

This project is a software system designed to **automatically calculate allowances for Omani students studying in China**.

The system calculates three types of payments:

1. Monthly living allowance
2. Annual study allowance
3. One-time excess baggage allowance after graduation

All allowances are **defined in USD**, converted to **RMB (CNY)** using a configurable exchange rate, and **settled in RMB**.

The system must ensure that all calculations are **accurate, deterministic, auditable, and reproducible**.

------

## 2. Scope & Applicability

### 2.1 Covered Students

- Degree students only:
  - Bachelor
  - Master
  - PhD
- Preparatory students are included **only if they belong to a degree stage**, and follow the allowance standard of that stage:
  - Preparatory Bachelor → Bachelor standard
  - Preparatory Master → Master standard
  - Preparatory PhD → PhD standard
- Non-degree students are **out of scope**.

------

## 3. Configurable Parameters

All monetary values, exchange rates, and policy switches must be configurable, with default values.

------

### 3.1 Currency & Exchange Rate Rules

- **Base currency:** USD
- **Settlement currency:** RMB (CNY)

#### Exchange Rate

- USD → CNY exchange rate is:
  - User-configurable
  - Has a system default value
- Exchange rate is applied **at calculation time**

#### Rounding Rule

- All RMB amounts must be:
  - Rounded to **2 decimal places**
  - Using **standard rounding (四舍五入, half-up)**

> ⚠️ Important:
> All intermediate calculations may be done in USD,
> **final settlement values must be converted to RMB and rounded**.

------

### 3.2 Living Allowance (Monthly, USD)

- Configured by degree level:
  - Bachelor
  - Master
  - PhD
- Each degree level has:
  - A default monthly amount (USD)
  - Allowance amount is selectable/configurable

------

### 3.3 Study Allowance (Annual, USD)

- Fixed amount (USD)
- Same for all students (configurable if needed)

------

### 3.4 Excess Baggage Allowance (USD)

- Fixed amount (USD)
- Same for all students
- Paid once after graduation

------

### 3.5 Policy Switch

- Boolean configuration:
  - Whether to issue the study allowance if a student graduates or withdraws **before October of the entry year**
- Default value must be configurable

------

## 4. Required Student Data Fields

Each student record must contain the following fields:

- `student_id` (unique)
- `name`
- `degree_level` (Bachelor / Master / PhD)
- `first_entry_date` (date)
- `graduation_date` (date)
- `status`
  - In-study
  - Graduated
  - Withdrawn

### Constraints

- Entry date **must not be modified**
- Suspension or stop-months are **not allowed**
- Graduation date **may be extended**, and allowances continue normally during the extension period

------

## 5. Living Allowance Rules

### 5.1 General Rule

- Living allowance is issued **monthly**
- Issuance period:
  - From the **month of first entry**
  - Through the **graduation month (inclusive)**

------

### 5.2 First Entry Month (Prorated)

- The first entry month is prorated **by natural calendar days**
- Calculation formula (USD):

```text
Entry month allowance (USD) =
Monthly allowance (USD) × (Days from entry date to month end ÷ Total days in that month)
```

- Natural calendar days are used:
  - 28 / 29 / 30 / 31

------

### 5.3 Subsequent Months

- From the month after entry through the graduation month:
  - Full monthly allowance (USD) is issued
- Graduation month is **not prorated**

------

### 5.4 Currency Conversion

- Monthly allowance is calculated in USD
- Converted to RMB using the configured exchange rate
- RMB amount is rounded to **2 decimal places (half-up)**

------

## 6. Study Allowance Rules (Annual)

### 6.1 Issuance Timing

- Issued **once per academic year**
- Fixed issuance month: **October**

------

### 6.2 Issuance Condition

- In October of a given year:
  - If the student is **in-study and not graduated**, issue **one study allowance (USD)**

------

### 6.3 Academic Year Definition

- A full academic year is **not required**
- Any year in which the student is in-study in October counts as **one academic year**

Examples:

- Bachelor student (5 years) → 5 payments
- Master student (2 years) → 2 payments

------

### 6.4 Special Case (Configurable)

- If a student graduates or withdraws **before October of the entry year**:
  - Whether to issue that year’s study allowance is controlled by the policy switch

------

### 6.5 Currency Conversion

- Study allowance is calculated in USD
- Converted to RMB using the configured exchange rate
- RMB amount is rounded to **2 decimal places (half-up)**

------

## 7. Excess Baggage Allowance

- Issued **once per student**
- Issued **after graduation**
- Fixed amount (USD)
- Not degree-dependent

### Trigger Condition

- Student status changes to `Graduated`

### Currency Conversion

- Converted from USD to RMB
- Rounded to **2 decimal places (half-up)**

------

## 8. Output Requirements

All outputs must be **settled in RMB (CNY)**.

### 8.1 Per-Student Breakdown

- Monthly living allowance:
  - USD value
  - Applied exchange rate
  - RMB settlement value
- Annual study allowance (RMB)
- Excess baggage allowance (RMB)

### 8.2 Aggregated Reports

- Summary by student
- Summary by year
- Summary by allowance type
- RMB totals only (for finance settlement)

### 8.3 Export

- Excel
- CSV

------

## 9. Design Principles

- Calculations must be:
  - Deterministic
  - Reproducible
  - Traceable by date, rule, and exchange rate
- No manual override of calculation results
- All policies, amounts, and exchange rates must be configurable

------

## 10. Non-Functional Notes

- No UI requirements in this version
- Implementation language and framework are flexible
- Focus on correctness of business logic and clean data modeling

------

## End of Document
