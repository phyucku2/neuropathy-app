"""Patient EMR data pull via SMART on FHIR (ADR-0008).

`smart` = pure OAuth2/PKCE + discovery helpers (fully unit-tested); `client` = the async
client that runs the flow and fetches lab Observations (parsed via app.fhir). Tokens are
secrets held behind the SecretStore (the encrypted-at-rest DB vault when a key is
configured, ADR-0017), referenced by `token_ref` — never plaintext in the DB or logs.
"""
