# Pushover (Next)

A Home Assistant custom integration for [Pushover](https://pushover.net), built to add the one
thing the built-in `pushover` integration can't: Pushover's
[end-to-end encryption](https://pushover.net/api#e2ee) (e2ee).

Home Assistant's built-in integration delegates everything to the third-party `pushover_complete`
library, whose `send_message()` has a fixed parameter list with no `encrypted` flag and no way to
pass one through. Encryption literally can't be added to it without patching that upstream
library first. This integration instead talks to the Pushover API directly, so it can support
encryption today, plus the rest of the Messages API the built-in integration also leaves out
(priority levels, sounds, URLs, HTML/monospace formatting, TTL, tags, attachments,
emergency-priority retry/expire/callback, receipt lookups, and cancel-by-receipt/by-tag).

## Installation (HACS)

This is a custom repository, not (yet) part of HACS's default store:

1. In HACS, go to **Integrations** → the **⋮** menu → **Custom repositories**.
2. Add `https://github.com/neurolit/ha-pushover-next` as an **Integration**.
3. Find **Pushover (Next)** in HACS and install it.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration** and search for **Pushover (Next)**.

## Setting up an account

The config flow asks for:

- **Application API token** — from your [Pushover application](https://pushover.net/apps/build).
- **User or group key** — from your [Pushover dashboard](https://pushover.net/dashboard).

Both are validated live against Pushover before the entry is created.

## Options

Open the integration's **Configure** button to set:

- **Sending defaults** — the device, priority, sound, TTL, and emergency retry/expire used by
  `notify.send_message` and as fallbacks for `pushover_next.send_message`.
- **End-to-end encryption key** — see below.

## End-to-end encryption

Pushover's e2ee is a single secret per **account**, not per device: every device you enable it on
(in the Pushover app, under **Settings → End-to-End Encryption**) must be given the exact same
64-character hex key. Because of that, this integration also stores just one key per account —
set it once in the options, and `encrypt: true` on any `send_message` call encrypts with it,
regardless of which device(s) you're targeting (or none, meaning "every device on the account").

Leaving the key blank disables encryption for that account; submitting a blank value when one
is already set removes it.

The encryption scheme itself (gzip → AES-256-CBC/PKCS7 → HMAC-SHA256 → base64, applied to
`message`, `title`, `url`, and `url_title`) matches Pushover's documented spec exactly, and was
verified byte-for-byte against Pushover's own reference implementation before being built into
this integration.

**Note:** if you don't give a title while encrypting, Pushover fills in its own plaintext
default title — which the receiving device then fails to decrypt. This integration works around
that automatically by always encrypting an explicit title ("Home Assistant" if you didn't supply
one), so you don't need to think about it.

## Services

### `pushover_next.send_message`

The full Messages API, as service fields: `message` (required), `title`, `priority`, `sound`,
`url`, `url_title`, `device`, `timestamp`, `html`, `monospace`, `ttl`, `tags`, `callback`,
`retry`, `expire`, `attachment` / `attachment_base64` (+ `attachment_type`), and `encrypt`. See
the field descriptions in Home Assistant's service picker (Developer Tools → Actions) for full
details and limits.

Example automation action, sent encrypted to every device on the account:

```yaml
action: pushover_next.send_message
data:
  message: "The garage door has been open for 10 minutes."
  title: "Garage door"
  priority: 1
  encrypt: true
```

Example emergency-priority message, sent only to a specific device:

```yaml
action: pushover_next.send_message
data:
  message: "Water leak detected in the basement!"
  priority: 2
  retry: 60
  expire: 3600
  device: ["phone"]
```

If you have more than one Pushover account configured, add `config_entry_id: <entry id>` to pick
which one a call applies to.

### `pushover_next.cancel_receipt` / `pushover_next.cancel_by_tag`

Stop further retries of a pending emergency-priority message, by its receipt id or by a tag you
set on the original `send_message` call.

### `pushover_next.get_receipt`

Look up the delivery/acknowledgement status of an emergency-priority message. Returns a response
(usable with `response_variable` in a script/automation).

## Also available

- `notify.send_message` targeting this account's notify entity — plain message/title only, using
  the account's configured defaults (no encryption; see `pushover_next.send_message` for that).

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE).
