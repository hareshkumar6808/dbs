"""Operational route geometry shared by tracking and intelligence queries."""

# The planned airway geometry remains stored on ROUTE. This SQL derives a
# temporary operational path around the first active hazard it intersects.
# It uses the hazard envelope to add two lateral clearance waypoints and keeps
# every calculation in PostGIS.
OPERATIONAL_ROUTE_LATERAL = """
LEFT JOIN LATERAL (
  SELECT hazard.geometry,hazard.kind,hazard.name FROM (
    SELECT we.affected_area_geometry AS geometry,'WEATHER'::text AS kind,
      we.weather_type::text AS name,1 AS priority
    FROM weather_event we
    WHERE we.weather_status='ACTIVE' AND now() BETWEEN we.start_time AND we.end_time
      AND ST_Intersects(r.route_geometry,we.affected_area_geometry)
    UNION ALL
    SELECT az.geometry,'AIRSPACE'::text,az.zone_name::text,2
    FROM airspace_zone az
    WHERE az.zone_status='ACTIVE' AND now() BETWEEN az.valid_from AND az.valid_until
      AND az.zone_type IN ('RESTRICTED','PROHIBITED','MILITARY','TEMPORARY')
      AND ST_Intersects(r.route_geometry,az.geometry)
  ) hazard ORDER BY priority LIMIT 1
) hazard ON true
LEFT JOIN LATERAL (
  SELECT CASE WHEN hazard.geometry IS NULL THEN r.route_geometry ELSE
    ST_MakeLine(ARRAY[
      ST_StartPoint(r.route_geometry),
      ST_SetSRID(ST_MakePoint(
        CASE WHEN ST_X(ST_StartPoint(r.route_geometry)) <= ST_X(ST_EndPoint(r.route_geometry))
          THEN ST_XMin(Box3D(hazard.geometry))-.65 ELSE ST_XMax(Box3D(hazard.geometry))+.65 END,
        ST_Y(ST_StartPoint(r.route_geometry))),4326),
      ST_SetSRID(ST_MakePoint(
        CASE WHEN ST_X(ST_StartPoint(r.route_geometry)) <= ST_X(ST_EndPoint(r.route_geometry))
          THEN ST_XMin(Box3D(hazard.geometry))-.65 ELSE ST_XMax(Box3D(hazard.geometry))+.65 END,
        ST_YMax(Box3D(hazard.geometry))+.55),4326),
      ST_SetSRID(ST_MakePoint(
        CASE WHEN ST_X(ST_StartPoint(r.route_geometry)) <= ST_X(ST_EndPoint(r.route_geometry))
          THEN ST_XMax(Box3D(hazard.geometry))+.65 ELSE ST_XMin(Box3D(hazard.geometry))-.65 END,
        ST_YMax(Box3D(hazard.geometry))+.55),4326),
      ST_SetSRID(ST_MakePoint(
        CASE WHEN ST_X(ST_StartPoint(r.route_geometry)) <= ST_X(ST_EndPoint(r.route_geometry))
          THEN ST_XMax(Box3D(hazard.geometry))+.65 ELSE ST_XMin(Box3D(hazard.geometry))-.65 END,
        ST_Y(ST_EndPoint(r.route_geometry))),4326),
      ST_EndPoint(r.route_geometry)
    ]) END AS geometry
) operational ON true
"""
