"""Constants for the Pushover Next integration."""
from __future__ import annotations

DOMAIN = "pushover_next"

CONF_API_TOKEN = "api_token"
CONF_USER_KEY = "user_key"
CONF_ENCRYPTION_KEY = "encryption_key"

CONF_DEFAULT_DEVICE = "default_device"
CONF_DEFAULT_PRIORITY = "default_priority"
CONF_DEFAULT_SOUND = "default_sound"
CONF_DEFAULT_TTL = "default_ttl"
CONF_DEFAULT_RETRY = "default_retry"
CONF_DEFAULT_EXPIRE = "default_expire"

API_BASE_URL = "https://api.pushover.net/1"
API_MESSAGES_URL = f"{API_BASE_URL}/messages.json"
API_VALIDATE_URL = f"{API_BASE_URL}/users/validate.json"
API_SOUNDS_URL = f"{API_BASE_URL}/sounds.json"
API_RECEIPT_URL = f"{API_BASE_URL}/receipts/{{receipt}}.json"
API_CANCEL_RECEIPT_URL = f"{API_BASE_URL}/receipts/{{receipt}}/cancel.json"
API_CANCEL_BY_TAG_URL = f"{API_BASE_URL}/receipts/cancel_by_tag/{{tag}}.json"
API_GROUP_URL = f"{API_BASE_URL}/groups/{{group}}.json"

ATTR_MESSAGE = "message"
ATTR_TITLE = "title"
ATTR_PRIORITY = "priority"
ATTR_SOUND = "sound"
ATTR_URL = "url"
ATTR_URL_TITLE = "url_title"
ATTR_DEVICE = "device"
ATTR_TIMESTAMP = "timestamp"
ATTR_HTML = "html"
ATTR_MONOSPACE = "monospace"
ATTR_TTL = "ttl"
ATTR_TAGS = "tags"
ATTR_CALLBACK = "callback"
ATTR_RETRY = "retry"
ATTR_EXPIRE = "expire"
ATTR_ATTACHMENT = "attachment"
ATTR_ATTACHMENT_BASE64 = "attachment_base64"
ATTR_ATTACHMENT_TYPE = "attachment_type"
ATTR_ENCRYPT = "encrypt"
ATTR_RECEIPT = "receipt"
ATTR_TAG = "tag"

PRIORITY_LOWEST = -2
PRIORITY_LOW = -1
PRIORITY_NORMAL = 0
PRIORITY_HIGH = 1
PRIORITY_EMERGENCY = 2
VALID_PRIORITIES = (PRIORITY_LOWEST, PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_EMERGENCY)

MIN_RETRY_SECONDS = 30
MAX_EXPIRE_SECONDS = 10800  # 3 hours; Pushover also caps total retries at 50.
MAX_RETRY_SECONDS = MAX_EXPIRE_SECONDS  # a retry interval longer than expire is meaningless.
MIN_TTL_SECONDS = 1  # Pushover: "must be a positive number of seconds".

MAX_MESSAGE_LENGTH = 1024
MAX_TITLE_LENGTH = 250
MAX_URL_LENGTH = 512
MAX_URL_TITLE_LENGTH = 100
MAX_TAGS_LENGTH = 200
MAX_ATTACHMENT_BYTES = 5_242_880  # 5 MB, current Pushover attachment limit.
ALLOWED_ATTACHMENT_TYPES = ("image/jpeg", "image/png", "image/gif")

# With encrypt=True and no explicit title, Pushover fills in its own plaintext
# default title, but the receiving device tries to decrypt every text field,
# title included, and fails on that plaintext default. Always encrypt an
# explicit title instead so there's nothing left in plaintext to choke on.
DEFAULT_ENCRYPTED_TITLE = "Home Assistant"

FALLBACK_SOUNDS = (
    "pushover",
    "bike",
    "bugle",
    "cashregister",
    "classical",
    "cosmic",
    "falling",
    "gamelan",
    "incoming",
    "intermission",
    "magic",
    "mechanical",
    "pianobar",
    "siren",
    "spacealarm",
    "tugboat",
    "alien",
    "climb",
    "persistent",
    "echo",
    "updown",
    "vibrate",
    "none",
)

SERVICE_SEND_MESSAGE = "send_message"
SERVICE_CANCEL_RECEIPT = "cancel_receipt"
SERVICE_CANCEL_BY_TAG = "cancel_by_tag"
SERVICE_GET_RECEIPT = "get_receipt"

DATA_CLIENTS = "clients"

CONF_ENTRY = "config_entry_id"
