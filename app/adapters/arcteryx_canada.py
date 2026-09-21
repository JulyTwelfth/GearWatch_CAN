from urllib.parse import urlsplit

from app.adapters.arcteryx_outlet import ArcTeryxOutletAdapter


class ArcTeryxCanadaAdapter(ArcTeryxOutletAdapter):
    """Parse Arc'teryx Canada's public ProductGroup JSON-LD."""

    retailer_name = "Arc'teryx Canada"
    _allowed_host = "arcteryx.com"

    @classmethod
    def _validate_product_url(cls, url: str) -> str:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"arcteryx.com", "www.arcteryx.com"}
            or not parsed.path.startswith(cls._allowed_path_prefix)
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Arc'teryx Canada URLs must be query-free Canadian HTTPS product pages"
            )
        return url
