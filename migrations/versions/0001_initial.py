"""Initial 13-entity PostGIS schema. Frozen DDL; independent of future ORM changes."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute(
        "CREATE TABLE aircraft_type (\n\taircraft_type_id SERIAL NOT NULL, \n\tmanufacturer VARCHAR(80) NOT NULL, \n\tmodel VARCHAR(80) NOT NULL, \n\taircraft_category VARCHAR(30) NOT NULL, \n\tpassenger_capacity INTEGER NOT NULL, \n\tcargo_capacity FLOAT NOT NULL, \n\tcruise_speed_kmh FLOAT NOT NULL, \n\trange_km FLOAT NOT NULL, \n\tPRIMARY KEY (aircraft_type_id), \n\tUNIQUE (manufacturer, model), \n\tCHECK (passenger_capacity >= 0 AND cargo_capacity >= 0 AND range_km > 0 AND cruise_speed_kmh > 0)\n)"
    )
    op.execute(
        "CREATE TABLE airline (\n\tairline_id SERIAL NOT NULL, \n\tiata_code VARCHAR(3) NOT NULL, \n\ticao_code VARCHAR(4) NOT NULL, \n\tairline_name VARCHAR(100) NOT NULL, \n\tcountry VARCHAR(80) NOT NULL, \n\toperational_status VARCHAR(24) NOT NULL, \n\tPRIMARY KEY (airline_id), \n\tUNIQUE (iata_code), \n\tUNIQUE (icao_code)\n)"
    )
    op.execute(
        "CREATE TABLE airport (\n\tairport_id SERIAL NOT NULL, \n\tiata_code VARCHAR(3) NOT NULL, \n\ticao_code VARCHAR(4) NOT NULL, \n\tairport_name VARCHAR(150) NOT NULL, \n\tcity VARCHAR(80) NOT NULL, \n\tcountry VARCHAR(80) NOT NULL, \n\televation_m FLOAT NOT NULL, \n\ttimezone VARCHAR(60) NOT NULL, \n\toperational_status VARCHAR(24) NOT NULL, \n\tlocation geometry(POINT,4326) NOT NULL, \n\tPRIMARY KEY (airport_id), \n\tUNIQUE (iata_code), \n\tUNIQUE (icao_code)\n)"
    )
    op.execute("CREATE INDEX idx_airport_location ON airport USING gist (location)")
    op.execute(
        "CREATE TABLE airspace_zone (\n\tairspace_zone_id SERIAL NOT NULL, \n\tzone_name VARCHAR(100) NOT NULL, \n\tzone_type VARCHAR(24) NOT NULL, \n\tlower_altitude FLOAT NOT NULL, \n\tupper_altitude FLOAT NOT NULL, \n\tgeometry geometry(POLYGON,4326) NOT NULL, \n\tvalid_from TIMESTAMP WITH TIME ZONE NOT NULL, \n\tvalid_until TIMESTAMP WITH TIME ZONE NOT NULL, \n\tzone_status VARCHAR(24) NOT NULL, \n\tPRIMARY KEY (airspace_zone_id), \n\tCHECK (zone_type IN ('RESTRICTED','PROHIBITED','TEMPORARY','MILITARY','SPECIAL_USE')), \n\tCHECK (upper_altitude > lower_altitude AND valid_until > valid_from)\n)"
    )
    op.execute("CREATE INDEX idx_airspace_zone_geometry ON airspace_zone USING gist (geometry)")
    op.execute(
        "CREATE TABLE weather_event (\n\tweather_id SERIAL NOT NULL, \n\tweather_type VARCHAR(40) NOT NULL, \n\tseverity INTEGER NOT NULL, \n\tmovement_direction FLOAT NOT NULL, \n\tmovement_speed_kmh FLOAT NOT NULL, \n\tstart_time TIMESTAMP WITH TIME ZONE NOT NULL, \n\tend_time TIMESTAMP WITH TIME ZONE NOT NULL, \n\tweather_status VARCHAR(24) NOT NULL, \n\taffected_area_geometry geometry(POLYGON,4326) NOT NULL, \n\tPRIMARY KEY (weather_id), \n\tCHECK (severity BETWEEN 1 AND 5), \n\tCHECK (end_time > start_time)\n)"
    )
    op.execute(
        "CREATE INDEX idx_weather_event_affected_area_geometry ON weather_event USING gist (affected_area_geometry)"
    )
    op.execute(
        "CREATE TABLE aircraft (\n\taircraft_id SERIAL NOT NULL, \n\tregistration_number VARCHAR(20) NOT NULL, \n\taircraft_type_id INTEGER NOT NULL, \n\tairline_id INTEGER NOT NULL, \n\taircraft_status VARCHAR(24) NOT NULL, \n\tcurrent_location geometry(POINTZ,4326), \n\tcurrent_speed FLOAT, \n\theading FLOAT, \n\tlast_updated TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (aircraft_id), \n\tUNIQUE (registration_number), \n\tFOREIGN KEY(aircraft_type_id) REFERENCES aircraft_type (aircraft_type_id), \n\tFOREIGN KEY(airline_id) REFERENCES airline (airline_id)\n)"
    )
    op.execute("CREATE INDEX idx_aircraft_current_location ON aircraft USING gist (current_location)")
    op.execute("CREATE INDEX ix_aircraft_airline_id ON aircraft (airline_id)")
    op.execute(
        "CREATE TABLE route (\n\troute_id SERIAL NOT NULL, \n\torigin_airport_id INTEGER NOT NULL, \n\tdestination_airport_id INTEGER NOT NULL, \n\troute_code VARCHAR(30) NOT NULL, \n\tdistance_km FLOAT NOT NULL, \n\testimated_duration_minutes INTEGER NOT NULL, \n\troute_geometry geometry(LINESTRING,4326) NOT NULL, \n\troute_status VARCHAR(24) NOT NULL, \n\tPRIMARY KEY (route_id), \n\tCHECK (origin_airport_id <> destination_airport_id), \n\tCHECK (distance_km > 0 AND estimated_duration_minutes > 0), \n\tFOREIGN KEY(origin_airport_id) REFERENCES airport (airport_id), \n\tFOREIGN KEY(destination_airport_id) REFERENCES airport (airport_id), \n\tUNIQUE (route_code)\n)"
    )
    op.execute("CREATE INDEX idx_route_route_geometry ON route USING gist (route_geometry)")
    op.execute("CREATE INDEX ix_route_destination_airport_id ON route (destination_airport_id)")
    op.execute("CREATE INDEX ix_route_origin_airport_id ON route (origin_airport_id)")
    op.execute(
        "CREATE TABLE runway (\n\trunway_id SERIAL NOT NULL, \n\tairport_id INTEGER NOT NULL, \n\trunway_identifier VARCHAR(16) NOT NULL, \n\tlength_m FLOAT NOT NULL, \n\twidth_m FLOAT NOT NULL, \n\tsurface_type VARCHAR(30) NOT NULL, \n\theading FLOAT NOT NULL, \n\trunway_status VARCHAR(24) NOT NULL, \n\tPRIMARY KEY (runway_id), \n\tUNIQUE (airport_id, runway_identifier), \n\tCHECK (length_m > 0 AND width_m > 0 AND heading >= 0 AND heading < 360), \n\tFOREIGN KEY(airport_id) REFERENCES airport (airport_id)\n)"
    )
    op.execute("CREATE INDEX ix_runway_airport_id ON runway (airport_id)")
    op.execute(
        "CREATE TABLE disruption_event (\n\tdisruption_id SERIAL NOT NULL, \n\tdisruption_type VARCHAR(32) NOT NULL, \n\tseverity INTEGER NOT NULL, \n\tairport_id INTEGER, \n\trunway_id INTEGER, \n\tweather_id INTEGER, \n\tstart_time TIMESTAMP WITH TIME ZONE NOT NULL, \n\texpected_end_time TIMESTAMP WITH TIME ZONE NOT NULL, \n\tactual_end_time TIMESTAMP WITH TIME ZONE, \n\tdescription VARCHAR(500) NOT NULL, \n\tdisruption_status VARCHAR(24) NOT NULL, \n\tPRIMARY KEY (disruption_id), \n\tCHECK (severity BETWEEN 1 AND 5), \n\tCHECK (expected_end_time > start_time), \n\tCHECK (disruption_type IN ('RUNWAY_CLOSURE','AIRPORT_CLOSURE','SEVERE_WEATHER','AIRSPACE_RESTRICTION','OPERATIONAL_FAILURE')), \n\tFOREIGN KEY(airport_id) REFERENCES airport (airport_id), \n\tFOREIGN KEY(runway_id) REFERENCES runway (runway_id), \n\tFOREIGN KEY(weather_id) REFERENCES weather_event (weather_id)\n)"
    )
    op.execute("CREATE INDEX ix_disruption_event_disruption_status ON disruption_event (disruption_status)")
    op.execute("CREATE INDEX ix_disruption_event_start_time ON disruption_event (start_time)")
    op.execute(
        "CREATE TABLE flight (\n\tflight_id SERIAL NOT NULL, \n\tflight_number VARCHAR(16) NOT NULL, \n\tairline_id INTEGER NOT NULL, \n\taircraft_id INTEGER NOT NULL, \n\troute_id INTEGER NOT NULL, \n\tscheduled_departure TIMESTAMP WITH TIME ZONE NOT NULL, \n\tscheduled_arrival TIMESTAMP WITH TIME ZONE NOT NULL, \n\tactual_departure TIMESTAMP WITH TIME ZONE, \n\tactual_arrival TIMESTAMP WITH TIME ZONE, \n\tflight_status VARCHAR(24) NOT NULL, \n\tdeparture_gate VARCHAR(10), \n\tarrival_gate VARCHAR(10), \n\tlast_updated TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (flight_id), \n\tCHECK (scheduled_arrival > scheduled_departure), \n\tFOREIGN KEY(airline_id) REFERENCES airline (airline_id), \n\tFOREIGN KEY(aircraft_id) REFERENCES aircraft (aircraft_id), \n\tFOREIGN KEY(route_id) REFERENCES route (route_id)\n)"
    )
    op.execute("CREATE INDEX ix_flight_aircraft_id ON flight (aircraft_id)")
    op.execute("CREATE INDEX ix_flight_airline_id ON flight (airline_id)")
    op.execute("CREATE INDEX ix_flight_flight_number ON flight (flight_number)")
    op.execute("CREATE INDEX ix_flight_flight_status ON flight (flight_status)")
    op.execute("CREATE INDEX ix_flight_route_id ON flight (route_id)")
    op.execute("CREATE INDEX ix_flight_scheduled_arrival ON flight (scheduled_arrival)")
    op.execute("CREATE INDEX ix_flight_scheduled_departure ON flight (scheduled_departure)")
    op.execute(
        "CREATE TABLE disruption_impact (\n\timpact_id SERIAL NOT NULL, \n\tdisruption_id INTEGER NOT NULL, \n\tflight_id INTEGER, \n\taircraft_id INTEGER, \n\tairport_id INTEGER, \n\timpact_type VARCHAR(32) NOT NULL, \n\tseverity INTEGER NOT NULL, \n\testimated_delay_minutes INTEGER NOT NULL, \n\tdetected_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tresolution_status VARCHAR(24) NOT NULL, \n\tPRIMARY KEY (impact_id), \n\tCHECK (flight_id IS NOT NULL OR aircraft_id IS NOT NULL OR airport_id IS NOT NULL), \n\tCHECK (severity BETWEEN 1 AND 5 AND estimated_delay_minutes >= 0), \n\tCHECK (impact_type IN ('FLIGHT_DELAY','FLIGHT_CANCELLATION','AIRPORT_CONGESTION','AIRCRAFT_UNAVAILABLE','ROUTE_DISRUPTION','DIVERSION_RISK')), \n\tFOREIGN KEY(disruption_id) REFERENCES disruption_event (disruption_id), \n\tFOREIGN KEY(flight_id) REFERENCES flight (flight_id), \n\tFOREIGN KEY(aircraft_id) REFERENCES aircraft (aircraft_id), \n\tFOREIGN KEY(airport_id) REFERENCES airport (airport_id)\n)"
    )
    op.execute("CREATE INDEX ix_disruption_impact_disruption_id ON disruption_impact (disruption_id)")
    op.execute("CREATE INDEX ix_disruption_impact_flight_id ON disruption_impact (flight_id)")
    op.execute(
        "CREATE TABLE flight_leg (\n\tflight_leg_id SERIAL NOT NULL, \n\tflight_id INTEGER NOT NULL, \n\tleg_sequence INTEGER NOT NULL, \n\tdeparture_airport_id INTEGER NOT NULL, \n\tarrival_airport_id INTEGER NOT NULL, \n\tscheduled_departure TIMESTAMP WITH TIME ZONE NOT NULL, \n\tscheduled_arrival TIMESTAMP WITH TIME ZONE NOT NULL, \n\tactual_departure TIMESTAMP WITH TIME ZONE, \n\tactual_arrival TIMESTAMP WITH TIME ZONE, \n\tleg_status VARCHAR(24) NOT NULL, \n\tPRIMARY KEY (flight_leg_id), \n\tUNIQUE (flight_id, leg_sequence), \n\tCHECK (leg_sequence > 0), \n\tCHECK (departure_airport_id <> arrival_airport_id), \n\tCHECK (scheduled_arrival > scheduled_departure), \n\tFOREIGN KEY(flight_id) REFERENCES flight (flight_id), \n\tFOREIGN KEY(departure_airport_id) REFERENCES airport (airport_id), \n\tFOREIGN KEY(arrival_airport_id) REFERENCES airport (airport_id)\n)"
    )
    op.execute(
        "CREATE TABLE flight_position (\n\tposition_id BIGSERIAL NOT NULL, \n\tflight_id INTEGER NOT NULL, \n\tposition geometry(POINTZ,4326) NOT NULL, \n\tground_speed FLOAT NOT NULL, \n\theading FLOAT NOT NULL, \n\trecorded_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (position_id), \n\tUNIQUE (flight_id, recorded_at), \n\tCHECK (ground_speed >= 0 AND heading >= 0 AND heading < 360), \n\tFOREIGN KEY(flight_id) REFERENCES flight (flight_id)\n)"
    )
    op.execute("CREATE INDEX idx_flight_position_position ON flight_position USING gist (position)")
    op.execute("CREATE INDEX ix_flight_position_recorded_at ON flight_position (recorded_at)")
    op.execute("CREATE INDEX ix_position_flight_time ON flight_position (flight_id, recorded_at)")
    op.execute("CREATE INDEX ix_airport_geography ON airport USING gist ((location::geography))")
    op.execute("CREATE INDEX ix_weather_geography ON weather_event USING gist ((affected_area_geometry::geography))")


def downgrade():
    op.execute("DROP TABLE flight_position")
    op.execute("DROP TABLE flight_leg")
    op.execute("DROP TABLE disruption_impact")
    op.execute("DROP TABLE flight")
    op.execute("DROP TABLE disruption_event")
    op.execute("DROP TABLE runway")
    op.execute("DROP TABLE route")
    op.execute("DROP TABLE aircraft")
    op.execute("DROP TABLE weather_event")
    op.execute("DROP TABLE airspace_zone")
    op.execute("DROP TABLE airport")
    op.execute("DROP TABLE airline")
    op.execute("DROP TABLE aircraft_type")
