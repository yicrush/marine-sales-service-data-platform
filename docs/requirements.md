# System Requirements

## 1. Purpose

This document defines the initial requirements for an end-to-end data engineering project designed to improve data management and workflow efficiency for a marine parts and service business.

The requirements were identified through an interview with the primary user who currently manages marine parts and service transactions.

The core objective is to transform fragmented business records, including quotations, purchase orders, invoices, PODs, and service reports, into structured and connected data that can support historical analysis and business process automation.

Based on the stakeholder interview, quotation preparation was identified as a key opportunity for automation. Therefore, quotation generation will be developed as one of the primary use cases built on top of the structured data platform, with service quotation generation prioritized in the initial implementation.

---

## 2. Stakeholder Interview

An initial interview was conducted to understand the current workflow, data storage methods, and major operational pain points.

### Q1. Is there a unique identifier that tracks a transaction from inquiry to completion?

**Answer:**
No. Individual documents have their own identifiers, such as quotation numbers and customer PO numbers, but there is no single identifier that connects the entire transaction.

### Q2. Where are transaction documents currently stored?

**Answer:**
Inquiries are not separately stored.

Quotations, purchase orders, invoices, Proofs of Delivery (POD), and service reports are stored in Google Drive.

The folders are generally organized as:

```text
Customer Company
└── Vessel
    └── Customer PO number
        ├── Purchase Orders
        ├── Invoices
        ├── POD
        └── Service Reports
```

### Q3. How are historical transactions retrieved?

**Answer:**
Historical transactions are manually located through the corresponding customer, vessel, and PO folders in Google Drive.

### Q4. How are historical prices retrieved when preparing a quotation?

**Answer:**

For **KIT / parts quotations**:

* New prices are obtained from an external supplier's customer service team.
* Prices for frequently requested items may be retrieved from an existing reference file.

For **SERVICE quotations**:

* Historical service pricing is manually retrieved from an Excel file maintained during previous operations.

### Q5. Which task is currently the most time-consuming or inconvenient?

**Answer:**
Preparing service quotations.

### Q6. Which task would provide the most value if automated?

**Answer:**
Service quotation preparation.

---

# 3. Current Pain Points

Based on the stakeholder interview, the following problems were identified.

### P-01 — Fragmented Transaction Data

Transaction information is distributed across multiple documents and folders. There is currently no single transaction identifier connecting quotations, purchase orders, invoices, PODs, and service reports.

### P-02 — Manual Historical Data Retrieval

Historical transactions must be manually located by navigating customer, vessel, and PO folders.

### P-03 — Unstructured Historical Pricing Process

Historical service pricing is maintained in Excel and must be manually searched when preparing new quotations.

### P-04 — Manual Service Quotation Preparation

Service quotations require repeated lookup of historical service and pricing information, making quotation preparation time-consuming.

### P-05 — Incomplete Transaction Lifecycle Data

Inquiries are not currently stored as part of the historical transaction records, making it difficult to capture the complete lifecycle from inquiry to completion.

---

# 4. User Requirements

Based on the identified pain points, the system should provide the following capabilities.

| ID    | User Requirement                                                                                                                            | Priority |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| UR-01 | The system should organize related business records under a single transaction.                                                             | High     |
| UR-02 | The user should be able to retrieve historical transactions by customer, vessel, PO number, and other relevant attributes.                  | High     |
| UR-03 | The system should store historical service and pricing data in a structured format.                                                         | High     |
| UR-04 | The user should be able to search and retrieve historical service prices efficiently.                                                       | High     |
| UR-05 | The system should assist with generating service quotations using structured historical service and pricing data.                           | High     |
| UR-06 | The system should maintain relationships between key transaction documents, including quotations, POs, invoices, PODs, and service reports. | Medium   |
| UR-07 | The system should support recording inquiry information as part of the transaction lifecycle.                                               | Medium   |

---

# 5. Initial Project Scope

Based on the stakeholder's priorities, the first implementation will focus on the **SERVICE workflow**.

The initial scope includes:

1. Extract historical service and pricing data from existing Excel files.
2. Clean and standardize the extracted data.
3. Load the transformed data into a structured database.
4. Link service records to customers, vessels, quotations, POs, and other relevant transaction information where available.
5. Provide a method for searching historical service records and prices.
6. Use the structured historical data to assist with service quotation generation.

The KIT / parts workflow will be considered as a later extension of the system.

---

# 6. Initial Data Sources

| Data Source                | Current Format                  | Expected Use                                 |
| -------------------------- | ------------------------------- | -------------------------------------------- |
| Historical service pricing | Excel                           | Service pricing ETL and quotation generation |
| Quotations                 | Documents in Google Drive       | Historical quotation data                    |
| Customer POs               | Documents in Google Drive       | Transaction identification and order data    |
| Invoices                   | Documents in Google Drive       | Billing and transaction data                 |
| Service Reports            | Documents in Google Drive       | Historical service activity                  |
| PODs                       | Documents in Google Drive       | Delivery confirmation for KIT transactions   |
| Inquiry                    | Not currently stored separately | Future transaction lifecycle tracking        |

---

# 7. Success Criteria

The initial version of the system will be considered successful if it can:

* Convert historical service data into a consistent and structured format.
* Store and retrieve historical service transactions from a centralized database.
* Allow users to find relevant historical service pricing without manually searching multiple files.
* Use stored historical data to reduce the manual work required to prepare a service quotation.

These criteria may be refined as the project progresses and additional user feedback is collected.
