from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Optional


class AstronomicalClock:
    """
    Pure-Python NOAA solar position calculator for local sunrise, sunset,
    and solar elevation angle triggers/conditions.
    Defaults to Northern Italy (Veneto: 45.55° N, 11.55° E).
    """

    def __init__(self, latitude_deg: float = 45.55, longitude_deg: float = 11.55) -> None:
        self.latitude_deg = float(latitude_deg)
        self.longitude_deg = float(longitude_deg)

    def get_sunrise_sunset_unix(self, ref_timestamp: float) -> tuple[float, float]:
        """
        Return (sunrise_unix, sunset_unix) for the local calendar day of `ref_timestamp`.
        Uses the standard NOAA solar equation (zenith = 90.833 deg for atmospheric refraction).
        """
        local_dt = datetime.fromtimestamp(ref_timestamp).astimezone()
        local_midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        tz_offset_hours = (local_dt.utcoffset().total_seconds() / 3600.0) if local_dt.utcoffset() else 0.0

        day_of_year = local_dt.timetuple().tm_yday
        days_in_year = 366.0 if self._is_leap_year(local_dt.year) else 365.0

        # Fractional year in radians
        gamma = (2.0 * math.pi / days_in_year) * (day_of_year - 1 + 0.5)

        # Equation of time (in minutes)
        eqtime = 229.18 * (
            0.000075
            + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2.0 * gamma)
            - 0.040849 * math.sin(2.0 * gamma)
        )

        # Solar declination angle (in radians)
        decl = (
            0.006918
            - 0.399912 * math.cos(gamma)
            + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2.0 * gamma)
            + 0.000907 * math.sin(2.0 * gamma)
            - 0.002697 * math.cos(3.0 * gamma)
            + 0.00148 * math.sin(3.0 * gamma)
        )

        lat_rad = math.radians(self.latitude_deg)
        zenith_rad = math.radians(90.833)

        cos_ha = (math.cos(zenith_rad) / (math.cos(lat_rad) * math.cos(decl))) - (
            math.tan(lat_rad) * math.tan(decl)
        )
        # Clamp for polar regions safety
        cos_ha = max(-1.0, min(1.0, cos_ha))
        ha_deg = math.degrees(math.acos(cos_ha))

        solar_noon_utc_min = 720.0 - (4.0 * self.longitude_deg) - eqtime
        sunrise_utc_min = solar_noon_utc_min - (4.0 * ha_deg)
        sunset_utc_min = solar_noon_utc_min + (4.0 * ha_deg)

        sunrise_local_sec = (sunrise_utc_min + tz_offset_hours * 60.0) * 60.0
        sunset_local_sec = (sunset_utc_min + tz_offset_hours * 60.0) * 60.0

        base_unix = local_midnight.timestamp()
        return (base_unix + sunrise_local_sec, base_unix + sunset_local_sec)

    def get_sun_summary(self, ref_timestamp: Optional[float] = None) -> dict[str, object]:
        ts = float(ref_timestamp if ref_timestamp is not None else datetime.now(timezone.utc).timestamp())
        sunrise_ts, sunset_ts = self.get_sunrise_sunset_unix(ts)
        sunrise_dt = datetime.fromtimestamp(sunrise_ts).astimezone()
        sunset_dt = datetime.fromtimestamp(sunset_ts).astimezone()
        is_daylight = sunrise_ts <= ts <= sunset_ts
        return {
            "latitude": self.latitude_deg,
            "longitude": self.longitude_deg,
            "sunrise_unix": round(sunrise_ts, 1),
            "sunset_unix": round(sunset_ts, 1),
            "sunrise_hhmm": sunrise_dt.strftime("%H:%M"),
            "sunset_hhmm": sunset_dt.strftime("%H:%M"),
            "is_daylight": is_daylight,
            "sun_state": "above_horizon" if is_daylight else "below_horizon",
        }

    @staticmethod
    def _is_leap_year(year: int) -> bool:
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
