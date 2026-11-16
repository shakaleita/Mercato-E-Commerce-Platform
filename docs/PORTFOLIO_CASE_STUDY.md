# Mercato — Engineering Case Study & Quality Roadmap

**Portfolio:** [Digital Solution9](https://github.com/shakaleita/teamforge-saas/blob/main/PORTFOLIO.md) · **Repository:** [Source](https://github.com/shakaleita/Mercato-E-Commerce-Platform)  
**Stack:** React, FastAPI, SQLite · **Status:** Portfolio application / local MVP, not audited production software.

## Problem and implemented workflow
Product inventory, order workflows, idempotent checkout, cancellation and inventory restoration.

This summary is grounded in the repository's existing public README and project documentation. It does not imply that every behavior has been independently re-tested for this particular review.

## Production invariants to enforce
- A checkout retry must never duplicate an order
- Reserved and available stock can never become negative
- Order cancellation must restore stock exactly once

## Test and evidence plan
- Concurrent checkout stress against a single SKU
- Cancellation and payment-failure recovery
- Role and permission checks for inventory changes

To demonstrate mature engineering, publish repeatable test results, screenshots recorded from a running app, a benchmark with its methodology, and a threat-model summary. No metrics are invented here.

## Highest-value upgrades
1. Use a relational database with transaction boundaries and migrations
2. Implement real sandbox payment webhooks with signature verification
3. Add robust pricing, tax, refunds and fulfillment state machines

## Release criteria before calling this 'production-ready'
- Authentication and authorization boundaries are implemented and tested for the entire API surface.
- Core domain invariants have positive, negative, concurrency, and rollback test cases.
- Fresh installation, migrations, backup/restore, and deployment are reproducible.
- Accessibility, browser flows, security review, application logs, and measured performance have been checked.
- Documentation accurately identifies demo-only functions and does not use real client/patient data.

**Note:** No production-readiness rating is assigned based only on this review. This file is an engineering improvement plan, not a certification.
