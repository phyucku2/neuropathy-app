"""HL7 FHIR R4 mapping for lab data (ADR-0007).

`resources` holds a typed subset of the FHIR `Observation` resource (laboratory
category); `mapping` converts between that and our internal `LabResultIn`, including
`Bundle` import. Field-by-field reference: docs/engineering/fhir-mapping.md.
"""
