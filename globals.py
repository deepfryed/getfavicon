import logging

inf = logging.info
war = logging.warning
err = logging.error
cri = logging.critical

SHARDS_PER_COUNTER = 1000
MC_CACHE_TIME = 2419200 #seconds (28 days)
DS_CACHE_TIME = 90 #days

MIN_ICON_LENGTH = 100
MAX_ICON_LENGTH = 20000
EMPTY_ICON_LENGTH = 1150

ICON_MIMETYPES = [
  "image/x-icon",
  "image/vnd.microsoft.icon",
  "image/ico",
  "image/icon",
  "text/ico",
  "application/ico",
  "image/x-ms-bmp",
  "image/x-bmp",
  "image/gif",
  "image/png",
  "image/jpeg",
  None,
]

ICON_MIMETYPE_BLACKLIST = [
  "application/xml",
  "text/html",
]

# Surpresses the index and test pages
HEADLESS = False

COUNTERS = [
  "favIconsServed",
  "favIconsServedDefault",
  "cacheNone",
  "cacheMC",
  "cacheDS",
]