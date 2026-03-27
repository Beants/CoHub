# Manual Verification

The recruiting-site MCP must support human-assisted verification.

## Expected behavior

- reuse a configured browser profile directory so login sessions can persist across runs
- detect when the site requires login, CAPTCHA, or other human verification
- surface a clear instruction asking the user to complete the required action in the browser
- resume search after verification is complete
- keep recruiting-site automation inside the Liepin MCP session instead of switching to generic `browser_use`

## V1 note

V1 should not store recruiting-site account passwords. Persistent local browser sessions are the primary mechanism for session reuse.

## Suggested verification flow

1. Mount `liepin-mcp` in CoPaw.
2. Set `LIEPIN_PROFILE_DIR` in the environment-variable page.
3. Call `liepin_prepare_browser` and complete any manual login or CAPTCHA.
4. Call `liepin_search_candidates` with a normalized query or plain keyword.
5. If a manual step interrupted the run, complete it in the browser and call `liepin_continue_last_search`.
