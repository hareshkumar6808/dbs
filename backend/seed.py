"""Deterministic India-linked traffic. Coordinates are approximate; not navigation data."""

from datetime import datetime, timedelta, timezone
from math import atan2, cos, degrees, radians, sin, sqrt

from sqlalchemy import text

from backend.db import one
from backend.models import (
    Aircraft, AircraftType, Airline, Airport, AirspaceZone, Flight, FlightLeg,
    FlightPosition, Route, Runway, WeatherEvent,
)

NETWORK_VERSION = 6
TARGET_FLIGHTS = 3800

# iata, icao, name, city, country, lon, lat, elevation m, runway m, timezone
AIRPORTS = [
    ("MAA", "VOMM", "Chennai International", "Chennai", "India", 80.1693, 12.9941, 16, 3658, "Asia/Kolkata"),
    ("BLR", "VOBL", "Kempegowda International", "Bengaluru", "India", 77.7066, 13.1986, 915, 4000, "Asia/Kolkata"),
    ("DEL", "VIDP", "Indira Gandhi International", "Delhi", "India", 77.1031, 28.5562, 237, 4430, "Asia/Kolkata"),
    ("BOM", "VABB", "Chhatrapati Shivaji Maharaj International", "Mumbai", "India", 72.8656, 19.0896, 11, 3445, "Asia/Kolkata"),
    ("HYD", "VOHS", "Rajiv Gandhi International", "Hyderabad", "India", 78.4294, 17.2403, 617, 4260, "Asia/Kolkata"),
    ("CCU", "VECC", "Netaji Subhas Chandra Bose International", "Kolkata", "India", 88.4467, 22.6547, 5, 3627, "Asia/Kolkata"),
    ("COK", "VOCI", "Cochin International", "Kochi", "India", 76.4019, 10.1520, 9, 3400, "Asia/Kolkata"),
    ("GOX", "VOGA", "Manohar International", "Goa", "India", 73.9135, 15.7443, 165, 3500, "Asia/Kolkata"),
    ("PNQ", "VAPO", "Pune Airport", "Pune", "India", 73.9197, 18.5821, 592, 2535, "Asia/Kolkata"),
    ("AMD", "VAAH", "Sardar Vallabhbhai Patel International", "Ahmedabad", "India", 72.6347, 23.0772, 58, 3505, "Asia/Kolkata"),
    ("TRV", "VOTV", "Thiruvananthapuram International", "Thiruvananthapuram", "India", 76.9201, 8.4821, 4, 3400, "Asia/Kolkata"),
    ("VTZ", "VOVZ", "Visakhapatnam Airport", "Visakhapatnam", "India", 83.2245, 17.7212, 5, 3050, "Asia/Kolkata"),
    ("JAI", "VIJP", "Jaipur International", "Jaipur", "India", 75.8122, 26.8242, 385, 3407, "Asia/Kolkata"),
    ("LKO", "VILK", "Chaudhary Charan Singh International", "Lucknow", "India", 80.8893, 26.7606, 123, 2742, "Asia/Kolkata"),
    ("GAU", "VEGT", "Lokpriya Gopinath Bordoloi International", "Guwahati", "India", 91.5859, 26.1061, 49, 3110, "Asia/Kolkata"),
    ("PAT", "VEPT", "Jay Prakash Narayan Airport", "Patna", "India", 85.0879, 25.5913, 52, 2072, "Asia/Kolkata"),
    ("BBI", "VEBS", "Biju Patnaik International", "Bhubaneswar", "India", 85.8178, 20.2444, 42, 2743, "Asia/Kolkata"),
    ("IXB", "VEBD", "Bagdogra Airport", "Siliguri", "India", 88.3286, 26.6812, 126, 2745, "Asia/Kolkata"),
    ("IXC", "VICG", "Chandigarh International", "Chandigarh", "India", 76.7885, 30.6735, 314, 3170, "Asia/Kolkata"),
    ("SXR", "VISR", "Srinagar International", "Srinagar", "India", 74.7742, 33.9871, 1655, 3685, "Asia/Kolkata"),
    ("ATQ", "VIAR", "Sri Guru Ram Dass Jee International", "Amritsar", "India", 74.7973, 31.7096, 230, 3658, "Asia/Kolkata"),
    ("VNS", "VEBN", "Lal Bahadur Shastri International", "Varanasi", "India", 82.8593, 25.4524, 81, 2745, "Asia/Kolkata"),
    ("NAG", "VANP", "Dr. Babasaheb Ambedkar International", "Nagpur", "India", 79.0472, 21.0922, 315, 3200, "Asia/Kolkata"),
    ("IDR", "VAID", "Devi Ahilya Bai Holkar Airport", "Indore", "India", 75.8011, 22.7218, 564, 2754, "Asia/Kolkata"),
    ("BHO", "VABP", "Raja Bhoj Airport", "Bhopal", "India", 77.3374, 23.2875, 524, 2744, "Asia/Kolkata"),
    ("RPR", "VERP", "Swami Vivekananda Airport", "Raipur", "India", 81.7388, 21.1804, 317, 3250, "Asia/Kolkata"),
    ("IXZ", "VOPB", "Veer Savarkar International", "Port Blair", "India", 92.7297, 11.6412, 4, 3290, "Asia/Kolkata"),
    ("IXM", "VOMD", "Madurai Airport", "Madurai", "India", 78.0934, 9.8345, 140, 2285, "Asia/Kolkata"),
    ("IXE", "VOML", "Mangaluru International", "Mangaluru", "India", 74.8901, 12.9613, 103, 2450, "Asia/Kolkata"),
    ("CCJ", "VOCL", "Calicut International", "Kozhikode", "India", 75.9553, 11.1368, 104, 2860, "Asia/Kolkata"),
    ("CJB", "VOCB", "Coimbatore International", "Coimbatore", "India", 77.0434, 11.0300, 399, 2990, "Asia/Kolkata"),
    ("TRZ", "VOTR", "Tiruchirappalli International", "Tiruchirappalli", "India", 78.7097, 10.7654, 88, 2480, "Asia/Kolkata"),
    ("BDQ", "VABO", "Vadodara Airport", "Vadodara", "India", 73.2263, 22.3362, 39, 2469, "Asia/Kolkata"),
    ("RAJ", "VARK", "Rajkot International", "Rajkot", "India", 70.7795, 22.3788, 98, 3040, "Asia/Kolkata"),
    ("UDR", "VAUD", "Maharana Pratap Airport", "Udaipur", "India", 73.8961, 24.6177, 513, 2743, "Asia/Kolkata"),
    ("DED", "VIDN", "Dehradun Airport", "Dehradun", "India", 78.1803, 30.1897, 558, 2140, "Asia/Kolkata"),
    ("IXR", "VERC", "Birsa Munda Airport", "Ranchi", "India", 85.3217, 23.3143, 655, 2740, "Asia/Kolkata"),
    ("IMF", "VEIM", "Imphal International", "Imphal", "India", 93.8967, 24.7600, 774, 2746, "Asia/Kolkata"),
    ("IXA", "VEAT", "Maharaja Bir Bikram Airport", "Agartala", "India", 91.2404, 23.8869, 14, 2286, "Asia/Kolkata"),
    ("IXJ", "VIJU", "Jammu Airport", "Jammu", "India", 74.8374, 32.6891, 314, 2042, "Asia/Kolkata"),
    ("DXB", "OMDB", "Dubai International", "Dubai", "United Arab Emirates", 55.3644, 25.2532, 19, 4000, "Asia/Dubai"),
    ("AUH", "OMAA", "Zayed International", "Abu Dhabi", "United Arab Emirates", 54.6511, 24.4330, 27, 4100, "Asia/Dubai"),
    ("DOH", "OTHH", "Hamad International", "Doha", "Qatar", 51.6081, 25.2731, 11, 4850, "Asia/Qatar"),
    ("SHJ", "OMSJ", "Sharjah International", "Sharjah", "United Arab Emirates", 55.5172, 25.3286, 34, 4060, "Asia/Dubai"),
    ("MCT", "OOMS", "Muscat International", "Muscat", "Oman", 58.2844, 23.5933, 15, 4000, "Asia/Muscat"),
    ("KWI", "OKKK", "Kuwait International", "Kuwait City", "Kuwait", 47.9689, 29.2266, 63, 3400, "Asia/Kuwait"),
    ("JED", "OEJN", "King Abdulaziz International", "Jeddah", "Saudi Arabia", 39.1565, 21.6796, 15, 4000, "Asia/Riyadh"),
    ("SIN", "WSSS", "Singapore Changi", "Singapore", "Singapore", 103.9915, 1.3644, 7, 4000, "Asia/Singapore"),
    ("KUL", "WMKK", "Kuala Lumpur International", "Kuala Lumpur", "Malaysia", 101.7099, 2.7456, 21, 4124, "Asia/Kuala_Lumpur"),
    ("BKK", "VTBS", "Suvarnabhumi Airport", "Bangkok", "Thailand", 100.7501, 13.6900, 2, 4000, "Asia/Bangkok"),
    ("CMB", "VCBI", "Bandaranaike International", "Colombo", "Sri Lanka", 79.8841, 7.1808, 9, 3350, "Asia/Colombo"),
    ("DAC", "VGHS", "Hazrat Shahjalal International", "Dhaka", "Bangladesh", 90.3978, 23.8433, 8, 3200, "Asia/Dhaka"),
    ("KTM", "VNKT", "Tribhuvan International", "Kathmandu", "Nepal", 85.3591, 27.6966, 1338, 3050, "Asia/Kathmandu"),
    ("MLE", "VRMM", "Velana International", "Male", "Maldives", 73.5291, 4.1918, 2, 3400, "Indian/Maldives"),
    ("HKG", "VHHH", "Hong Kong International", "Hong Kong", "Hong Kong", 113.9185, 22.3080, 9, 3800, "Asia/Hong_Kong"),
    ("NRT", "RJAA", "Narita International", "Tokyo", "Japan", 140.3929, 35.7720, 43, 4000, "Asia/Tokyo"),
    ("ICN", "RKSI", "Incheon International", "Seoul", "South Korea", 126.4505, 37.4602, 7, 3750, "Asia/Seoul"),
    ("LHR", "EGLL", "Heathrow Airport", "London", "United Kingdom", -0.4543, 51.4700, 25, 3902, "Europe/London"),
    ("CDG", "LFPG", "Charles de Gaulle Airport", "Paris", "France", 2.55, 49.0097, 119, 4215, "Europe/Paris"),
    ("FRA", "EDDF", "Frankfurt Airport", "Frankfurt", "Germany", 8.5706, 50.0333, 111, 4000, "Europe/Berlin"),
    ("AMS", "EHAM", "Amsterdam Airport Schiphol", "Amsterdam", "Netherlands", 4.7639, 52.3086, -3, 3800, "Europe/Amsterdam"),
    ("IST", "LTFM", "Istanbul Airport", "Istanbul", "Turkey", 28.7519, 41.2753, 99, 4100, "Europe/Istanbul"),
    ("JFK", "KJFK", "John F. Kennedy International", "New York", "United States", -73.7781, 40.6413, 4, 4423, "America/New_York"),
    ("EWR", "KEWR", "Newark Liberty International", "Newark", "United States", -74.1745, 40.6895, 5, 3353, "America/New_York"),
    ("YYZ", "CYYZ", "Toronto Pearson International", "Toronto", "Canada", -79.6306, 43.6777, 173, 3389, "America/Toronto"),
    ("SFO", "KSFO", "San Francisco International", "San Francisco", "United States", -122.3790, 37.6213, 4, 3618, "America/Los_Angeles"),
    ("SYD", "YSSY", "Sydney Kingsford Smith", "Sydney", "Australia", 151.1772, -33.9461, 6, 3962, "Australia/Sydney"),
    ("MEL", "YMML", "Melbourne Airport", "Melbourne", "Australia", 144.8430, -37.6733, 132, 3657, "Australia/Melbourne"),
    ("PER", "YPPH", "Perth Airport", "Perth", "Australia", 115.9672, -31.9403, 20, 3444, "Australia/Perth"),
    ("NBO", "HKJK", "Jomo Kenyatta International", "Nairobi", "Kenya", 36.9278, -1.3192, 1624, 4117, "Africa/Nairobi"),
    ("ADD", "HAAB", "Addis Ababa Bole International", "Addis Ababa", "Ethiopia", 38.7993, 8.9779, 2334, 3800, "Africa/Addis_Ababa"),
    ("MRU", "FIMP", "Sir Seewoosagur Ramgoolam International", "Mauritius", "Mauritius", 57.6836, -20.4302, 57, 3370, "Indian/Mauritius"),
]

AIRLINES = [
    ("6E", "IGO", "IndiGo", "India"), ("AI", "AIC", "Air India", "India"),
    ("IX", "AXB", "Air India Express", "India"), ("QP", "AKJ", "Akasa Air", "India"),
    ("SG", "SEJ", "SpiceJet", "India"), ("S5", "LLR", "Star Air", "India"),
    ("EK", "UAE", "Emirates", "United Arab Emirates"), ("QR", "QTR", "Qatar Airways", "Qatar"),
    ("EY", "ETD", "Etihad Airways", "United Arab Emirates"), ("SQ", "SIA", "Singapore Airlines", "Singapore"),
    ("BA", "BAW", "British Airways", "United Kingdom"), ("LH", "DLH", "Lufthansa", "Germany"),
    ("TK", "THY", "Turkish Airlines", "Turkey"), ("UL", "ALK", "SriLankan Airlines", "Sri Lanka"),
    ("MH", "MAS", "Malaysia Airlines", "Malaysia"), ("TG", "THA", "Thai Airways", "Thailand"),
    ("CX", "CPA", "Cathay Pacific", "Hong Kong"), ("QF", "QFA", "Qantas", "Australia"),
]

AIRCRAFT_TYPES = [
    ("Airbus", "A320neo", "NARROW_BODY", 186, 19000, 830, 6300),
    ("Airbus", "A321neo", "NARROW_BODY", 220, 23000, 840, 7400),
    ("Boeing", "737 MAX 8", "NARROW_BODY", 189, 20000, 840, 6570),
    ("Boeing", "737-800", "NARROW_BODY", 189, 20000, 828, 5765),
    ("Airbus", "A350-900", "WIDE_BODY", 325, 36000, 905, 15000),
    ("Boeing", "787-9 Dreamliner", "WIDE_BODY", 290, 36000, 903, 14140),
    ("Boeing", "777-300ER", "WIDE_BODY", 354, 44000, 905, 13650),
    ("ATR", "72-600", "TURBOPROP", 78, 7000, 510, 1528),
    ("Embraer", "ERJ-145", "REGIONAL_JET", 50, 5000, 780, 2870),
    ("Airbus", "A330-300", "WIDE_BODY", 300, 37000, 880, 11750),
]


def _distance(a, b):
    lon1, lat1, lon2, lat2 = map(radians, (a[5], a[6], b[5], b[6]))
    x = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * atan2(sqrt(x), sqrt(1 - x))


def _heading(a, b):
    lon1, lat1, lon2, lat2 = map(radians, (a[5], a[6], b[5], b[6]))
    y = sin(lon2 - lon1) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2 - lon1)
    return (degrees(atan2(y, x)) + 360) % 360


def _waypoint_coordinates(a, b, route_id):
    """Build deterministic terminal and en-route fix coordinates."""
    lon1, lat1, lon2, lat2 = a[5], a[6], b[5], b[6]
    span = max(abs(lon2 - lon1), abs(lat2 - lat1))
    bend = min(1.15, max(0.12, span * 0.035)) * (1 if route_id % 2 else -1)
    points = []
    for i, fraction in enumerate((0, .06, .2, .42, .65, .84, .96, 1)):
        lon = lon1 + (lon2 - lon1) * fraction
        lat = lat1 + (lat2 - lat1) * fraction
        if i not in (0, 7):
            curve = sin(3.14159265 * fraction)
            length = max(0.001, sqrt((lon2 - lon1) ** 2 + (lat2 - lat1) ** 2))
            lon += -(lat2 - lat1) / length * bend * curve
            lat += (lon2 - lon1) / length * bend * curve
        points.append((lon, lat))
    return points


def _waypoint_geometry(a, b, route_id):
    points = _waypoint_coordinates(a, b, route_id)
    return "SRID=4326;LINESTRING(" + ",".join(f"{lon:.5f} {lat:.5f}" for lon, lat in points) + ")"


def _interpolate(points, fraction):
    lengths = [sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) for a, b in zip(points, points[1:])]
    target, travelled = sum(lengths) * fraction, 0
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if travelled + length >= target:
            local = 0 if not length else (target - travelled) / length
            return a[0] + (b[0] - a[0]) * local, a[1] + (b[1] - a[1]) * local
        travelled += length
    return points[-1]


def ensure_demo_network(db):
    """Upgrade an older demonstration database to the current deterministic network."""
    db.execute(text("SELECT pg_advisory_xact_lock(73001)"))
    counts = one(db, """SELECT
        (SELECT count(*) FROM airport) AS airports,
        (SELECT count(*) FROM flight) AS flights,
        (SELECT count(*) FROM flight f
          JOIN route r ON r.route_id=f.route_id
          JOIN aircraft a ON a.aircraft_id=f.aircraft_id
          JOIN aircraft_type t ON t.aircraft_type_id=a.aircraft_type_id
         WHERE r.distance_km > 4000 AND t.aircraft_category <> 'WIDE_BODY') AS bad_longhaul,
        (SELECT count(*) FROM flight f
          JOIN route r ON r.route_id=f.route_id
          JOIN airport origin ON origin.airport_id=r.origin_airport_id
          JOIN airport destination ON destination.airport_id=r.destination_airport_id
          JOIN airline al ON al.airline_id=f.airline_id
         WHERE origin.country='India' AND destination.country='India' AND al.country <> 'India') AS bad_domestic,
        (SELECT count(*) FROM route WHERE ST_NPoints(route_geometry) < 5) AS simple_routes,
        (SELECT count(*) FROM flight f JOIN route r USING(route_id)
          JOIN airport o ON o.airport_id=r.origin_airport_id JOIN airport d ON d.airport_id=r.destination_airport_id
         WHERE o.country='India' AND d.country<>'India' AND f.scheduled_arrival>now()-interval '90 minutes'
           AND f.scheduled_departure<now()+interval '6 hours') AS outbound_international,
        (SELECT count(*) FROM flight f JOIN route r USING(route_id)
          JOIN airport o ON o.airport_id=r.origin_airport_id JOIN airport d ON d.airport_id=r.destination_airport_id
         WHERE o.country<>'India' AND d.country='India' AND f.scheduled_arrival>now()-interval '90 minutes'
           AND f.scheduled_departure<now()+interval '6 hours') AS inbound_international,
        (SELECT count(DISTINCT flight_status) FROM flight
          WHERE flight_status IN ('EN_ROUTE','APPROACHING','TAXIING','BOARDING','DELAYED','LANDED','SCHEDULED','DIVERTED','CANCELLED')) AS scenario_states""")
    if (counts["airports"] >= 70 and counts["flights"] >= TARGET_FLIGHTS
            and not counts["bad_longhaul"] and not counts["bad_domestic"] and not counts["simple_routes"]
            and counts["outbound_international"] >= 20 and counts["inbound_international"] >= 20
            and counts["scenario_states"] == 9):
        _sync_sequences(db)
        db.commit()
        return {"seeded": False, "version": NETWORK_VERSION, **counts}
    if counts["airports"]:
        db.execute(text("TRUNCATE airport, airline, aircraft_type RESTART IDENTITY CASCADE"))
    return seed(db)


def _sync_sequences(db):
    for table, key in (
        ("airport", "airport_id"), ("airline", "airline_id"), ("aircraft_type", "aircraft_type_id"),
        ("aircraft", "aircraft_id"), ("route", "route_id"), ("flight", "flight_id"),
        ("flight_leg", "flight_leg_id"), ("flight_position", "position_id"),
    ):
        db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}','{key}'),(SELECT max({key}) FROM {table}),true)"))


def seed(db):
    db.execute(text("SELECT pg_advisory_xact_lock(73001)"))
    if one(db, "SELECT count(*) AS n FROM airport")["n"]:
        return {"seeded": False, "reason": "Database already contains airports"}
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for idx, item in enumerate(AIRPORTS, 1):
        iata, icao, name, city, country, lon, lat, elevation, _, tz = item
        db.add(Airport(airport_id=idx, iata_code=iata, icao_code=icao, airport_name=name, city=city, country=country,
                       elevation_m=elevation, timezone=tz, operational_status="OPEN",
                       location=f"SRID=4326;POINT({lon} {lat})"))
    for idx, (iata, icao, name, country) in enumerate(AIRLINES, 1):
        db.add(Airline(airline_id=idx, iata_code=iata, icao_code=icao, airline_name=name, country=country,
                       operational_status="ACTIVE"))
    for idx, item in enumerate(AIRCRAFT_TYPES, 1):
        db.add(AircraftType(aircraft_type_id=idx, manufacturer=item[0], model=item[1], aircraft_category=item[2],
                            passenger_capacity=item[3], cargo_capacity=item[4], cruise_speed_kmh=item[5], range_km=item[6]))
    db.flush()
    for idx, airport in enumerate(AIRPORTS, 1):
        db.add(Runway(airport_id=idx, runway_identifier="09/27", length_m=airport[8], width_m=45,
                      surface_type="ASPHALT", heading=90, runway_status="OPEN"))
    domestic, international = list(range(1, 41)), list(range(41, len(AIRPORTS) + 1))
    hubs = [3, 4, 2, 1, 5, 6, 7, 10]
    planned = []
    for idx in range(760):
        if idx % 5:
            sequence = [domestic[(idx * 11) % len(domestic)]]
            for leg in range(5):
                target = hubs[(idx + leg * 3) % len(hubs)] if leg % 2 == 0 else domestic[(idx * 7 + leg * 13) % len(domestic)]
                if target == sequence[-1]:
                    target = domestic[(target + leg + 5) % len(domestic)]
                sequence.append(target)
        else:
            hub = hubs[idx % len(hubs)]
            foreign = [international[(idx + leg * 9) % len(international)] for leg in range(3)]
            # Alternate the first active leg so the live window always contains
            # both India departures and India arrivals, plus hub connections.
            sequence = ([hub, foreign[0], hub, foreign[1], hub, foreign[2]]
                        if (idx // 5) % 2 else [foreign[0], hub, foreign[1], hub, foreign[2], hub])
        planned.append(sequence)
    pairs = {(seq[i], seq[i + 1]) for seq in planned for i in range(5)}
    route_map = {}
    for route_id, (origin, dest) in enumerate(sorted(pairs), 1):
        a, b = AIRPORTS[origin - 1], AIRPORTS[dest - 1]
        km = _distance(a, b)
        route = Route(route_id=route_id, origin_airport_id=origin, destination_airport_id=dest, route_code=f"{a[0]}-{b[0]}",
                      distance_km=km, estimated_duration_minutes=max(40, round(km / (790 if km < 4000 else 870) * 60 + 25)),
                      route_geometry=_waypoint_geometry(a, b, route_id), route_status="ACTIVE")
        db.add(route)
        route_map[origin, dest] = route
    db.flush()
    statuses = ["EN_ROUTE"] * 4 + ["APPROACHING", "TAXIING", "BOARDING", "DELAYED", "LANDED", "SCHEDULED",
                "DIVERTED", "CANCELLED"]
    domestic_airlines = [1, 1, 1, 1, 2, 2, 2, 3, 3, 4, 5, 6]
    international_airlines = [1, 2, 3, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
    wide_body_types = [5, 6, 7, 10]
    flight_id = leg_id = position_id = 0
    for idx, sequence in enumerate(planned, 1):
        international_rotation = any(x > 40 for x in sequence)
        airline_pool = international_airlines if international_rotation else domestic_airlines
        airline_id = airline_pool[(idx - 1) % len(airline_pool)]
        type_id = wide_body_types[idx % len(wide_body_types)] if international_rotation else (
            9 if idx % 17 == 0 else 8 if idx % 13 == 0 else 1 + idx % 4
        )
        prefix = AIRLINES[airline_id - 1][0]
        registration = ("VT-" if airline_id <= 6 else f"{prefix}-") + f"{idx:03d}"
        aircraft = Aircraft(aircraft_id=idx, registration_number=registration, aircraft_type_id=type_id,
                            airline_id=airline_id, aircraft_status="IN_SERVICE", current_speed=0, heading=0,
                            last_updated=now)
        db.add(aircraft)
        status = statuses[(idx - 1) % len(statuses)]
        first_route = route_map[sequence[0], sequence[1]]
        duration = first_route.estimated_duration_minutes
        if status == "EN_ROUTE":
            fraction, departure = 0.18 + (idx % 55) / 100, None
            departure = now - timedelta(minutes=round(duration * fraction))
        elif status == "APPROACHING":
            fraction, departure = 0.92, now - timedelta(minutes=round(duration * 0.92))
        elif status == "TAXIING":
            fraction, departure = 0.008, now - timedelta(minutes=4)
        elif status == "BOARDING":
            fraction, departure = 0.0, now + timedelta(minutes=20 + idx % 15)
        elif status == "DELAYED":
            fraction, departure = 0.0, now - timedelta(minutes=20 + idx % 25)
        elif status == "LANDED":
            fraction, departure = 1.0, now - timedelta(minutes=duration + 5 + idx % 20)
        elif status == "DIVERTED":
            fraction, departure = 0.68, now - timedelta(minutes=round(duration * 0.68))
        elif status == "CANCELLED":
            fraction, departure = 0.0, now + timedelta(minutes=25 + idx % 20)
        else:
            fraction, departure = 0.0, now + timedelta(minutes=50 + idx % 40)
        for leg in range(5):
            flight_id += 1
            leg_id += 1
            origin, dest = sequence[leg], sequence[leg + 1]
            route = route_map[origin, dest]
            arrival = departure + timedelta(minutes=route.estimated_duration_minutes)
            leg_status = status if leg == 0 else "SCHEDULED"
            actual_departure = departure if leg == 0 and status in {"EN_ROUTE", "APPROACHING", "TAXIING", "LANDED", "DIVERTED"} else None
            actual_arrival = arrival if leg == 0 and status == "LANDED" else None
            flight = Flight(flight_id=flight_id, flight_number=f"{prefix}{100 + idx}{leg + 1}", airline_id=airline_id,
                            aircraft_id=idx, route_id=route.route_id, scheduled_departure=departure,
                            scheduled_arrival=arrival, actual_departure=actual_departure, actual_arrival=actual_arrival,
                            flight_status=leg_status, departure_gate=f"{chr(65 + idx % 5)}{1 + idx % 24}",
                            arrival_gate=f"{chr(65 + (idx + 2) % 5)}{1 + idx % 20}", last_updated=now)
            db.add(flight)
            db.add(FlightLeg(flight_leg_id=leg_id, flight_id=flight_id, leg_sequence=1, departure_airport_id=origin,
                             arrival_airport_id=dest, scheduled_departure=departure, scheduled_arrival=arrival,
                             actual_departure=actual_departure, actual_arrival=actual_arrival, leg_status=leg_status))
            if leg == 0:
                a, b = AIRPORTS[origin - 1], AIRPORTS[dest - 1]
                heading = _heading(a, b)
                samples = 4 if status in {"EN_ROUTE", "APPROACHING", "DIVERTED"} else 1
                for sample in range(samples):
                    position_id += 1
                    sample_fraction = max(0.0, fraction - (samples - 1 - sample) * 0.012)
                    # Seeded samples follow the waypoint route; live ticks later apply active hazard avoidance.
                    lon, lat = _interpolate(_waypoint_coordinates(a, b, route.route_id), sample_fraction)
                    altitude = 0 if status in {"BOARDING", "DELAYED", "TAXIING", "LANDED", "SCHEDULED", "CANCELLED"} else round(11200 * sin(3.14159 * sample_fraction))
                    speed = 0 if altitude == 0 else (35 if status == "TAXIING" else AIRCRAFT_TYPES[type_id - 1][5])
                    recorded = now - timedelta(minutes=samples - 1 - sample)
                    db.add(FlightPosition(position_id=position_id, flight_id=flight_id,
                                          position=f"SRID=4326;POINT Z({lon} {lat} {altitude})", ground_speed=speed,
                                          heading=heading, recorded_at=recorded))
                    if sample == samples - 1:
                        aircraft.current_location = f"SRID=4326;POINT Z({lon} {lat} {altitude})"
                        aircraft.current_speed, aircraft.heading = speed, heading
            departure = arrival + timedelta(minutes=35 + idx % 25)
    db.add(WeatherEvent(weather_type="CONVECTIVE_STORM", severity=4, movement_direction=280,
                        movement_speed_kmh=22, start_time=now - timedelta(hours=2), end_time=now + timedelta(days=30),
                        weather_status="ACTIVE", affected_area_geometry="SRID=4326;POLYGON((79 12,81.8 12.8,82.2 15.8,80.1 16.5,78.9 14.5,79 12))"))
    db.add(AirspaceZone(zone_name="Deccan training sector · DEMO", zone_type="MILITARY", lower_altitude=0,
                        upper_altitude=14000, valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=30),
                        zone_status="ACTIVE", geometry="SRID=4326;POLYGON((75.8 16,77.5 16,77.5 18,75.8 18,75.8 16))"))
    db.flush()
    _sync_sequences(db)
    db.commit()
    return {"seeded": True, "version": NETWORK_VERSION, "airports": len(AIRPORTS), "aircraft": len(planned),
            "flights": len(planned) * 5, "routes": len(route_map), "international_airports": len(international)}
