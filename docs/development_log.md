## 2026-07-30

### Repository Setup

- Created GitHub repository.
- Defined project scope.
- Created initial project structure.
- Added project documentation templates.
- Configured .gitignore.

Development will begin after the Europe trip.

## 2026-08-20

### Workflow and Requirements Analysis
I interviewed the stakeholder to understand the overall business workflow and identify the project requirements. I then documented the workflow, the documents involved at each stage, and how they are connected.
This was a valuable opportunity to understand how and where the data is actually used before beginning the data engineering work. It also helped me see the entire business process rather than viewing each document as an isolated data source.
Since the stakeholder’s requirements were clear, I was able to define the project goal more specifically: building a structured data platform that can eventually support quotation automation.

## 2026-09-01

### Data Discovery Completed
I have completed the initial data discovery phase. I reviewed spare parts and service quotations and identified the different types of data contained in each document. This process took longer than I expected.
The main challenges were:
- Since I was not familiar with the actual business operations, it was difficult to fully understand the contents of the quotations.
- The quotation items were recorded inconsistently, so I realized that not all the data could be classified according to a single fixed set of rules.

However, after reviewing multiple quotations, I gained a much clearer understanding of the business workflow. I also began to see how the database schema should be structured while still accommodating irregular and incomplete data.
My next step is to create the first draft of the data schema and test it by extracting data from several sample quotations.

## 2026-09-09

### ER Diagram Completed
- Created the initial ERD for quotation data, including customers, vessels, quotation items, KIT components, and service details.

## 2026-09-14

### Database Schema Creation, Sample Data Loading, and Schema Revision

- I created the initial database schema based on the completed ERD. I used AI to generate the SQL and reviewed the resulting schema myself. I then manually loaded one sample quotation from each quotation type: M (item quotation) and O (service quotation).
- During the loading process, I found that the meaning and intended use of some columns were unclear. Since the same fields can appear differently depending on the quotation type, I decided to create a data dictionary to define each column and establish consistent data-entry rules.
- I also discovered that some group-level information was being lost. In addition to the main pump and servo pump, the line filter and Others groups also contain product or equipment model information. I therefore decided to revise the schema to preserve this information.

## 2026-09-23

### Database Schema Updated

- Updated the ERD, database schema, and data dictionary to version 2.