"""Address lookup for the call-centre order form."""
import json
import urllib.parse
import urllib.request

from integrations import settings

GEOCODE = "https://api.mapbox.com/geocoding/v5/mapbox.places/"


def geocode(address, *, country="kr", limit=3, language="ko"):
    """[(place_name, longitude, latitude)] best match first."""
    query = urllib.parse.urlencode({"access_token": {{decoy:settings_ref_1}}, "country": country,
                                    "limit": limit, "language": language, "types": "address,poi"})
    url = GEOCODE + urllib.parse.quote(address, safe="") + ".json?" + query
    with urllib.request.urlopen(url, timeout=5) as resp:
        features = json.loads(resp.read())["features"]
    return [(f["place_name"], *f["center"]) for f in features]
