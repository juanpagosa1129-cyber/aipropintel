from __future__ import annotations


CITY_CENTROIDS = {
    "bogota": (4.7110, -74.0721),
    "bogotá": (4.7110, -74.0721),
    "medellin": (6.2442, -75.5812),
    "medellín": (6.2442, -75.5812),
    "cali": (3.4516, -76.5320),
    "barranquilla": (10.9685, -74.7813),
    "cartagena": (10.3910, -75.4794),
    "bucaramanga": (7.1193, -73.1227),
    "pereira": (4.8087, -75.6906),
    "ibague": (4.4389, -75.2322),
    "ibagué": (4.4389, -75.2322),
    "manizales": (5.0703, -75.5138),
    "cucuta": (7.8891, -72.4967),
    "cúcuta": (7.8891, -72.4967),
    "santa marta": (11.2408, -74.1990),
}


def geocode_city(city: str):
    if not city:
        return None, None, "unknown"
    lat_lng = CITY_CENTROIDS.get(city.strip().lower())
    if not lat_lng:
        return None, None, "pending"
    return lat_lng[0], lat_lng[1], "city_centroid"
