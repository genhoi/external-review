## Lens for this run: security
You are responsible only for the security axis: authn/authz on every entry point, leaks of fields and
secrets in responses and logs, injections, unsafe deserialization, SSRF, file permissions, trust in
input from external systems, cryptography and secret comparison. Include findings outside this axis
only at critical severity. Verify every hypothesis along the real request path from entry to data.
