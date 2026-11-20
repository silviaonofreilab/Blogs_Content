// Neo4j 2026.10+ with APOC Core and local JSON imports enabled. Run statements in order.
// _graph_id scopes this graph; MimicGraphNode is temporary and removed in Finalize.
// Set the graph file first. With APOC defaults, file:/// resolves to Neo4j's import folder:
// :param graphFile => 'file:///mimic-graph.json'

CREATE CONSTRAINT mimic_graph_node_identity IF NOT EXISTS
FOR (n:MimicGraphNode) REQUIRE (n._graph_id, n.id) IS UNIQUE;

CREATE CONSTRAINT mimic_graph_had_admission_identity IF NOT EXISTS
FOR ()-[r:HAD_ADMISSION]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_had_recorded_diagnosis_identity IF NOT EXISTS
FOR ()-[r:HAD_RECORDED_DIAGNOSIS]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_underwent_identity IF NOT EXISTS
FOR ()-[r:UNDERWENT]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_had_lab_test_identity IF NOT EXISTS
FOR ()-[r:HAD_LAB_TEST]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_had_medication_record_identity IF NOT EXISTS
FOR ()-[r:HAD_MEDICATION_RECORD]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_had_medication_detail_identity IF NOT EXISTS
FOR ()-[r:HAD_MEDICATION_DETAIL]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_had_pharmacy_order_identity IF NOT EXISTS
FOR ()-[r:HAD_PHARMACY_ORDER]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_was_prescribed_identity IF NOT EXISTS
FOR ()-[r:WAS_PRESCRIBED]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_recorded_diagnosis_identity IF NOT EXISTS
FOR ()-[r:RECORDED_DIAGNOSIS]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_included_procedure_identity IF NOT EXISTS
FOR ()-[r:INCLUDED_PROCEDURE]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_included_lab_test_identity IF NOT EXISTS
FOR ()-[r:INCLUDED_LAB_TEST]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_included_medication_event_identity IF NOT EXISTS
FOR ()-[r:INCLUDED_MEDICATION_EVENT]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_included_pharmacy_order_identity IF NOT EXISTS
FOR ()-[r:INCLUDED_PHARMACY_ORDER]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_included_prescription_identity IF NOT EXISTS
FOR ()-[r:INCLUDED_PRESCRIPTION]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_for_prescription_identity IF NOT EXISTS
FOR ()-[r:FOR_PRESCRIPTION]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_has_dose_detail_identity IF NOT EXISTS
FOR ()-[r:HAS_DOSE_DETAIL]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_measures_identity IF NOT EXISTS
FOR ()-[r:MEASURES]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_has_diagnosis_code_identity IF NOT EXISTS
FOR ()-[r:HAS_DIAGNOSIS_CODE]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_has_procedure_code_identity IF NOT EXISTS
FOR ()-[r:HAS_PROCEDURE_CODE]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_references_pharmacy_order_identity IF NOT EXISTS
FOR ()-[r:REFERENCES_PHARMACY_ORDER]-() REQUIRE (r._graph_id, r.id) IS UNIQUE;

// Nodes
CALL apoc.load.json($graphFile) YIELD value
UNWIND value.nodes AS row
WITH value.metadata.graph_id AS graphId, row
MERGE (node:$(row.type) {_graph_id: graphId, id: row.id})
SET node:MimicGraphNode,
    node += row.properties,
    node.name = row.name;

// Relationships: in Neo4j Browser, prepend :auto to this statement.
CALL apoc.load.json($graphFile, '$.metadata') YIELD value
WITH value.graph_id AS graphId
CALL apoc.load.json($graphFile, '$.relations[*]') YIELD value AS row
CALL (graphId, row) {
  MATCH (source:MimicGraphNode {_graph_id: graphId, id: row.source})
  MATCH (target:MimicGraphNode {_graph_id: graphId, id: row.target})
  MERGE (source)-[relation:$(row.type) {_graph_id: graphId, id: row.id}]->(target)
  SET relation += row.properties,
      relation._admission_id_mismatch = row.properties._admission_id_mismatch
} IN TRANSACTIONS OF 100 ROWS;

// Finalize: run only after the relationship import succeeds.
CREATE CONSTRAINT mimic_graph_admission_identity IF NOT EXISTS
FOR (n:Admission) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_diagnosis_code_identity IF NOT EXISTS
FOR (n:DiagnosisCode) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_procedure_code_identity IF NOT EXISTS
FOR (n:ProcedureCode) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_lab_item_identity IF NOT EXISTS
FOR (n:LabItem) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_diagnosis_identity IF NOT EXISTS
FOR (n:Diagnosis) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_med_admin_identity IF NOT EXISTS
FOR (n:MedAdmin) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_med_admin_detail_identity IF NOT EXISTS
FOR (n:MedAdminDetail) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_lab_event_identity IF NOT EXISTS
FOR (n:LabEvent) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_patient_identity IF NOT EXISTS
FOR (n:Patient) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_pharmacy_order_identity IF NOT EXISTS
FOR (n:PharmacyOrder) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_prescription_identity IF NOT EXISTS
FOR (n:Prescription) REQUIRE (n._graph_id, n.id) IS UNIQUE;
CREATE CONSTRAINT mimic_graph_procedure_identity IF NOT EXISTS
FOR (n:Procedure) REQUIRE (n._graph_id, n.id) IS UNIQUE;

MATCH (node:MimicGraphNode {_graph_id: 'mimic_decision_12tables_v2'})
REMOVE node:MimicGraphNode;

DROP CONSTRAINT mimic_graph_node_identity IF EXISTS;
