"""The 13 core relational entities. Spatial calculations use PostGIS, SRID 4326."""

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base
from geoalchemy2 import Geometry

Base = declarative_base()


class Airport(Base):
    __tablename__ = "airport"
    airport_id = Column(Integer, primary_key=True)
    iata_code = Column(String(3), unique=True, nullable=False)
    icao_code = Column(String(4), unique=True, nullable=False)
    airport_name = Column(String(150), nullable=False)
    city = Column(String(80), nullable=False)
    country = Column(String(80), nullable=False)
    elevation_m = Column(Float, nullable=False)
    timezone = Column(String(60), nullable=False)
    operational_status = Column(String(24), nullable=False)
    location = Column(Geometry("POINT", srid=4326), nullable=False)


class Airline(Base):
    __tablename__ = "airline"
    airline_id = Column(Integer, primary_key=True)
    iata_code = Column(String(3), unique=True, nullable=False)
    icao_code = Column(String(4), unique=True, nullable=False)
    airline_name = Column(String(100), nullable=False)
    country = Column(String(80), nullable=False)
    operational_status = Column(String(24), nullable=False)


class AircraftType(Base):
    __tablename__ = "aircraft_type"
    aircraft_type_id = Column(Integer, primary_key=True)
    manufacturer = Column(String(80), nullable=False)
    model = Column(String(80), nullable=False)
    aircraft_category = Column(String(30), nullable=False)
    passenger_capacity = Column(Integer, nullable=False)
    cargo_capacity = Column(Float, nullable=False)
    cruise_speed_kmh = Column(Float, nullable=False)
    range_km = Column(Float, nullable=False)
    __table_args__ = (
        UniqueConstraint("manufacturer", "model"),
        CheckConstraint("passenger_capacity >= 0 AND cargo_capacity >= 0 AND range_km > 0 AND cruise_speed_kmh > 0"),
    )


class Aircraft(Base):
    __tablename__ = "aircraft"
    aircraft_id = Column(Integer, primary_key=True)
    registration_number = Column(String(20), unique=True, nullable=False)
    aircraft_type_id = Column(ForeignKey("aircraft_type.aircraft_type_id"), nullable=False)
    airline_id = Column(ForeignKey("airline.airline_id"), nullable=False, index=True)
    aircraft_status = Column(String(24), nullable=False)
    current_location = Column(Geometry("POINTZ", srid=4326, dimension=3))
    current_speed = Column(Float)
    heading = Column(Float)
    last_updated = Column(DateTime(timezone=True))


class Route(Base):
    __tablename__ = "route"
    route_id = Column(Integer, primary_key=True)
    origin_airport_id = Column(ForeignKey("airport.airport_id"), nullable=False, index=True)
    destination_airport_id = Column(ForeignKey("airport.airport_id"), nullable=False, index=True)
    route_code = Column(String(30), unique=True, nullable=False)
    distance_km = Column(Float, nullable=False)
    estimated_duration_minutes = Column(Integer, nullable=False)
    route_geometry = Column(Geometry("LINESTRING", srid=4326), nullable=False)
    route_status = Column(String(24), nullable=False)
    __table_args__ = (
        CheckConstraint("origin_airport_id <> destination_airport_id"),
        CheckConstraint("distance_km > 0 AND estimated_duration_minutes > 0"),
    )


class Flight(Base):
    __tablename__ = "flight"
    flight_id = Column(Integer, primary_key=True)
    flight_number = Column(String(16), nullable=False, index=True)
    airline_id = Column(ForeignKey("airline.airline_id"), nullable=False, index=True)
    aircraft_id = Column(ForeignKey("aircraft.aircraft_id"), nullable=False, index=True)
    route_id = Column(ForeignKey("route.route_id"), nullable=False, index=True)
    scheduled_departure = Column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_arrival = Column(DateTime(timezone=True), nullable=False, index=True)
    actual_departure = Column(DateTime(timezone=True))
    actual_arrival = Column(DateTime(timezone=True))
    flight_status = Column(String(24), nullable=False, index=True)
    departure_gate = Column(String(10))
    arrival_gate = Column(String(10))
    last_updated = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (CheckConstraint("scheduled_arrival > scheduled_departure"),)


class FlightLeg(Base):
    __tablename__ = "flight_leg"
    flight_leg_id = Column(Integer, primary_key=True)
    flight_id = Column(ForeignKey("flight.flight_id"), nullable=False)
    leg_sequence = Column(Integer, nullable=False)
    departure_airport_id = Column(ForeignKey("airport.airport_id"), nullable=False)
    arrival_airport_id = Column(ForeignKey("airport.airport_id"), nullable=False)
    scheduled_departure = Column(DateTime(timezone=True), nullable=False)
    scheduled_arrival = Column(DateTime(timezone=True), nullable=False)
    actual_departure = Column(DateTime(timezone=True))
    actual_arrival = Column(DateTime(timezone=True))
    leg_status = Column(String(24), nullable=False)
    __table_args__ = (
        UniqueConstraint("flight_id", "leg_sequence"),
        CheckConstraint("leg_sequence > 0"),
        CheckConstraint("departure_airport_id <> arrival_airport_id"),
        CheckConstraint("scheduled_arrival > scheduled_departure"),
    )


class Runway(Base):
    __tablename__ = "runway"
    runway_id = Column(Integer, primary_key=True)
    airport_id = Column(ForeignKey("airport.airport_id"), nullable=False, index=True)
    runway_identifier = Column(String(16), nullable=False)
    length_m = Column(Float, nullable=False)
    width_m = Column(Float, nullable=False)
    surface_type = Column(String(30), nullable=False)
    heading = Column(Float, nullable=False)
    runway_status = Column(String(24), nullable=False)
    __table_args__ = (
        UniqueConstraint("airport_id", "runway_identifier"),
        CheckConstraint("length_m > 0 AND width_m > 0 AND heading >= 0 AND heading < 360"),
    )


class WeatherEvent(Base):
    __tablename__ = "weather_event"
    weather_id = Column(Integer, primary_key=True)
    weather_type = Column(String(40), nullable=False)
    severity = Column(Integer, nullable=False)
    movement_direction = Column(Float, nullable=False)
    movement_speed_kmh = Column(Float, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    weather_status = Column(String(24), nullable=False)
    affected_area_geometry = Column(Geometry("POLYGON", srid=4326), nullable=False)
    __table_args__ = (CheckConstraint("severity BETWEEN 1 AND 5"), CheckConstraint("end_time > start_time"))


class AirspaceZone(Base):
    __tablename__ = "airspace_zone"
    airspace_zone_id = Column(Integer, primary_key=True)
    zone_name = Column(String(100), nullable=False)
    zone_type = Column(String(24), nullable=False)
    lower_altitude = Column(Float, nullable=False)
    upper_altitude = Column(Float, nullable=False)
    geometry = Column(Geometry("POLYGON", srid=4326), nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    zone_status = Column(String(24), nullable=False)
    __table_args__ = (
        CheckConstraint("zone_type IN ('RESTRICTED','PROHIBITED','TEMPORARY','MILITARY','SPECIAL_USE')"),
        CheckConstraint("upper_altitude > lower_altitude AND valid_until > valid_from"),
    )


class DisruptionEvent(Base):
    __tablename__ = "disruption_event"
    disruption_id = Column(Integer, primary_key=True)
    disruption_type = Column(String(32), nullable=False)
    severity = Column(Integer, nullable=False)
    airport_id = Column(ForeignKey("airport.airport_id"))
    runway_id = Column(ForeignKey("runway.runway_id"))
    weather_id = Column(ForeignKey("weather_event.weather_id"))
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    expected_end_time = Column(DateTime(timezone=True), nullable=False)
    actual_end_time = Column(DateTime(timezone=True))
    description = Column(String(500), nullable=False)
    disruption_status = Column(String(24), nullable=False, index=True)
    __table_args__ = (
        CheckConstraint("severity BETWEEN 1 AND 5"),
        CheckConstraint("expected_end_time > start_time"),
        CheckConstraint(
            "disruption_type IN ('RUNWAY_CLOSURE','AIRPORT_CLOSURE','SEVERE_WEATHER','AIRSPACE_RESTRICTION','OPERATIONAL_FAILURE')"
        ),
    )


class DisruptionImpact(Base):
    __tablename__ = "disruption_impact"
    impact_id = Column(Integer, primary_key=True)
    disruption_id = Column(ForeignKey("disruption_event.disruption_id"), nullable=False, index=True)
    flight_id = Column(ForeignKey("flight.flight_id"), index=True)
    aircraft_id = Column(ForeignKey("aircraft.aircraft_id"))
    airport_id = Column(ForeignKey("airport.airport_id"))
    impact_type = Column(String(32), nullable=False)
    severity = Column(Integer, nullable=False)
    estimated_delay_minutes = Column(Integer, nullable=False)
    detected_at = Column(DateTime(timezone=True), nullable=False)
    resolution_status = Column(String(24), nullable=False)
    __table_args__ = (
        CheckConstraint("flight_id IS NOT NULL OR aircraft_id IS NOT NULL OR airport_id IS NOT NULL"),
        CheckConstraint("severity BETWEEN 1 AND 5 AND estimated_delay_minutes >= 0"),
        CheckConstraint(
            "impact_type IN ('FLIGHT_DELAY','FLIGHT_CANCELLATION','AIRPORT_CONGESTION','AIRCRAFT_UNAVAILABLE','ROUTE_DISRUPTION','DIVERSION_RISK')"
        ),
    )


class FlightPosition(Base):
    __tablename__ = "flight_position"
    position_id = Column(BigInteger, primary_key=True)
    flight_id = Column(ForeignKey("flight.flight_id"), nullable=False)
    position = Column(Geometry("POINTZ", srid=4326, dimension=3), nullable=False)
    ground_speed = Column(Float, nullable=False)
    heading = Column(Float, nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, index=True)
    __table_args__ = (
        UniqueConstraint("flight_id", "recorded_at"),
        Index("ix_position_flight_time", "flight_id", "recorded_at"),
        CheckConstraint("ground_speed >= 0 AND heading >= 0 AND heading < 360"),
    )
