"""Spécification des zones Gabès pour la carte (données métier)."""

from __future__ import annotations

from typing import Any

GABES_ZONES_SPEC: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Zone Industrielle Ghannouch (GCT)",
        "name_ar": "منطقة المجمع الكيماوي بغنوش",
        "latitude": 33.88,
        "longitude": 10.09,
        "pollution_type": "SO2 / NH3 / fluorures",
    },
    {
        "id": 2,
        "name": "Port de Gabès",
        "name_ar": "ميناء قابس",
        "latitude": 33.901,
        "longitude": 10.098,
        "pollution_type": "NO2 marin-portuaire",
    },
    {
        "id": 3,
        "name": "Chott Essalem",
        "name_ar": "شط السالم",
        "latitude": 33.875,
        "longitude": 10.12,
        "pollution_type": "Poussières / retombées",
    },
    {
        "id": 4,
        "name": "Zone Agricole Nord",
        "name_ar": "المنطقة الزراعية الشمالية",
        "latitude": 33.92,
        "longitude": 10.08,
        "pollution_type": "Phosphates / brumes acides",
    },
    {
        "id": 5,
        "name": "Zone Agricole Sud",
        "name_ar": "المنطقة الزراعية الجنوبية",
        "latitude": 33.82,
        "longitude": 10.05,
        "pollution_type": "Irrigation / sols",
    },
    {
        "id": 6,
        "name": "Médina de Gabès",
        "name_ar": "مدينة قابس القديمة",
        "latitude": 33.884,
        "longitude": 10.097,
        "pollution_type": "Exposition population / SO2",
    },
    {
        "id": 7,
        "name": "Plage de Gabès",
        "name_ar": "شاطئ قابس",
        "latitude": 33.893,
        "longitude": 10.105,
        "pollution_type": "Aérosols salins / qualité air côtier",
    },
    {
        "id": 8,
        "name": "Oasis de Gabès",
        "name_ar": "واحة قابس",
        "latitude": 33.868,
        "longitude": 10.082,
        "pollution_type": "Palmiers / brumisation phosphatée",
    },
]
