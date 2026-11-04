from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    api_url: str
    token_url: str | None = None


# Same names and hosts as the official `ovh` package.
ENDPOINTS: dict[str, Endpoint] = {
    "ovh-eu": Endpoint(
        "https://eu.api.ovh.com", "https://www.ovh.com/auth/oauth2/token"
    ),
    "ovh-ca": Endpoint(
        "https://ca.api.ovh.com", "https://ca.ovh.com/auth/oauth2/token"
    ),
    "ovh-us": Endpoint(
        "https://api.us.ovhcloud.com", "https://us.ovhcloud.com/auth/oauth2/token"
    ),
    "kimsufi-eu": Endpoint("https://eu.api.kimsufi.com"),
    "kimsufi-ca": Endpoint("https://ca.api.kimsufi.com"),
    "soyoustart-eu": Endpoint("https://eu.api.soyoustart.com"),
    "soyoustart-ca": Endpoint("https://ca.api.soyoustart.com"),
}
