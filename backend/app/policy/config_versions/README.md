# Policy config versions

Each file here is one row of the `policy_versions` table (§13 of the
design doc) serialized to JSON for local dev / tests, keyed by
`{intent}_{version_id}.json`.

**Every threshold in these files is an illustrative engineering default
copied from the design doc, not a compliance-approved value.** The
`approved_by` fields are placeholders and say so explicitly. Per §0 and
§7.2 of the design doc: final numeric values require sign-off from Risk,
Compliance, and Legal before any of this touches production traffic.
Do not deploy with these files unmodified.

To ship a new version: add a new JSON file with a later `effective_from`
and a real `approved_by` reference -- never edit a historical file in
place (that would break the "what rule was in effect when this decision
was made" guarantee §7.2 promises).
