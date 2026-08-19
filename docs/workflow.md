# Current Business Workflow (AS-IS)

This document describes the current operational workflow of a marine parts and service company.

Company and partner names have been generalized to protect confidential business information.

## Business Entities

| Entity         | Description                                                    |
| -------------- | -------------------------------------------------------------- |
| **Customer**   | Shipping company requesting marine parts or technical services |
| **Company**    | Marine parts and service provider                              |
| **Supplier A** | Primary subcontractor / supplier                               |
| **Supplier B** | Upstream manufacturer or supplier                              |
| **Forwarder**  | Logistics company designated by the customer                   |
| **Engineer**   | Engineer dispatched for onboard or dry dock service            |

---

# 1. KIT / Parts Supply Workflow

| Step | Activity                                                                                   | From                    | To         | Document / Data                                                        |
| ---- | ------------------------------------------------------------------------------------------ | ----------------------- | ---------- | ---------------------------------------------------------------------- |
| 1    | Customer requests parts                                                                    | Customer                | Company    | **Inquiry**                                                            |
| 2    | Company provides pricing and supply terms                                                  | Company                 | Customer   | **Quotation**                                                          |
| 3    | Customer confirms the order                                                                | Customer                | Company    | **Customer Purchase Order (PO)**                                       |
| 4    | Company places an order with Supplier A                                                    | Company                 | Supplier A | **Company Purchase Order (PO)**                                        |
| 5    | Supplier A places an upstream order with Supplier B                                        | Supplier A              | Supplier B | **Supplier PO**                                                        |
| 6    | Supplier B confirms that the goods are ready                                               | Supplier B → Supplier A | Company    | **Goods Ready Notification**                                           |
| 7    | Company informs the customer; customer provides its designated forwarding address          | Company ↔ Customer      | —          | **Forwarding Instructions / Address**                                  |
| 8    | Shipping and customs clearance are requested for delivery to the designated forwarder      | Company                 | Forwarder  | **Company Invoice + Supplier Invoice + Shipping/Customs Instructions** |
| 9    | Forwarder receives the goods and confirms delivery                                         | Forwarder               | Company    | **Proof of Delivery (POD)**                                            |
| 10   | Company issues the final billing to the customer using the POD and transaction information | Company                 | Customer   | **Invoice + POD**                                                      |

### Simplified Flow

Customer Inquiry
↓
Quotation
↓
Customer PO
↓
Company PO
↓
Supplier PO
↓
Goods Ready
↓
Forwarding Instructions
↓
Shipment / Customs Clearance
↓
POD
↓
Customer Invoice
↓
**Completed**

---

# 2. SERVICE Workflow

| Step | Activity                                                  | From     | To                          | Document / Data                     |
| ---- | --------------------------------------------------------- | -------- | --------------------------- | ----------------------------------- |
| 1    | Customer requests technical service                       | Customer | Company                     | **Inquiry**                         |
| 2    | Company provides service pricing and conditions           | Company  | Customer                    | **Quotation**                       |
| 3    | Customer confirms the service order                       | Customer | Company                     | **Customer Purchase Order (PO)**    |
| 4    | Customer provides the dry dock schedule                   | Customer | Company                     | **Dry Dock Schedule**               |
| 5    | Engineer is scheduled and dispatched                      | Company  | Engineer / Service Location | **Dispatch / Schedule Information** |
| 6    | Technical service is performed                            | Engineer | Customer                    | Service Activity                    |
| 7    | Engineer submits the completed service report             | Engineer | Company                     | **Service Report**                  |
| 8    | Company issues the invoice based on the completed service | Company  | Customer                    | **Invoice + Service Report**        |

### Simplified Flow

Customer Inquiry
↓
Quotation
↓
Customer PO
↓
Dry Dock Schedule
↓
Engineer Dispatch
↓
Service Completion
↓
Service Report
↓
Customer Invoice
↓
**Completed**

---

# 3. Common Workflow

Both KIT and SERVICE transactions share the same initial commercial process:

**Inquiry → Quotation → Customer PO**

After receiving the customer PO, the workflow branches depending on the order type.

```text
                         Inquiry
                            │
                            ▼
                        Quotation
                            │
                            ▼
                       Customer PO
                            │
               ┌────────────┴────────────┐
               │                         │
               ▼                         ▼
              KIT                      SERVICE
               │                         │
          Supplier PO              Dry Dock Schedule
               │                         │
          Goods Ready              Engineer Dispatch
               │                         │
        Shipment / Delivery          Service Work
               │                         │
              POD                  Service Report
               │                         │
               └────────────┬────────────┘
                            │
                            ▼
                     Customer Invoice
                            │
                            ▼
                         Completed
```

---

# 4. Key Business Documents

The current workflow generates or uses the following key documents:

| Document                    | Purpose                                                               |
| --------------------------- | --------------------------------------------------------------------- |
| **Inquiry**                 | Records the customer's initial request                                |
| **Quotation**               | Provides proposed items/services, pricing, and commercial terms       |
| **Customer PO**             | Confirms the customer's order                                         |
| **Company PO**              | Places an order with a supplier                                       |
| **Supplier PO**             | Records upstream procurement                                          |
| **Supplier Invoice**        | Records supplier-side charges                                         |
| **Company Invoice**         | Bills the customer                                                    |
| **Proof of Delivery (POD)** | Confirms that the goods were delivered                                |
| **Service Report**          | Records completed technical service work                              |
| **Dry Dock Schedule**       | Provides scheduling information for service operations                |
| **Forwarding Instructions** | Provides the destination and logistics information for parts delivery |

---

# 5. Initial Data Engineering Observation

A single business transaction may generate multiple documents across different stages of the workflow.

For example, one KIT transaction may contain:

```text
Transaction
├── Inquiry
├── Quotation
├── Customer PO
├── Company PO
├── Supplier PO
├── Supplier Invoice
├── Company Invoice
└── POD
```

A SERVICE transaction may contain:

```text
Transaction
├── Inquiry
├── Quotation
├── Customer PO
├── Dry Dock Schedule
├── Service Report
└── Company Invoice
```

These documents contain related information but are currently generated at different stages of the business process.

The project will investigate how these documents can be extracted, standardized, linked, and stored as structured data for downstream analysis and workflow automation.
