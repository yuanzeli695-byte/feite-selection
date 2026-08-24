# Source access policy

This is a private repository for the Feite selection workflow.

## Access

- Keep repository visibility set to `private`.
- Keep the collaborator list empty unless the owner explicitly approves an
  account.
- Do not commit personal access tokens, Bridge pairing codes, cookies,
  browser profiles, SellerSprite credentials, or exported product data.
- Treat userscripts as executable source. Do not install a changed script into
  a live browser session without review and an explicit version check.

## Local secrets

The local console reads runtime secrets from Windows-protected files outside
this repository. The source package must never contain those files or their
contents. If a credential is exposed, revoke it at the provider immediately,
remove it from the working tree, and rotate the credential before resuming.

## Changes

Every change to Collector, Runner, Bridge, strict gates, or credential-handling
code requires a review of the relevant operational documentation and a
rollback point. The current approved browser pair is Bridge `2.1.3`, Collector
`0.4.6.4`, and Runner `0.3.8.13`.

