# FHIR R4 Mapping — Lab Observations

The formal, bidirectional mapping between our internal lab representation
(`app/schemas/lab.py::LabResultIn`) and HL7 **FHIR R4 `Observation`** (laboratory
category). Implemented in `app/fhir/` (`resources.py` = typed FHIR subset,
`mapping.py` = the converters). ADR-0007.

## Scope
- **Resource:** `Observation` with `category = laboratory`.
- **Directions:** import (FHIR → internal, `from_fhir`) and export (internal → FHIR,
  `to_fhir`); plus `Bundle` (type `collection`) via `bundle_from_fhir` /
  `bundle_to_fhir`.
- **Tolerant parse:** unknown FHIR elements are ignored, so richer real-world resources
  (e.g. US Core profiles) still import for the fields we use.
- **Not yet:** writing to an external FHIR server, `Patient`/`Specimen`/`DiagnosticReport`
  resources, component observations (panels-as-one-resource), profile validation. These
  are future increments; the core value mapping is complete.

## Field-by-field

| Internal (`LabResultIn`) | FHIR `Observation` | Notes |
|---|---|---|
| `status` | `status` | `entered_in_error` ⇄ `entered-in-error` (underscore ⇄ hyphen). |
| `loinc_code` | `code.coding[system=http://loinc.org].code` | LOINC required; import raises if absent. |
| `display` | `code.coding[…].display` / `code.text` | |
| `value` | `valueQuantity.value` | |
| `unit` | `valueQuantity.unit` and `.code` | System fixed to UCUM. |
| `unit_system` (="UCUM") | `valueQuantity.system` = `http://unitsofmeasure.org` | |
| `code_system` (="LOINC") | `code.coding[].system` = `http://loinc.org` | |
| `value_text` | `valueString` | Qualitative results (e.g. "positive"). |
| `effective_at` | `effectiveDateTime` | Required; import raises if absent. |
| `issued_at` | `issued` | |
| `reference_range.low/high/unit` | `referenceRange[0].low/high` (Quantity, UCUM) | First range used. |
| `interpretation` (N/H/L/A) | `interpretation[0].coding[system=v3-ObservationInterpretation].code` | Codes are the v3 codes directly. |
| (constant) | `category[0]` = `laboratory` | Added on export. |
| `subject_id` (param) | `subject.reference` = `Patient/{id}` | Optional on export. |

## Validation guarantees
- **Export** always emits: a LOINC coding, `laboratory` category, a status, and either
  `valueQuantity` (with UCUM system) or `valueString`. Null elements are omitted.
- **Import** requires a LOINC coding, an `effectiveDateTime`, and (via `LabResultIn`)
  either a numeric value with a UCUM unit or a text value — otherwise it raises.
- **Round-trip** (`internal → FHIR → internal`) preserves code, value, unit, timestamps,
  status, reference range, and interpretation (locked by tests).

## Example (exported FHIR JSON)
```json
{
  "resourceType": "Observation",
  "status": "final",
  "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory", "display": "Laboratory"}]}],
  "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4", "display": "Hemoglobin A1c"}], "text": "Hemoglobin A1c"},
  "subject": {"reference": "Patient/…"},
  "effectiveDateTime": "2026-05-01T00:00:00+00:00",
  "valueQuantity": {"value": 7.2, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"},
  "referenceRange": [{"low": {"value": 4.0, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"}, "high": {"value": 5.6, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"}}],
  "interpretation": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": "H"}]}]
}
```
