from ChatBotAI.services.smoobu_service import SmoobuService


def test_extract_property_fields_includes_street():
    svc = SmoobuService.__new__(SmoobuService)  # no __init__/network needed
    apt = {'location': {'street': 'Hertigswalder Str. 27', 'zip': '01855', 'city': 'Sebnitz'}}
    fields = svc._extract_property_fields(apt)
    assert fields['street'] == 'Hertigswalder Str. 27'
    assert fields['address'].startswith('Hertigswalder Str. 27')


def test_extract_property_fields_no_street_omits_key():
    svc = SmoobuService.__new__(SmoobuService)
    fields = svc._extract_property_fields({'location': {'city': 'Sebnitz'}})
    assert 'street' not in fields
