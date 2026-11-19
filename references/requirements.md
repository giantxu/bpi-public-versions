# CBP EAPA confidentiality essentials (19 C.F.R. § 165.4) and similar proceedings

- **Brackets**: enclose claimed business confidential information (BCI) in single brackets `[ ]`. The first page of
  a submission containing BCI must say so; the BPI version therefore carries a "BUSINESS CONFIDENTIAL" header.
- **Explanation**: the submitter must explain why each bracketed item is entitled to confidential treatment – the
  BCI log produced by `bpi.py log` (one row per bracket, category, basis) is the working base for that explanation.
- **Public version**: filed the same day; contains a non-confidential summary of bracketed information "in sufficient
  detail to permit a reasonable understanding of the substance" – this applies to attachments, worksheets and
  exhibits too, not only the narrative. Hence summary labels inside the brackets. If summarisation is impossible, a
  full explanation is required. First page marked "PUBLIC VERSION".
- **Must be bracketed at minimum** (privacy, CIT Rule 5.2): social-security / taxpayer-identification numbers, birth
  dates, names of minors, financial-account numbers; and from CF-28 type data: entry numbers (except last 4 digits),
  importer-of-record numbers, manufacturer IDs (MID).
- **Cannot be protected**: the name and address of the importer against whom the allegation is brought.
- **Double brackets `[[ ]]`** (information not releasable even under APO) require a request to CBP at least five
  business days before the deadline; not used in normal exhibit work.
- **Public version certification** (§ 165.4(d)): the submitter certifies the public version contains only its own
  information or publicly available information – which is why third-party identities and negotiated terms are
  bracketed. A certificate of service accompanies each public document (RFI appendix). These certifications belong
  to the cover submission, not to each exhibit – remind the user.
- **CBP's own example (RFI Appendix II)**: the respondent's own name/address left public; customer name and contact
  info, destination, terms of sale, quantities, unit prices, amounts, individual names, container numbers bracketed;
  document numbers and dates left public; summary words ("Name", "Numbers", "Company name and contact info") written
  inside hand-drawn brackets; "PUBLIC VERSION" stamped on each page.

Commerce (AD/CVD) and USITC use the same bracket convention with "BPI" terminology and APO rules; header text,
bracket style and summary requirements are configurable in `bpi_config.json`, so the same workflow applies – read
the specific instructions and adjust the rules file.
