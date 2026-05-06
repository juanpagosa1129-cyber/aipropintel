from __future__ import annotations

import json
import urllib.parse
import urllib.request


class InteractiveControlRequired(Exception):
    pass


class RamaJudicialSource:
    """Adaptador HTTP configurable.

    La Rama Judicial y otras fuentes publicas pueden cambiar endpoints,
    controles de acceso y terminos de uso. Este adaptador no intenta evadir
    bloqueos ni automatizar CAPTCHAs. Opera solo contra un endpoint permitido
    configurado en RAMA_JUDICIAL_BASE_URL que devuelva JSON normalizado o una
    lista de registros equivalentes al esquema de Propintel.
    """

    def __init__(self, settings):
        self.settings = settings

    def fetch(self, params: dict) -> list[dict]:
        base_url = self.settings.rama_judicial_base_url
        if not base_url:
            raise ValueError(
                "RAMA_JUDICIAL_BASE_URL no esta configurado. Configure un endpoint autorizado o use importacion CSV."
            )

        safe_params = {
            key: value
            for key, value in params.items()
            if key in {"numero_proceso", "ciudad", "juzgado", "tipo_proceso", "page", "limit"}
        }
        url = f"{base_url}?{urllib.parse.urlencode(safe_params)}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.settings.crawler_user_agent,
            },
        )
        with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            raw_text = response.read().decode("utf-8", errors="replace")

        lowered = raw_text.lower()
        interactive_signals = ["captcha", "recaptcha", "hcaptcha", "no soy un robot", "control interactivo"]
        if any(signal in lowered for signal in interactive_signals):
            raise InteractiveControlRequired(
                "La fuente oficial devolvio un control interactivo (CAPTCHA). Requiere intervencion humana."
            )

        if "application/json" in content_type.lower() or raw_text.strip().startswith(("{", "[")):
            payload = json.loads(raw_text)
        else:
            raise ValueError("La fuente oficial no devolvio JSON utilizable para ingestión automatica.")

        if isinstance(payload, dict):
            records = payload.get("items") or payload.get("data") or []
        elif isinstance(payload, list):
            records = payload
        else:
            records = []
        if not isinstance(records, list):
            raise ValueError("Respuesta de fuente no compatible")
        return records
