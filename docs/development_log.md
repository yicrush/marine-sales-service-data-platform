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
Since the stakeholder’s requirements were clear, I was able to define the project goal more specifically: building a structured data platform that can eventually support quotation automation and pricing analysis.

## 2026-09-01

### Data Discovery Completed
I have completed the initial data discovery phase. I reviewed spare parts and service quotations and identified the different types of data contained in each document. This process took longer than I expected.
The main challenges were:
- Since I was not familiar with the actual business operations, it was difficult to fully understand the contents of the quotations.
- The quotation items were recorded inconsistently, so I realized that not all the data could be classified according to a single fixed set of rules.

However, after reviewing multiple quotations, I gained a much clearer understanding of the business workflow. I also began to see how the database schema should be structured while still accommodating irregular and incomplete data.
My next step is to create the first draft of the data schema and test it by extracting data from several sample quotations.
