from unittest.mock import patch
from backend import copilot


def test_general_count_reads_all_retained_flights():
    with patch.object(copilot, 'one', return_value={'n': 1400}) as query:
        result = copilot.query(None, 'How many flights are in the database?')
    assert '1400' in result['answer']
    assert 'historical' in result['answer']
    assert query.call_args.args[1] == 'SELECT count(*) AS n FROM flight'


def test_schema_answer_needs_no_database_query():
    result = copilot.query(None, 'Explain the database tables')
    assert 'PostGIS' in result['answer']
    assert 'positions' in result['answer'].lower()


def test_airport_country_filter():
    airports = [{'airport_id': 1, 'iata_code': 'MAA', 'city': 'Chennai', 'country': 'India', 'airport_name': 'Chennai'},
                {'airport_id': 2, 'iata_code': 'DXB', 'city': 'Dubai', 'country': 'UAE', 'airport_name': 'Dubai'}]
    with patch.object(copilot, 'rows', return_value=airports):
        result = copilot.query(None, 'List airports in India')
    assert '1 matching' in result['answer']
    assert 'Chennai' in result['answer']
    assert 'Dubai' not in result['answer']


def test_delayed_flights_include_disruption_delays():
    flights = [{'flight_id': 1, 'flight_number': 'AI123', 'route_code': 'MAA-DEL', 'flight_status': 'EN_ROUTE',
                'estimated_delay_minutes': 45, 'risk': {'level': 'HIGH'}, 'impacts': []},
               {'flight_id': 2, 'flight_number': 'AI124', 'route_code': 'MAA-BOM', 'flight_status': 'EN_ROUTE',
                'estimated_delay_minutes': 0, 'risk': {'level': 'LOW'}, 'impacts': []}]
    with patch.object(copilot, 'rows', return_value=[]), patch.object(copilot.intelligence, 'flights', return_value=flights):
        result = copilot.query(None, 'Show delayed flights')
    assert [item['flight_id'] for item in result['items']] == [1]
