from __future__ import annotations


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "si", "sí", "yes", "y"}


def risk_label(score: int) -> str:
    if score >= 70:
        return "alto"
    if score >= 42:
        return "medio"
    return "bajo"


def score_process(process: dict) -> dict:
    estado = str(process.get("estado", "")).lower()
    tipo = str(process.get("tipo_proceso", "")).lower()
    edad = int(float(process.get("edad_meses") or 0))
    demandados = int(float(process.get("demandados") or 1))
    acreedores = int(float(process.get("acreedores") or 1))

    avaluo_aprobado = as_bool(process.get("avaluo_aprobado")) or "avaluo" in estado or "avalúo" in estado
    embargo = as_bool(process.get("embargo")) or "embargo" in estado
    remate_fijado = as_bool(process.get("remate_fijado")) or "remate" in estado

    score = 10
    score += min(edad, 96) * 0.45
    score += 20 if avaluo_aprobado else 0
    score += 16 if embargo else 0
    score += 30 if remate_fijado else 0
    score += 14 if "hipotecario" in tipo else 0
    score += 7 if "ejecutivo" in tipo else 0
    score += 7 if acreedores <= 2 else -5
    score += 5 if demandados <= 3 else -6
    score += -45 if "archivo" in estado else 0

    rounded = max(3, min(97, round(score)))
    factors = {
        "edad_meses": edad,
        "avaluo_aprobado": avaluo_aprobado,
        "embargo": embargo,
        "remate_fijado": remate_fijado,
        "tipo_ejecutivo": "ejecutivo" in tipo,
        "tipo_hipotecario": "hipotecario" in tipo,
    }
    return {"score": rounded, "risk": risk_label(rounded), "factors": factors}
