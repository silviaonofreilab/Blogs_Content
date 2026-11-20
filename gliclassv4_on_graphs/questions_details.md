
_This document contains details on the structure of the set of questions, using type, graph structure (hops) and topic. There are 48 questions in this set._

## 1. Questions by types

- **lookup (5): Q07, Q08, Q15, Q24, Q26**
Read one recorded value off a node or its direct link, such as a dose amount, a unit, or whether a vaccine was recorded as administered.

- **graph (13): Q11, Q13, Q17–Q22, Q28–Q30, Q44, Q48**  
Follow and compare linked records, one to three hops. Examples: does an administered dose match its prescription; do two admissions carry the same diagnoses; does a medication event point to another admission's order; which lab results belong to a stay but are linked only to the patient. Q11 and Q13 check a medication event's status against its dose details.

- **computation (16): Q01, Q05, Q06, Q09, Q10, Q12, Q14, Q16, Q23, Q25, Q27, Q41–Q43, Q45, Q47**  
Calculate from recorded values: date and time order, 30-day readmission and mortality windows, time tolerances, total dose against the prescribed dose, lab values against a reference range or a threshold, and a lab trend.

- **semantic (14): Q02–Q04, Q31–Q40, Q46**  
Read and interpret the text in the nodes (what diagnosis and drug names mean, and which lab test a diagnosis refers to), rather than follow the graph's structure. A Cypher query alone can't answer these without an outside mapping.

**Twins (10, counted above):** Q23 of Q05, Q24 of Q08, Q25 of Q10, Q26 of Q15, Q27 of Q16, Q28 and Q29 of Q18, Q30 of Q22, Q42 of Q41, Q48 of Q17. Each copies its original and edits the evidence; Q48 edits only the edges.  Each twin carries its original's type.


## 2. Questions by graph hops

A hop is an edge in the graph. A linear path with three nodes has two hops.

- **Hops = 0**:  Q01 (1)  
Both admissions are looked up directly; nothing is traversed.

- **Hops = 1**:  Q02–Q15, Q23–Q26, Q31–Q43, Q45–Q47 (34)  
One step out from an admission, a patient or a medication event, to its diagnoses, procedures, prescriptions, dose details or lab results. One 1 hop is a star around one node. In particular, Q10, Q14 and Q46 fan out to several first neighbors.

- **Hops = 2**: Q16–Q20, Q27–Q29, Q44, Q48 (10)  
patient → admission → diagnosis or procedure (Q17, Q19, Q20, Q48); 
medication event → pharmacy order → prescription (Q16, Q18, Q27–Q29); or admission ← patient → lab result (Q44), where the lab results reached through the patient are compared with those linked to the admission.

- **Hops  3 or more**: Q21, Q22, Q30 (3)  
Patient → admission → pharmacy order → prescription (Q21).
Q22/Q30 is a cross admission loop with more than 3 hops. The Cypher goes patient → admission 1 → medication event → pharmacy order ← admission 2 <- patient. 


## 3. Questions by topic

- **Diagnoses (meaning of codes)**  
Q02, Q03, Q04, Q31, Q35, Q37, Q38, Q39, Q40 (9)  
Telling personal history from family history, current from past, bacterial from viral.

- **Drug classes**  
Q32, Q33, Q34, Q36 (4)  
Whether a drug name falls in a class: antithrombotic, opioid, beta-lactam.

- **Prescription details**  
Q07, Q08, Q24 (3)  
Reading the prescribed dose amount and unit.

- **Medication administration status**  
Q11, Q13, Q15, Q26 (4)  
Whether a dose was actually given (the event's status text against its dose details).

- **Prescriptions or pharmacy orders vs medication administrations**  
Q16, Q18, Q27, Q28, Q29 (5)  
Dose given against dose prescribed.

- **Timing within an admission**  
Q05, Q06, Q09, Q12, Q14, Q23 (6)  
Order of procedures and drugs; given on schedule or inside the order's window.

- **Lab results**  
Q41, Q42, Q43, Q45, Q46 (5)  
Values against reference ranges, a value exactly at the limit (Q42), a masked value (Q43), a trend (Q45), and whether a lab result supports a coded diagnosis (Q46).

- **30-day windows after discharge**  
Q01, Q10, Q25, Q47 (4)  
Readmission (Q01, Q10, Q25) and death (Q47) within 30 calendar days of discharge.

- **Across admissions**  
Q17, Q19, Q20, Q21, Q48 (5)  
Same patient: comparing diagnoses, procedures and prescriptions between admissions. 

- **Admission assignment**  
Q22, Q30, Q44 (3)  
Records tied to the wrong admission or to no admission: a medication event pointing to another admission's order (Q22, Q30), and lab results linked only to the patient (Q44).

**Overlaps:** Q36 is both diagnoses and drug classes; Q14 is both timing and orders; Q46 is both lab results and diagnosis meaning; Q44 is both lab results and admission assignment. Each is listed where its decision happens.