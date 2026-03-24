import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from typing import Optional
import httpx
from models.signals import RawSignal, SignalSource
from config import get_settings

settings = get_settings()

@dataclass
class WeatherImpact:
    condition:         str
    description:       str
    temperature_c:     float
    feels_like_c:      float
    humidity_pct:      int
    rain_probability:  float
    wind_kmh:          float
    commute_risk:      str   = ""
    clothing_advice:   str   = ""
    urgency_score:     float = 0.2

    def compute_impacts(self):
        if self.rain_probability > 0.6 or self.wind_kmh > 40:
            self.commute_risk  = "high"
            self.urgency_score = 0.75
        elif self.rain_probability > 0.3:
            self.commute_risk  = "moderate"
            self.urgency_score = 0.45
        else:
            self.commute_risk  = "low"
            self.urgency_score = 0.2

        if self.feels_like_c < 10:
            self.clothing_advice = "Heavy jacket essential"
        elif self.feels_like_c < 18:
            self.clothing_advice = "Carry a light jacket"
        elif self.rain_probability > 0.4:
            self.clothing_advice = "Bring an umbrella"
        else:
            self.clothing_advice = "Light clothing fine"

        return self


class WeatherModule:
    BASE = "https://api.openweathermap.org/data/2.5"

    def __init__(self):
        self.api_key = settings.openweather_api_key
        self.lat     = settings.lat
        self.lon     = settings.lon
        self.city    = settings.city

    async def _fetch(self, client: httpx.AsyncClient, endpoint: str, params: dict) -> dict:
        params["appid"] = self.api_key
        params["units"] = "metric"
        r = await client.get(f"{self.BASE}/{endpoint}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    async def get_impact(self) -> Optional[WeatherImpact]:
        async with httpx.AsyncClient() as client:
            current  = await self._fetch(client, "weather",   {"lat": self.lat, "lon": self.lon})
            forecast = await self._fetch(client, "forecast",  {"lat": self.lat, "lon": self.lon, "cnt": 2})

        rain_prob = forecast["list"][0].get("pop", 0.0)

        return WeatherImpact(
            condition        = current["weather"][0]["main"],
            description      = current["weather"][0]["description"],
            temperature_c    = current["main"]["temp"],
            feels_like_c     = current["main"]["feels_like"],
            humidity_pct     = current["main"]["humidity"],
            rain_probability = rain_prob,
            wind_kmh         = round(current["wind"]["speed"] * 3.6, 1),
        ).compute_impacts()

    async def fetch_signals(self) -> list[RawSignal]:
        impact = await self.get_impact()
        if not impact:
            return []

        content = (
            f"Weather in {self.city}: {impact.description.title()}\n"
            f"Temp: {impact.temperature_c:.1f}°C (feels {impact.feels_like_c:.1f}°C)\n"
            f"Rain probability: {impact.rain_probability*100:.0f}%\n"
            f"Wind: {impact.wind_kmh} km/h\n"
            f"Commute risk: {impact.commute_risk}\n"
            f"Advice: {impact.clothing_advice}"
        )

        return [RawSignal(
            source    = SignalSource.WEATHER,
            content   = content,
            metadata  = {
                "condition":        impact.condition,
                "temperature_c":    impact.temperature_c,
                "feels_like_c":     impact.feels_like_c,
                "rain_probability": impact.rain_probability,
                "wind_kmh":         impact.wind_kmh,
                "commute_risk":     impact.commute_risk,
                "clothing_advice":  impact.clothing_advice,
                "urgency_score":    impact.urgency_score,
            },
            signal_id = f"weather_{self.city}",
        )]


async def test():
    module  = WeatherModule()
    signals = await module.fetch_signals()
    if not signals:
        print("No data — check your API key")
        return
    s = signals[0]
    print(f"\n✓ Weather signal ready\n")
    print(s.content)
    print(f"\nUrgency score : {s.metadata['urgency_score']}")
    print(f"Commute risk  : {s.metadata['commute_risk']}")
    print(f"Advice        : {s.metadata['clothing_advice']}")

if __name__ == "__main__":
    asyncio.run(test())