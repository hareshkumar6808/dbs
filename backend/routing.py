"""Operational route geometry shared by tracking and intelligence queries."""

# The planned airway geometry remains stored on ROUTE. This SQL derives a
# temporary operational path around the first active hazard it intersects.
# It keeps the filed route before and after the hazard, replacing only the
# intersecting neighborhood with a small clearance segment.
OPERATIONAL_ROUTE_LATERAL = """
LEFT JOIN LATERAL (
  SELECT hazard.geometry,hazard.kind,hazard.name FROM (
    SELECT we.affected_area_geometry AS geometry,'WEATHER'::text AS kind,
      we.weather_type::text AS name,2 AS priority
    FROM weather_event we
    WHERE we.weather_status='ACTIVE' AND now() BETWEEN we.start_time AND we.end_time
      AND ST_Intersects(r.route_geometry,we.affected_area_geometry)
    UNION ALL
    SELECT az.geometry,'AIRSPACE'::text,az.zone_name::text,1
    FROM airspace_zone az
    WHERE az.zone_status='ACTIVE' AND now() BETWEEN az.valid_from AND az.valid_until
      AND az.zone_type IN ('RESTRICTED','PROHIBITED','MILITARY','TEMPORARY')
      AND ST_Intersects(r.route_geometry,az.geometry)
  ) hazard ORDER BY priority LIMIT 1
) hazard ON true
LEFT JOIN LATERAL (
  SELECT located.entry_fraction,located.exit_fraction,points.before_point,points.after_point,
    ST_XMin(Box3D(hazard.geometry))-.16 AS west,
    ST_XMax(Box3D(hazard.geometry))+.16 AS east,
    ST_YMin(Box3D(hazard.geometry))-.16 AS south,
    ST_YMax(Box3D(hazard.geometry))+.16 AS north
  FROM LATERAL (
    SELECT GREATEST(.001,min(fraction)-.006) AS entry_fraction,
      LEAST(.999,max(fraction)+.006) AS exit_fraction
    FROM (
      SELECT ST_LineLocatePoint(r.route_geometry,(dumped).geom) AS fraction
      FROM (SELECT ST_DumpPoints(ST_Intersection(r.route_geometry,hazard.geometry)) AS dumped) intersections
    ) crossing_points
  ) located
  CROSS JOIN LATERAL (SELECT
    ST_LineInterpolatePoint(r.route_geometry,located.entry_fraction) AS before_point,
    ST_LineInterpolatePoint(r.route_geometry,located.exit_fraction) AS after_point) points
) hit ON hazard.geometry IS NOT NULL
LEFT JOIN LATERAL (
  SELECT CASE WHEN hazard.geometry IS NULL THEN r.route_geometry ELSE detour.geometry END AS geometry
  FROM LATERAL (
    SELECT candidate.geometry
    FROM (VALUES
      (ST_MakeLine(ARRAY[
        ST_LineSubstring(r.route_geometry,0,hit.entry_fraction),
        ST_SetSRID(ST_MakePoint(CASE WHEN ST_X(hit.before_point)<=ST_X(hit.after_point) THEN hit.west ELSE hit.east END,hit.north),4326),
        ST_SetSRID(ST_MakePoint(CASE WHEN ST_X(hit.before_point)<=ST_X(hit.after_point) THEN hit.east ELSE hit.west END,hit.north),4326),
        ST_LineSubstring(r.route_geometry,hit.exit_fraction,1)])),
      (ST_MakeLine(ARRAY[
        ST_LineSubstring(r.route_geometry,0,hit.entry_fraction),
        ST_SetSRID(ST_MakePoint(CASE WHEN ST_X(hit.before_point)<=ST_X(hit.after_point) THEN hit.east ELSE hit.west END,hit.north),4326),
        ST_SetSRID(ST_MakePoint(CASE WHEN ST_X(hit.before_point)<=ST_X(hit.after_point) THEN hit.west ELSE hit.east END,hit.north),4326),
        ST_LineSubstring(r.route_geometry,hit.exit_fraction,1)])),
      (ST_MakeLine(ARRAY[
        ST_LineSubstring(r.route_geometry,0,hit.entry_fraction),
        ST_SetSRID(ST_MakePoint(CASE WHEN ST_X(hit.before_point)<=ST_X(hit.after_point) THEN hit.west ELSE hit.east END,hit.south),4326),
        ST_SetSRID(ST_MakePoint(CASE WHEN ST_X(hit.before_point)<=ST_X(hit.after_point) THEN hit.east ELSE hit.west END,hit.south),4326),
        ST_LineSubstring(r.route_geometry,hit.exit_fraction,1)])),
      (ST_MakeLine(ARRAY[
        ST_LineSubstring(r.route_geometry,0,hit.entry_fraction),
        ST_SetSRID(ST_MakePoint(CASE WHEN ST_X(hit.before_point)<=ST_X(hit.after_point) THEN hit.east ELSE hit.west END,hit.south),4326),
        ST_SetSRID(ST_MakePoint(CASE WHEN ST_X(hit.before_point)<=ST_X(hit.after_point) THEN hit.west ELSE hit.east END,hit.south),4326),
        ST_LineSubstring(r.route_geometry,hit.exit_fraction,1)])),
      (ST_MakeLine(ARRAY[
        ST_LineSubstring(r.route_geometry,0,hit.entry_fraction),
        ST_SetSRID(ST_MakePoint(hit.west,CASE WHEN ST_Y(hit.before_point)<=ST_Y(hit.after_point) THEN hit.south ELSE hit.north END),4326),
        ST_SetSRID(ST_MakePoint(hit.west,CASE WHEN ST_Y(hit.before_point)<=ST_Y(hit.after_point) THEN hit.north ELSE hit.south END),4326),
        ST_LineSubstring(r.route_geometry,hit.exit_fraction,1)])),
      (ST_MakeLine(ARRAY[
        ST_LineSubstring(r.route_geometry,0,hit.entry_fraction),
        ST_SetSRID(ST_MakePoint(hit.west,CASE WHEN ST_Y(hit.before_point)<=ST_Y(hit.after_point) THEN hit.north ELSE hit.south END),4326),
        ST_SetSRID(ST_MakePoint(hit.west,CASE WHEN ST_Y(hit.before_point)<=ST_Y(hit.after_point) THEN hit.south ELSE hit.north END),4326),
        ST_LineSubstring(r.route_geometry,hit.exit_fraction,1)])),
      (ST_MakeLine(ARRAY[
        ST_LineSubstring(r.route_geometry,0,hit.entry_fraction),
        ST_SetSRID(ST_MakePoint(hit.east,CASE WHEN ST_Y(hit.before_point)<=ST_Y(hit.after_point) THEN hit.south ELSE hit.north END),4326),
        ST_SetSRID(ST_MakePoint(hit.east,CASE WHEN ST_Y(hit.before_point)<=ST_Y(hit.after_point) THEN hit.north ELSE hit.south END),4326),
        ST_LineSubstring(r.route_geometry,hit.exit_fraction,1)])),
      (ST_MakeLine(ARRAY[
        ST_LineSubstring(r.route_geometry,0,hit.entry_fraction),
        ST_SetSRID(ST_MakePoint(hit.east,CASE WHEN ST_Y(hit.before_point)<=ST_Y(hit.after_point) THEN hit.north ELSE hit.south END),4326),
        ST_SetSRID(ST_MakePoint(hit.east,CASE WHEN ST_Y(hit.before_point)<=ST_Y(hit.after_point) THEN hit.south ELSE hit.north END),4326),
        ST_LineSubstring(r.route_geometry,hit.exit_fraction,1)]))
    ) candidate(geometry)
    ORDER BY ST_Intersects(candidate.geometry,ST_Buffer(hazard.geometry,-.005)),
      ST_Length(candidate.geometry::geography)
    LIMIT 1
  ) detour
) operational ON true
"""
